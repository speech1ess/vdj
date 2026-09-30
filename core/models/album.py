from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.artist import Artist
    from core.models.audiofile import AudioFile
    from core.models.genre import Genre
    from core.models.label import RecordLabel
    from core.models.track import Track
    from core.models.track_relations import TrackAlbum

import datetime
import json
import re
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class Album(Base):
    """Модель музыкального альбома (SQLAlchemy 2.0 стандарт)."""

    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Мапим скрытое поле _title на колонку "title" с индексом для оптимизации поисковых запросов
    _title: Mapped[str] = mapped_column("title", String(255), nullable=False, default="Unknown", index=True)
    release_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    release_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    date_added: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    date_modified: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    album_type: Mapped[str] = mapped_column(String(50), default="album")
    total_tracks: Mapped[int] = mapped_column(Integer, default=0)
    disc_count: Mapped[int] = mapped_column(Integer, default=1)
    compilation: Mapped[bool] = mapped_column(Boolean, default=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    external_ids: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON-строка с ID (Spotify, Discogs)

    # (Опционально) связь с аудиофайлом для CUE-контекста
    audiofile_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("audiofiles.id"), nullable=True)
    audiofile: Mapped[Optional[AudioFile]] = relationship("AudioFile")

    # Сохраняем все оригинальные связи без потерь
    artists: Mapped[list[Artist]] = relationship("Artist", secondary="artist_album", back_populates="albums")
    genres: Mapped[list[Genre]] = relationship("Genre", secondary="album_genre", back_populates="albums")
    recordlabels: Mapped[list[RecordLabel]] = relationship("RecordLabel", secondary="album_recordlabel", back_populates="albums")
    tracks: Mapped[list[Track]] = relationship(
        "Track",
        secondary="track_album",
        back_populates="albums",
        overlaps="track_album_links,track_album_links_rel,track",
    )

    # Прямая связь со связками TrackAlbum
    track_album_links: Mapped[list[TrackAlbum]] = relationship(
        "TrackAlbum", back_populates="album", cascade="all, delete-orphan", overlaps="tracks,albums"
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.release_date and not self.release_year:
            self.release_year = self.release_date.year

    @classmethod
    def from_raw_title(cls, raw_title: str) -> Album:
        """Создаёт альбом из необработанного названия."""
        clean_title, disc_num, album_type = cls.normalize_album_title(raw_title)
        return cls(title=clean_title, disc_count=disc_num, album_type=album_type)

    @property
    def title(self) -> str:
        """Получить нормализованное название."""
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        """Нормализовать название при установке."""
        clean_title, _, _ = self.normalize_album_title(value)
        self._title = clean_title

    @property
    def sort_title(self) -> str:
        """Генерирует название для сортировки."""
        return self.generate_sort_title(self.title) if self.title else "Unknown"

    @sort_title.setter
    def sort_title(self, value: str) -> None:
        """Игнорируем установку sort_title."""
        pass

    def matches(self, search_term: str) -> bool:
        """Проверяет, соответствует ли альбом поисковому запросу."""
        search_term = search_term.lower()
        return (
            search_term in self.title.lower()
            or search_term in self.sort_title.lower()
            or (self.description and search_term in self.description.lower())
            or any(search_term in genre.name.lower() for genre in self.genres if self.genres)
            or any(search_term in recordlabel.name.lower() for recordlabel in self.recordlabels if self.recordlabels)
            or any(search_term in artist.name.lower() for artist in self.artists if self.artists)
            or (self.barcode and search_term in self.barcode)
        )

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект Album в словарь."""
        return {
            "id": self.id,
            "title": self.title,
            "sort_title": self.sort_title,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "release_year": self.release_year,
            "description": self.description,
            "cover_path": self.cover_path,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "album_type": self.album_type,
            "total_tracks": self.total_tracks,
            "disc_count": self.disc_count,
            "compilation": self.compilation,
            "barcode": self.barcode,
            "external_ids": json.loads(self.external_ids) if self.external_ids else {},
            "artist_ids": [artist.id for artist in self.artists] if self.artists else [],
            "genre_ids": [genre.id for genre in self.genres] if self.genres else [],
            "recordlabel_ids": [recordlabel.id for recordlabel in self.recordlabels] if self.recordlabels else [],
            "track_ids": [track.id for track in self.tracks] if self.tracks else [],
            "audiofile_id": self.audiofile_id,
        }

    @staticmethod
    def generate_sort_title(title: str) -> str:
        """
        Генерирует название для сортировки
        ("The Dark Side of the Moon" → "Dark Side of the Moon, The").
        """
        title = title.strip()
        articles = ["the", "a", "an", "el", "la", "los", "las", "le", "les", "die", "der", "das"]
        parts = title.split(" ", 1)
        if len(parts) > 1 and parts[0].lower() in articles:
            return f"{parts[1]}, {parts[0]}"
        return title

    @staticmethod
    def normalize_album_title(raw_title: str) -> tuple[str, int, str]:
        """Нормализует название альбома, извлекая диск и тип."""
        if not raw_title:
            return "Unknown", 1, "album"

        album_types = [
            "album",
            "lp",
            "ep",
            "single",
            "compilation",
            "demo",
            "mixtape",
            "live",
            "remix",
            "soundtrack",
            "bootleg",
            "reissue",
            "promo",
            "deluxe",
            "instrumental",
        ]
        album_type_pattern = r"\s*(?:" + "|".join(album_types) + r")\s*$"
        disc_pattern = r"\s*(Disc|CD|Disk|BonusCD|Bonus\s+Disc)\s*(\d+)(?:\s*(?:of|-|:)\s*\d+)?\s*$"

        clean_title = raw_title.strip()
        disc_num = 1
        album_type = "album"

        type_match = re.search(album_type_pattern, clean_title, re.IGNORECASE)
        if type_match:
            album_type = type_match.group(0).strip().lower()
            clean_title = clean_title[: type_match.start()].rstrip(" -:/")

        disc_match = re.search(disc_pattern, clean_title, re.IGNORECASE)
        if disc_match:
            disc_num = int(disc_match.group(2))
            clean_title = clean_title[: disc_match.start()].rstrip(" -:/")

        if re.search(r"\s*OST\s*$", clean_title, re.IGNORECASE):
            album_type = "soundtrack"
            clean_title = re.sub(r"\s*OST\s*$", "", clean_title, flags=re.IGNORECASE).rstrip(" -:/")

        return clean_title or "Unknown", disc_num, album_type

    @classmethod
    def consolidate_from_tracks(cls, tracks_with_order: list[tuple[Any, int, int]]) -> Optional[Album]:
        """Объединяет треки в один альбом, сохраняя порядок через TrackAlbum."""
        if not tracks_with_order or not tracks_with_order[0][0].albums:
            return None

        tracks = [t[0] for t in tracks_with_order]
        base_album = tracks[0].albums[0]
        album_key, _, album_type = cls.normalize_album_title(base_album.title)

        album = cls(title=album_key, album_type=album_type)
        album.total_tracks = len(tracks_with_order)

        max_disc_number = 1
        for track, disc_num, track_num in tracks_with_order:
            # Импорт локально, чтобы избежать циклических зависимостей на уровне модулей
            from core.models.track_relations import TrackAlbum

            _ = TrackAlbum(disc_number=disc_num, track_number=track_num)
            track.albums = [album]
            max_disc_number = max(max_disc_number, disc_num)

        album.disc_count = max_disc_number
        return album

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Album:
        """Создает объект Album из словаря."""
        return cls(
            id=data.get("id"),
            title=data.get("title", "Unknown"),
            release_date=datetime.datetime.fromisoformat(data["release_date"]) if data.get("release_date") else None,
            release_year=data.get("release_year"),
            description=data.get("description"),
            cover_path=data.get("cover_path"),
            date_added=datetime.datetime.fromisoformat(data["date_added"]) if data.get("date_added") else datetime.datetime.utcnow(),
            date_modified=datetime.datetime.fromisoformat(data["date_modified"]) if data.get("date_modified") else datetime.datetime.utcnow(),
            album_type=data.get("album_type", "album"),
            total_tracks=data.get("total_tracks", 0),
            disc_count=data.get("disc_count", 1),
            compilation=data.get("compilation", False),
            barcode=data.get("barcode"),
            external_ids=json.dumps(data.get("external_ids", {})),
            audiofile_id=data.get("audiofile_id"),
        )

    def __repr__(self) -> str:
        return f"<Album(title='{self.title}', release_year={self.release_year})>"
