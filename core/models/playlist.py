from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.track import Track
    from core.models.user import User

import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base


class Playlist(Base):
    """Модель плейлиста (SQLAlchemy 2.0)."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Индекс обязателен для поиска плейлистов по имени
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="New Playlist", index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Архитектурное исправление: если есть user_id, это ДОЛЖЕН быть ForeignKey.
    # Если плейлист системный/глобальный, nullable=True спасет ситуацию.
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Параметры для DJ
    min_bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    key: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # Расширил до 10 на случай сложных ключей
    energy_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)
    transition_style: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mixing_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Метаданные (Агрегированные кэши)
    popularity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dj_notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Связи
    tracks: Mapped[list[Track]] = relationship(
        "Track", secondary="track_playlist", back_populates="playlists"
    )

    # Прямая связь с владельцем плейлиста (One-to-Many)
    owner: Mapped[Optional[User]] = relationship(
        "User", foreign_keys=[user_id], back_populates="owned_playlists"
    )

    # Связь с соавторами/подписчиками (Many-to-Many)
    collaborators: Mapped[list[User]] = relationship(
        "User", secondary="user_playlist", back_populates="shared_playlists"
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Преобразует объект в словарь.
        ВНИМАНИЕ: Если tracks не загружены жадно (joinedload), это вызовет N+1 запросы!
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "user_id": self.user_id,
            "min_bpm": self.min_bpm,
            "max_bpm": self.max_bpm,
            "key": self.key,
            "energy_level": self.energy_level,
            "mood": self.mood,
            "auto_update": self.auto_update,
            "transition_style": self.transition_style,
            "mixing_preference": self.mixing_preference,
            "popularity_score": self.popularity_score,
            "avg_bpm": self.avg_bpm,
            "avg_duration": self.avg_duration,
            "dj_notes": self.dj_notes,
            # Оставил для обратной совместимости,
            # но в будущем лучше перенести сериализацию в Pydantic/Слой API
            "track_ids": [track.id for track in self.tracks] if self.tracks else [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Playlist:
        """Создает объект Playlist из словаря."""
        return cls(
            id=data.get("id"),
            name=data.get("name", "New Playlist"),
            description=data.get("description"),
            created_at=datetime.datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.datetime.utcnow(),
            modified_at=datetime.datetime.fromisoformat(data["modified_at"])
            if data.get("modified_at")
            else datetime.datetime.utcnow(),
            user_id=data.get("user_id"),
            min_bpm=data.get("min_bpm"),
            max_bpm=data.get("max_bpm"),
            key=data.get("key"),
            energy_level=data.get("energy_level"),
            mood=data.get("mood"),
            auto_update=data.get("auto_update", False),
            transition_style=data.get("transition_style"),
            mixing_preference=data.get("mixing_preference"),
            popularity_score=data.get("popularity_score"),
            avg_bpm=data.get("avg_bpm"),
            avg_duration=data.get("avg_duration"),
            dj_notes=data.get("dj_notes"),
        )

    # УДАЛЕНО: get_by_id(cls, session, playlist_id)
    # Причина: Паттерн Repository. Модель не должна ничего знать о сессии БД.

    def add_track(self, track: Track) -> None:
        """Добавляет трек в плейлист (только в памяти!). Коммит делает сервисный слой."""
        if track not in self.tracks:
            self.tracks.append(track)
            self.modified_at = datetime.datetime.utcnow()

    def remove_track(self, track: Track) -> None:
        """Удаляет трек из плейлиста (только в памяти!). Коммит делает сервисный слой."""
        if track in self.tracks:
            self.tracks.remove(track)
            self.modified_at = datetime.datetime.utcnow()

    def update_metadata(self) -> None:
        """Обновляет метаданные плейлиста (только в памяти!)."""
        if self.tracks:
            self.avg_bpm = sum(track.bpm or 0.0 for track in self.tracks) / len(self.tracks)
            self.avg_duration = sum(track.duration or 0 for track in self.tracks) // len(
                self.tracks
            )
        else:
            self.avg_bpm = None
            self.avg_duration = None
        self.modified_at = datetime.datetime.utcnow()

    def __repr__(self) -> str:
        return f"<Playlist(name='{self.name}', user_id={self.user_id})>"
