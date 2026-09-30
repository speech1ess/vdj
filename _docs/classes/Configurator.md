# Класс Configurator (conf.py)

## Описание

Класс поддерживает следующие типы баз данных:
- CSV - простые файлы с разделителями
- SQLite - встраиваемая локальная СУБД
- PostgreSQL - удаленная СУБД

Основные возможности:
- Загрузка и сохранение настроек в JSON-файл
- Валидация параметров конфигурации
- Настройка различных типов баз данных
- Управление путями к директориям
- Интеграция с GUI через функцию обратного вызова

## Константы

| Константа | Описание |
|-----------|----------|
| `DEFAULT_DB_TYPE` | Тип БД по умолчанию ("csv"). |
| `DEFAULT_OUTPUT_DIR` | Директория для данных по умолчанию ("./data"). |
| `DEFAULT_SQL_SCRIPTS_DIR` | Директория для SQL-скриптов по умолчанию ("./sql"). |
| `DEFAULT_CONFIG_FILE` | Имя файла конфигурации по умолчанию ("config.json"). |
| `DB_TYPES` | Словарь допустимых типов БД с комментариями. |
| `DB_REQUIRED_PARAMS` | Словарь обязательных параметров для каждого типа БД. |
| `DB_DEFAULT_PARAMS` | Словарь значений по умолчанию для параметров каждого типа БД. |

## Основные методы

| Метод | Описание |
|-------|----------|
| `__init__(config_file, gui_callback, logger)` | Инициализирует объект Configurator с указанным файлом конфигурации и функцией обратного вызова для GUI. |
| `load_config()` | Загружает конфигурацию из файла, если он существует и корректен. |
| `save_config()` | Сохраняет текущую конфигурацию в файл. |
| `set_db_type(db_type)` | Устанавливает тип базы данных после проверки допустимых значений. |
| `set_output_dir(output_dir)` | Устанавливает каталог для сохранения файлов. |
| `set_sql_scripts_dir(sql_scripts_dir)` | Устанавливает каталог с SQL-скриптами. |
| `set_postgres_config(host, port, dbname, user, password, ssl_mode, connection_timeout)` | Устанавливает параметры подключения к PostgreSQL. |
| `set_sqlite_config(db_path, timeout)` | Устанавливает параметры подключения к SQLite. |
| `set_csv_config(delimiter, encoding, quotechar)` | Устанавливает параметры для работы с CSV файлами. |
| `update_config(**kwargs)` | Обновляет несколько параметров конфигурации за один вызов. |
| `get_config()` | Возвращает текущие настройки конфигурации. |
| `validate_config()` | Проверяет текущую конфигурацию на корректность. |

## Вспомогательные методы

| Метод | Описание |
|-------|----------|
| `_validate_and_set_path(config_value, default_value, error_message)` | Проверяет и устанавливает путь, возвращая к значению по умолчанию при ошибке. |
| `_validate_db_type(db_type)` | Проверяет корректность типа базы данных. |
| `_ensure_default_directories()` | Создает директории по умолчанию, если они не существуют. |
| `_ensure_db_config_defaults()` | Проверяет и дополняет конфигурацию БД значениями по умолчанию. |
| `_show_message(message)` | Отображает сообщение через GUI-callback и/или логгер. |

## Статические методы

| Метод | Описание |
|-------|----------|
| `read_config(config_file)` | Читает конфигурационный файл и возвращает его содержимое как словарь. |

## Примеры использования

### Базовое использование
```python
from conf import Configurator

# Создание конфигуратора с настройками по умолчанию
config = Configurator()

# Получение текущих настроек
settings = config.get_config()
print(f"Текущий тип БД: {settings['db_type']}")

# Изменение типа БД
config.set_db_type("postgresql")

# Настройка подключения к PostgreSQL
config.set_postgres_config(
    host="localhost",
    port=5432,
    dbname="PLG",
    user="plg",
    password="plg"
)
```

### Обновление нескольких параметров
```python
from conf import Configurator

# Создание конфигуратора с настройками по умолчанию
config = Configurator()

# Получение текущих настроек
settings = config.get_config()
print(f"Текущий тип БД: {settings['db_type']}")

# Изменение типа БД
config.set_db_type("postgresql")

# Настройка подключения к PostgreSQL
config.set_postgres_config(
    host="localhost",
    port=5432,
    dbname="PLG",
    user="plg",
    password="plg"
)
```

## Интеграция с GUI
Класс `Configurator` интегрируется с GUI через функцию обратного вызова:
```python
def show_message(message):
    # Отображение сообщения в GUI
    message_label.config(text=message)

configurator = Configurator(gui_callback=show_message)

```
## Расширение функциональности
Для добавления новых параметров конфигурации:

- Добавьте константы для значений по умолчанию в класс Configurator
- Обновите методы load_config() и save_config() для работы с новыми параметрами
- Добавьте методы для установки и получения новых параметров
- Обновите метод validate_config() для проверки новых параметров
- При необходимости добавьте новые методы в интерфейс GUI

## Формат файла конфигурации
Конфигурация хранится в JSON-файле следующего формата:
```json
{
  "db_type": "postgresql",
  "output_dir": "C:/Users/username/Documents/PLG/data",
  "sql_scripts_dir": "C:/Users/username/Documents/PLG/sql",
  "db_config": {
    "host": "localhost",
    "port": "5432",
    "dbname": "PLG",
    "user": "plg",
    "password": "plg"
  }
}

```