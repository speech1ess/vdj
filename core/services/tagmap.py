from pathlib import Path
from typing import Any

import yaml

from core.database import base as models
from core.services.logging import get_logger

Base = models.Base
TAGMAP_PATH = Path(__file__).parent / "tagmap.yaml"


class TagMapper:
    """
    Высокопроизводительный Data-Driven слой для маппинга ID3/Vorbis тегов
    в поля ORM моделей. Оптимизирован с использованием обратных индексов O(1).
    """

    def __init__(self, tagmap_path: Path = TAGMAP_PATH) -> None:
        self.logger = get_logger("PlaylistAI.TagMapper")

        try:
            with open(tagmap_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.logger.critical(f"❌ Не удалось загрузить {tagmap_path}: {e}")
            config = {}

        self.unified_tags: dict[str, list[str]] = config.get("UNIFIED_TAGS", {})
        self.models_to_tag: dict[str, dict[str, str]] = config.get("MODELS_TO_TAG", {})

        # Прямой индекс: Тег -> Поле БД
        self.tag_to_field: dict[str, str] = {
            tag.upper(): field for field, aliases in self.unified_tags.items() for tag in aliases
        }

        # Обратный индекс: Поле БД -> Список Тегов (Оптимизация O(1) Lookup)
        self.field_to_tags: dict[str, list[str]] = {}
        for field, aliases in self.unified_tags.items():
            self.field_to_tags[field] = [tag.upper() for tag in aliases]

    def get_supported_tags(self) -> list[str]:
        """Возвращает список всех унифицированных полей."""
        return sorted(self.unified_tags.keys())

    def get_model_fields(self, model_name: str) -> list[str]:
        """Возвращает список полей, явно прописанных для модели в MODELS_TO_TAG."""
        return list(self.models_to_tag.get(model_name, {}).keys())

    def map_req_tags(self) -> dict[str, list[str]]:
        """Сопоставляет обязательные (Required) поля ORM моделей с ID3 тегами."""
        return self._map_fields_to_tags(Base.get_required_fields())

    def map_all_tags(self) -> dict[str, list[str]]:
        """Сопоставляет все (All) поля ORM моделей с ID3 тегами."""
        return self._map_fields_to_tags(Base.get_all_fields())

    def _map_fields_to_tags(self, model_field_map: dict[str, list[str]]) -> dict[str, list[str]]:
        """
        Молниеносный маппер O(N) вместо старого O(N*M).
        Использует предварительно вычисленный обратный индекс field_to_tags.
        """
        result = {}
        for model, fields in model_field_map.items():
            tags = []
            model_mapping = self.models_to_tag.get(model, {})

            for field in fields:
                # 1. Сначала ищем жесткий маппинг модели
                if field in model_mapping:
                    tags.append(model_mapping[field])
                    continue

                # 2. Ищем прямое совпадение с унифицированным полем
                if field in self.unified_tags:
                    tags.append(field)
                    continue

                # 3. Ищем через обратный индекс за O(1)
                if field in self.field_to_tags:
                    tags.extend(self.field_to_tags[field])
                else:
                    # Поле существует в БД, но для него нет маппинга тегов
                    # Это нормально для суррогатных ключей (id) и системных полей.
                    pass

            result[model] = sorted(list(set(tags)))

        return result


class TagEvaluator:
    """Оценщик покрытия метаданных (Coverage Analytics)."""

    def __init__(self, tag_mapper: TagMapper) -> None:
        self.mapper = tag_mapper

    def evaluate(
        self, metadata: dict[str, Any], required_fields: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Оценивает наличие требуемых ключей в словаре метаданных."""
        # Убрана избыточная проверка isinstance(metadata, dict). Мы доверяем своему коду.
        return {
            field: {"present": metadata.get(field) is not None, "value": metadata.get(field)}
            for field in required_fields
        }

    def get_coverage_by_model(self, metadata: dict[str, Any], model_name: str) -> dict[str, Any]:
        """
        Вычисляет статистику покрытия обязательных полей для конкретной ORM модели.
        """
        fields = self.mapper.get_model_fields(model_name)
        model_mapping = self.mapper.models_to_tag.get(model_name, {})

        # Получаем только теги, которые реально привязаны
        tags = [model_mapping.get(field) for field in fields if model_mapping.get(field)]

        evaluations = self.evaluate(metadata, tags)
        total = len(tags)
        present = sum(1 for info in evaluations.values() if info["present"])

        return {
            "model": model_name,
            "coverage": round(present / total, 2) if total > 0 else 1.0,
            "present_fields": [f for f, info in evaluations.items() if info["present"]],
            "missing_fields": [f for f, info in evaluations.items() if not info["present"]],
        }

    def get_coverage_report_all_models(self, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Генерирует сводный отчет покрытия по всем моделям базы данных."""
        return [
            self.get_coverage_by_model(metadata, model)
            for model in self.mapper.map_req_tags().keys()
        ]
