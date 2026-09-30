from collections.abc import Callable
from typing import Optional

from core.viewmodels.basevwm import BaseViewModel
from core.viewmodels.managervwm import ManagerViewModel
from core.viewmodels.playlistvwm import PlaylistViewModel
from core.viewmodels.scanvwm import ScanViewModel
from core.viewmodels.statvwm import StatisticsViewModel


class MainViewModel(BaseViewModel):
    """
    Главный оркестратор состояний (State Router) для UI.
    ВНИМАНИЕ: Не содержит импортов tkinter. Управляет только потоком данных.
    """

    def __init__(self, configurator, log_callback: Optional[Callable] = None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.current_view_name = "statistics"

    def get_view_model_for(self, view_name: str) -> BaseViewModel:
        """Фабрика: возвращает нужную ViewModel для запрошенного экрана."""
        if view_name == "statistics":
            stats_vm = StatisticsViewModel(self.configurator)
            # Если база сломана, принудительно переключаем на настройки
            has_data, _ = stats_vm.check_data_source()
            if not has_data:
                self.set_status("⚠️ БД недоступна. Требуется настройка.")
                self.current_view_name = "configurator"
                from core.viewmodels.confvwm import ConfiguratorViewModel

                return ConfiguratorViewModel(self.configurator)
            return stats_vm

        elif view_name == "configurator":
            from core.viewmodels.confvwm import ConfiguratorViewModel

            return ConfiguratorViewModel(self.configurator)

        elif view_name == "scanner":
            return ScanViewModel(self.configurator)

        elif view_name == "manager":
            return ManagerViewModel(self.configurator)

        elif view_name == "playlists":
            return PlaylistViewModel(self.configurator)

        else:
            self.logger.warning(f"Запрошена неизвестная ViewModel: {view_name}")
            return None

    def set_directory(self, directory: str):
        if directory:
            self.logger.info(f"Выбран каталог: {directory}")
            # Предполагаем, что set_scan_directory есть в Configurator
            if hasattr(self.configurator, "set_scan_directory"):
                self.configurator.set_scan_directory(directory)

    def get_db_status_color(self) -> str:
        """Возвращает цвет индикатора состояния БД для статус-бара."""
        db_type = self.configurator.db_type
        if db_type == "csv":
            return "green"
        elif db_type == "sqlite":
            import os

            db_path = self.configurator.db_config.get("db_path", "")
            return "green" if db_path and os.path.exists(db_path) else "red"
        elif db_type == "postgresql":
            # Используем встроенный метод пула
            return "green" if self.db_manager.check_connection() else "red"
        return "gray"

    def test_database_connection(self):
        if self.db_manager.check_connection():
            self.set_status("✅ Соединение с БД успешно")
        else:
            self.set_status("❌ Ошибка соединения с БД")
