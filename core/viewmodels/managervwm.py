from __future__ import annotations

from typing import Optional

from core.models.artist import Artist
from core.models.genre import Genre
from core.repositories.audiofile_rep import AudioFileRepository
from core.repositories.metadata_rep import MetadataRepository
from core.repositories.track_rep import TrackRepository
from core.services.config import Configurator
from core.viewmodels.basevwm import BaseViewModel


class ManagerViewModel(BaseViewModel):
    """ViewModel для управления медиатекой. Обеспечивает безопасный ORM -> DTO маппинг."""

    def __init__(self, configurator: Configurator, log_callback: Optional[callable] = None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        metadata_repo = MetadataRepository(self.configurator)
        audiofile_repo = AudioFileRepository(self.configurator)
        self.track_repo = TrackRepository(self.configurator, metadata_repo, audiofile_repo)

    def format_duration(self, seconds: int) -> str:
        """Форматирует секунды в mm:ss (перенесено из слоя репозиториев для чистоты)."""
        if not seconds:
            return "00:00"
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def get_tracks(self, genre: str = None, artist: str = None) -> list[dict[str, str]]:
        try:
            with self.get_db_session() as db:
                tracks_tuple = self.track_repo.get_tracks(db, genre, artist)

                formatted_tracks = []
                for t in tracks_tuple:
                    # t = (track_id, track_title, track_duration, track_bpm, track_key, track_year,
                    # artist_name, album_title, genre_name, file_path)
                    formatted_tracks.append(
                        {
                            "title": t.track_title or "Unknown",
                            "artist": t.artist_name or "Unknown",
                            "album": t.album_title or "Unknown",
                            "duration": self.format_duration(t.track_duration),
                            "bpm": str(t.track_bpm) if t.track_bpm else "",
                            "genre": t.genre_name or "",
                            "key": t.track_key or "",
                            "file": t.file_path or "",
                        }
                    )
                return formatted_tracks
        except Exception as e:
            self.logger.error(f"Ошибка загрузки треков: {e}")
            return []

    def get_genres(self) -> list[str]:
        try:
            with self.get_db_session() as db:
                # Маппинг в список строк внутри транзакции (защита от DetachedInstanceError)
                return [g.name for g in db.query(Genre).order_by(Genre.name).all()]
        except Exception as e:
            self.logger.error(f"Ошибка загрузки жанров: {e}")
            return []

    def get_artists(self) -> list[str]:
        try:
            with self.get_db_session() as db:
                # Маппинг в список строк внутри транзакции
                return [a.name for a in db.query(Artist).order_by(Artist.name).all()]
        except Exception as e:
            self.logger.error(f"Ошибка загрузки артистов: {e}")
            return []
