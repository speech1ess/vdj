import re
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Optional

from core.models import Album, Artist, Genre, RecordLabel
from core.services.logging import get_logger
from core.services.tagmap import TagEvaluator, TagMapper


class MetadataNormalizer:
    """
    Высокопроизводительный класс для нормализации, очистки и приведения типов
    метаданных аудиофайлов перед загрузкой в БД.
    """

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.MetadataNormalizer")

    def normalize(self, metadata: dict[str, Any], file: Path) -> dict[str, Any]:
        """Главный пайплайн очистки метаданных."""

        # 1. Нормализация Title
        title = metadata.get("title")
        # Исправлен баг со str(None) -> "None"
        if not title or (isinstance(title, str) and not title.strip()):
            metadata["title"] = "Unknown"
        else:
            metadata["title"] = str(title).strip()

        # 2. Нормализация Artist
        raw_artist = metadata.get("artist")
        if raw_artist:
            if not isinstance(raw_artist, str):
                self.logger.warning(f"Неожиданный тип артиста {type(raw_artist).__name__} в файле {file.name}")
            metadata["artist"] = Artist.normalize_artist_names(str(raw_artist))
        else:
            metadata["artist"] = ["Unknown"]

        # 3. Нормализация Album
        album_raw = metadata.get("album")
        if not album_raw or (isinstance(album_raw, str) and not album_raw.strip()):
            album_raw = "Unknown"

        album_title, disc_number, album_type = Album.normalize_album_title(str(album_raw))
        metadata["album"] = album_title
        metadata["album_type"] = album_type

        # 4. Нормализация Track Number
        track_number = metadata.get("track") or metadata.get("track_number")
        if track_number:
            try:
                parsed_track = int(str(track_number).split("/")[0].strip())
                if parsed_track < 1:
                    raise ValueError
                metadata["track_number"] = parsed_track
            except (ValueError, TypeError):
                metadata["track_number"] = self._extract_track_number_from_filename(file)
        else:
            metadata["track_number"] = self._extract_track_number_from_filename(file)

        # 5. Нормализация Disc Number
        current_disc = disc_number or metadata.get("disc_number")
        try:
            parsed_disc = int(current_disc) if current_disc else 1
            if parsed_disc < 1:
                raise ValueError
            metadata["disc_number"] = parsed_disc
        except (ValueError, TypeError):
            metadata["disc_number"] = 1

        # 6. Нормализация Genre
        genre_input = metadata.get("genre")
        genres = []
        if isinstance(genre_input, list):
            for g in genre_input:
                genres.extend(Genre.normalize_genre_name(g))
        elif genre_input:
            genres = Genre.normalize_genre_name(genre_input)

        metadata["genre"] = [g for g in genres if g] or ["Unknown"]

        # 7. Нормализация Label
        label_raw = metadata.get("label")
        if label_raw is not None:
            metadata["label"] = RecordLabel.normalize_label_name(label_raw)

        # 8. Дата релиза
        release_year, release_date = self._normalize_date(metadata, file)
        metadata["release_year"] = release_year
        metadata["release_date"] = release_date

        # 9. Булевые и Float значения
        if metadata.get("compilation") is not None:
            metadata["compilation"] = self._normalize_bool(metadata["compilation"])

        if metadata.get("track_gain") is not None:
            metadata["track_gain"] = self._normalize_float(metadata["track_gain"])

        # 10. Пути
        metadata["file_path"] = str(file)
        metadata.setdefault("cover_path", None)

        return metadata

    def _extract_track_number_from_filename(self, file: Path) -> Optional[int]:
        match = re.match(r"^(\d+)", file.stem)
        if match:
            try:
                num = int(match.group(1))
                if num >= 1:
                    return num
            except ValueError:
                pass
        return None

    def _normalize_date(self, metadata: dict[str, Any], file: Path) -> Optional[tuple[int, Optional[str]]]:
        release_date = metadata.get("release_date")
        release_year = None

        if release_date:
            date_str = str(release_date).strip()
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m", "%b %Y", "%Y %b", "%Y"):
                try:
                    parsed_date = dt.strptime(date_str, fmt)
                    release_year = parsed_date.year
                    release_date = f"{release_year}-01-01" if fmt == "%Y" else parsed_date.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            else:
                release_date = None

        if not release_date and metadata.get("release_year"):
            try:
                release_year = int(metadata["release_year"])
                release_date = f"{release_year}-01-01"
            except (ValueError, TypeError):
                pass

        if release_date and metadata.get("release_year"):
            try:
                year_tag = int(metadata["release_year"])
                date_year = int(release_date[:4])
                if year_tag != date_year:
                    release_year = date_year
            except (ValueError, TypeError):
                pass

        return release_year, release_date

    def _normalize_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            cleaned_value = str(value).replace("дБ", "").replace("dB", "").strip()
            return float(cleaned_value)
        except (ValueError, TypeError):
            return None

    def _normalize_bool(self, value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        try:
            cleaned_value = str(value).strip().lower()
            if cleaned_value in ("true", "1", "yes", "y", "t", "+"):
                return True
            if cleaned_value in ("false", "0", "no", "n", "f", "-"):
                return False
            return None
        except (ValueError, TypeError):
            return None


class MetadataValidator:
    """
    Утилита для оценки качества и полноты извлеченных метаданных.
    Использует TagEvaluator для проверки покрытия обязательных полей.
    """

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.MetadataValidator")
        self.mapper = TagMapper()
        self.evaluator = TagEvaluator(self.mapper)

    def validate(self, metadata: dict[str, Any], file: Path) -> tuple[list[str], list[str]]:
        errors = []
        required_fields = self.mapper.map_req_tags()
        available_models = []

        for model, _tags in required_fields.items():
            coverage = self.evaluator.get_coverage_by_model(metadata, model)
            if coverage["coverage"] > 0:
                available_models.append(model)

            if coverage["coverage"] < 1.0:
                for missing in coverage["missing_fields"]:
                    errors.append(f"Missing field: {model}.{missing}")

        if not available_models:
            errors.append("❌ Metadata doesn't satisfy any model requirements")
            self.logger.warning(f"Файл {file.name} не содержит метаданных для маппинга.")

        return available_models, errors
