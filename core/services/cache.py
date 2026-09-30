from pathlib import Path
from typing import Any, Optional, Union

from core.models import (
    Album,
    AlbumGenre,
    AlbumRecordLabel,
    Artist,
    ArtistAlbum,
    ArtistGenre,
    ArtistRecordLabel,
    AudioFile,
    Genre,
    RecordLabel,
    Track,
    TrackAlbum,
    TrackArtist,
    TrackAudioFile,
    TrackGenre,
)
from core.services.logging import get_logger
from core.services.tagmap import TagMapper


class CacheManager:
    """Высокопроизводительный In-Memory кэш для пакетного сканирования и дедупликации."""

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.CacheManager")

        self.audiofile_cache: dict[str, AudioFile] = {}
        self.album_cache: dict[str, Album] = {}
        self.artist_cache: dict[str, Artist] = {}
        self.track_cache: dict[str, Track] = {}
        self.genre_cache: dict[str, Genre] = {}
        self.label_cache: dict[str, RecordLabel] = {}

        self.track_audiofile_cache: dict[tuple[int, int], TrackAudioFile] = {}
        self.track_album_cache: dict[tuple[int, int], TrackAlbum] = {}
        self.track_artist_cache: dict[tuple[int, int], TrackArtist] = {}
        self.track_genre_cache: dict[tuple[int, int], TrackGenre] = {}
        self.artist_album_cache: dict[tuple[int, int], ArtistAlbum] = {}
        self.artist_genre_cache: dict[tuple[int, int], ArtistGenre] = {}
        self.artist_label_cache: dict[tuple[int, int], ArtistRecordLabel] = {}
        self.album_genre_cache: dict[tuple[int, int], AlbumGenre] = {}
        self.album_label_cache: dict[tuple[int, int], AlbumRecordLabel] = {}

        self.next_id = 1

    def assign_temp_id(self, obj: Any) -> int:
        """Назначает временный ID для корректной сборки связей в кэше до сброса в БД."""
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        return obj.id

    def add_audiofile(self, file_path: str, data: dict) -> AudioFile:
        if file_path not in self.audiofile_cache:
            audiofile = AudioFile.from_dict(data)
            self.assign_temp_id(audiofile)
            self.audiofile_cache[file_path] = audiofile
        return self.audiofile_cache[file_path]

    def add_album(self, raw_title: str, artist: str, data: dict) -> Album:
        key = f"{artist}:{raw_title}"
        if key not in self.album_cache:
            album = Album.from_dict(data)
            self.assign_temp_id(album)
            self.album_cache[key] = album
        return self.album_cache[key]

    def add_artists(self, data: dict[str, Any]) -> list[Artist]:
        artists = []
        artist_names = data.get("name", [])

        if not isinstance(artist_names, (list, tuple)):
            return artists

        for name in artist_names:
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if name not in self.artist_cache:
                artist = Artist.from_dict({"name": name})
                self.assign_temp_id(artist)
                self.artist_cache[name] = artist
            artists.append(self.artist_cache[name])
        return artists

    def add_track(self, audiofile: Optional[AudioFile], disc_number: int, track_number: int, data: dict) -> Track:
        file_path = getattr(audiofile, "file_path", "no_file") if audiofile else "no_file"
        title = data.get("title", "Unknown")
        disc_num = disc_number or 1
        track_num = track_number or 1

        key = f"{file_path}:{title}:{disc_num}:{track_num}"
        if key not in self.track_cache:
            track = Track.from_dict(data)
            track.audiofile = audiofile
            self.assign_temp_id(track)
            self.track_cache[key] = track
        return self.track_cache[key]

    def add_genre(self, name: str) -> Genre:
        if name not in self.genre_cache:
            genre = Genre.from_dict({"name": name})
            self.assign_temp_id(genre)
            self.genre_cache[name] = genre
        return self.genre_cache[name]

    def add_label(self, name: str) -> RecordLabel:
        name = name or "Unknown"
        if name not in self.label_cache:
            label = RecordLabel.from_dict({"name": name})
            self.assign_temp_id(label)
            self.label_cache[name] = label
        return self.label_cache[name]

    # --- M2M Relations ---

    def add_track_audiofile(self, track: Track, audiofile: AudioFile) -> TrackAudioFile:
        key = (track.id, audiofile.id)
        if key not in self.track_audiofile_cache:
            relation = TrackAudioFile(track_id=track.id, audiofile_id=audiofile.id)
            self.assign_temp_id(relation)
            self.track_audiofile_cache[key] = relation
        return self.track_audiofile_cache[key]

    def add_track_album(self, track: Track, album: Album, disc_number: int, track_number: int) -> TrackAlbum:
        key = (track.id, album.id)
        if key not in self.track_album_cache:
            relation = TrackAlbum(
                track_id=track.id,
                album_id=album.id,
                disc_number=disc_number,
                track_number=track_number,
            )
            self.assign_temp_id(relation)
            self.track_album_cache[key] = relation
        return self.track_album_cache[key]

    def add_track_artist(self, track: Track, artist: Artist) -> TrackArtist:
        key = (track.id, artist.id)
        if key not in self.track_artist_cache:
            relation = TrackArtist(track_id=track.id, artist_id=artist.id)
            self.assign_temp_id(relation)
            self.track_artist_cache[key] = relation
        return self.track_artist_cache[key]

    def add_track_genre(self, track: Track, genre: Genre) -> TrackGenre:
        key = (track.id, genre.id)
        if key not in self.track_genre_cache:
            relation = TrackGenre(track_id=track.id, genre_id=genre.id)
            self.assign_temp_id(relation)
            self.track_genre_cache[key] = relation
        return self.track_genre_cache[key]

    def add_artist_album(self, artist: Artist, album: Album) -> ArtistAlbum:
        key = (artist.id, album.id)
        if key not in self.artist_album_cache:
            relation = ArtistAlbum(artist_id=artist.id, album_id=album.id)
            self.assign_temp_id(relation)
            self.artist_album_cache[key] = relation
        return self.artist_album_cache[key]

    def add_artist_genre(self, artist: Artist, genre: Genre) -> ArtistGenre:
        key = (artist.id, genre.id)
        if key not in self.artist_genre_cache:
            relation = ArtistGenre(artist_id=artist.id, genre_id=genre.id)
            self.assign_temp_id(relation)
            self.artist_genre_cache[key] = relation
        return self.artist_genre_cache[key]

    def add_artist_label(self, artist: Artist, label: RecordLabel) -> ArtistRecordLabel:
        key = (artist.id, label.id)
        if key not in self.artist_label_cache:
            relation = ArtistRecordLabel(artist_id=artist.id, recordlabel_id=label.id)
            self.assign_temp_id(relation)
            self.artist_label_cache[key] = relation
        return self.artist_label_cache[key]

    def add_album_genre(self, album: Album, genre: Genre) -> AlbumGenre:
        key = (album.id, genre.id)
        if key not in self.album_genre_cache:
            relation = AlbumGenre(album_id=album.id, genre_id=genre.id)
            self.assign_temp_id(relation)
            self.album_genre_cache[key] = relation
        return self.album_genre_cache[key]

    def add_album_label(self, album: Album, label: RecordLabel) -> AlbumRecordLabel:
        key = (album.id, label.id)
        if key not in self.album_label_cache:
            relation = AlbumRecordLabel(album_id=album.id, recordlabel_id=label.id)
            self.assign_temp_id(relation)
            self.album_label_cache[key] = relation
        return self.album_label_cache[key]

    def get_cache(self, model_name: str) -> tuple[dict, list[str]]:
        """Динамически возвращает кэш для указанной модели и список имен связанных M2M кэшей."""
        cache_name = f"{model_name.lower()}_cache"
        if not hasattr(self, cache_name):
            raise ValueError(f"Кэш '{cache_name}' не существует.")

        cache = getattr(self, cache_name)
        all_caches = [attr for attr in dir(self) if attr.endswith("_cache")]
        related_cache_names = [c for c in all_caches if model_name in c.split("_")[:-1] and c != cache_name]

        return cache, related_cache_names

    def clear(self) -> None:
        """Сбрасывает состояние кэша (предотвращает OOM при мульти-пакетной загрузке)."""
        self.__init__()

    def consolidate_albums(self) -> None:
        for album in self.album_cache.values():
            album.consolidate_from_tracks(self.track_album_cache)


