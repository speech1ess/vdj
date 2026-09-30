from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import and_, inspect, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Integer

from core.database.base import get_all_fields
from core.services.cache import CacheManager
from core.services.config import Configurator
from core.services.logging import get_logger

logger = get_logger("PlaylistAI.Repository.Base")


class _CacheOps:
    """Внутренний хелпер для менеджмента промежуточного кэша при массовом сканировании."""

    PRIMARY_ID = 1
    SECONDARY_ID = 2

    def __init__(self, log_instance, cache_manager: CacheManager):
        self.logger = log_instance
        self.cache = cache_manager

    def get_ids(self, cache: dict[str, Any], model_name: str) -> dict[str, int]:
        original_ids = {}
        for key, obj in cache.items():
            if hasattr(obj, "id") and obj.id is not None:
                original_ids[key] = obj.id
        self.logger.debug(f"Collected original_ids for {model_name}: {original_ids}")
        return original_ids

    def update_cache(
        self,
        cache: dict[str, Any],
        model_name: str,
        id_map: dict[str, int],
        original_ids: dict[str, int],
    ) -> int:
        updated = 0
        cache_name = f"{model_name}_cache"
        for key, obj in cache.items():
            new_id = id_map.get(key)
            if new_id and hasattr(obj, "id") and obj.id != new_id:
                obj.id = new_id
                updated += 1
        self.logger.debug(f"Updated ID in cache {cache_name}: {updated} objects")
        return updated

    def get_new_id(self, old_id: int, original_ids: dict[str, int], id_map: dict[str, int]) -> int:
        for key, oid in original_ids.items():
            if oid == old_id and key in id_map:
                return id_map[key]
        return old_id

    def get_rel_id(self, related_cache_name: str, model_name: str) -> Optional[tuple[str, int]]:
        parts = related_cache_name.replace("_cache", "").split("_")
        if len(parts) < 2:
            self.logger.warning(f"Некорректное имя кэша: {related_cache_name}")
            return None
        first_model, second_model = parts[0], parts[1]
        if model_name == second_model:
            return f"{second_model}_id", self.SECONDARY_ID
        elif model_name == first_model:
            return f"{first_model}_id", self.PRIMARY_ID
        self.logger.warning(f"Модель {model_name} не соответствует кэшу {related_cache_name}")
        return None

    def update_rel_cache(
        self,
        related_cache: dict[Any, Any],
        related_cache_name: str,
        model_name: str,
        id_map: dict[str, int],
        original_ids: dict[str, int],
    ) -> None:
        mapping = self.get_rel_id(related_cache_name, model_name)
        if not mapping:
            return
        field_to_update, position = mapping

        updated_related = {}
        for (id1, id2), related_obj in related_cache.items():
            new_id1, new_id2 = id1, id2
            if position == self.PRIMARY_ID:
                new_id1 = self.get_new_id(id1, original_ids, id_map)
                if new_id1 != id1:
                    setattr(related_obj, field_to_update, new_id1)
            else:
                new_id2 = self.get_new_id(id2, original_ids, id_map)
                if new_id2 != id2:
                    setattr(related_obj, field_to_update, new_id2)
            updated_related[(new_id1, new_id2)] = related_obj

        related_cache.clear()
        related_cache.update(updated_related)
        self.logger.debug(f"Related cache {related_cache_name} updated successfully.")

    def update_rel(
        self,
        related_cache_names: list[str],
        model_name: str,
        id_map: dict[str, int],
        original_ids: dict[str, int],
    ) -> None:
        for related_cache_name in related_cache_names:
            related_cache = getattr(self.cache, related_cache_name, None)
            if not isinstance(related_cache, dict):
                self.logger.error(f"Связанный кэш {related_cache_name} должен быть словарем, получен {type(related_cache)}")
                continue
            self.update_rel_cache(related_cache, related_cache_name, model_name, id_map, original_ids)

    def update_all(self, model_name: str, id_map: dict[str, int]) -> None:
        cache, related_cache_names = self.cache.get_cache(model_name)
        cache_name = f"{model_name}_cache"
        if not isinstance(cache, dict):
            self.logger.error(f"Кэш {cache_name} должен быть словарем, получен {type(cache)}")
            raise ValueError(f"Кэш {cache_name} должен быть словарем")

        original_ids = self.get_ids(cache, model_name)
        self.update_cache(cache, model_name, id_map, original_ids)
        self.update_rel(related_cache_names, model_name, id_map, original_ids)

    def clear(self, model_name: str) -> None:
        cache, _ = self.cache.get_cache(model_name)
        if isinstance(cache, dict):
            cache.clear()
        elif isinstance(cache, list):
            cache[:] = []
        self.logger.debug(f"Кэш {model_name}_cache очищен.")


