"""
Модуль управления конфигурацией Playlist AI.
Оптимизирован для высокой надежности (Atomic Writes) и строгой типизации.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from core.services.logging import get_logger


class Configurator:
    """
    Класс для управления конфигурацией приложения с поддержкой атомарной записи
    и валидации параметров.
    """

    DEFAULT_DB_TYPE = "csv"
    DEFAULT_OUTPUT_DIR = "./data"
    DEFAULT_SQL_SCRIPTS_DIR = "./data/sql"
    DEFAULT_CONFIG_FILE = "./core/config.json"

    DB_TYPES = {
        "csv": "CSV - файл.",
        "sqlite": "SQLite - встраиваемая локальная СУБД.",
        "postgresql": "PostgreSQL - удаленная СУБД.",
    }

    DB_REQUIRED_PARAMS = {
        "postgresql": ["host", "port", "dbname", "user", "password"],
        "sqlite": ["db_path"],
        "csv": ["delimiter", "encoding"],
    }

    DB_DEFAULT_PARAMS = {
        "postgresql": {
            "host": "localhost",
            "port": "5432",
            "dbname": "PLG",
            "user": "plg",
            "password": "plg",
        },
        "sqlite": {"db_path": "./data/database.db", "timeout": 20},
        "csv": {"delimiter": ",", "encoding": "utf-8", "quotechar": '"'},
    }

    DEFAULT_API_CONFIG = {
        "discogs_user_agent": "PlaylistAI/1.0 +http://example.com",
        "discogs_token": "",
    }

    def __init__(
        self,
        config_file: str | Optional[Path] = None,
        gui_callback: Optional[Callable[[str], None]] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self.config_file = Path(config_file or self.DEFAULT_CONFIG_FILE)
        self.db_type = self.DEFAULT_DB_TYPE
        self.output_dir = self.DEFAULT_OUTPUT_DIR
        self.sql_scripts_dir = self.DEFAULT_SQL_SCRIPTS_DIR
        self.db_config: dict[str, Any] = {}
        self.api_config = self.DEFAULT_API_CONFIG.copy()
        self.audio_folder = ""
        self.analysis_duration = 60
        self.gui_callback = gui_callback
        self.logger = logger or get_logger("PlaylistAI.Configurator")

        # Инициализация конфигурации и директорий
        self.load_config()
        self._ensure_default_directories()

    def _show_message(self, message: str) -> None:
        """Отображает сообщение через GUI-callback и централизованный логгер."""
        if self.gui_callback:
            try:
                self.gui_callback(message)
            except Exception as e:
                self.logger.error(f"Ошибка вызова gui_callback: {e}")
        self.logger.info(message)

    def _validate_db_type(self, db_type: str) -> str:
        if db_type not in self.DB_TYPES:
            message = f"⚠️ Тип БД '{db_type}' не поддерживается. Сброс на дефолт: {self.DEFAULT_DB_TYPE}."
            self._show_message(message)
            return self.DEFAULT_DB_TYPE
        return db_type

    def _ensure_db_config_defaults(self) -> None:
        if self.db_type in self.DB_DEFAULT_PARAMS:
            default_params = self.DB_DEFAULT_PARAMS[self.db_type]
            for key, value in default_params.items():
                if key not in self.db_config:
                    self.db_config[key] = value

    def _ensure_default_directories(self) -> None:
        for directory in [self.output_dir, self.sql_scripts_dir]:
            path = Path(directory)
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    self._show_message(f"📂 Создана директория: {directory}")
                except OSError as e:
                    self._show_message(f"❌ Не удалось создать директорию {directory}: {e}")

    @staticmethod
    def read_config(config_file: str | Path = DEFAULT_CONFIG_FILE) -> dict[str, Any]:
        """Статическое чтение файла конфигурации с обработкой ошибок десериализации."""
        path = Path(config_file)
        logger = get_logger("PlaylistAI.Configurator.Static")
        if path.exists():
            try:
                with open(path, encoding="utf-8") as file:
                    return json.load(file)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"❌ Ошибка чтения конфигурационного файла: {e}")
                return {}
        else:
            logger.warning("⚠️ Конфигурационный файл не найден.")
            return {}

    def save_config(self) -> None:
        """
        Атомарное сохранение конфигурации в файл (Atomic Write).
        Исключает повреждение файла при аварийном завершении процесса.
        """
        config = {
            "db_type": self.db_type,
            "output_dir": self.output_dir,
            "sql_scripts_dir": self.sql_scripts_dir,
            "db_config": self.db_config,
            "api_config": self.api_config,
            "audio_folder": self.audio_folder,
            "analysis_duration": self.analysis_duration,
        }

        try:
            # Создаем временный файл в той же директории, чтобы fsync/rename были атомарными
            # на уровне ФС Linux
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile("w", dir=self.config_file.parent, delete=False, encoding="utf-8") as tmp_file:
                json.dump(config, tmp_file, indent=4, ensure_ascii=False)
                tmp_temp_path = Path(tmp_file.name)

            # Атомарная замена старого файла новым (POSIX compliant)
            os.replace(tmp_temp_path, self.config_file)

        except OSError as e:
            self._show_message(f"❌ Ошибка атомарного сохранения конфигурации: {e}")
            if "tmp_temp_path" in locals() and tmp_temp_path.exists():
                try:
                    tmp_temp_path.unlink()
                except OSError:
                    pass

    def validate_config(self) -> tuple[bool, str]:
        """Проверяет текущую конфигурацию на корректность."""
        if self.db_type not in self.DB_TYPES:
            return False, f"Неверный тип БД: {self.db_type}"

        if not os.path.isdir(self.output_dir):
            return False, f"Директория вывода не существует: {self.output_dir}"

        if not os.path.isdir(self.sql_scripts_dir):
            return False, f"Директория SQL-скриптов не существует: {self.sql_scripts_dir}"

        if self.db_type in self.DB_REQUIRED_PARAMS:
            required_keys = self.DB_REQUIRED_PARAMS[self.db_type]
            missing_keys = [key for key in required_keys if key not in self.db_config]
            if missing_keys:
                return (
                    False,
                    f"Отсутствуют обязательные параметры для {self.db_type}: {missing_keys}",
                )

        return True, "Конфигурация корректна"

    def update_config(self, **kwargs: Any) -> None:
        """Обновляет параметры конфигурации за один вызов с валидацией."""
        changes_made = False

        if "db_type" in kwargs:
            db_type = kwargs["db_type"]
            if db_type not in self.DB_TYPES:
                raise ValueError(f"Неверный тип базы данных: {db_type}. Доступные: {list(self.DB_TYPES.keys())}")
            self.db_type = db_type
            changes_made = True

        if "output_dir" in kwargs:
            output_dir = kwargs["output_dir"]
            if not os.path.isdir(output_dir):
                raise ValueError(f"Указанный путь '{output_dir}' не является директорией.")
            self.output_dir = output_dir
            changes_made = True

        if "sql_scripts_dir" in kwargs:
            sql_scripts_dir = kwargs["sql_scripts_dir"]
            if not os.path.isdir(sql_scripts_dir):
                raise ValueError(f"Указанный путь '{sql_scripts_dir}' не является директорией.")
            self.sql_scripts_dir = sql_scripts_dir
            changes_made = True

        if "db_config" in kwargs:
            db_config = kwargs["db_config"]
            if not isinstance(db_config, dict):
                raise ValueError("db_config должен быть словарем")

            if self.db_type in self.DB_REQUIRED_PARAMS:
                required_params = self.DB_REQUIRED_PARAMS[self.db_type]
                missing_params = [param for param in required_params if param not in db_config]
                if missing_params:
                    raise ValueError(f"Отсутствуют параметры для {self.db_type}: {missing_params}")

            self.db_config = db_config
            changes_made = True

        if changes_made:
            self.save_config()

    def get_config(self) -> dict[str, Any]:
        return {
            "db_type": self.db_type,
            "output_dir": self.output_dir,
            "sql_scripts_dir": self.sql_scripts_dir,
            "db_config": self.db_config,
            "api_config": self.api_config,
        }

    @property
    def config(self) -> dict[str, Any]:
        """
        Прокси-свойство для обратной совместимости с модулями,
        ожидающими атрибут .config (например, ConnectionManager).
        """
        return self.get_config()

    def get_audio_folder(self) -> str:
        return self.audio_folder

    def get_analysis_duration(self) -> int:
        return self.analysis_duration

    def set_audio_folder(self, folder_path: str) -> None:
        path = Path(folder_path)
        if not path.is_dir():
            raise ValueError(f"Путь '{folder_path}' не является директорией.")
        self.audio_folder = str(path)
        self.save_config()

    def set_db_type(self, db_type: str) -> None:
        if db_type not in self.DB_TYPES:
            raise ValueError(f"Неверный тип БД: {db_type}")
        self.db_type = db_type
        self.db_config = self.DB_DEFAULT_PARAMS.get(db_type, {}).copy()
        self.save_config()

    def set_output_dir(self, output_dir: str) -> None:
        path = Path(output_dir)
        if not path.is_dir():
            try:
                path.mkdir(parents=True, exist_ok=True)
                self._show_message(f"📂 Создана директория: {output_dir}")
            except OSError as e:
                raise ValueError(f"Не удалось создать директорию '{output_dir}': {e}")
        self.output_dir = str(path)
        self.save_config()

    def set_sql_scripts_dir(self, sql_scripts_dir: str) -> None:
        if not os.path.isdir(sql_scripts_dir):
            raise ValueError(f"Путь '{sql_scripts_dir}' не является директорией.")
        self.sql_scripts_dir = sql_scripts_dir
        self.save_config()

    def set_postgres_config(
        self,
        host: str,
        port: str | int,
        dbname: str,
        user: str,
        password: str,
        ssl_mode: str = "prefer",
        connection_timeout: int = 30,
    ) -> None:
        if not all([host, port, dbname, user, password]):
            raise ValueError("Все поля подключения к PostgreSQL должны быть заполнены.")

        try:
            port_int = int(port)
            if not (1 <= port_int <= 65535):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"Некорректный порт: {port}. Ожидается число от 1 до 65535.")

        self.db_config = {
            "host": host,
            "port": str(port),
            "dbname": dbname,
            "user": user,
            "password": password,
            "ssl_mode": ssl_mode,
            "connection_timeout": connection_timeout,
        }
        self.save_config()

    def set_sqlite_config(self, db_path: str, timeout: int = 20) -> None:
        if not db_path:
            raise ValueError("Путь к файлу SQLite не указан.")

        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                self._show_message(f"📂 Создана директория для SQLite: {db_dir}")
            except OSError as e:
                raise ValueError(f"Не удалось создать директорию для SQLite: {e}")

        self.db_config = {"db_path": db_path, "timeout": timeout}
        self.save_config()

    def set_csv_config(self, delimiter: str = ",", encoding: str = "utf-8", quotechar: str = '"') -> None:
        self.db_config = {"delimiter": delimiter, "encoding": encoding, "quotechar": quotechar}
        self.save_config()

    def set_api_config(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if key in self.api_config:
                self.api_config[key] = value
        self.save_config()

    def set_analysis_duration(self, duration: int) -> None:
        if duration < 0:
            raise ValueError("Длительность анализа не может быть отрицательной.")
        self.analysis_duration = duration
        self.save_config()

    def load_config(self) -> bool:
        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as file:
                    config = json.load(file)

                if not config:
                    self.logger.warning("⚠️ Конфигурационный файл пуст. Сброс на дефолт.")
                    return self.reset_config()

                self.db_type = self._validate_db_type(config.get("db_type", self.DEFAULT_DB_TYPE))
                self.output_dir = config.get("output_dir", self.DEFAULT_OUTPUT_DIR)
                self.sql_scripts_dir = config.get("sql_scripts_dir", self.DEFAULT_SQL_SCRIPTS_DIR)
                self.db_config = config.get("db_config", {})
                self.api_config = config.get("api_config", self.DEFAULT_API_CONFIG.copy())
                self.audio_folder = config.get("audio_folder", "")
                self.analysis_duration = config.get("analysis_duration", 60)

                self._ensure_db_config_defaults()
                return True
            except (OSError, json.JSONDecodeError) as e:
                self.logger.error(f"❌ Ошибка разбора конфигурационного файла: {e}")
                return self.reset_config()
        else:
            self.logger.warning("⚠️ Конфигурационный файл отсутствует. Создание нового.")
            return self.reset_config()

    def reset_config(self) -> bool:
        default_config = {
            "db_type": self.DEFAULT_DB_TYPE,
            "output_dir": self.DEFAULT_OUTPUT_DIR,
            "sql_scripts_dir": self.DEFAULT_SQL_SCRIPTS_DIR,
            "db_config": self.DB_DEFAULT_PARAMS.get(self.DEFAULT_DB_TYPE, {}).copy(),
            "api_config": self.DEFAULT_API_CONFIG.copy(),
            "audio_folder": "",
            "analysis_duration": 60,
        }

        self.db_type = default_config["db_type"]
        self.output_dir = default_config["output_dir"]
        self.sql_scripts_dir = default_config["sql_scripts_dir"]
        self.db_config = default_config["db_config"]
        self.api_config = default_config["api_config"]
        self.audio_folder = default_config["audio_folder"]
        self.analysis_duration = default_config["analysis_duration"]

        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=self.config_file.parent, delete=False, encoding="utf-8") as tmp_file:
                json.dump(default_config, tmp_file, indent=4, ensure_ascii=False)
                tmp_temp_path = Path(tmp_file.name)
            os.replace(tmp_temp_path, self.config_file)
            self.logger.info("✅ Новый конфигурационный файл успешно создан.")
            return True
        except OSError as e:
            self.logger.error(f"❌ Не удалось создать конфигурационный файл: {e}")
            return False
