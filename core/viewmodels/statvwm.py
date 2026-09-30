import os
from typing import Any, Optional

from core.database.schema import DatabaseSchema
from core.repositories.stat_rep import StatisticsRepository
from core.viewmodels.basevwm import BaseViewModel


class StatisticsViewModel(BaseViewModel):
    """ViewModel для отображения агрегированной статистики по библиотеке."""

    def __init__(self, configurator, log_callback=None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.stats_repo = StatisticsRepository(self.configurator)
        # Инициализируем схему автономно (без проброса UI-коллбэков)
        self.schema = DatabaseSchema(self.configurator)

    def check_data_source(self) -> tuple[bool, bool]:
        """
        Проверяет доступность источника данных.
        Возвращает: (has_data_source, db_connection_status)
        """
        has_data_source = False
        db_connection_status = False

        db_type = getattr(self.configurator, "db_type", None)

        if db_type == "csv":
            has_data_source = True
            db_connection_status = True

        elif db_type == "sqlite":
            db_path = self.configurator.db_config.get("db_path", "")
            has_data_source = bool(db_path and os.path.exists(db_path))
            db_connection_status = has_data_source

        elif db_type == "postgresql":
            try:
                # Используем интегрированный пулер вместо легаси импортов
                db_connection_status = self.db_manager.check_connection()
                has_data_source = db_connection_status
            except Exception as e:
                self.logger.error(f"Сбой проверки PostgreSQL: {e}")
                db_connection_status = False
                has_data_source = False

        return has_data_source, db_connection_status

    def get_statistics_data(self) -> Optional[dict[str, Any]]:
        """Запрашивает статистику через репозиторий."""
        has_data_source, _ = self.check_data_source()

        if not has_data_source:
            self.logger.info("Источник данных не настроен или недоступен.")
            return None

        # Проверяем целостность структуры таблиц (без UI-хуков внутри)
        if not self.schema.check_schema():
            self.logger.warning("Схема БД неконсистентна. Необходима инициализация БД в настройках.")
            return {"schema_error": True}

        try:
            # На уровне репозиториев (stat_rep.py) мы уже оптимизировали это до 1-2 SQL запросов
            return {
                "bpm_values": self.stats_repo.get_bpm_distribution(),
                "genres": self.stats_repo.get_genre_distribution(),
                "totals": self.stats_repo.get_totals(),
            }
        except Exception as e:
            self.logger.error(f"Сбой при агрегации статистики: {e}", exc_info=True)
            return None
