from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.models.playlist import Playlist
    from core.models.track import Track

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class User(Base):
    """Модель пользователя (SQLAlchemy 2.0)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Unique constraint автоматом создает индекс, но явное указание index=True - хороший тон
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    # Критично для SaaS: быстрый поиск при авторизации
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)

    date_added: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    # ==========================================
    # ВНИМАНИЕ: Связи синхронизированы с новой архитектурой
    # ==========================================

    # 1. Плейлисты, которыми единолично владеет пользователь (One-to-Many)
    owned_playlists: Mapped[list[Playlist]] = relationship("Playlist", foreign_keys="[Playlist.user_id]", back_populates="owner")

    # 2. Плейлисты, к которым у пользователя есть доступ как у соавтора (Many-to-Many)
    shared_playlists: Mapped[list[Playlist]] = relationship("Playlist", secondary="user_playlist", back_populates="collaborators")

    # 3. Избранные треки
    favorites: Mapped[list[Track]] = relationship("Track", secondary="user_track", back_populates="favorited_by")

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект в словарь (DTS)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "date_added": self.date_added.isoformat() if self.date_added else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        """Создает объект из словаря."""
        date_added = data.get("date_added")
        if isinstance(date_added, str):
            try:
                date_added = datetime.datetime.fromisoformat(date_added)
            except (ValueError, TypeError):
                date_added = datetime.datetime.utcnow()

        return cls(
            id=data.get("id"),
            username=data.get("username", ""),
            email=data.get("email"),
            date_added=date_added,
        )

    def __repr__(self) -> str:
        return f"<User(username='{self.username}')>"
