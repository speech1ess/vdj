from sqlalchemy.orm import configure_mappers

from core.database.base import Base
from core.models.album import Album
from core.models.artist import Artist
from core.models.audiofile import AudioFile
from core.models.genre import Genre
from core.models.label import RecordLabel
from core.models.playlist import Playlist
from core.models.tag import Tag
from core.models.track import Track

# 1. Промежуточные связи (Association Tables)
from core.models.track_relations import (
    AlbumGenre,
    AlbumRecordLabel,
    ArtistAlbum,
    ArtistGenre,
    ArtistRecordLabel,
    TrackAlbum,
    TrackArtist,
    TrackAudioFile,
    TrackGenre,
    TrackPlaylist,
    TrackTag,
    UserPlaylist,
    UserTrack,
)

# 2. Основные DTO-модели
from core.models.user import User
from core.services.logging import get_logger

logger = get_logger("PlaylistAI.Models")

try:
    configure_mappers()
    logger.debug("SQLAlchemy ORM mappers configured and validated successfully.")
except Exception as e:
    logger.critical(f"FATAL: ORM mapping validation failed. Graph is inconsistent: {e}")
    raise

__all__ = [
    "Base",
    "Track",
    "AudioFile",
    "Artist",
    "Album",
    "Genre",
    "RecordLabel",
    "Playlist",
    "Tag",
    "User",
    "TrackArtist",
    "TrackAlbum",
    "TrackGenre",
    "TrackAudioFile",
    "TrackTag",
    "TrackPlaylist",
    "UserTrack",
    "UserPlaylist",
    "ArtistAlbum",
    "ArtistGenre",
    "ArtistRecordLabel",
    "AlbumGenre",
    "AlbumRecordLabel",
]
