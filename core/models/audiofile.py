from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.models.track import Track
    from core.models.track_relations import TrackAudioFile

import datetime
import os
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base
from core.models.enums import AudioFormat


class AudioFile(Base):
    """Модель данных для аудиофайла (SQLAlchemy 2.0)."""

    __tablename__ = "audiofiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Индекс обязателен, так как мы будем часто искать файлы по пути при сканировании
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)

    # Храним формат как строку (enum value) для простоты и совместимости с БД
    file_format: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bit_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Расширяем длину, если в будущем перейдем с MD5 на SHA-256 (64 символа)
    file_hash: Mapped[str] = mapped_column(
        "hash", String(64), nullable=False, unique=True, index=True
    )

    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    date_modified: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    channels: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    bit_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=16)

    contains_multiple_tracks: Mapped[bool] = mapped_column(Boolean, default=False)
    cue_sheet_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Связь "один ко многим" с Track
    tracks: Mapped[list[Track]] = relationship(
        "Track",
        back_populates="audiofile",
        foreign_keys="[Track.audiofile_id]",
        cascade="all, delete-orphan",
    )

    # Связь через промежуточную таблицу TrackAudioFile
    track_links: Mapped[list[TrackAudioFile]] = relationship(
        "TrackAudioFile", back_populates="audiofile", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs: Any) -> None:
        """
        Инициализация.
        ВНИМАНИЕ: Никакого дискового I/O (os.path.*) здесь быть не должно!
        Эти данные собирает слой Services (Scanner) и передает сюда уже готовыми.
        """
        # Преобразование Enum в строку, если передан объект AudioFormat
        if "file_format" in kwargs and isinstance(kwargs["file_format"], AudioFormat):
            kwargs["file_format"] = kwargs["file_format"].value

        super().__init__(**kwargs)

    @property
    def filename(self) -> str:
        """Возвращает имя файла без пути."""
        return os.path.basename(self.file_path) if self.file_path else ""

    @property
    def directory(self) -> str:
        """Возвращает директорию файла."""
        return os.path.dirname(self.file_path) if self.file_path else ""

    @property
    def size_formatted(self) -> str:
        """Возвращает размер файла в человекочитаемом формате."""
        if not self.file_size:
            return "Unknown"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(self.file_size)
        unit_index = 0
        while size >= 1024.0 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    @property
    def bit_rate_formatted(self) -> str:
        """Возвращает битрейт в человекочитаемом формате."""
        if not self.bit_rate:
            return "Unknown"
        if self.bit_rate >= 1000000:
            return f"{self.bit_rate / 1000000:.2f} Mbps"
        elif self.bit_rate >= 1000:
            return f"{self.bit_rate / 1000:.0f} kbps"
        return f"{self.bit_rate} bps"

    def to_dict(self) -> dict[str, Any]:
        """Преобразует объект AudioFile в словарь."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_format": self.file_format,
            "file_size": self.file_size,
            "bit_rate": self.bit_rate,
            "sample_rate": self.sample_rate,
            "hash": self.file_hash,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "contains_multiple_tracks": self.contains_multiple_tracks,
            "cue_sheet_path": self.cue_sheet_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioFile:
        """Создает объект AudioFile из словаря."""
        file_format = data.get("file_format")
        if isinstance(file_format, AudioFormat):
            file_format = file_format.value

        return cls(
            file_path=data.get("file_path", ""),
            file_format=file_format,
            file_size=data.get("file_size", 0),
            bit_rate=data.get("bit_rate", 0),
            sample_rate=data.get("sample_rate", 0),
            file_hash=data.get("hash", ""),
            date_added=datetime.datetime.fromisoformat(data["date_added"])
            if data.get("date_added")
            else datetime.datetime.utcnow(),
            date_modified=datetime.datetime.fromisoformat(data["date_modified"])
            if data.get("date_modified")
            else None,
            channels=data.get("channels", 2),
            bit_depth=data.get("bit_depth", 16),
            contains_multiple_tracks=data.get("contains_multiple_tracks", False),
            cue_sheet_path=data.get("cue_sheet_path"),
        )

    def __repr__(self) -> str:
        return f"<AudioFile(path='{self.filename}', format='{self.file_format}')>"
