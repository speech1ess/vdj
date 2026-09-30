from __future__ import annotations

from typing import Optional

from core.models.playlist import Playlist
from core.models.track import Track
from core.models.track_relations import TrackPlaylist
from core.viewmodels.basevwm import BaseViewModel


class PlaylistViewModel(BaseViewModel):
    """ViewModel для управления плейлистами."""

    def __init__(self, configurator, log_callback=None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.logger.info("PlaylistViewModel инициализирован")

    def get_playlists(self) -> list[dict]:
        try:
            with self.get_db_session() as session:
                playlists = session.query(Playlist).all()
                # Трансляция ORM в DTO
                result = [{"id": p.id, "name": p.name} for p in playlists]
                self.set_status(f"Загружено {len(result)} плейлистов")
                return result
        except Exception as e:
            self.logger.error(f"Ошибка загрузки плейлистов: {e}")
            self.set_status("Ошибка загрузки плейлистов")
            return []

    def get_playlist_tracks(self, playlist_id: int) -> list[dict]:
        try:
            with self.get_db_session() as session:
                tracks = (
                    session.query(Track)
                    .join(TrackPlaylist, Track.id == TrackPlaylist.track_id)
                    .filter(TrackPlaylist.playlist_id == playlist_id)
                    .all()
                )
                result = [self._track_to_dict(track) for track in tracks]
                self.set_status(f"Загружено {len(result)} треков")
                return result
        except Exception as e:
            self.logger.error(f"Ошибка загрузки треков плейлиста {playlist_id}: {e}")
            self.set_status("Ошибка загрузки треков")
            return []

    def create_playlist(self, name: str) -> Optional[int]:
        try:
            with self.get_db_session() as session:
                playlist = Playlist(name=name)
                session.add(playlist)
                session.commit()
                # Доступ к ID безопасен, так как SQLAlchemy заполнит его после commit
                p_id = playlist.id

            self.set_status(f"Плейлист '{name}' создан")
            return p_id
        except Exception as e:
            self.logger.error(f"Ошибка создания плейлиста: {e}")
            self.set_status("Ошибка создания плейлиста")
            return None

    def delete_playlist(self, playlist_id: int) -> bool:
        try:
            with self.get_db_session() as session:
                playlist = session.query(Playlist).filter(Playlist.id == playlist_id).first()
                if not playlist:
                    self.set_status("Плейлист не найден")
                    return False

                session.delete(playlist)
                session.commit()

            self.set_status("Плейлист удалён")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка удаления плейлиста: {e}")
            self.set_status("Ошибка удаления плейлиста")
            return False

    def _track_to_dict(self, track: Track) -> dict:
        """Транслирует ORM трек в безопасный словарь (вызывать ТОЛЬКО внутри открытой сессии)."""
        artist_names = ", ".join(artist.name for artist in track.artists) if track.artists else "Unknown"
        duration = str(track.duration) if track.duration else "N/A"
        return {"title": track.title, "artist": artist_names, "duration": duration}
