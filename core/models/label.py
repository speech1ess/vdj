from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.album import Album
    from core.models.artist import Artist

import datetime
import re
from typing import Any

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base
from core.models import Album, Artist


class RecordLabel(Base):
    """Модель музыкального лейбла (SQLAlchemy 2.0)."""

    __tablename__ = "recordlabels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Индекс и уникальность обязательны для быстрого lookup'a при импорте
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, default=""
    )

    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    albums_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    # Связи many-to-many
    albums: Mapped[list[Album]] = relationship(
        "Album", secondary="album_recordlabel", back_populates="recordlabels"
    )
    artists: Mapped[list[Artist]] = relationship(
        "Artist", secondary="artist_recordlabel", back_populates="recordlabels"
    )

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект RecordLabel в словарь."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "website": self.website,
            "country": self.country,
            "founded_year": self.founded_year,
            "albums_count": self.albums_count,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "album_ids": [album.id for album in self.albums] if self.albums else [],
            "artist_ids": [artist.id for artist in self.artists] if self.artists else [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordLabel:
        """Создает объект RecordLabel из словаря."""
        date_added = data.get("date_added")
        if isinstance(date_added, str):
            try:
                date_added = datetime.datetime.fromisoformat(date_added)
            except (ValueError, TypeError):
                date_added = datetime.datetime.utcnow()

        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description"),
            website=data.get("website"),
            country=data.get("country"),
            founded_year=data.get("founded_year"),
            albums_count=data.get("albums_count"),
            date_added=date_added,
        )

    # УДАЛЕНО: Метод get_by_id.
    # Причина: Модель ORM (Data Mapper) не должна выполнять запросы к БД.
    # Эта ответственность переносится в слой Repositories (core/repositories/label_rep.py)

    @staticmethod
    def normalize_label_name(recordlabel_string: str) -> str:
        """
        Нормализует название лейбла, удаляя суффиксы (Ltd., Records) и годы.
        TODO: Вынести эту CPU-bound логику в слой Services перед сохранением в БД.
        """
        if not recordlabel_string or not isinstance(recordlabel_string, str):
            return ""

        cleaned_recordlabel = recordlabel_string.strip()

        suffixes = [
            r"\bltd\.?\b",
            r"\brec\.?\b",
            r"\brecords\b",
            r"\brecordings\b",
            r"\binc\.?\b",
            r"\bcorp\.?\b",
            r"\bcompany\b",
            r"\bco\.?\b",
            r"\bgroup\b",
            r"\b\d{4}\b",
        ]
        for suffix in suffixes:
            cleaned_recordlabel = re.sub(
                suffix, "", cleaned_recordlabel, flags=re.IGNORECASE
            ).strip()

        cleaned_recordlabel = " ".join(cleaned_recordlabel.split())

        if cleaned_recordlabel and not cleaned_recordlabel.isupper():
            cleaned_recordlabel = cleaned_recordlabel.title()

        return cleaned_recordlabel or ""

    def __repr__(self) -> str:
        return f"<RecordLabel(name='{self.name}', country='{self.country}')>"
