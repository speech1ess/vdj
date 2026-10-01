import multiprocessing
import sys
import tkinter as tk

from core.services.config import Configurator
from core.services.logging import get_logger, setup_logging
from gui.views.mainvw import MainView

# 1. BOOTSTRAP: Поднимаем инфраструктуру строго до инициализации бизнес-логики
setup_logging()
logger = get_logger("PlaylistAI.Main")


def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    """Глобальный перехватчик неконтролируемых исключений (Global Exception Handler)."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Неперехваченное исключение (Uncaught Exception):", exc_info=(exc_type, exc_value, exc_traceback))


# Перехватываем все падения вне try-except блоков
sys.excepthook = handle_unhandled_exception


def run_app() -> None:
    """Оркестратор запуска приложения Playlist AI."""
    logger.info("Инициализация Playlist AI...")

    try:
        configurator = Configurator()
    except Exception as e:
        logger.error(f"Сбой при загрузке конфигурации: {e}", exc_info=True)
        sys.exit(1)

    root = tk.Tk()
    root.title("Playlist AI - Data-Driven Media Manager")
    root.geometry("1024x768")
    root.minsize(800, 600)

    logger.debug("Перед инициализацией графа UI (MainView)")
    try:
        MainView(root=root, config=configurator)
        logger.debug("MainView успешно инициализирован")
    except Exception as e:
        logger.critical(f"Фатальная ошибка при рендеринге MainView: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Вход в Event Loop (Tkinter mainloop).")
    try:
        root.mainloop()
    finally:
        logger.info("Завершение работы приложения (Shutdown).")


if __name__ == "__main__":
    # Защита от рекурсивного создания процессов (Safe Process Spawning) под Windows
    multiprocessing.freeze_support()
    run_app()
