from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.artist import Album
    from core.models.genre import Genre
    from core.models.label import RecordLabel
    from core.models.track import Track

import datetime
import json
import os
import re
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class Artist(Base):
    """Модель исполнителя музыки (SQLAlchemy 2.0)."""

    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Индекс на имя артиста обязателен для быстрых фильтраций и автокомплита в GUI
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    sort_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    date_modified: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Архитектурное исправление: уходим от CSV-строк к нативному типу JSON.
    # В PostgreSQL это мапится в JSONB, что позволяет строить GIN-индексы.
    # В SQLite (от 3.38+) JSON поддерживается нативно.
    aliases: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    members: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)

    image_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    formed_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    disbanded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_band: Mapped[bool] = mapped_column(Boolean, default=False)

    external_ids: Mapped[Optional[dict[str, str]]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    official_website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Сохраняем связи Many-to-many
    tracks: Mapped[list[Track]] = relationship(
        "Track", secondary="track_artist", back_populates="artists"
    )
    albums: Mapped[list[Album]] = relationship(
        "Album", secondary="artist_album", back_populates="artists"
    )
    genres: Mapped[list[Genre]] = relationship(
        "Genre", secondary="artist_genre", back_populates="artists"
    )
    recordlabels: Mapped[list[RecordLabel]] = relationship(
        "RecordLabel", secondary="artist_recordlabel", back_populates="artists"
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not self.sort_name and self.name:
            self.sort_name = self.generate_sort_name(self.name)

        # Защита от старого кода, который может попытаться передать CSV-строку
        if isinstance(self.aliases, str):
            self.aliases = [a.strip() for a in self.aliases.split(",") if a.strip()]
        if isinstance(self.members, str):
            self.members = [m.strip() for m in self.members.split(",") if m.strip()]
        if isinstance(self.external_ids, str):
            try:
                self.external_ids = json.loads(self.external_ids)
            except json.JSONDecodeError:
                self.external_ids = {}

    @staticmethod
    def generate_sort_name(name: str) -> str:
        """Генерирует имя для сортировки ("The Beatles" → "Beatles, The")."""
        name = name.strip()
        articles = ["the", "a", "an", "el", "la", "los", "las", "le", "les", "die", "der", "das"]
        parts = name.split(" ", 1)
        if len(parts) > 1 and parts[0].lower() in articles:
            return f"{parts[1]}, {parts[0]}"
        return name

    @staticmethod
    def normalize_artist_names(artist_string: str) -> list[str]:
        """
        Парсит строку с артистами в список,
        не разбивая 'feat.', 'with', 'prod.' как отдельных исполнителей.
        """
        if not artist_string or not isinstance(artist_string, str):
            return []

        separators = r"[&;,|/]|vs\."
        parts = re.split(separators, artist_string)
        normalized_artists = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            cleaned_part = " ".join(part.split())

            if any(
                x in cleaned_part.lower() for x in ["feat.", "featuring", "ft.", "with", "prod."]
            ):
                normalized_artists.append(cleaned_part)
            else:
                if cleaned_part.isupper():
                    normalized_artists.append(cleaned_part)
                else:
                    normalized_artists.append(cleaned_part.title())

        return [artist for artist in normalized_artists if artist]

    @property
    def image_exists(self) -> bool:
        """Проверяет, существует ли изображение артиста."""
        return bool(self.image_path and os.path.exists(self.image_path))

    def matches(self, search_term: str) -> bool:
        """Проверяет, соответствует ли артист поисковому запросу."""
        search_term = search_term.lower()
        return (
            search_term in self.name.lower()
            or (self.sort_name and search_term in self.sort_name.lower())
            or (self.description and search_term in self.description.lower())
            or (self.aliases and any(search_term in alias.lower() for alias in self.aliases))
            or (self.members and any(search_term in member.lower() for member in self.members))
            or (self.official_website and search_term in self.official_website.lower())
        )

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект Artist в словарь."""
        return {
            "id": self.id,
            "name": self.name,
            "sort_name": self.sort_name,
            "description": self.description,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "aliases": self.aliases or [],
            "image_path": self.image_path,
            "country": self.country,
            "formed_year": self.formed_year,
            "disbanded_year": self.disbanded_year,
            "is_band": self.is_band,
            "members": self.members or [],
            "external_ids": self.external_ids or {},
            "official_website": self.official_website,
            "track_ids": [track.id for track in self.tracks] if self.tracks else [],
            "album_ids": [album.id for album in self.albums] if self.albums else [],
            "genre_ids": [genre.id for genre in self.genres] if self.genres else [],
            "recordlabel_ids": [recordlabel.id for recordlabel in self.recordlabels]
            if self.recordlabels
            else [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artist:
        """Создает объект Artist из словаря."""
        # Обеспечиваем обратную совместимость со старыми CSV-строками в словарях
        aliases = data.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.split(",") if a.strip()]

        members = data.get("members", [])
        if isinstance(members, str):
            members = [m.strip() for m in members.split(",") if m.strip()]

        external_ids = data.get("external_ids", {})
        if isinstance(external_ids, str):
            try:
                external_ids = json.loads(external_ids)
            except json.JSONDecodeError:
                external_ids = {}

        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            sort_name=data.get("sort_name"),
            description=data.get("description"),
            date_added=datetime.datetime.fromisoformat(data["date_added"])
            if data.get("date_added")
            else datetime.datetime.utcnow(),
            date_modified=datetime.datetime.fromisoformat(data["date_modified"])
            if data.get("date_modified")
            else datetime.datetime.utcnow(),
            aliases=aliases,
            image_path=data.get("image_path"),
            country=data.get("country"),
            formed_year=data.get("formed_year"),
            disbanded_year=data.get("disbanded_year"),
            is_band=data.get("is_band", False),
            members=members,
            external_ids=external_ids,
            official_website=data.get("official_website"),
        )

    def __repr__(self) -> str:
        return f"<Artist(name='{self.name}', is_band={self.is_band})>"
