from collections.abc import Callable
from typing import Any, Optional

from core.database.schema import DatabaseSchema
from core.services.config import Configurator
from core.viewmodels.basevwm import BaseViewModel


class ConfiguratorViewModel(BaseViewModel):
    """ViewModel для изоляции логики экрана настроек (Settings View)."""

    def __init__(self, configurator: Configurator, log_callback: Optional[Callable[[str], None]] = None):
        # Исправлено сломанное наследование: передаем configurator в родителя
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.schema_manager = DatabaseSchema(self.configurator)

    def get_db_types(self) -> list[str]:
        """Возвращает список доступных типов БД из конфигуратора."""
        return list(self.configurator.DB_TYPES.keys())

    def set_db_type(self, db_type: str) -> None:
        """Устанавливает тип базы данных."""
        try:
            self.configurator.set_db_type(db_type)
            self.set_status(f"Выбран тип БД: {db_type}")
        except ValueError as e:
            self.set_status(f"Ошибка выбора БД: {e}")

    def test_connection(self) -> None:
        """Тестирует соединение с БД (использует пул из ConnectionManager)."""
        try:
            # check_connection теперь встроен в ConnectionManager
            success = self.db_manager.check_connection()
            if success:
                self.set_status("✅ Соединение с БД успешно установлено!")
            else:
                self.set_status("❌ Ошибка: БД недоступна.")
        except Exception as e:
            self.set_status(f"⚠️ Ошибка проверки соединения: {e}")

    def create_database(self) -> None:
        """Создаёт структуру таблиц в соответствии с текущей конфигурацией."""
        try:
            # Слой БД больше не принимает GUI-коллбэки. Он автономен.
            self.schema_manager.create_schema()
            self.set_status("✅ База данных успешно инициализирована (таблицы созданы)!")
        except Exception as e:
            self.set_status(f"⚠️ Критическая ошибка при создании БД: {e}")

    def drop_database(self) -> None:
        """Опасная зона: Удаляет всю структуру БД."""
        try:
            self.schema_manager.drop_schema()
            self.set_status("⚠️ Внимание: Все таблицы и данные успешно удалены из БД!")
        except Exception as e:
            self.set_status(f"❌ Ошибка при удалении БД: {e}")

    def set_output_dir(self, directory: str) -> None:
        """Устанавливает путь для выходных данных."""
        if directory:
            try:
                self.configurator.set_output_dir(directory)
                self.set_status(f"Выбрана рабочая директория: {directory}")
            except ValueError as e:
                self.set_status(str(e))

    def set_sql_scripts_dir(self, directory: str) -> None:
        """Устанавливает путь для пользовательских SQL-скриптов."""
        if directory:
            try:
                self.configurator.set_sql_scripts_dir(directory)
                self.set_status(f"Выбрана директория SQL-скриптов: {directory}")
            except ValueError as e:
                self.set_status(str(e))

    def get_current_config(self) -> dict[str, Any]:
        """Возвращает текущую конфигурацию для отображения в View."""
        return self.configurator.get_config()
