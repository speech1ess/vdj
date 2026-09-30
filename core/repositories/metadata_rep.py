# 2025/05/09
# @authors: <GROK> & <speech1ess>

from typing import Any

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from core.models import (
    Album,
    AlbumGenre,
    AlbumRecordLabel,
    Artist,
    ArtistAlbum,
    ArtistGenre,
    ArtistRecordLabel,
    Genre,
    RecordLabel,
)
from core.repositories.base_rep import BaseRepository


class MetadataRepository(BaseRepository):
    """Высокопроизводительный репозиторий для массовой загрузки метаданных."""

    def __init__(self, configurator: Any, cachemanager: Any = None) -> None:
        super().__init__(configurator, cachemanager)

    def save_genres_batch(self, db: Session) -> dict[str, int]:
        """Батч-сохранение жанров."""
        try:
            self.logger.debug("Сохранение жанров из кэша")
            genre_cache, _ = self.cache.get_cache("genre")
            if not genre_cache:
                return {}

            normalized_genres = {}
            for genre in genre_cache.values():
                # TODO: Вынести enhance_genre_name в слой сервисов (MetadataNormalizer)
                enhanced_genres = Genre.enhance_genre_name(genre.name, db)
                for enhanced_name, parent_name in enhanced_genres:
                    normalized_genres[genre.name] = (enhanced_name, parent_name)

            existing = self._check_exist(
                db, Genre, [name for name, _ in normalized_genres.values()], "name"
            )
            genre_ids = {}

            for genre in genre_cache.values():
                enhanced_name, parent_name = normalized_genres[genre.name]
                if enhanced_name in existing:
                    genre_ids[genre.name] = existing[enhanced_name][0]
                else:
                    enhanced_genre = Genre(name=enhanced_name)
                    genre_id, _ = self._save_or_update(
                        db, enhanced_genre, enhanced_name, {}, exclude_fields=["id"]
                    )

                    if parent_name:
                        parent_existing = self._check_exist(db, Genre, [parent_name], "name")
                        if parent_name in parent_existing:
                            parent_id = parent_existing[parent_name][0]
                        else:
                            parent_genre = Genre(name=parent_name)
                            parent_id, _ = self._save_or_update(
                                db, parent_genre, parent_name, {}, exclude_fields=["id"]
                            )
                        enhanced_genre.parent_id = parent_id
                        db.flush()

                    genre_ids[genre.name] = genre_id

            self.cacheops.update_all("genre", genre_ids)
            return genre_ids

        except Exception as e:
            self.logger.error(f"Ошибка сохранения жанров: {e}")
            raise

    def save_labels_batch(self, db: Session) -> dict[str, int]:
        """Батч-сохранение лейблов."""
        try:
            label_cache, _ = self.cache.get_cache("label")
            if not label_cache:
                return {}

            existing = self._check_exist(db, RecordLabel, list(label_cache.keys()), "name")
            label_ids = {}

            for key, label in label_cache.items():
                label_id, _ = self._save_or_update(db, label, key, existing, exclude_fields=["id"])
                label_ids[key] = label_id

            self.cacheops.update_all("label", label_ids)
            return label_ids
        except Exception as e:
            self.logger.error(f"Ошибка сохранения лейблов: {e}")
            raise

    def save_artists_batch(self, db: Session) -> dict[str, int]:
        """Батч-сохранение артистов."""
        try:
            artist_cache, _ = self.cache.get_cache("artist")
            if not artist_cache:
                return {}

            existing = self._check_exist(db, Artist, list(artist_cache.keys()), "name")
            artist_ids = {}

            for key, artist in artist_cache.items():
                artist_id, _ = self._save_or_update(
                    db, artist, key, existing, exclude_fields=["id"]
                )
                artist_ids[key] = artist_id

            self.cacheops.update_all("artist", artist_ids)
            return artist_ids
        except Exception as e:
            self.logger.error(f"Ошибка сохранения артистов: {e}")
            raise

    def save_albums_batch(self, db: Session) -> dict[str, int]:
        """Батч-сохранение альбомов."""
        try:
            album_cache, _ = self.cache.get_cache("album")
            if not album_cache:
                return {}

            composite_keys = list(album_cache.keys())
            album_titles = [key.split(":", 1)[1] if ":" in key else key for key in composite_keys]
            existing = self._check_exist(db, Album, album_titles, "_title")

            album_ids = {}
            for key, album in album_cache.items():
                album_id, _ = self._save_or_update(
                    db, album, album._title, existing, exclude_fields=["id"]
                )
                album_ids[key] = album_id

            self.cacheops.update_all("album", album_ids)
            return album_ids
        except Exception as e:
            self.logger.error(f"Ошибка сохранения альбомов: {e}")
            raise

    def _save_m2m_batch(
        self,
        db: Session,
        model_class: Any,
        cache_data: dict,
        id_map_1: dict,
        id_map_2: dict,
        fk_name_1: str,
        fk_name_2: str,
    ) -> dict[tuple[int, int], int]:
        """
        Универсальный метод для сохранения связей Many-to-Many без N+1 запросов.
        Использует пакетную проверку существующих связей (IN tuple).
        """
        if not cache_data:
            return {}

        rel_ids = {}
        # Собираем пары ключей, которые валидны
        valid_pairs = []
        for id1, id2 in cache_data.keys():
            if id1 in id_map_1.values() and id2 in id_map_2.values():
                valid_pairs.append((id1, id2))

        if not valid_pairs:
            return {}

        # Решаем проблему N+1: вытаскиваем все существующие связи ОДНИМ запросом
        existing_records = (
            db.query(model_class)
            .filter(
                tuple_(getattr(model_class, fk_name_1), getattr(model_class, fk_name_2)).in_(
                    valid_pairs
                )
            )
            .all()
        )

        # Индексируем для быстрого O(1) поиска в памяти
        existing_map = {(getattr(r, fk_name_1), getattr(r, fk_name_2)): r for r in existing_records}

        for id1, id2 in valid_pairs:
            pair = (id1, id2)
            if pair in existing_map:
                # Если PK нет (как в некоторых M2M), используем сам tuple как идентификатор
                rel_ids[pair] = getattr(existing_map[pair], "id", pair)
                continue

            new_rel = model_class(**{fk_name_1: id1, fk_name_2: id2})
            rel_key = self._save_rel(db, new_rel, f"{model_class.__tablename__}_{id1}_{id2}")
            if rel_key is not None:
                rel_ids[pair] = rel_key

        return rel_ids

    # Использование универсального оптимизированного метода для всех связей:

    def save_artist_albums_batch(
        self, db: Session, artist_ids: dict[str, int], album_ids: dict[str, int]
    ) -> dict[tuple[int, int], int]:
        return self._save_m2m_batch(
            db,
            ArtistAlbum,
            self.cache.artist_album_cache,
            artist_ids,
            album_ids,
            "artist_id",
            "album_id",
        )

    def save_artist_genres_batch(
        self, db: Session, artist_ids: dict[str, int], genre_ids: dict[str, int]
    ) -> dict[tuple[int, int], int]:
        return self._save_m2m_batch(
            db,
            ArtistGenre,
            self.cache.artist_genre_cache,
            artist_ids,
            genre_ids,
            "artist_id",
            "genre_id",
        )

    def save_artist_labels_batch(
        self, db: Session, artist_ids: dict[str, int], label_ids: dict[str, int]
    ) -> dict[tuple[int, int], int]:
        return self._save_m2m_batch(
            db,
            ArtistRecordLabel,
            self.cache.artist_label_cache,
            artist_ids,
            label_ids,
            "artist_id",
            "recordlabel_id",
        )

    def save_album_genres_batch(
        self, db: Session, album_ids: dict[str, int], genre_ids: dict[str, int]
    ) -> dict[tuple[int, int], int]:
        return self._save_m2m_batch(
            db,
            AlbumGenre,
            self.cache.album_genre_cache,
            album_ids,
            genre_ids,
            "album_id",
            "genre_id",
        )

    def save_album_labels_batch(
        self, db: Session, album_ids: dict[str, int], label_ids: dict[str, int]
    ) -> dict[tuple[int, int], int]:
        return self._save_m2m_batch(
            db,
            AlbumRecordLabel,
            self.cache.album_label_cache,
            album_ids,
            label_ids,
            "album_id",
            "recordlabel_id",
        )
