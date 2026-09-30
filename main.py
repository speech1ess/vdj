import sys
import tkinter as tk
from concurrent.futures import ProcessPoolExecutor

from core.services.config import Configurator
from core.services.logging import get_logger
from gui.views.mainvw import MainView

logger = get_logger("PlaylistAI.Main")


def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    """Глобальный перехватчик неконтролируемых исключений."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА:", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_unhandled_exception


def run_app() -> None:
    """Запускает приложение Playlist AI."""
    logger.info("Инициализация Playlist AI...")

    process_pool = ProcessPoolExecutor()

    try:
        configurator = Configurator()
    except Exception as e:
        logger.error(f"Сбой при загрузке конфигурации: {e}")
        sys.exit(1)

    root = tk.Tk()
    root.title("Playlist AI - Media Manager")
    root.geometry("1024x768")
    root.minsize(800, 600)

    print("DEBUG: Перед инициализацией MainView", flush=True)
    try:
        MainView(root=root, config=configurator)
        print("DEBUG: MainView успешно инициализирован", flush=True)
    except Exception:
        import traceback

        print("CRITICAL EXCEPTION IN MAINVIEW:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    logger.info("Запуск UI цикла (mainloop).")
    try:
        root.mainloop()
    finally:
        print("DEBUG: Выход из mainloop, завершение...", flush=True)
        logger.info("Завершение работы приложения. Остановка пула процессов...")
        process_pool.shutdown(wait=True)


if __name__ == "__main__":
    run_app()
