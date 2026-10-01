import csv
import json
from typing import Any

from core.services.logging import get_logger


class CSVService:
    """
    Высокопроизводительный сервис для импорта и экспорта CSV-данных.
    Адаптирован для работы с Staging Area (DTO словари).
    """

    def __init__(self) -> None:
        self.logger = get_logger("PlaylistAI.CSVService")

    def save_to_csv(self, dtos: list[dict[str, Any]], file_path: str) -> bool:
        """
        Сохраняет список DTO (словарей) в CSV-файл.
        Используется как оффлайн-кэш Staging Area.
        """
        try:
            self.logger.info(f"Инициация пакетного экспорта {len(dtos)} записей в {file_path}")
            if not dtos:
                return False

            # Собираем все ключи для заголовка CSV
            fieldnames = set()
            for dto in dtos:
                fieldnames.update(dto.keys())
            fieldnames = sorted(list(fieldnames))

            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()

                for dto in dtos:
                    row = {}
                    for k, v in dto.items():
                        # Сериализация коллекций (списки/сеты артистов и жанров)
                        if isinstance(v, (list, set, tuple)):
                            row[k] = json.dumps(list(v))
                        else:
                            row[k] = v
                    writer.writerow(row)

            self.logger.info(f"✅ CSV успешно сохранен: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения CSV: {e}", exc_info=True)
            return False

    def load_from_csv(self, file_path: str) -> list[dict[str, Any]]:
        """
        Загружает DTO из CSV-файла в Staging Area.
        """
        self.logger.info(f"Инициация импорта данных из CSV: {file_path}")
        dtos = []

        try:
            with open(file_path, newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file, delimiter=";")

                for row in reader:
                    dto = {}
                    for k, v in row.items():
                        if not v:
                            dto[k] = None
                            continue

                        # Десериализация коллекций
                        if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
                            try:
                                dto[k] = json.loads(v)
                                continue
                            except json.JSONDecodeError:
                                pass

                        # Приведение типов для чисел (BPM, Duration, Track Number)
                        try:
                            if "." in v:
                                dto[k] = float(v)
                            elif v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                                dto[k] = int(v)
                            else:
                                dto[k] = v
                        except ValueError:
                            dto[k] = v

                    dtos.append(dto)

            self.logger.info(f"✅ Успешно загружено и распарсено записей: {len(dtos)}")
            return dtos

        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка загрузки CSV: {e}", exc_info=True)
            raise
