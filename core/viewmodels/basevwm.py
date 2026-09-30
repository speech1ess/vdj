from __future__ import annotations

import threading
from collections.abc import Callable

from core.database.connmgr import ConnectionManager
from core.services.config import Configurator
from core.services.logging import add_gui_handler, get_logger, remove_gui_handler


class BaseViewModel:
    """
    Базовый класс ViewModel (MVVM).
    Обеспечивает связь между View (UI) и бизнес-логикой (Сервисами/БД) без жесткой связности.
    """

    def __init__(self, configurator: Configurator, log_callback: Optional[Callable[[str], None]] = None):
        self.logger = get_logger("PlaylistAI.ViewModel")
        self.configurator = configurator
        self.db_manager = ConnectionManager(self.configurator)
        self.status_message = ""
        self.thread_lock = threading.Lock()

        self.log_callback = None
        if log_callback:
            self.attach_log_callback(log_callback)

    def attach_log_callback(self, log_callback: Callable[[str], None]) -> None:
        """Безопасная привязка GUI-коллбэка с предотвращением утечек памяти."""
        # Сначала удаляем старый хендлер, если он был, чтобы избежать дублирования
        remove_gui_handler("PlaylistAI")
        add_gui_handler("PlaylistAI", log_callback)
        self.log_callback = log_callback

    def detach_log_callback(self) -> None:
        """Обязательно вызывать при уничтожении View, чтобы не было утечек."""
        remove_gui_handler("PlaylistAI")
        self.log_callback = None

    def set_status(self, message: str) -> None:
        """Обновляет статус для UI и параллельно пишет в системный лог."""
        with self.thread_lock:
            self.status_message = message
        self.logger.info(f"UI Status: {message}")

        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception as e:
                self.logger.error(f"Ошибка вызова UI коллбэка: {e}")

    def get_db_session(self):
        """Возвращает сессию для работы с БД."""
        return self.db_manager.get_session()
