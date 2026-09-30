# 2025/05/08
# @authors: <GROK> & <speech1ess>

import uuid

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from core.database.base import get_all_fields
from core.models import AudioFile, Track, TrackAlbum, TrackArtist, TrackAudioFile, TrackGenre
from core.repositories.base_rep import BaseRepository


class TrackRepository(BaseRepository):
    """Высокопроизводительный репозиторий для пакетной персистентности треков и связей."""

    def _make_track_key(self, file_path: str, title: str, disc_num: int, track_num: int) -> str:
        return (
            f"{str(file_path).strip().lower()}:{str(title).strip().lower()}:{disc_num}:{track_num}"
        )

    def save_tracks(
        self,
        db: Session,
        tracks: list[Track],
        audiofile_ids: dict[str, int],
        artist_ids: dict[str, int],
        album_ids: dict[str, int],
        genre_ids: dict[str, int],
    ) -> dict[str, int]:
        """
        Пакетное сохранение треков. Устраняет N+1 проблему с помощью батч-запросов
        и исключает лишние flush-операции внутри циклов.
        """
        call_id = str(uuid.uuid4())
        self.logger.info(f"Начало save_tracks [call_id={call_id}], получено треков: {len(tracks)}")

        if not tracks:
            return {}

        track_fields = get_all_fields().get("Track", [])
        audiofile_ids = {str(k): v for k, v in audiofile_ids.items()}

        # 1. Предварительная подготовка ключей и маппинга путей
        track_payloads = []
        lookup_pairs = []

        for track in tracks:
            title_norm = track.title.strip().lower()
            file_path = str(track.audiofile.file_path).strip()
            disc_number = getattr(track, "disc_number", 1) or 1
            track_number = getattr(track, "track_number", 1) or 1

            key = self._make_track_key(file_path, track.title, disc_number, track_number)
            lookup_pairs.append((file_path, track.title))

            track_payloads.append(
                {
                    "track_obj": track,
                    "title_norm": title_norm,
                    "file_path": file_path,
                    "disc_number": disc_number,
                    "track_number": track_number,
                    "key": key,
                }
            )

        # 2. РЕШЕНИЕ ПРОБЛЕМЫ N+1: Загружаем все потенциально существующие треки ОДНИМ запросом
        existing_tracks_map = {}
        if lookup_pairs:
            # Используем батч-фильтрацию через туплеры для высокой эффективности СУБД
            existing_query = (
                db.query(Track)
                .join(AudioFile, Track.audiofile_id == AudioFile.id)
                .filter(tuple_(AudioFile.file_path, Track.title).in_(lookup_pairs))
                .all()
            )
            for ex in existing_query:
                # Воссоздаем ключ для маппинга в памяти
                ex_disc = 1
                ex_track_num = getattr(ex, "track_number", 1) or 1
                ex_key = self._make_track_key(
                    ex.audiofile.file_path, ex.title, ex_disc, ex_track_num
                )
                existing_tracks_map[ex_key] = ex

        track_ids: dict[str, int] = {}
        processed_tracks = []

        # 3. Пакетная подготовка сущностей для сессии (без вызова flush в цикле)
        for payload in track_payloads:
            track = payload["track_obj"]
            key = payload["key"]
            title_norm = payload["title_norm"]
            file_path = payload["file_path"]

            audiofile_id = audiofile_ids.get(file_path)
            if not audiofile_id:
                raise ValueError(f"КРИТИЧЕСКИЙ СБОЙ: audiofile_id не найден для пути: {file_path}")

            if key in existing_tracks_map:
                track_entity = existing_tracks_map[key]
            else:
                track_entity = Track()
                db.add(track_entity)

            # Маппинг полей
            for field in track_fields:
                if hasattr(track, field):
                    setattr(track_entity, field, getattr(track, field))
            track_entity.audiofile_id = audiofile_id

            processed_tracks.append((track_entity, track, title_norm))

        # Единый flush для генерации ID всех треков батчем
        db.flush()

        for track_entity, track, title_norm in processed_tracks:
            track_ids[title_norm] = track_entity.id
            key = self._make_track_key(track.audiofile.file_path, track.title, 1, 1)
            try:
                self.cache.track_cache[key] = track_entity
            except AttributeError:
                pass

        self.cacheops.update_all("track", track_ids)

        # 4. Пакетное сохранение связей
        self._save_track_relations(
            db, processed_tracks, track_ids, audiofile_ids, artist_ids, album_ids, genre_ids
        )

        self.logger.info(f"✅ Успешно обработано и сохранено треков: {len(track_ids)}")
        return track_ids

    def _save_track_genres(
        self,
        db: Session,
        processed_tracks: list[tuple],
        track_ids: dict[str, int],
        genre_ids: dict[str, int],
    ) -> None:
        new_cache = {}
        relations_to_add = []

        for _track_entity, track, title_norm in processed_tracks:
            track_id = track_ids.get(title_norm)
            if not track_id or not getattr(track, "genres", None):
                continue

            for genre in track.genres:
                genre_id = genre_ids.get(genre)
                if genre_id:
                    relations_to_add.append(TrackGenre(track_id=track_id, genre_id=genre_id))
                    new_cache[(track_id, genre_id)] = True

        if relations_to_add:
            db.bulk_save_objects(
                relations_to_add, return_defaults=False, update_existing_on_duplicate=True
            )
        self.cache.track_genre_cache = new_cache

    def _save_track_artists(
        self,
        db: Session,
        processed_tracks: list[tuple],
        track_ids: dict[str, int],
        artist_ids: dict[str, int],
    ) -> None:
        new_cache = {}
        relations_to_add = []

        for _track_entity, track, title_norm in processed_tracks:
            track_id = track_ids.get(title_norm)
            if not track_id or not getattr(track, "artists", None):
                continue

            for artist in track.artists:
                artist_id = artist_ids.get(artist)
                if artist_id:
                    relations_to_add.append(TrackArtist(track_id=track_id, artist_id=artist_id))
                    new_cache[(track_id, artist_id)] = True

        if relations_to_add:
            db.bulk_save_objects(
                relations_to_add, return_defaults=False, update_existing_on_duplicate=True
            )
        self.cache.track_artist_cache = new_cache

    def _save_track_albums(
        self,
        db: Session,
        processed_tracks: list[tuple],
        track_ids: dict[str, int],
        album_ids: dict[str, int],
    ) -> None:
        new_cache = {}
        relations_to_add = []

        for _track_entity, track, title_norm in processed_tracks:
            track_id = track_ids.get(title_norm)
            if not track_id or not getattr(track, "albums", None):
                continue

            for album in track.albums:
                album_id = album_ids.get(album)
                if album_id:
                    relations_to_add.append(
                        TrackAlbum(
                            track_id=track_id,
                            album_id=album_id,
                            disc_number=getattr(track, "disc_number", 1) or 1,
                            track_number=getattr(track, "track_number", 1) or 1,
                        )
                    )
                    new_cache[(track_id, album_id)] = True

        if relations_to_add:
            db.bulk_save_objects(
                relations_to_add, return_defaults=False, update_existing_on_duplicate=True
            )
        self.cache.track_album_cache = new_cache

    def _save_track_audiofiles(
        self,
        db: Session,
        processed_tracks: list[tuple],
        track_ids: dict[str, int],
        audiofile_ids: dict[str, int],
    ) -> None:
        new_cache = {}
        track_ids_list = [t[0].id for t in processed_tracks if t[0].id]

        if track_ids_list:
            # Очищаем старые привязки аудиофайлов за один запрос, избегая N+1 удаления
            db.query(TrackAudioFile).filter(TrackAudioFile.track_id.in_(track_ids_list)).delete(
                synchronize_session=False
            )

        relations_to_add = []
        for track_entity, track, _title_norm in processed_tracks:
            track_id = track_entity.id
            file_path = str(track.audiofile.file_path).strip()
            audiofile_id = audiofile_ids.get(file_path)

            if track_id and audiofile_id:
                relations_to_add.append(
                    TrackAudioFile(
                        track_id=track_id,
                        audiofile_id=audiofile_id,
                        is_multitrack=False,
                        start_time=0.0,
                    )
                )
                new_cache[(track_id, audiofile_id)] = True

        if relations_to_add:
            db.bulk_save_objects(relations_to_add, return_defaults=False)
        self.cache.track_audiofile_cache = new_cache

    def _save_track_relations(
        self,
        db: Session,
        processed_tracks: list[tuple],
        track_ids: dict[str, int],
        audiofile_ids: dict[str, int],
        artist_ids: dict[str, int],
        album_ids: dict[str, int],
        genre_ids: dict[str, int],
    ) -> None:
        """Оркестрация пакетного сохранения всех связей трека."""
        self._save_track_audiofiles(db, processed_tracks, track_ids, audiofile_ids)
        self._save_track_genres(db, processed_tracks, track_ids, genre_ids)
        self._save_track_artists(db, processed_tracks, track_ids, artist_ids)
        self._save_track_albums(db, processed_tracks, track_ids, album_ids)
