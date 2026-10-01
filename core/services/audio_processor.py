from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pytz

# ГАРАНТИЯ ПОТОКОБЕЗОПАСНОСТИ (Thread-Safe IPC):
# Жестко глушим OpenMP и LLVM до 1 потока на уровне МОДУЛЯ.
# Это гарантирует, что ни одна импортированная C-библиотека (ни soundfile, ни librosa)
# не поднимет пул потоков при форке/спавне процесса.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["NUMBA_NUM_THREADS"] = "1"


from core.models import Album, Artist, AudioFile, Genre, Track
from core.models.enums import AudioFormat, MusicalKey
from core.services.logging import get_logger
from core.services.metadata_extractor import CueParser, MetadataExtractor


class AudioProcessor:
    """
    Высокопроизводительный процессор для анализа аудиофайлов и CUE-сплиттинга.
    Использует Lazy Initialization для защиты от Segfault в ProcessPoolExecutor
    и минимизирует CPU overhead за счет Data-Driven конвейера.
    """

    AUDIO_EXTENSIONS = {fmt.value for fmt in AudioFormat}
    COVER_FILE_NAMES = frozenset(
        {
            "cover.jpg",
            "cover.png",
            "folder.jpg",
            "folder.png",
            "front.jpg",
            "album.jpg",
            "album.png",
        }
    )

    def __init__(self, duration: int = 60):
        self.duration = duration
        self.logger = get_logger("PlaylistAI.AudioProcessor")
        self.metadata_extractor = MetadataExtractor()
        self.cue_parser = CueParser()

        # Только основные тональности (без энгармонических дубликатов _alt)
        self.key_order = [k for k in MusicalKey if not k.name.endswith("_alt")]
        self.logger.debug(f"AudioProcessor инициализирован. Поддерживаемые форматы: {self.AUDIO_EXTENSIONS}")

    def get_file_hash(self, file_path: str, chunk_size: int = 65536) -> Optional[str]:
        """Оптимизированное вычисление хэша крупными чанками (64KB под Linux VFS)."""
        hasher = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            self.logger.error(f"Ошибка вычисления хеша {file_path}: {e}")
            return None

    def _analyze_bpm_key(self, file_path: str, offset: float = 0.0) -> Optional[tuple[float, Optional[str]]]:
        """
        Изолированный DSP-анализ (Sandboxed Fallback).
        Инкапсулирует вызов librosa в независимый процесс ОС с уникальным JIT-кэшем
        для предотвращения коллизий компилятора Numba в Windows.
        """
        import json
        import shutil
        import subprocess
        import sys
        import tempfile
        import uuid
        from pathlib import Path

        # Генерируем уникальную директорию кэша для 100% изоляции JIT Numba
        unique_cache = Path(tempfile.gettempdir()) / f"numba_cache_{uuid.uuid4().hex}"
        unique_cache.mkdir(parents=True, exist_ok=True)

        script_code = f"""
import sys, json, warnings, os
warnings.simplefilter('ignore')

# Тотальная изоляция C-контекста
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['NUMBA_NUM_THREADS'] = '1'
os.environ['NUMBA_CACHE_DIR'] = r'{str(unique_cache)}'
os.environ['NUMBA_UPDATE_CACHE'] = '0'  # Запрещаем конкурентную перезапись

try:
    import librosa
    import numpy as np

    file_path = sys.argv[1]
    y, sr = librosa.load(file_path, sr=22050, mono=True, offset={offset}, duration={self.duration})

    # Защита от битых кадров и деления на ноль (Numba Segfault Protection)
    y = np.nan_to_num(y.astype(np.float32))

    if np.max(np.abs(y)) < 1e-4:
        # Трек состоит из тишины (часто бывает в экспериментальной или битой FLAC музыке)
        print(json.dumps({{"bpm": 0.0, "key_idx": -1}}))
        sys.exit(0)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = round(float(tempo[0] if isinstance(tempo, (list, tuple)) or hasattr(tempo, 'shape') else tempo), 1)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_idx = int(chroma.mean(axis=1).argmax())

    print(json.dumps({{"bpm": bpm, "key_idx": key_idx}}))
except Exception as e:
    # Прокидываем Python exception в stderr для перехвата оркестратором
    print(f"SANDBOX_ERR: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
        try:
            result = subprocess.run([sys.executable, "-c", script_code, file_path], capture_output=True, text=True, timeout=25)

            if result.returncode != 0 or not result.stdout.strip():
                err_msg = result.stderr.strip() if result.stderr else "Нативный LLVM Segfault"
                self.logger.warning(f"⚠️ Сбой DSP для {Path(file_path).name}: {err_msg}")
                return None, None

            data = json.loads(result.stdout.strip())

            if data["key_idx"] == -1:
                self.logger.debug(f"Тишина обнаружена в {Path(file_path).name}, DSP пропущен.")
                return 0.0, None

            key = self.key_order[data["key_idx"]].value if 0 <= data["key_idx"] < len(self.key_order) else None
            return data["bpm"], key

        except subprocess.TimeoutExpired:
            self.logger.warning(f"⏳ DSP-анализ превысил таймаут для {Path(file_path).name}")
            return None, None
        except Exception as e:
            self.logger.error(f"Ошибка изоляции: {e}")
            return None, None
        finally:
            # Уничтожаем следы песочницы
            shutil.rmtree(unique_cache, ignore_errors=True)

    def _analyze_audio_properties(
        self, file_path: str, file_size: int, duration: float
    ) -> Optional[tuple[Optional[int], Optional[int], Optional[int], Optional[int]]]:
        """
        Мгновенное извлечение технических параметров.
        Использует Lazy Import soundfile для защиты от краша пула процессов.
        """
        try:
            import soundfile as sf

            info = sf.info(file_path)
            channels = info.channels
            sample_rate = info.samplerate

            bit_depth = None
            if info.subtype and "PCM_" in info.subtype:
                try:
                    bit_depth = int(info.subtype.split("_")[1])
                except ValueError:
                    pass
            elif info.subtype == "FLOAT":
                bit_depth = 32

            bit_rate = int((file_size * 8) / duration) if duration > 0 else None
            return bit_rate, channels, bit_depth, sample_rate

        except Exception as e:
            self.logger.debug(f"Ошибка чтения заголовков (soundfile) для {file_path}: {e}")
            return None, None, None, None

    def _find_cover_image(self, directory: Path) -> Optional[str]:
        try:
            for file in directory.iterdir():
                if file.is_file() and file.name.lower() in self.COVER_FILE_NAMES:
                    return str(file)
        except OSError:
            pass
        return None

    def _normalize_metadata(
        self,
        file: Path,
        metadata: dict,
        cue_metadata: Optional[dict],
        track_data: Optional[Union[list[dict], dict]],
    ) -> dict:
        """Нормализует метаданные с приоритетом: CUE -> Встроенные теги -> Имя файла."""
        cue_album_title = cue_metadata.get("album_title") if cue_metadata else None
        cue_album_performer = cue_metadata.get("album_performer") if cue_metadata else None
        cue_album_year = cue_metadata.get("album_year") if cue_metadata else None
        cue_album_genre = cue_metadata.get("album_genre") if cue_metadata else None

        default_artist = (
            cue_album_performer
            or (track_data.get("performer") if track_data and isinstance(track_data, dict) else metadata.get("artist", "Unknown"))
            or file.parent.name.split(" - ")[0].strip()
        )
        raw_default_album = cue_album_title or metadata.get("album", "Unknown") or file.parent.name.split(" - ")[-1].strip()
        default_year = cue_album_year or metadata.get("year")
        default_genre = cue_album_genre or metadata.get("genre", "Unknown") or "Unknown"

        album_title, disc_num = Album.normalize_album_title(raw_default_album)

        return {
            "artist": default_artist,
            "album": album_title,
            "disc_num": disc_num,
            "year": default_year,
            "genre": default_genre,
        }

    def create_audio_file(
        self,
        file: Path,
        file_size: int,
        file_format_str: str,
        bit_rate: int,
        channels: int,
        bit_depth: int,
        sample_rate: int,
        contains_multiple_tracks: bool,
    ) -> AudioFile:
        """Создает DTO объект физического аудиофайла."""
        file_hash = self.get_file_hash(str(file))
        cue_path = file.with_suffix(".cue") if contains_multiple_tracks and file.with_suffix(".cue").exists() else None

        audio_file_data = {
            "file_path": str(file),
            "file_size": file_size,
            "file_format": file_format_str,
            "hash": file_hash,
            "bit_rate": bit_rate,
            "channels": channels,
            "bit_depth": bit_depth,
            "sample_rate": sample_rate,
            "date_added": datetime.now(pytz.utc).isoformat(),
            "date_modified": datetime.fromtimestamp(file.stat().st_mtime, tz=pytz.utc).isoformat(),
            "contains_multiple_tracks": contains_multiple_tracks,
            "cue_sheet_path": str(cue_path) if cue_path else None,
        }
        return AudioFile.from_dict(audio_file_data)

    def _create_multi_tracks(
        self,
        audio_file: AudioFile,
        track_data: list[dict],
        file: Path,
        duration: float,
        norm_metadata: dict,
        cover_path: Optional[str],
    ) -> list[tuple[Track, int, int]]:
        """Нарезка CUE. Оптимизировано: технические параметры не пересчитываются, только BPM/Key."""
        tracks = []
        album = Album(title=norm_metadata["album"], disc_count=norm_metadata["disc_num"])

        for i, cue_track in enumerate(track_data):
            start_time = cue_track.get("start_time", 0.0)
            next_start_time = track_data[i + 1]["start_time"] if i + 1 < len(track_data) else None
            track_duration = (next_start_time - start_time) if next_start_time is not None else (duration - start_time)

            # Для мультитреков всегда используем librosa, так как теги общие для всего файла
            track_bpm, track_key = self._analyze_bpm_key(str(file), offset=start_time)

            track_dict = {
                "title": cue_track.get("title", f"Track {cue_track.get('index', i + 1)}"),
                "duration": int(track_duration),
                "bpm": track_bpm,
                "key": track_key,
                "year": norm_metadata["year"],
                "date_added": datetime.now(pytz.utc).isoformat(),
                "cover_path": cover_path,
            }

            track = Track.from_dict(track_dict)
            track.audiofile = audio_file

            artist_names = Artist.normalize_artist_names(cue_track.get("performer") or norm_metadata["artist"])
            track.artists = [Artist(name=name) for name in artist_names if name]
            track.albums = [album]

            genres = norm_metadata["genre"].split("|") if "|" in norm_metadata["genre"] else [norm_metadata["genre"]]
            track.genres = [Genre(name=g.strip()) for g in genres if g.strip() and g != "Unknown"]

            tracks.append((track, norm_metadata["disc_num"], cue_track.get("index", i + 1)))

        return tracks

    def _create_single_track(
        self,
        audio_file: AudioFile,
        track_data: Optional[dict],
        metadata: dict,
        file: Path,
        duration: float,
        bpm: Optional[float],
        key: Optional[str],
        norm_metadata: dict,
        cover_path: Optional[str],
    ) -> list[tuple[Track, int, int]]:
        """Сборка стандартного сингла."""
        album = Album(title=norm_metadata["album"], disc_count=norm_metadata["disc_num"])

        track_dict = {
            "title": track_data.get("title") if track_data else metadata.get("title", file.stem.split(" - ")[-1].strip()),
            "duration": int(duration),
            "bpm": bpm,
            "key": key,
            "year": norm_metadata["year"],
            "date_added": datetime.now(pytz.utc).isoformat(),
            "cover_path": cover_path,
        }

        track = Track.from_dict(track_dict)
        track.audiofile = audio_file

        artist_names = Artist.normalize_artist_names(norm_metadata["artist"])
        track.artists = [Artist(name=name) for name in artist_names if name]
        track.albums = [album]

        genres = norm_metadata["genre"].split("|") if "|" in norm_metadata["genre"] else [norm_metadata["genre"]]
        track.genres = [Genre(name=g.strip()) for g in genres if g.strip() and g != "Unknown"]

        return [(track, norm_metadata["disc_num"], 1)]

    def _extract_cue_metadata(self, file: Path) -> Optional[dict]:
        cue_path = file.with_suffix(".cue")
        if cue_path.exists():
            try:
                _, album_title, album_performer, album_year, album_genre = self.cue_parser.parse_cue(str(cue_path))
                return {
                    "album_title": album_title,
                    "album_performer": album_performer,
                    "album_year": album_year,
                    "album_genre": album_genre,
                }
            except Exception as e:
                self.logger.error(f"Ошибка парсинга .cue для {file}: {e}")
        return None

    def extract_unified_metadata(self, file_path: Path) -> dict:
        """
        [STRICT I/O BOUND]
        Извлекает сырые теги и технические параметры.
        ЗАПРЕЩЕНЫ любые вызовы тяжелой математики (DSP) на этом этапе.
        """
        metadata = self.metadata_extractor.extract(str(file_path))
        file_size = file_path.stat().st_size
        duration = metadata.get("duration", 0.0)

        # Легкий I/O (чтение заголовков через libsndfile)
        br, ch, bd, sr = self._analyze_audio_properties(str(file_path), file_size, duration)

        # Достаем то, что есть в тегах. Если пусто - оставляем как есть.
        bpm = metadata.get("bpm")
        key = metadata.get("key")

        metadata.update(
            {
                "file_path": str(file_path),
                "file_size": file_size,
                "file_format": file_path.suffix.upper().lstrip("."),
                "bit_rate": br,
                "channels": ch,
                "bit_depth": bd,
                "sample_rate": sr,
                "bpm": bpm,
                "key": key,
            }
        )
        return metadata

    def process_audio_file(
        self,
        file: Path,
        track_data: list[dict] | Optional[dict] = None,
        disc_number: Optional[int] = None,
    ) -> Optional[tuple[AudioFile, list[Track]]]:
        """
        Главный оркестратор. Анализирует файл и собирает графы ORM-объектов.
        """
        file_suffix = file.suffix.upper().lstrip(".")
        if file_suffix not in self.AUDIO_EXTENSIONS or not file.is_file():
            return None

        self.logger.debug(f"Начало обработки: {file}")
        contains_multiple_tracks = isinstance(track_data, list) and len(track_data) > 1

        metadata = self.metadata_extractor.extract(str(file))
        file_size = file.stat().st_size
        duration = metadata.get("duration", 0.0)

        cue_metadata = self._extract_cue_metadata(file) if contains_multiple_tracks else None

        bit_rate, channels, bit_depth, sample_rate = self._analyze_audio_properties(str(file), file_size, duration)

        bpm = metadata.get("bpm")
        key = metadata.get("key")

        if not contains_multiple_tracks and (not bpm or not key):
            calc_bpm, calc_key = self._analyze_bpm_key(str(file))
            bpm = bpm or calc_bpm
            key = key or calc_key

        audio_file = self.create_audio_file(
            file,
            file_size,
            file_suffix,
            bit_rate or 0,
            channels or 0,
            bit_depth or 0,
            sample_rate or 0,
            contains_multiple_tracks,
        )

        cover_path = self._find_cover_image(file.parent)
        norm_metadata = self._normalize_metadata(file, metadata, cue_metadata, track_data)
        if disc_number:
            norm_metadata["disc_num"] = disc_number

        if contains_multiple_tracks:
            tracks_with_order = self._create_multi_tracks(audio_file, track_data, file, duration, norm_metadata, cover_path)  # type: ignore
        else:
            tracks_with_order = self._create_single_track(
                audio_file,
                track_data,  # type: ignore
                metadata,
                file,
                duration,
                bpm,
                key,
                norm_metadata,
                cover_path,
            )

        tracks = [t[0] for t in tracks_with_order]

        self.logger.info(f"✅ Успешно проанализирован: {file.name} (Треков: {len(tracks)})")
        return audio_file, tracks