class ObjFactory:
    """Оптимизированная фабрика для трансляции сырых метаданных в графы ORM-объектов."""

    def __init__(self, cache_manager: CacheManager) -> None:
        self.cache = cache_manager
        self.logger = get_logger("PlaylistAI.ObjFactory")
        self.tag_mapper = TagMapper()

    def _map_fields(self, model_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Универсальный и быстрый маппер полей.
        Снижает CPU bound нагрузку: убраны тысячи вызовов logger.debug внутри цикла.
        """
        fields = self.tag_mapper.get_model_fields(model_name)
        model_tags = self.tag_mapper.models_to_tag.get(model_name, {})
        data = {}

        for field in fields:
            tag = model_tags.get(field)
            if tag and tag in metadata:
                value = metadata[tag]
                if value is not None:
                    data[field] = value
        return data

    def create_audiofile(self, file: Union[str, Path], metadata: dict[str, Any]) -> AudioFile:
        data = self._map_fields("AudioFile", metadata)
        return self.cache.add_audiofile(str(file), data)

    def create_genre(self, metadata: dict[str, Any]) -> list[Genre]:
        genre_names = metadata.get("genre", [])
        genres = []
        if not isinstance(genre_names, (list, tuple)):
            return genres

        for name in genre_names:
            if isinstance(name, str) and name.strip():
                genres.append(self.cache.add_genre(name.strip()))
        return genres

    def create_artist(self, metadata: dict[str, Any]) -> list[Artist]:
        data = self._map_fields("Artist", metadata)
        return self.cache.add_artists(data)

    def create_album(self, artists: list[Artist], metadata: dict[str, Any]) -> Album:
        data = self._map_fields("Album", metadata)
        raw_title = metadata.get("album", "Unknown")

        artist_name = "Unknown"
        if artists:
            artist_name = artists[0].name
        elif metadata.get("artist"):
            artist_names = metadata["artist"]
            if isinstance(artist_names, list) and artist_names:
                artist_name = str(artist_names[0])

        return self.cache.add_album(raw_title, artist_name, data)

    def create_track(
        self,
        metadata: dict[str, Any],
        disc_number: int,
        track_number: int,
        audiofile: Optional[AudioFile] = None,
    ) -> Track:
        data = self._map_fields("Track", metadata)
        if audiofile and hasattr(audiofile, "id"):
            data["audiofile_id"] = audiofile.id

        return self.cache.add_track(audiofile, disc_number, track_number, data)

    def create_label(self, label_names: Union[str, list[str]]) -> list[RecordLabel]:
        labels = []
        if isinstance(label_names, str):
            label_names = [label_names]
        elif not isinstance(label_names, (list, tuple)):
            return labels

        for name in label_names:
            if isinstance(name, str) and name.strip():
                labels.append(self.cache.add_label(name.strip()))
        return labels

    def create_objects(self, file: Path, metadata: dict[str, Any], models_found: list[str]) -> tuple[AudioFile, list[Track]]:
        """Оркестратор сборки графа объектов для одного физического файла."""

        audiofile = self.create_audiofile(file, metadata)

        genres = self.create_genre(metadata) if "Genre" in models_found and "genre" in metadata else []
        labels = self.create_label(metadata["label"]) if "RecordLabel" in models_found and "label" in metadata else []
        artists = self.create_artist(metadata) if "Artist" in models_found and "artist" in metadata else []
        album = self.create_album(artists, metadata) if "Album" in models_found else None

        disc_number = metadata.get("disc_number", 1)
        track_number = metadata.get("track_number", 1)
        track = self.create_track(metadata, disc_number, track_number, audiofile) if "Track" in models_found else None

        # Сборка графа связей
        if track and audiofile:
            self.cache.add_track_audiofile(track, audiofile)
        if track and album:
            self.cache.add_track_album(track, album, disc_number, track_number)
            for genre in genres:
                self.cache.add_track_genre(track, genre)
            for artist in artists:
                self.cache.add_track_artist(track, artist)

        if artists and album:
            self.cache.add_artist_album(artists[0], album)
            for label in labels:
                for artist in artists:
                    self.cache.add_artist_label(artist, label)
                self.cache.add_album_label(album, label)
            for genre in genres:
                for artist in artists:
                    self.cache.add_artist_genre(artist, genre)
                self.cache.add_album_genre(album, genre)

        return audiofile, [track] if track else []
