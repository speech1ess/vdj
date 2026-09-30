from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from core.database.base import Base
from core.database.connmgr import ConnectionManager
from core.database.db_config import BASE_GENRES, SUB_GENRES
from core.models import Genre, Track
from core.models.enums import AudioFormat, MusicalKey
from core.services.logging import get_logger

logger = get_logger("PlaylistAI.Database.Schema")


class DatabaseSchema:
    """Класс для управления схемой БД и заливкой начальных данных (Seed)."""

    def __init__(self, configurator):
        self.configurator = configurator
        self.conn_manager = ConnectionManager(configurator)

    def init_genres(self, session: Session) -> None:
        """Безопасная (идемпотентная) заливка базовых жанров."""
        try:
            # 1. Заливаем базовые жанры
            for data in BASE_GENRES:
                # Используем first() для проверки существования (идемпотентность)
                exists = session.query(Genre).filter_by(name=data["name"]).first()
                if not exists:
                    # Разворачиваем словари в kwargs, как и ожидают наши модели
                    session.add(Genre(**data))
            session.commit()

            # 2. Заливаем поджанры (после того как родители точно есть в БД)
            for sub in SUB_GENRES:
                exists = session.query(Genre).filter_by(name=sub["name"]).first()
                if not exists:
                    parent = session.query(Genre).filter_by(name=sub["parent_name"]).first()
                    if parent:
                        session.add(Genre(name=sub["name"], parent_id=parent.id))
                    else:
                        logger.warning(
                            f"Родительский жанр {sub['parent_name']} не найден для {sub['name']}"
                        )
            session.commit()
            logger.info("ℹ️ Инициализация жанров (Seed) успешно завершена.")

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка при инициализации жанров: {e}")
            raise

    def create_schema(self) -> None:
        """Создает таблицы и нативные типы (Enum)."""
        engine = self.conn_manager.engine
        db_type = self.configurator.config.get("db_type", "sqlite")

        try:
            logger.info(f"Инициализация создания схемы. Engine: {engine.url}")

            # Если мы в PostgreSQL, нам нужно явно создать ENUM типы до создания таблиц
            if db_type == "postgresql":
                from sqlalchemy.dialects.postgresql import ENUM

                musical_key_enum = ENUM(
                    *[e.value for e in MusicalKey], name="musicalkey", create_type=True
                )
                musical_key_enum.create(engine, checkfirst=True)

                audio_format_enum = ENUM(
                    *[e.value for e in AudioFormat], name="audioformat", create_type=True
                )
                audio_format_enum.create(engine, checkfirst=True)
                logger.info("✅ PostgreSQL ENUM типы созданы/проверены.")

            # Создаем таблицы (в SQLite ENUM'ы эмулируются строками автоматически)
            Base.metadata.create_all(engine)
            logger.info("✅ Таблицы ORM успешно созданы.")

            # Инициализация Seed Data
            with self.conn_manager.get_session() as session:
                self.init_genres(session)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка при создании схемы БД: {e}")
            raise

    def check_schema(self) -> bool:
        """
        Проверяет наличие таблиц.
        ВНИМАНИЕ: Это наивная проверка. В будущем заменить на Alembic.
        """
        engine = self.conn_manager.engine
        inspector = inspect(engine)

        try:
            expected_tables = set(Base.metadata.tables.keys())
            existing_tables = set(inspector.get_table_names())

            missing_tables = expected_tables - existing_tables
            if missing_tables:
                logger.warning(f"⚠️ Отсутствуют необходимые таблицы: {missing_tables}")
                return False

            # Проверяем наличие колонок хотя бы в одной ключевой таблице
            expected_columns = {col.name for col in Track.__table__.columns}
            actual_columns = {col["name"] for col in inspector.get_columns("tracks")}
            missing_columns = expected_columns - actual_columns

            if missing_columns:
                logger.warning(
                    f"⚠️ В таблице 'tracks' отсутствуют колонки: {missing_columns}. Требуется миграция!"
                )
                return False

            # Проверяем Seed-данные
            with self.conn_manager.get_session() as session:
                current_genre_count = session.query(Genre).count()
                if current_genre_count < len(BASE_GENRES):
                    logger.info("⚠️ В БД не хватает базовых жанров. Запускаем инициализацию...")
                    self.init_genres(session)

            logger.info("✅ Схема БД актуальна.")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при инспекции схемы БД: {e}")
            return False

    def drop_schema(self) -> None:
        """Опасная зона: Уничтожает всю схему БД. Использовать только в разработке."""
        engine = self.conn_manager.engine
        db_type = self.configurator.config.get("db_type", "sqlite")

        try:
            logger.warning(f"Инициация DROP SCHEMA для: {engine.url}")

            # SQLAlchemy Base.metadata.drop_all работает безопаснее ручного CASCADE
            Base.metadata.drop_all(engine)

            # Для PostgreSQL подчищаем типы ENUM (SQLAlchemy не всегда делает это автоматически)
            if db_type == "postgresql":
                with engine.connect() as conn:
                    try:
                        conn.execute(text("DROP TYPE IF EXISTS musicalkey CASCADE"))
                        conn.execute(text("DROP TYPE IF EXISTS audioformat CASCADE"))
                        conn.commit()
                    except (ProgrammingError, OperationalError) as e:
                        logger.warning(
                            f"Не удалось удалить ENUM типы в PostgreSQL (возможно, их не было): {e}"
                        )

            logger.info("⚠️ Все таблицы успешно удалены из БД!")

        except Exception as e:
            logger.error(f"❌ Ошибка при удалении таблиц: {e}")
            raise
