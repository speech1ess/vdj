from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase

from core.services.logging import get_logger

logger = get_logger("PlaylistAI.Database")


# ==========================================
# 1. Единый базовый класс SQLAlchemy 2.0
# ==========================================
class Base(DeclarativeBase):
    """Фундаментальный класс для всех ORM моделей (SQLAlchemy 2.0)."""

    pass


# ==========================================
# 2. Вспомогательные функции
# ==========================================
def to_dict_base(obj: Any, exclude: list[str] = None) -> dict[str, Any]:
    """Базовая функция для сериализации объекта SQLAlchemy в словарь."""
    exclude = exclude or []
    result = {}
    for column in obj.__table__.columns:
        if column.name not in exclude:
            value = getattr(obj, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
    return result


# ==========================================
# 3. Кешированная инспекция схемы БД
# ==========================================
# Используем lru_cache, чтобы инспекция ORM выполнялась строго 1 раз.
# Это экономит такты CPU и снижает latency при частых вызовах.
@lru_cache(maxsize=1)
def get_required_fields() -> dict[str, list[str]]:
    """
    Извлекает обязательные поля из всех моделей (nullable=False).
    Результат кешируется в RAM.
    """
    logger.debug("Выполняется тяжелая инспекция ORM: get_required_fields (вызвано 1 раз)")
    required_fields = {}

    excluded_fields = {"id", "created_at", "modified_at", "date_added", "date_modified", "user_id"}
    excluded_models = {
        "Playlist",
        "Tag",
        "User",
        "UserPlaylist",
        "TrackTag",
        "UserTrack",
        "TrackPlaylist",
    }

    model_names: set[str] = set()
    for mapper in Base.registry.mappers:
        model_name = mapper.class_.__name__
        if model_name not in excluded_models:
            model_names.add(model_name)

    for mapper in Base.registry.mappers:
        model = mapper.class_
        model_name = model.__name__

        if model_name in excluded_models:
            continue

        # Проверяем, является ли таблица ассоциативной связкой
        is_relation = any(
            model_name == f"{m1}{m2}" or model_name == f"{m2}{m1}"
            for m1 in model_names
            for m2 in model_names
            if m1 != m2
        )

        if is_relation:
            model_names.discard(model_name)
            continue

        required_fields[model_name] = []
        for column in inspect(model).columns:
            if column.name not in excluded_fields and (
                not column.nullable or not column.autoincrement
            ):
                required_fields[model_name].append(column.name)

    return {k: v for k, v in required_fields.items() if v}


@lru_cache(maxsize=1)
def get_all_fields() -> dict[str, list[str]]:
    """
    Извлекает все поля из всех моделей, исключая системные.
    Результат кешируется в RAM.
    """
    logger.debug("Выполняется тяжелая инспекция ORM: get_all_fields (вызвано 1 раз)")
    all_fields = {}

    excluded_fields = {
        "id",
        "created_at",
        "modified_at",
        "date_added",
        "date_modified",
        "user_id",
        "albums_count",
        "rating",
        "play_count",
        "audiofile_id",
        "description",
        "parent_id",
        "is_composite",
        "aliases",
        "sort_name",
        "contains_multiple_tracks",
        "is_band",
        "external_ids",
    }
    excluded_models = {
        "Playlist",
        "Tag",
        "User",
        "UserPlaylist",
        "TrackTag",
        "UserTrack",
        "TrackPlaylist",
    }

    model_names: set[str] = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if mapper.class_.__name__ not in excluded_models
    }

    for mapper in Base.registry.mappers:
        model = mapper.class_
        model_name = model.__name__

        if model_name in excluded_models:
            continue

        is_relation = any(
            model_name == f"{m1}{m2}" or model_name == f"{m2}{m1}"
            for m1 in model_names
            for m2 in model_names
            if m1 != m2
        )

        if is_relation:
            continue

        all_fields[model_name] = []
        for column in inspect(model).columns:
            if column.name not in excluded_fields:
                all_fields[model_name].append(column.name)

    return {k: v for k, v in all_fields.items() if v}


# Привязываем методы к классу Base
Base.get_required_fields = staticmethod(get_required_fields)
Base.get_all_fields = staticmethod(get_all_fields)
