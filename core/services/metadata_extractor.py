from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import charset_normalizer
import mutagen

from core.models.enums import AudioFormat
from core.services.logging import get_logger
from core.services.tagmap import TagMapper


class MetadataExtractor:
    """
    Высокопроизводительный экстрактор метаданных (Mutagen-based).
    Оптимизирован для Zero-Copy чтения и гарантированной консистентности контракта.
    """

    AUDIO_EXTENSIONS = {fmt.value for fmt in AudioFormat}

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.MetadataExtractor")
        self.tag_mapper = TagMapper()
        self.logger.debug("MetadataExtractor инициализирован.")

    def extract(self, file_path: str | Path) -> dict[str, Any]:
        """Извлекает нормализованные метаданные с гарантией контракта."""
        file_path = Path(file_path)
        ext = file_path.suffix.upper().lstrip(".")

        # Жесткий Data Contract, который ожидает ObjFactory и Normalizer
        metadata: dict[str, Any] = {
            "artist": None,
            "album": None,
            "title": file_path.stem,  # Фоллбэк
            "genre": None,
            "year": None,
            "duration": 0.0,
            "track_number": None,
            "disc_number": None,
            "bpm": None,
            "key": None,
            "label": None,
        }

        if ext not in self.AUDIO_EXTENSIONS:
            return metadata

        try:
            # mutagen.File сам определяет тип файла без O(N) проверок расширения
            audio = mutagen.File(file_path, easy=True)

            if audio is None:
                # Если EasyID3 не сработал (редкие форматы), пробуем сырой парсинг
                audio = mutagen.File(file_path)

            if audio:
                metadata["duration"] = getattr(audio.info, "length", 0.0)

                # Мульти-форматный извлекатель (EasyID3/Vorbis/MP4)
                if hasattr(audio, "tags") and audio.tags:
                    tags = audio.tags

                    # 1. Извлекаем Artist (поддержка множественных артистов)
                    artists = tags.get("artist", []) or tags.get("TPE1", [])
                    if artists:
                        # Склеиваем, ObjFactory потом разобьет
                        metadata["artist"] = ", ".join(str(a) for a in artists)

                    # 2. Извлекаем Album
                    albums = tags.get("album", []) or tags.get("TALB", [])
                    if albums:
                        metadata["album"] = str(albums[0])

                    # 3. Извлекаем Title
                    titles = tags.get("title", []) or tags.get("TIT2", [])
                    if titles:
                        metadata["title"] = str(titles[0])

                    # 4. Извлекаем Genre
                    genres = tags.get("genre", []) or tags.get("TCON", [])
                    if genres:
                        metadata["genre"] = ", ".join(str(g) for g in genres)

                    # 5. Извлекаем Date/Year
                    dates = tags.get("date", []) or tags.get("TDRC", []) or tags.get("year", []) or tags.get("TYER", [])
                    if dates:
                        # Берем первые 4 цифры (год)
                        year_match = re.search(r"\d{4}", str(dates[0]))
                        if year_match:
                            metadata["year"] = int(year_match.group(0))

                    # 6. Track & Disc Number
                    track_nums = tags.get("tracknumber", []) or tags.get("TRCK", [])
                    if track_nums:
                        metadata["track_number"] = self._parse_num(track_nums[0])

                    disc_nums = tags.get("discnumber", []) or tags.get("TPOS", [])
                    if disc_nums:
                        metadata["disc_number"] = self._parse_num(disc_nums[0])

                    # 7. BPM и Key (Критично для диджейской библиотеки)
                    bpms = tags.get("bpm", []) or tags.get("TBPM", [])
                    if bpms:
                        try:
                            metadata["bpm"] = float(str(bpms[0]))
                        except ValueError:
                            pass

                    keys = tags.get("initialkey", []) or tags.get("TKEY", [])
                    if keys:
                        metadata["key"] = str(keys[0])

                    # 8. Record Label / Publisher
                    labels = tags.get("organization", []) or tags.get("publisher", []) or tags.get("TPUB", [])
                    if labels:
                        metadata["label"] = str(labels[0])

        except Exception as e:
            self.logger.error(f"Сбой извлечения тегов из {file_path.name}: {e}")

        # Фоллбэк трек-номера из имени файла
        if metadata.get("track_number") is None:
            match = re.match(r"^\d+", file_path.stem) or re.search(r"track\s*(\d+)", file_path.stem, re.IGNORECASE)
            if match:
                val = match.group(0) if match.group(0).isdigit() else match.group(1)
                metadata["track_number"] = int(val)

        # Вычищаем None значения, чтобы работали дефолты в ObjFactory
        return {k: v for k, v in metadata.items() if v is not None}

    def _parse_num(self, value: Any) -> Optional[int]:
        """Безопасный парсинг номеров треков/дисков (например '1/12' -> 1)"""
        try:
            cleaned = str(value).split("/")[0].strip()
            return int(cleaned) if cleaned.isdigit() else None
        except Exception:
            return None


# --- CueParser оставляем без изменений ---
class CueParser:
    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.CueParser")
        self.tag_mapper = TagMapper()
        self.reverse_cue_tags = {k.upper(): field for field, aliases in self.tag_mapper.unified_tags.items() for k in aliases if k.startswith("REM ")}

    def parse_cue(self, cue_path: str | Path) -> tuple[list[dict], Optional[str], Optional[str], Optional[str], Optional[str]]:
        cue_path = Path(cue_path)
        tracks = []
        album_title, album_performer, album_year, album_genre = None, None, None, None
        current_file, current_track = None, None

        try:
            with open(cue_path, "rb") as f:
                raw_data = f.read()

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
