import csv
from datetime import datetime
from pathlib import Path

import pytz

from core.models.album import Album
from core.models.artist import Artist
from core.models.audiofile import AudioFile
from core.models.enums import AudioFormat, MusicalKey
from core.models.genre import Genre
from core.models.track import Track
from core.services.logging import get_logger


class CSVService:
    """Высокопроизводительный сервис для импорта и экспорта CSV-данных."""

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.CSVService")

    def save_to_csv(self, tracks: list[Track], file_path: str) -> bool:
        """
        Сохраняет список треков в CSV-файл.
        ВНИМАНИЕ: Для избежания N+1 проблемы, передаваемые треки должны быть
        загружены с использованием joinedload для artists, albums и genres.
        """
        try:
            self.logger.info(f"Инициация пакетного экспорта {len(tracks)} треков в {file_path}")
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(["file_path", "title", "artist", "album", "genre", "bpm", "key"])

                # Используем генератор для минимизации аллокаций памяти (O(1) memory overhead)
                def row_generator():
                    for track in tracks:
                        yield [
                            track.audiofile.file_path if track.audiofile else "Unknown Path",
                            track.title,
                            ", ".join(a.name for a in track.artists)
                            if track.artists
                            else "Unknown Artist",
                            ", ".join(a.title for a in track.albums)
                            if track.albums
                            else "Unknown Album",
                            ", ".join(g.name for g in track.genres)
                            if track.genres
                            else "Unknown Genre",
                            track.bpm if track.bpm is not None else "",
                            track.key.value if track.key else "",
                        ]

                # Запись единым батчем на уровне C-расширения csv-модуля
                writer.writerows(row_generator())

            self.logger.info(f"✅ CSV успешно сохранен: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения CSV: {e}", exc_info=True)
            return False

    def load_from_csv(self, file_path: str) -> list[Track]:
        """Загружает треки из CSV-файла, минимизируя CPU-затраты внутри цикла."""
        self.logger.info(f"Инициация импорта данных из CSV: {file_path}")
        tracks = []

        # Выносим вычисления из Data Loop, чтобы не нагружать CPU
        import_time = datetime.now(pytz.utc)

        try:
            with open(file_path, newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file, delimiter=";")

                for row in reader:
                    file_path_str = row.get("file_path", "")

                    # Безопасное извлечение расширения через pathlib (без риска IndexError)
                    ext_str = Path(file_path_str).suffix.lstrip(".").upper()

                    try:
                        file_format = AudioFormat(ext_str)
                    except ValueError:
                        # Fallback на случай, если расширение неизвестно
                        file_format = None

                    audiofile = AudioFile(
                        file_path=file_path_str,
                        file_size=0,
                        hash=None,
                        file_format=file_format,
                        date_added=import_time,
                    )

                    # Безопасный кастинг BPM во Float (как заявлено в SRS)
                    bpm_raw = row.get("bpm", "")
                    bpm_val = None
                    if bpm_raw:
                        try:
                            bpm_val = float(bpm_raw)
                        except ValueError:
                            pass

                    key_raw = row.get("key", "")
                    key_val = MusicalKey[key_raw] if key_raw in MusicalKey.__members__ else None

                    track = Track(
                        title=row.get("title", "Unknown"),
                        artists=[
                            Artist(name=a.strip())
                            for a in row.get("artist", "").split(", ")
                            if a.strip()
                        ]
                        or [Artist(name="Unknown Artist")],
                        albums=[
                            Album(title=a.strip())
                            for a in row.get("album", "").split(", ")
                            if a.strip()
                        ]
                        or [Album(title="Unknown Album")],
                        genres=[
                            Genre(name=g.strip())
                            for g in row.get("genre", "").split(", ")
                            if g.strip()
                        ]
                        or [Genre(name="Unknown Genre")],
                        bpm=bpm_val,
                        key=key_val,
                    )
                    track.audiofile = audiofile
                    tracks.append(track)

            self.logger.info(f"✅ Успешно загружено и распарсено треков: {len(tracks)}")
            return tracks

        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка загрузки CSV: {e}", exc_info=True)
            raise
