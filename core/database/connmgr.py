# core/database/connmgr.py

import logging
import sqlite3
import traceback  # Добавляем импорт
from contextlib import contextmanager

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.services.config import Configurator

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Менеджер соединений с базами данных.
    """

    def __init__(self, configurator: Configurator):
        """Инициализирует менеджер с конфигуратором."""
        self.configurator = configurator
        self.connection = None
        self.engine = None
        self.Session = None
        self._setup_engine()

    def _setup_engine(self):
        """Настраивает SQLAlchemy engine на основе конфигурации."""
        db_type = self.configurator.db_type
        db_config = self.configurator.db_config

        if db_type == "sqlite":
            db_path = db_config.get("db_path", "data/playlist_ai.db")
            self.engine = create_engine(f"sqlite:///{db_path}")
        elif db_type == "postgresql":
            self.engine = create_engine(
                f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}",
                pool_pre_ping=True,
            )
        else:
            raise ValueError(f"Неизвестный тип базы данных: {db_type}")

        if self.engine:
            self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def connect(self):
        """Устанавливает соединение с БД (для sqlite3/psycopg2)."""
        try:
            if self.configurator.db_type == "sqlite":
                self.connection = sqlite3.connect(self.configurator.db_config["db_path"])
                logger.info("✅ Подключение к SQLite успешно")
            elif self.configurator.db_type == "postgresql":
                self.connection = psycopg2.connect(**self.configurator.db_config)
                logger.info("✅ Подключение к PostgreSQL успешно")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к {self.configurator.db_type}: {e}")
            self.connection = None
            return False

    def disconnect(self):
        """Закрывает соединение с БД."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("🔌 Соединение закрыто")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии соединения: {e}")
            finally:
                self.connection = None

    def get_connection(self):
        """Возвращает текущее соединение или создаёт новое (для sqlite3/psycopg2)."""
        if self.connection is None:
            self.connect()
        return self.connection

    def get_session(self):
        """Возвращает SQLAlchemy сессию."""
        if self.Session:
            return self.Session()
        raise NotImplementedError("Сессия недоступна для данного типа БД")

    def __getattr__(self, name):
        """Ловим вызов несуществующих методов и логируем стек вызовов."""
        logger.error(f"Попытка вызвать несуществующий метод: {name}")
        logger.error("Полный стек вызовов:\n" + "".join(traceback.format_stack()))
        raise AttributeError(f"'ConnectionManager' object has no attribute '{name}'")


def check_connection(configurator: Configurator):
    """Проверяет, работает ли подключение к БД."""
    try:
        engine = create_engine(
            f"sqlite:///{configurator.db_config['db_path']}"
            if configurator.db_type == "sqlite"
            else f"postgresql://{configurator.db_config['user']}:{configurator.db_config['password']}@"
            f"{configurator.db_config['host']}:{configurator.db_config['port']}/{configurator.db_config['dbname']}"
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка проверки соединения: {e}")
        return False


@contextmanager
def get_db(configurator: Configurator):
    """Контекстный менеджер для SQLAlchemy-сессии."""
    cm = ConnectionManager(configurator)
    db = cm.get_session()
    try:
        yield db
    finally:
        db.close()
