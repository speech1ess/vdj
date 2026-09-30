# 2025/05/09
# @authors: <GROK> & <speech1ess>

from typing import Any, Optional

from sqlalchemy import func

from core.database.connmgr import get_db
from core.models.album import Album
from core.models.artist import Artist
from core.models.audiofile import AudioFile
from core.models.genre import Genre
from core.models.playlist import Playlist
from core.models.track import Track
from core.models.track_relations import TrackGenre
from core.repositories.base_rep import BaseRepository
from core.services.config import Configurator


class StatisticsRepository(BaseRepository):
    """Высокопроизводительный репозиторий для сбора системной и медиа-статистики."""

    def __init__(self, configurator: Optional[Configurator] = None) -> None:
        super().__init__(configurator)

    def get_totals(self) -> dict[str, Any]:
        """
        Возвращает общую статистику медиатеки за 1 SQL раунд-трип.
        Устраняет проблему N+1 запросов к статистическим таблицам.
        """
        with get_db(self.configurator) as db:
            # Выполняем агрегацию за один запрос, минимизируя сетевой и дисковый overhead
            totals_query = db.query(
                func.count(Track.id).label("tracks"),
                func.count(Album.id).label("albums"),
                func.count(Artist.id).label("artists"),
                func.count(Genre.id).label("genres"),
                func.count(Playlist.id).label("playlists"),
                func.coalesce(func.sum(Track.duration), 0).label("duration"),
                func.coalesce(
                    db.query(func.sum(AudioFile.file_size)).join(Track, Track.audiofile_id == AudioFile.id).scalar_subquery(),
                    0,
                ).label("size"),
            ).one()

            return {
                "total_tracks": totals_query.tracks,
                "total_albums": totals_query.albums,
                "total_artists": totals_query.artists,
                "total_genres": totals_query.genres,
                "total_playlists": totals_query.playlists,
                "total_duration_seconds": totals_query.duration,
                "total_size_bytes": totals_query.size,  # Форматирование переносим на уровень UI/DTO
            }

    def get_bpm_distribution(self) -> list[float]:
        """
        Возвращает распределение BPM.
        TODO: При росте базы > 100k треков переписать на SQL-гистограммы (bucketing),
        чтобы не вытягивать сырой массив в RAM.
        """
        with get_db(self.configurator) as db:
            bpm_result = db.query(Track.bpm).filter(Track.bpm.isnot(None)).all()
            return [row[0] for row in bpm_result]

    def get_genre_distribution(self) -> dict[str, int]:
        """Возвращает распределение треков по жанрам с использованием серверной агрегации."""
        with get_db(self.configurator) as db:
            genre_result = (
                db.query(Genre.name, func.count(TrackGenre.track_id)).join(TrackGenre, Genre.id == TrackGenre.genre_id).group_by(Genre.name).all()
            )
            return {name: count for name, count in genre_result if name}
