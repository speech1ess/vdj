from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import charset_normalizer
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from core.models.enums import AudioFormat
from core.services.logging import get_logger
from core.services.tagmap import TagMapper


class MetadataExtractor:
    """
    Высокопроизводительный экстрактор метаданных.
    Использует TagMapper для Data-Driven маппинга тегов и минимизирует аллокации.
    """

    AUDIO_EXTENSIONS = {fmt.value for fmt in AudioFormat}

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.MetadataExtractor")
        self.tag_mapper = TagMapper()
        self.logger.debug(f"MetadataExtractor инициализирован. Форматы: {self.AUDIO_EXTENSIONS}")

    def extract(self, file_path: str | Path) -> dict[str, Any]:
        """Точка входа для извлечения метаданных из файла."""
        file_path = Path(file_path)
        ext = file_path.suffix.upper().lstrip(".")

        # Базовая структура метаданных
        metadata: dict[str, Any] = {
            "artist": "Unknown",
            "album": "Unknown",
            "title": file_path.stem,  # Дефолт - имя файла без расширения
            "genre": "Unknown",
            "year": None,
            "duration": None,
            "track_number": None,
            "disc_number": None,
            "composer": None,
            "performer": None,
            "album_artist": None,
            "comment": None,
            "publisher": None,
            "initial_key": None,
        }

        try:
            if ext == "MP3":
                metadata = self._extract_mp3(file_path, metadata)
            elif ext == "FLAC":
                metadata = self._extract_flac(file_path, metadata)
            elif ext in ("AIFF", "AIF"):
                metadata = self._extract_aiff(file_path, metadata)
            elif ext not in self.AUDIO_EXTENSIONS:
                self.logger.warning(f"Формат {ext} не поддерживается для {file_path.name}")

            # Fallback: Если track_number не найден в тегах, пытаемся вытащить из имени файла
            if metadata.get("track_number") is None:
                match = re.match(r"^\d+", file_path.stem) or re.search(r"track\s*(\d+)", file_path.stem, re.IGNORECASE)
                if match:
                    val = match.group(0) if match.group(0).isdigit() else match.group(1)
                    metadata["track_number"] = int(val)

        except Exception as e:
            self.logger.error(f"Сбой извлечения метаданных из {file_path.name}: {e}")

        return metadata

    def extract_with_cue(self, file_path: str | Path, cue_data: dict[str, Any], track_index: int = 0) -> dict[str, Any]:
        """Извлекает метаданные из файла и перекрывает их данными из CUE sheet."""
        raw_metadata = self.extract(file_path)
        tracks = cue_data.get("tracks", [])
        cue_track = tracks[track_index] if track_index < len(tracks) else {}

        merged_cue = {
            "album": cue_data.get("album_title"),
            "album_artist": cue_data.get("album_performer"),
            "track_number": cue_track.get("index"),
            "title": cue_track.get("title"),
            "performer": cue_track.get("performer"),
        }

        # Маппинг дополнительных REM полей из CUE
        for field, aliases in self.tag_mapper.unified_tags.items():
            for alias in aliases:
                if alias in cue_track:
                    merged_cue[field] = cue_track[alias]
                    break

        # Слияние: CUE имеет приоритет над встроенными тегами
        for key, value in merged_cue.items():
            if value is not None:
                raw_metadata[key] = value

        return raw_metadata

    def _clean_value(self, field: str, value: Any) -> Any:
        """Безопасно очищает и приводит типы (распаковка списков/кортежей, парсинг чисел)."""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None

        if isinstance(value, bytes):
            value = value.decode(errors="ignore")

        if value and field in ("track_number", "disc_number"):
            try:
                # Обработка форматов вида "1/12"
                cleaned = str(value).split("/")[0].strip()
                return int(cleaned) if cleaned.isdigit() else None
            except Exception:
                return None

        return str(value).strip() if value else None

    def _extract_mp3(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        audio = MP3(file_path, ID3=ID3)
        metadata["duration"] = round(audio.info.length) if audio.info else 0

        if audio.tags:
            for tag in audio.tags.keys():
                tag_upper = tag.upper()
                if tag_upper in self.tag_mapper.tag_to_field:
                    field = self.tag_mapper.tag_to_field[tag_upper]
                    tag_values = audio.tags.getall(tag)

                    if tag_values:
                        raw_val = tag_values[0].text[0] if hasattr(tag_values[0], "text") else tag_values[0]
                        metadata[field] = self._clean_value(field, raw_val)
        return metadata

    def _extract_flac(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        audio = FLAC(file_path)
        metadata["duration"] = round(audio.info.length) if audio.info else 0

        if audio.tags:
            for tag, value_list in audio.tags.items():
                tag_upper = tag.upper()
                if tag_upper in self.tag_mapper.tag_to_field:
                    field = self.tag_mapper.tag_to_field[tag_upper]
                    if value_list:
                        # FLAC хранит год в поле DATE. Перехватываем его.
                        if field == "date":
                            field = "year"
                        metadata[field] = self._clean_value(field, value_list[0])
        return metadata

    def _extract_aiff(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        audio = AIFF(file_path)
        metadata["duration"] = round(audio.info.length) if audio.info else 0

        # AIFF может хранить теги как в ID3 чанке (audio.tags), так и в IFF чанках (dict(audio))
        sources = [getattr(audio, "tags", {}), dict(audio)]
        for source in sources:
            if not source:
                continue
            for tag, value in source.items():
                tag_upper = tag.upper()
                if tag_upper in self.tag_mapper.tag_to_field:
                    field = self.tag_mapper.tag_to_field[tag_upper]
                    metadata[field] = self._clean_value(field, value)
        return metadata


class CueParser:
    """Парсер CUE-таблиц (Cuesheets) с автоматическим определением кодировки (Single I/O pass)."""

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.CueParser")
        self.tag_mapper = TagMapper()
        # Инвертируем маппинг: ищем теги REM, чтобы понимать в какие поля бизнес-логики их класть
        self.reverse_cue_tags = {k.upper(): field for field, aliases in self.tag_mapper.unified_tags.items() for k in aliases if k.startswith("REM ")}

    def parse_cue(self, cue_path: str | Path) -> tuple[list[dict], Optional[str], Optional[str], Optional[str], Optional[str]]:
        cue_path = Path(cue_path)
        tracks = []
        album_title, album_performer, album_year, album_genre = None, None, None, None
        current_file, current_track = None, None

        try:
            # ОПТИМИЗАЦИЯ I/O: Читаем файл один раз в байты.
            with open(cue_path, "rb") as f:
                raw_data = f.read()

            # Определяем кодировку в памяти и сразу декодируем
            detected = charset_normalizer.detect(raw_data)
            encoding = detected.get("encoding") or "utf-8"
            lines = raw_data.decode(encoding, errors="replace").splitlines()

        except Exception as e:
            self.logger.error(f"Сбой чтения CUE-файла {cue_path.name}: {e}")
            return tracks, None, None, None, None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("FILE"):
                parts = line.split('"')
                if len(parts) > 1:
                    current_file = parts[1]

            elif line.startswith("TRACK"):
                if current_track:
                    tracks.append(current_track)
                try:
                    track_num = int(line.split()[1])
                except (IndexError, ValueError):
                    track_num = len(tracks) + 1
                current_track = {"index": track_num, "file": current_file}

            elif line.startswith("TITLE"):
                parts = line.split("TITLE", 1)
                if len(parts) > 1:
                    value = parts[1].strip().strip('"')
                    if current_track:
                        current_track["title"] = value
                    else:
                        album_title = value

            elif line.startswith("PERFORMER"):
                parts = line.split("PERFORMER", 1)
                if len(parts) > 1:
                    value = parts[1].strip().strip('"')
                    if current_track:
                        current_track["performer"] = value
                    else:
                        album_performer = value

            elif line.startswith("INDEX 01") and current_track:
                parts = line.split("INDEX 01")
                if len(parts) > 1:
                    time_str = parts[1].strip()
                    try:
                        minutes, seconds, frames = map(int, time_str.split(":"))
                        current_track["start_time"] = minutes * 60 + seconds + frames / 75.0
                    except ValueError:
                        current_track["start_time"] = None

            elif line.startswith("REM"):
                parts = line.split(" ", 2)
                if len(parts) < 3:
                    continue
                rem_key = f"REM {parts[1].upper()}"
                rem_value = parts[2].strip().strip('"')

                field = self.reverse_cue_tags.get(rem_key)
                if current_track and field:
                    current_track[field] = rem_value
                elif not current_track:
                    if "GENRE" in rem_key:
                        album_genre = rem_value
                    elif "DATE" in rem_key:
                        album_year = rem_value
                    elif "PERFORMER" in rem_key:
                        album_performer = rem_value

        if current_track:
            tracks.append(current_track)

        return tracks, album_title, album_performer, album_year, album_genre

    def map_cue(self, directory: Path, all_files: list[Path]) -> dict[Path, dict[str, Any]]:
        """Сканирует папку на CUE и сопоставляет их с физическими аудиофайлами."""
        cue_files = list(directory.rglob("*.cue"))
        cue_data = {}
        all_files_by_stem = {f.stem: f for f in all_files}

        for cue_path in cue_files:
            tracks, album_title, album_performer, album_year, album_genre = self.parse_cue(cue_path)
            if not tracks:
                continue

            file_tracks: dict[Path, list[dict]] = {}
            for track in tracks:
                file_name = track.get("file")
                if not file_name:
                    continue

                file_path = (cue_path.parent / file_name).resolve()
                matched_file = None

                if file_path in all_files:
                    matched_file = file_path
                elif file_path.stem in all_files_by_stem:
                    matched_file = all_files_by_stem[file_path.stem]

                if matched_file:
                    file_tracks.setdefault(matched_file, []).append(track)
                else:
                    self.logger.warning(f"Файл {file_name} из CUE {cue_path.name} не найден на диске.")

            for audio_file, tracks_for_file in file_tracks.items():
                contains_multiple_tracks = len(tracks) > 1 and len(file_tracks) == 1
                cue_data[audio_file] = {
                    "tracks": tracks_for_file,
                    "album_title": album_title or cue_path.parent.name,
                    "album_performer": album_performer or "",
                    "album_year": album_year,
                    "album_genre": album_genre,
                    "contains_multiple_tracks": contains_multiple_tracks,
                }

        return cue_data