class BaseRepository:
    """
    Базовый высокопроизводительный класс для всех репозиториев
    (Data Mapper / Repository Pattern).
    """

    PRIMARY_ID = 1
    SECONDARY_ID = 2

    def __init__(
        self,
        configurator: Optional[Configurator] = None,
        cachemanager: Optional[CacheManager] = None,
    ):
        self.logger = get_logger("PlaylistAI.Repository")
        self.configurator = configurator or Configurator()
        self.cache = cachemanager or CacheManager()
        self.cacheops = _CacheOps(self.logger, self.cache)

    def _check_by_key(self, db: Session, model: Any, keys: list[str], key_field: str) -> dict[str, tuple[int, Any]]:
        try:
            if not hasattr(model, key_field):
                self.logger.error(f"Поле {key_field} не существует в модели {model.__name__}")
                raise AttributeError(f"Поле {key_field} не существует в модели {model.__name__}")

            existing_objects = db.query(model).filter(getattr(model, key_field).in_(keys)).all()
            return {getattr(obj, key_field): (obj.id, obj) for obj in existing_objects}

        except Exception as e:
            self.logger.error(f"Ошибка при проверке дубликатов {model.__name__} по полю {key_field}: {e}")
            raise

    def _check_by_composite(self, db: Session, model: Any, keys: list[str], key_field: list[str]) -> dict[str, tuple[int, Any]]:
        try:
            for field in key_field:
                if not hasattr(model, field):
                    self.logger.error(f"Поле {field} не существует в модели {model.__name__}")
                    raise AttributeError(f"Поле {field} не существует в модели {model.__name__}")

            conditions = []
            for key in keys:
                parts = key.split(":")
                if len(parts) != len(key_field):
                    continue

                key_conditions = []
                for field, value in zip(key_field, parts, strict=False):
                    column = getattr(model, field)
                    if isinstance(column.property.columns[0].type, Integer):
                        try:
                            value = int(value)
                        except ValueError:
                            continue
                    key_conditions.append(column == value)

                if len(key_conditions) == len(key_field):
                    conditions.append(and_(*key_conditions))

            if not conditions:
                return {}

            existing_objects = db.query(model).filter(or_(*conditions)).all()
            existing = {}
            for obj in existing_objects:
                key_parts = [str(getattr(obj, field)) for field in key_field]
                key = ":".join(key_parts)
                if key in keys:
                    existing[key] = (obj.id, obj)

            return existing

        except Exception as e:
            self.logger.error(f"Ошибка при проверке композитных дубликатов {model.__name__}: {e}")
            raise

    def _check_exist(self, db: Session, model: Any, keys: list[str], key_field: str | list[str]) -> dict[str, tuple[int, Any]]:
        if not keys:
            return {}
        if isinstance(key_field, str):
            return self._check_by_key(db, model, keys, key_field)
        return self._check_by_composite(db, model, keys, key_field)

    def _save_obj(self, db: Session, obj: Any, key: str) -> Optional[int]:
        """
        Сохранение объекта в сессию без использования тяжеловесного deepcopy.
        Предотвращает утечки памяти и снижает CPU overhead.
        """
        try:
            # Очищаем ID, если объект является новым
            # (не валидируется по системному неймингу классов)
            if hasattr(obj, "id") and not re.match(r"^[A-Z][a-z]+([A-Z][a-z]+)+$", obj.__class__.__name__):
                obj.id = None

            db.add(obj)
            db.flush()  # Выполняем flush для генерации primary key (id) без полного commit

            if hasattr(obj, "id"):
                return obj.id
            return None

        except IntegrityError as e:
            self.logger.error(f"Ошибка целостности при сохранении {obj.__class__.__name__} '{key}': {e}")
            db.rollback()
            raise
        except Exception as e:
            self.logger.error(f"Неизвестная ошибка при сохранении {obj.__class__.__name__} '{key}': {e}")
            raise

    def _save_rel(self, db: Session, obj: Any, key: str) -> Optional[tuple[int, int]]:
        try:
            db.add(obj)
            db.flush()
            mapper = inspect(obj.__class__)
            primary_keys = [col.name for col in mapper.primary_key]
            if len(primary_keys) != 2:
                raise ValueError(f"Ожидалось 2 первичных ключа для связи {obj.__class__.__name__}")
            return tuple(getattr(obj, pk) for pk in primary_keys)
        except IntegrityError as e:
            self.logger.warning(f"Связь {obj.__class__.__name__} уже существует ({key}): {e}")
            db.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении связи {obj.__class__.__name__} '{key}': {e}")
            raise

    def _upd_obj(
        self,
        db: Session,
        obj: Any,
        existing_id: int,
        update_fields: Optional[list[str]] = None,
        exclude_fields: Optional[list[str]] = None,
    ) -> tuple[int, bool]:
        """Оптимизированное обновление объекта через SQLAlchemy Unit of Work."""
        try:
            existing_obj = db.query(obj.__class__).filter_by(id=existing_id).first()
            if not existing_obj:
                raise ValueError(f"Объект {obj.__class__.__name__} с id={existing_id} не найден.")

            updated = False
            all_fields_dict = get_all_fields()
            fields_to_compare = update_fields or all_fields_dict.get(obj.__class__.__name__, [])

            for field in fields_to_compare:
                cache_value = getattr(obj, field, None)
                db_value = getattr(existing_obj, field, None)
                if cache_value != db_value:
                    setattr(existing_obj, field, cache_value)
                    updated = True

            if updated:
                db.flush()

            return existing_id, updated

        except IntegrityError as e:
            self.logger.error(f"Ошибка обновления {obj.__class__.__name__} id={existing_id}: {e}")
            db.rollback()
            raise
        except Exception as e:
            self.logger.error(f"Неизвестная ошибка при обновлении {obj.__class__.__name__} id={existing_id}: {e}")
            raise

    def _save_or_update(
        self,
        db: Session,
        obj: Any,
        key: str,
        existing: dict[str, tuple[int, Any]],
        update_fields: Optional[list[str]] = None,
        exclude_fields: Optional[list[str]] = None,
    ) -> tuple[int, bool]:
        if key in existing:
            existing_id, _ = existing[key]
            return self._upd_obj(db, obj, existing_id, update_fields, exclude_fields)
        return self._save_obj(db, obj, key), False

    def _handle_db_error(self, error: Exception, operation: str, context: str) -> None:
        if isinstance(error, IntegrityError):
            self.logger.error(f"Ошибка целостности при {operation} ({context}): {error}")
            raise error
        self.logger.error(f"Неизвестная ошибка при {operation} ({context}): {error}")
        raise error
