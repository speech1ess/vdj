from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.album import Album
    from core.models.artist import Artist
    from core.models.audiofile import AudioFile
    from core.models.genre import Genre
    from core.models.playlist import Playlist
    from core.models.tag import Tag
    from core.models.track_relations import TrackAlbum, TrackAudioFile
    from core.models.user import User

import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base
from core.models.enums import MusicalKey


class Track(Base):
    """Ядерная модель музыкального трека (SQLAlchemy 2.0)."""

    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Unknown", index=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ИСПРАВЛЕНИЕ: BPM должен быть Float (как заявлено в SRS) и иметь ИНДЕКС для быстрых DJ-выборок
    bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)

    # Тональность. Индекс обязателен для гармонического сведения (Camelot Wheel)
    key: Mapped[Optional[MusicalKey]] = mapped_column(SQLEnum(MusicalKey, native_enum=False, length=32), nullable=True, index=True)

    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    date_added: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    track_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Поля Essentia/Librosa. Индексы обязательны для алгоритмов генерации плейлистов.
    energy_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    mood: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    loudness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dynamic_range: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Связь "многие к одному" с AudioFile
    audiofile_id: Mapped[int] = mapped_column(Integer, ForeignKey("audiofiles.id", ondelete="CASCADE"), nullable=False, index=True)
    audiofile: Mapped[AudioFile] = relationship("AudioFile", back_populates="tracks")
    track_links: Mapped[list[TrackAudioFile]] = relationship("TrackAudioFile", back_populates="track", cascade="all, delete-orphan")

    # Many-to-Many связи
    artists: Mapped[list[Artist]] = relationship("Artist", secondary="track_artist", back_populates="tracks")
    albums: Mapped[list[Album]] = relationship(
        "Album",
        secondary="track_album",
        back_populates="tracks",
        overlaps="track_album_links_rel,track",
    )
    genres: Mapped[list[Genre]] = relationship("Genre", secondary="track_genre", back_populates="tracks")
    playlists: Mapped[list[Playlist]] = relationship("Playlist", secondary="track_playlist", back_populates="tracks")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary="track_tag", back_populates="tracks")
    favorited_by: Mapped[list[User]] = relationship("User", secondary="user_track", back_populates="favorites")

    track_album_links_rel: Mapped[list[TrackAlbum]] = relationship(
        "TrackAlbum", back_populates="track", cascade="all, delete-orphan", overlaps="albums"
    )

    @property
    def disc_number(self) -> int:
        """Возвращает номер диска из связки TrackAlbum (если есть)."""
        if self.albums:
            link = next((ta for ta in self.track_album_links_rel if ta.album_id == self.albums[0].id), None)
            if link:
                return link.disc_number
        return 1

    @disc_number.setter
    def disc_number(self, value: int) -> None:
        if self.albums:
            link = next((ta for ta in self.track_album_links_rel if ta.album_id == self.albums[0].id), None)
            if link:
                link.disc_number = value
            else:
                raise ValueError("TrackAlbum link not found for disc_number assignment.")
        else:
            raise ValueError("Cannot set disc_number — no album linked.")

    @property
    def album_track_number(self) -> int:
        """Возвращает номер трека внутри альбома из связки TrackAlbum (если есть)."""
        if self.albums:
            link = next((ta for ta in self.track_album_links_rel if ta.album_id == self.albums[0].id), None)
            if link:
                return link.track_number
        return self.track_number or 0

    @album_track_number.setter
    def album_track_number(self, value: int) -> None:
        if self.albums:
            link = next((ta for ta in self.track_album_links_rel if ta.album_id == self.albums[0].id), None)
            if link:
                link.track_number = value
            else:
                raise ValueError("TrackAlbum link not found for track_number assignment.")
        else:
            raise ValueError("Cannot set track_number — no album linked.")

    @property
    def duration_formatted(self) -> str:
        """Возвращает длительность трека в формате MM:SS."""
        if not self.duration or self.duration <= 0:
            return "00:00"
        minutes, seconds = divmod(self.duration, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект Track в словарь."""
        return {
            "id": self.id,
            "title": self.title,
            "duration": self.duration,
            "bpm": self.bpm,
            "key": self.key.value if self.key else None,
            "rating": self.rating,
            "play_count": self.play_count,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "audiofile_id": self.audiofile_id,
            "year": self.year,
            "track_number": self.track_number,
            "energy_level": self.energy_level,
            "mood": self.mood,
            "loudness": self.loudness,
            "dynamic_range": self.dynamic_range,
            # Осторожно: вызов relationships без joinedload вызовет N+1 запросы к БД
            "artist_ids": [artist.id for artist in self.artists] if self.artists else [],
            "album_ids": [album.id for album in self.albums] if self.albums else [],
            "genre_ids": [genre.id for genre in self.genres] if self.genres else [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Track:
        """Создает объект Track из словаря."""
        key_val = data.get("key")
        key_enum = next((m for m in MusicalKey if m.value == key_val), None) if key_val else None

        return cls(
            id=data.get("id"),
            title=data.get("title", "Unknown"),
            duration=data.get("duration", 0),
            bpm=data.get("bpm"),
            key=key_enum,
            rating=data.get("rating"),
            play_count=data.get("play_count", 0),
            date_added=datetime.datetime.fromisoformat(data["date_added"]) if data.get("date_added") else datetime.datetime.utcnow(),
            audiofile_id=data.get("audiofile_id"),
            year=data.get("year"),
            track_number=data.get("track_number"),
            energy_level=data.get("energy_level"),
            mood=data.get("mood"),
            loudness=data.get("loudness"),
            dynamic_range=data.get("dynamic_range"),
        )

    def __repr__(self) -> str:
        return f"<Track(title='{self.title}', bpm={self.bpm}, key={self.key.value if self.key else None})>"
