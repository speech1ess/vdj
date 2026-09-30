from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.album import Album
    from core.models.artist import Artist
    from core.models.track import Track

import datetime
import re
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from core.database.base import Base
from core.database.db_config import MODIFIERS


class Genre(Base):
    """Модель жанра музыки (SQLAlchemy 2.0)."""

    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    date_added: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("genres.id"), nullable=True, index=True)

    # Переводим алиасы на нативный JSON, сохраняя обратную совместимость с CSV
    aliases: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    is_composite: Mapped[bool] = mapped_column(Boolean, default=False)

    # Связи many-to-many
    tracks: Mapped[list[Track]] = relationship("Track", secondary="track_genre", back_populates="genres")
    artists: Mapped[list[Artist]] = relationship("Artist", secondary="artist_genre", back_populates="genres")
    albums: Mapped[list[Album]] = relationship("Album", secondary="album_genre", back_populates="genres")

    # Родительская/дочерняя связь для поджанров
    subgenres: Mapped[list[Genre]] = relationship("Genre", backref="parent", remote_side=[id])

    def __init__(self, **kwargs: Any) -> None:
        if "aliases" in kwargs and isinstance(kwargs["aliases"], str):
            kwargs["aliases"] = [a.strip() for a in kwargs["aliases"].split(",") if a.strip()]
        super().__init__(**kwargs)

    @staticmethod
    def normalize_genre_name(name: str) -> list[str]:
        """
        Нормализует название жанра и возвращает список отдельных жанров.
        Разделяет по , / & | ; и капитализирует составные части.
        """
        if not name:
            return []
        parts = re.split(r"[,/&|;]", name)
        normalized_genres = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.isupper():
                normalized_genres.append(part)
                continue
            subparts = re.split(r"([- ]+)", part)
            normalized_part = []
            i = 0
            while i < len(subparts):
                sp = subparts[i].strip()
                if sp:
                    if sp.lower() == "n" and i > 0 and i < len(subparts) - 1 and subparts[i - 1] and subparts[i + 1]:
                        normalized_part.append("n")
                    else:
                        normalized_part.append(sp.capitalize() if sp else sp)
                if i + 1 < len(subparts):
                    separator = subparts[i + 1]
                    normalized_part.append(separator)
                i += 2 if i + 1 < len(subparts) else 1
            normalized_genres.append("".join(normalized_part))

        return [genre for genre in normalized_genres if genre]

    @staticmethod
    def enhance_genre_name(name: str, session: Optional[Session] = None) -> list[tuple[str, Optional[str]]]:
        if not name:
            return []
        if not session:
            return [(name.strip(), None)]

        name_clean = name.strip()
        name_lower = name_clean.lower().replace(" ", "")

        genres = session.query(Genre).all()
        for genre in genres:
            genre_aliases = [a.strip().lower().replace(" ", "") for a in (genre.aliases or [])]
            if name_lower == genre.name.lower().replace(" ", "") or name_lower in genre_aliases:
                return [(genre.name, None)]

        def detect_parent(genre_str: str) -> tuple[str, Optional[str]]:
            genre_lower = genre_str.lower()
            parts = re.split(r"[- ]+", genre_lower)
            base_genres = {g.name.lower() for g in genres if not g.parent_id}
            modifiers = set(MODIFIERS)

            if len(parts) == 1:
                return genre_str, None

            for base in base_genres:
                if base in genre_lower:
                    if any(m in genre_lower for m in modifiers) or len(parts) > 1:
                        canonical_base = next(g.name for g in genres if g.name.lower() == base)
                        return genre_str, canonical_base
            return genre_str, None

        parts = re.split(r"[,/|;]", name_clean)
        enhanced_genres = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            part_lower = part.lower().replace(" ", "")
            for genre in genres:
                genre_aliases = [a.strip().lower().replace(" ", "") for a in (genre.aliases or [])]
                if part_lower == genre.name.lower().replace(" ", "") or part_lower in genre_aliases:
                    enhanced_genres.append((genre.name, None))
                    break
            else:
                if "&" in part:
                    is_composite = any(part_lower == g.name.lower().replace(" ", "") and g.is_composite for g in genres)
                    if is_composite:
                        enhanced_genres.append(detect_parent(part))
                    else:
                        subparts = re.split(r"[&]", part)
                        for sp in subparts:
                            sp = sp.strip()
                            if sp:
                                enhanced_genres.append(detect_parent(sp))
                else:
                    enhanced_genres.append(detect_parent(part))

        return enhanced_genres

    def is_subgenre_of(self, parent_genre_id: int) -> bool:
        return self.parent_id == parent_genre_id

    def matches(self, search_term: str) -> bool:
        search_term = search_term.lower()
        aliases_list = self.aliases or []
        return (
            search_term in self.name.lower()
            or (self.description and search_term in self.description.lower())
            or any(search_term in alias.lower() for alias in aliases_list)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "parent_id": self.parent_id,
            "aliases": self.aliases or [],
            "is_composite": self.is_composite,
            "track_ids": [track.id for track in self.tracks] if self.tracks else [],
            "artist_ids": [artist.id for artist in self.artists] if self.artists else [],
            "album_ids": [album.id for album in self.albums] if self.albums else [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Genre:
        aliases = data.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.split(",") if a.strip()]

        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description"),
            date_added=datetime.datetime.fromisoformat(data["date_added"]) if data.get("date_added") else datetime.datetime.utcnow(),
            parent_id=data.get("parent_id"),
            aliases=aliases,
            is_composite=data.get("is_composite", False),
        )

    def __eq__(self, other: Any) -> bool:
        """Сравнивает жанры по имени или алиасам (без учета регистра)."""
        if not isinstance(other, Genre):
            return False
        self_lower = self.name.lower().replace(" ", "")
        other_lower = other.name.lower().replace(" ", "")
        self_aliases = [a.strip().lower().replace(" ", "") for a in (self.aliases or [])]
        other_aliases = [a.strip().lower().replace(" ", "") for a in (other.aliases or [])]
        return (
            self_lower == other_lower or self_lower in other_aliases or other_lower in self_aliases or any(a in other_aliases for a in self_aliases)
        )

    def __hash__(self) -> int:
        return hash(self.name.lower())

    def __repr__(self) -> str:
        return f"<Genre(name='{self.name}', is_composite={self.is_composite})>"
