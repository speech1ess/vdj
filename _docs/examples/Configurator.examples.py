"""
Примеры использования модуля конфигурации Playlist AI.

Этот файл содержит примеры использования класса Configurator
для различных сценариев настройки приложения.
"""

import os
import sys
import logging

# Добавляем родительскую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conf import Configurator

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ConfigExamples")

def print_section(title):
    """Выводит заголовок секции примера."""
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}\n")

def basic_usage():
    """Демонстрирует базовое использование Configurator."""
    print_section("Базовое использование")
    
    # Создание конфигуратора с настройками по умолчанию
    config = Configurator(logger=logger)
    
    # Получение текущих настроек
    settings = config.get_config()
    print(f"Текущий тип БД: {settings['db_type']}")
    print(f"Директория для данных: {settings['output_dir']}")
    print(f"Директория для SQL: {settings['sql_scripts_dir']}")
    print(f"Конфигурация БД: {settings['db_config']}")

def csv_config_example():
    """Демонстрирует настройку CSV."""
    print_section("Настройка CSV")
    
    config = Configurator(config_file="examples/csv_config.json", logger=logger)
    config.set_db_type("csv")
    
    # Настройка параметров CSV
    config.set_csv_config(
        delimiter=";",
        encoding="utf-8",
        quotechar='"'
    )
    
    print(f"Конфигурация CSV: {config.db_config}")
    
    # Проверка конфигурации
    is_valid, message = config.validate_config()
    print(f"Конфигурация валидна: {is_valid}, сообщение: {message}")

def sqlite_config_example():
    """Демонстрирует настройку SQLite."""
    print_section("Настройка SQLite")
    
    config = Configurator(config_file="examples/sqlite_config.json", logger=logger)
    config.set_db_type("sqlite")
    
    # Создаем временную директорию для примера
    temp_dir = "./examples/temp_sqlite"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # Настройка параметров SQLite
    config.set_sqlite_config(
        db_path=f"{temp_dir}/example.db",
        timeout=30
    )
    
    print(f"Конфигурация SQLite: {config.db_config}")
    
    # Проверка конфигурации
    is_valid, message = config.validate_config()
    print(f"Конфигурация валидна: {is_valid}, сообщение: {message}")

def postgresql_config_example():
    """Демонстрирует настройку PostgreSQL."""
    print_section("Настройка PostgreSQL")
    
    config = Configurator(config_file="examples/pg_config.json", logger=logger)
    config.set_db_type("postgresql")
    
    # Настройка параметров PostgreSQL
    try:
        config.set_postgres_config(
            host="localhost",
            port=5432,
            dbname="PLG",
            user="plg",
            password="plg",
            ssl_mode="prefer",
            connection_timeout=30
        )
        print("PostgreSQL настроен успешно")
    except ValueError as e:
        print(f"Ошибка настройки PostgreSQL: {e}")
    
    print(f"Конфигурация PostgreSQL: {config.db_config}")
    
    # Проверка конфигурации
    is_valid, message = config.validate_config()
    print(f"Конфигурация валидна: {is_valid}, сообщение: {message}")

def update_multiple_settings_example():
    """Демонстрирует обновление нескольких настроек за один вызов."""
    print_section("Обновление нескольких настроек")
    
    config = Configurator(config_file="examples/multi_config.json", logger=logger)
    
    # Создаем временные директории для примера
    temp_output = "./examples/temp_output"
    temp_sql = "./examples/temp_sql"
    for directory in [temp_output, temp_sql]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    # Обновление нескольких параметров за один вызов
    try:
        config.update_config(
            db_type="postgresql",
            output_dir=temp_output,
            sql_scripts_dir=temp_sql,
            db_config={
                "host": "localhost",
                "port": "5432",
                "dbname": "PLG",
                "user": "plg",
                "password": "plg"
            }
        )
        print("Множественное обновление выполнено успешно")
    except ValueError as e:
        print(f"Ошибка при обновлении: {e}")
    
    # Проверяем результат
    settings = config.get_config()
    print(f"Обновленные настройки: {settings}")

def gui_integration_example():
    """Демонстрирует интеграцию с GUI."""
    print_section("Интеграция с GUI")
    
    messages = []
    
    def gui_callback(message):
        """Имитация функции обратного вызова GUI."""
        messages.append(message)
        print(f"GUI сообщение: {message}")
    
    config = Configurator(config_file="examples/gui_config.json", gui_callback=gui_callback)
    
    # Вызываем методы, которые будут отправлять сообщения через callback
    config.set_db_type("csv")
    config._show_message("Тестовое сообщение для GUI")
    
    print(f"Всего сообщений GUI: {len(messages)}")

def cleanup():
    """Удаляет временные файлы и директории."""
    print_section("Очистка временных файлов")
    
    temp_dirs = ["./examples/temp_output", "./examples/temp_sql", "./examples/temp_sqlite"]
    config_files = ["examples/csv_config.json", "examples/sqlite_config.json", 
                   "examples/pg_config.json", "examples/multi_config.json", 
                   "examples/gui_config.json"]
    
    for directory in temp_dirs:
        if os.path.exists(directory):
            try:
                os.rmdir(directory)
                print(f"Удалена директория: {directory}")
            except OSError:
                print(f"Не удалось удалить директорию: {directory}")
    
    for file in config_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"Удален файл: {file}")
            except OSError:
                print(f"Не удалось удалить файл: {file}")

if __name__ == "__main__":
    basic_usage()
    csv_config_example()
    sqlite_config_example()
    postgresql_config_example()
    update_multiple_settings_example()
    gui_integration_example()
    cleanup()