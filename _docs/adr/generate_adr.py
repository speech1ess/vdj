import os
import sys
from datetime import datetime
import yaml
from jinja2 import Environment, FileSystemLoader

# Добавляем корень проекта в sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # _docs/adr/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))  # PLG/
sys.path.append(PROJECT_ROOT)

from core.services.logging import get_logger, setup_logging

# Настройки папок
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
YAML_DIR = os.path.join(BASE_DIR, "yaml")
README_FILE = os.path.join(BASE_DIR, "README.md")

# Инициализация логирования
setup_logging(log_to_file=True)
logger = get_logger(__name__)

# Проверка наличия шаблона
if not os.path.exists(os.path.join(TEMPLATE_DIR, "adr_template.md")):
    logger.error("Шаблон adr_template.md не найден в папке templates!")
    exit(1)

# Загружаем шаблон
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template = env.get_template("adr_template.md")

def generate_adr_from_yaml(yaml_file):
    """Генерирует ADR-файл на основе YAML-конфигурации."""
    with open(yaml_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    required_keys = {"number", "title", "context", "decision", "alternatives", "consequences", "status"}
    if not required_keys.issubset(data.keys()):
        logger.error(f"{yaml_file} не содержит все необходимые поля!")
        return None

    adr_number = data["number"]
    software_name = data["title"].split()[1] if len(data["title"].split()) > 1 else data["title"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(BASE_DIR, f"{adr_number}-{software_name}_[{date_str}].md")

    if os.path.exists(filename):
        logger.warning(f"Файл {filename} уже существует! Пропускаем создание.")
        return None

    content = template.render(data)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"ADR создан: {filename}")
    return adr_number, software_name

def update_readme():
    """Обновляет README.md, добавляя список файлов ADR с заголовками из YAML."""
    adr_files = [f for f in os.listdir(BASE_DIR) if f.endswith(".md") and f != "README.md"]
    adr_files.sort()

    adr_list = []
    for file in adr_files:
        adr_number, software_name = file.split("-")[:2]
        software_name = software_name.split("_")[0]

        yaml_file = os.path.join(YAML_DIR, f"{adr_number}.yaml")
        if os.path.exists(yaml_file):
            with open(yaml_file, "r", encoding="utf-8") as yf:
                yaml_data = yaml.safe_load(yf)
                title = yaml_data.get("title", software_name)
            adr_list.append(f"- [{adr_number}-{software_name}.md](./{file}) — {title}")
        else:
            adr_list.append(f"- [{adr_number}-{software_name}.md](./{file}) — {software_name}")

    with open(README_FILE, "r", encoding="utf-8") as f:
        readme_content = f.read()

    new_readme = []
    in_adr_section = False
    for line in readme_content.splitlines():
        if line.startswith("## Список файлов с решениями"):
            in_adr_section = True
            new_readme.append(line)
            new_readme.append("")
            new_readme.extend(adr_list)
        elif in_adr_section and line.startswith("## "):
            in_adr_section = False
            new_readme.append("")
            new_readme.append(line)
        elif not in_adr_section:
            new_readme.append(line)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(new_readme))
    logger.info("README.md обновлен.")

if __name__ == "__main__":
    os.makedirs(YAML_DIR, exist_ok=True)
    
    yaml_files = [f for f in os.listdir(YAML_DIR) if f.endswith(".yaml")]
    if not yaml_files:
        logger.error("Нет YAML-файлов с ADR!")
    else:
        for file in yaml_files:
            adr_info = generate_adr_from_yaml(os.path.join(YAML_DIR, file))
            if adr_info:
                adr_number, software_name = adr_info
        
        update_readme()