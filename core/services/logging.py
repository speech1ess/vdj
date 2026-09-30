"""
Высокопроизводительный модуль логирования Playlist AI.
Обеспечивает ротацию логов, вывод в stdout и интеграцию с GUI.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

# Константы для настройки логирования
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Определение путей через pathlib
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "data" / "logs"

MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 МБ
BACKUP_COUNT = 5

# Словарь для хранения ссылок на GUI-обработчики (для безопасного удаления)
_gui_handlers: dict[str, logging.Handler] = {}


def setup_logging(
    log_level: int = DEFAULT_LOG_LEVEL,
    log_format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    log_to_console: bool = True,
    log_to_file: bool = True,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    log_filename: str = "playlist_ai.log",
) -> None:
    """
    Настраивает базовую конфигурацию логирования.
    ВНИМАНИЕ: Вызывать строго один раз при старте приложения (точкой входа main.py).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Очищаем существующие обработчики для избежания дублирования логов
    root_logger.handlers.clear()

    formatter = logging.Formatter(log_format, date_format)

    # stdout handler (более производительный, чем stderr для общих логов)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # file handler с ротацией
    if log_to_file:
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)

        log_path = log_dir_path / log_filename

        # RotatingFileHandler выполняет fsync() при ротации.
        # Если потребуется экстремальный throughput, нужно обернуть его в QueueHandler.
        file_handler = RotatingFileHandler(str(log_path), maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger.debug(f"Логирование PlaylistAI инициализировано (Уровень: {logging.getLevelName(log_level)}).")


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Фабрика логгеров.
    Использует внутренний Singleton-кэш модуля logging (нет нужды в самописных словарях).
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger


def add_gui_handler(logger_name: str, callback: Callable[[str], None]) -> None:
    """
    Подключает вывод логов в графический интерфейс.

    ⚠️ АРХИТЕКТУРНОЕ ПРЕДУПРЕЖДЕНИЕ (THREAD SAFETY):
    Коллбэк `callback` ОБЯЗАН быть потокобезопасным! Если логирование вызывается из
    фонового потока (Thread), прямое обновление Tkinter/GUI вызовет Segmentation Fault.
    Используйте queue.Queue на стороне GUI для обработки этих сообщений.
    """

    class GUILogHandler(logging.Handler):
        def __init__(self, callback_func: Callable[[str], None]):
            super().__init__()
            self.callback_func = callback_func

        def emit(self, record: logging.LogRecord):
            try:
                log_message = self.format(record)
                self.callback_func(log_message)
            except Exception:
                self.handleError(record)

    logger = logging.getLogger(logger_name)

    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    gui_handler = GUILogHandler(callback)
    gui_handler.setFormatter(formatter)

    logger.addHandler(gui_handler)
    _gui_handlers[logger_name] = gui_handler


def remove_gui_handler(logger_name: str) -> None:
    """Безопасно отключает GUI-обработчик от указанного логгера."""
    handler = _gui_handlers.pop(logger_name, None)
    if handler:
        logging.getLogger(logger_name).removeHandler(handler)


def set_log_level(level: int | str, logger_name: Optional[str] = None) -> None:
    """Изменяет уровень логирования в runtime."""
    if isinstance(level, str):
        level = getattr(logging, level.upper())

    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    logger.setLevel(level)
    logger.debug(f"Уровень логирования изменен на {logging.getLevelName(level)}")


def create_daily_rotating_file_handler(
    log_dir: str | Path, base_filename: str, formatter: logging.Optional[Formatter] = None
) -> TimedRotatingFileHandler:
    """Фабрика для обработчика с ежедневной ротацией."""
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    log_path = log_dir_path / base_filename
    handler = TimedRotatingFileHandler(str(log_path), when="midnight", interval=1, backupCount=30, encoding="utf-8")

    if formatter is None:
        formatter = logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)

    handler.setFormatter(formatter)
    return handler


def log_exception(logger: logging.Logger, message: str, level: int = logging.ERROR) -> None:
    """
    Оптимизированный хелпер для логирования исключений.
    Использует нативные средства C-интерпретатора (exc_info=True).
    """
    logger.log(level, message, exc_info=True)
