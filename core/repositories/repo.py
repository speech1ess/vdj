from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.database.connmgr import get_db
from core.models import Track
from core.repositories.audiofile_rep import AudioFileRepository
from core.repositories.metadata_rep import MetadataRepository
from core.repositories.track_rep import TrackRepository
from core.services.cache import CacheManager
from core.services.config import Configurator
from core.services.logging import get_logger


class Repo:
    """Оркестратор персистентности музыкальных данных (Atomic Unit of Work)."""

    def __init__(
        self,
        configurator: Optional[Configurator] = None,
        cachemanager: Optional[CacheManager] = None,
    ) -> None:
        self.configurator = configurator or Configurator()
        self.cachemanager = cachemanager or CacheManager()
        self.logger = get_logger("PlaylistAI.Repo.Orchestrator")

        # Инициализация специализированных репозиториев
        self.audiofile_repo = AudioFileRepository(self.configurator, self.cachemanager)
        self.metadata_repo = MetadataRepository(self.configurator, self.cachemanager)
        self.track_repo = TrackRepository(self.configurator, self.cachemanager)

        # Доступ к cacheops через track_repo для обратной совместимости
        self.cacheops = self.track_repo.cacheops

    def _save_metadata_blocks(self, db: Session) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
        """Сохраняет блоки метаданных и синхронизирует кэш в памяти."""
        self.logger.debug("Сохранение блоков метаданных (genres, labels, artists, albums).")

        genre_ids = self.metadata_repo.save_genres_batch(db)
        self.cacheops.update_all("genre", genre_ids)

        label_ids = self.metadata_repo.save_labels_batch(db)
        self.cacheops.update_all("label", label_ids)

        artist_ids = self.metadata_repo.save_artists_batch(db)
        self.cacheops.update_all("artist", artist_ids)

        album_ids = self.metadata_repo.save_albums_batch(db)
        self.cacheops.update_all("album", album_ids)

        return genre_ids, label_ids, artist_ids, album_ids

    def _save_relationships(
        self,
        db: Session,
        artist_ids: dict[str, int],
        album_ids: dict[str, int],
        genre_ids: dict[str, int],
        label_ids: dict[str, int],
    ) -> None:
        """Сохраняет связи Many-to-Many между метаданными."""
        self.logger.debug("Сохранение связей метаданных (M2M).")
        self.metadata_repo.save_artist_albums_batch(db, artist_ids, album_ids)
        self.metadata_repo.save_artist_genres_batch(db, artist_ids, genre_ids)
        self.metadata_repo.save_artist_labels_batch(db, artist_ids, label_ids)
        self.metadata_repo.save_album_genres_batch(db, album_ids, genre_ids)
        self.metadata_repo.save_album_labels_batch(db, album_ids, label_ids)

    def save_data(self, tracks: list[Track]) -> bool:
        """
        Атомарно сохраняет всю музыкальную библиотеку: аудиофайлы, метаданные, треки и связи.
        Применяется паттерн Unit of Work: либо записывается целиком, либо происходит ROLLBACK.
        """
        try:
            self.logger.info(f"=== НАЧАЛО АТОМАРНОГО ИМПОРТА: {len(tracks)} треков ===")

            with get_db(self.configurator) as db:
                # 1. Сохранение и нормализация базовых метаданных
                genre_ids, label_ids, artist_ids, album_ids = self._save_metadata_blocks(db)

                # 2. Сохранение связей метаданных
                self._save_relationships(db, artist_ids, album_ids, genre_ids, label_ids)

                # 3. Сохранение физических аудиофайлов
                self.logger.debug("Сохранение аудиофайлов.")
                audiofile_ids = self.audiofile_repo._save_audiofiles(db, self.audiofile_repo.cache.audiofile_cache)

                # 4. Сохранение треков и их связей с файлами и метаданными
                self.logger.debug("Сохранение треков.")
                self.track_repo.save_tracks(db, tracks, audiofile_ids, artist_ids, album_ids, genre_ids)

                # Единый атомарный коммит на всю сессию.
                # Минимизируем fsync syscalls, максимизируем I/O throughput.
                db.commit()

            self.logger.info(f"✅ Успешно импортировано и закоммичено треков: {len(tracks)}")
            return True

        except Exception as e:
            self.logger.critical(
                f"❌ Критический сбой при импорте данных. Выполнен полный ROLLBACK: {e}",
                exc_info=True,
            )
            return False
