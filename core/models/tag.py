from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.track import Track

import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class Tag(Base):
    """Модель тега для треков (SQLAlchemy 2.0)."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Индекс обязателен для быстрых фильтраций и сопоставления тегов при поиске
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    # Связь с треками (Many-to-Many)
    tracks: Mapped[list[Track]] = relationship(
        "Track", secondary="track_tag", back_populates="tags"
    )

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект Tag в словарь."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "date_added": self.date_added.isoformat() if self.date_added else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tag:
        """Создает объект Tag из словаря."""
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
            date_added=date_added,
        )

    def __repr__(self) -> str:
        return f"<Tag(name='{self.name}')>"
