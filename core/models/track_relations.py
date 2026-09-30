from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.album import Album
    from core.models.audiofile import AudioFile
    from core.models.track import Track

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class TrackArtist(Base):
    __tablename__ = "track_artist"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )


class TrackAlbum(Base):
    __tablename__ = "track_album"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )
    disc_number: Mapped[int] = mapped_column(Integer, default=1)
    track_number: Mapped[int] = mapped_column(Integer, nullable=False)

    track: Mapped[Track] = relationship(
        "Track", back_populates="track_album_links_rel", overlaps="albums"
    )
    album: Mapped[Album] = relationship(
        "Album", back_populates="track_album_links", overlaps="tracks,albums"
    )

    def __repr__(self) -> str:
        return f"<TrackAlbum(track_id={self.track_id}, album_id={self.album_id}, disc_number={self.disc_number}, track_number={self.track_number})>"


class TrackGenre(Base):
    __tablename__ = "track_genre"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


class TrackAudioFile(Base):
    __tablename__ = "track_audiofile"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    audiofile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audiofiles.id", ondelete="CASCADE"), primary_key=True
    )

    is_multitrack: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[float] = mapped_column(
        Float, default=0.0
    )  # Смещение в секундах для CUE-файлов

    track: Mapped[Track] = relationship("Track", back_populates="track_links", overlaps="audiofile")
    audiofile: Mapped[AudioFile] = relationship(
        "AudioFile", back_populates="track_links", overlaps="tracks"
    )

    def __repr__(self) -> str:
        return (
            f"<TrackAudioFile(track_id={self.track_id}, audiofile_id={self.audiofile_id}, "
            f"start_time={self.start_time}, is_multitrack={self.is_multitrack})>"
        )


class ArtistAlbum(Base):
    __tablename__ = "artist_album"

    artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )


class ArtistGenre(Base):
    __tablename__ = "artist_genre"

    artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


class ArtistRecordLabel(Base):
    __tablename__ = "artist_recordlabel"

    artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    recordlabel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recordlabels.id", ondelete="CASCADE"), primary_key=True
    )


class AlbumGenre(Base):
    __tablename__ = "album_genre"

    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


class AlbumRecordLabel(Base):
    __tablename__ = "album_recordlabel"

    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )
    recordlabel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recordlabels.id", ondelete="CASCADE"), primary_key=True
    )


class TrackTag(Base):
    __tablename__ = "track_tag"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class TrackPlaylist(Base):
    __tablename__ = "track_playlist"

    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )


class UserPlaylist(Base):
    __tablename__ = "user_playlist"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )


class UserTrack(Base):
    __tablename__ = "user_track"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
