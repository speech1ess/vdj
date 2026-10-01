import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from core.repositories.repo import Repo

# Отложенный импорт для избежания циклических зависимостей, если ObjFactory использует модели
from core.services.cache import CacheManager, ObjFactory
from core.services.scanner import ScannerService
from core.viewmodels.basevwm import BaseViewModel


class ScanViewModel(BaseViewModel):
    """
    ViewModel для экрана сканирования (Staging Pipeline).
    Управляет I/O сканированием, хранит DTO в памяти (Staging Area)
    и управляет коммитом в базу данных после Quality Gate.
    """

    def __init__(self, configurator, log_callback=None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.folder_path: Optional[Path] = None

        # Инициализируем I/O Scanner
        self.scanner = ScannerService(cue_analyze=True, stop_event=threading.Event())
        self.scanning_thread = None
        self.scan_event = self.scanner.stop_event
        self.is_scanning = False

        # STAGING AREA: Храним плоские DTO-словари, а не ORM-объекты
        self.staged_dtos: list[dict] = []

        # Фабрика объектов и кэш теперь живут на уровне ViewModel
        self.cache = CacheManager()
        self.obj_factory = ObjFactory(self.cache)

        self.progress_callback = None
        self.completion_callback = None

        # Защищенные внутренние счетчики для сохранения консистентности UI
        self._cached_total_tracks = 0

    def set_callbacks(
        self,
        progress_callback: Callable[[dict[str, Any]], None],
        completion_callback: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        # Подключаем коллбэки I/O сканера
        self.scanner.set_callbacks(self._on_scanner_progress, None)

    def _on_scanner_progress(self, progress_data: dict[str, Any]) -> None:
        """Перехватчик прогресса из сервиса сканера (ACL)."""
        if self.progress_callback:
            try:
                # Фиксируем общее число треков, если оно передано из I/O слоя
                tracks_total = progress_data.get("total_tracks", 0)
                if tracks_total > 0:
                    self._cached_total_tracks = tracks_total

                normalized_data = {
                    "progress": progress_data.get("progress", 0.0),
                    "processed_files": progress_data.get("processed_files", 0),
                    "total_files": progress_data.get("total_files", 0),
                    "processed_tracks": progress_data.get("processed_tracks", 0),
                    "total_tracks": self._cached_total_tracks or tracks_total,
                    "stage": progress_data.get("stage", "Processing"),
                }
                self.progress_callback(normalized_data)
            except Exception as e:
                self.logger.error(f"UI Progress Callback Error: {e}")

    def set_folder(self, folder_path: str) -> None:
        if folder_path:
            self.folder_path = Path(folder_path)
        else:
            self.folder_path = None
            self.logger.warning("⚠️ Передан пустой путь к папке сканирования")

    def cancel_scan(self) -> None:
        if self.is_scanning:
            self.logger.info("⏹ Инициирована отмена сканирования...")
            self.scanner.stop_event.set()
            self.is_scanning = False

            if self.progress_callback:
                self.progress_callback(
                    {
                        "progress": 0,
                        "processed_files": 0,
                        "total_files": 0,
                        "processed_tracks": 0,
                        "total_tracks": 0,
                        "stage": "Cancelled",
                    }
                )

    def start_scan(self):
        """Запускает Фазу 1 (Fast Ingestion I/O) и Фазу 2 (DSP Enrichment) в фоновом потоке."""
        if not self.folder_path or not self.folder_path.is_dir():
            self.set_status("❌ Не выбрана или недоступна папка для сканирования.")
            return

        self.set_status(f"🔍 Быстрое сканирование (I/O): {self.folder_path.name}...")
        self.is_scanning = True
        self.staged_dtos = []
        self._cached_total_tracks = 0
        self.scan_event.clear()

        def scan_worker():
            """
            Двухконтурный пайплайн: I/O Ingestion -> CPU Enrichment -> UI Update.
            """
            try:
                # === СТАДИЯ 1: Мгновенное I/O сканирование ===
                raw_dtos = self.scanner.scan_directory(self.folder_path)

                if not raw_dtos or self.scan_event.is_set():
                    return

                # Предварительный расчет треков для UI-стабильности
                calculated_tracks = 0
                for dto in raw_dtos:
                    if dto.get("_is_multi"):
                        calculated_tracks += len(dto.get("_cue_tracks", []))
                    else:
                        calculated_tracks += 1
                self._cached_total_tracks = calculated_tracks

                # Промежуточный рендер: показываем пользователю найденные треки (BPM/Key = None)
                self.staged_dtos = raw_dtos
                intermediate_data = self._prepare_display_data(self.staged_dtos)
                if self.completion_callback:
                    self.completion_callback(intermediate_data)

                # Сигнализируем UI о смене контекста (Подготовка к Фазе 2)
                if self.progress_callback:
                    self.progress_callback(
                        {
                            "progress": 0.0,
                            "processed_files": 0,
                            "total_files": len(raw_dtos),
                            "processed_tracks": self._cached_total_tracks,
                            "total_tracks": self._cached_total_tracks,
                            "stage": "DSP Math: Инициализация пула процессов...",
                        }
                    )

                # === СТАДИЯ 2: Тяжелая математика (DSP Enrichment) ===
                from core.services.dsp_worker import DSPEnrichmentService

                # Изолируем ядра для предотвращения context switching шторма в ОС
                dsp_cores = max(1, self.scanner.max_workers // 2)
                dsp = DSPEnrichmentService(stop_event=self.scan_event, max_workers=dsp_cores)

                # Защищенный адаптер прогресса для DSP-контура
                def dsp_progress_adapter(data):
                    if self.progress_callback:
                        self.progress_callback(
                            {
                                "progress": data.get("progress", 0.0),
                                "processed_files": data.get("processed_files", 0),
                                "total_files": data.get("total_files", 0),
                                "processed_tracks": self._cached_total_tracks,  # Удерживаем консистентность
                                "total_tracks": self._cached_total_tracks,
                                "stage": data.get("stage", "DSP Math: Вычисление..."),
                            }
                        )

                dsp.set_callbacks(dsp_progress_adapter)

                # Запуск CPU-пула процессов
                enriched_dtos = dsp.process_dtos(raw_dtos)

                # === СТАДИЯ 3: Финальный рендеринг (Quality Gate Ready) ===
                self.staged_dtos = enriched_dtos
                final_display_data = self._prepare_display_data(self.staged_dtos)

                # Финальный пуш в UI. Активирует кнопки сохранения черезвью.
                if self.completion_callback and not self.scan_event.is_set():
                    try:
                        self.completion_callback(final_display_data)
                    except Exception as e:
                        self.logger.error(f"UI Completion Callback Error: {e}")

            except Exception as e:
                self.logger.error(f"⚠️ Критический сбой пайплайна сканирования: {e}", exc_info=True)
            finally:
                self.is_scanning = False

        self.scanning_thread = threading.Thread(target=scan_worker, daemon=True)
        self.scanning_thread.start()

    def _prepare_display_data(self, dtos: list[dict]) -> list[dict[str, Any]]:
        """
        Подготавливает сырые DTO для отображения в UI-таблице (Quality Gate).
        Гарантирует отсутствие структур данных (sets/lists) в финальном словаре.
        """
        display_data = []

        def _stringify(val, default="Unknown"):
            if isinstance(val, (set, list)):
                return ", ".join(str(v) for v in val if v) if val else default
            return str(val) if val else default

        for index, item in enumerate(dtos):
            display_data.append(
                {
                    "id": f"stg_{index}",  # Временный ID для UI
                    "title": _stringify(item.get("title"), "Unknown"),
                    "duration": item.get("duration", 0),
                    "bpm": item.get("bpm", ""),
                    "key": item.get("key", ""),
                    "disc_number": item.get("disc_num", 1),
                    "track_number": item.get("track_num", 1),
                    "artists": _stringify(item.get("artist"), "Unknown Artist"),
                    "albums": _stringify(item.get("album"), "Unknown Album"),
                    "genres": _stringify(item.get("genre"), "Unknown Genre"),
                    "file_path": item.get("file_path", ""),
                }
            )
        return display_data

    def save_results(self) -> bool:
        """
        Завершение Quality Gate (Commit Phase).
        Транслирует DTO из Staging Area в ORM-графы и сохраняет в БД.
        """
        if not self.staged_dtos:
            self.set_status("⚠️ Нет данных для сохранения")
            return False

        try:
            self.set_status("⏳ Сборка связей и запись в базу данных...")
            self.logger.info(f"Передаём {len(self.staged_dtos)} DTO в фабрику для сборки ORM.")

            orm_tracks = []

            # Собираем ORM-объекты из словарей
            for dto in self.staged_dtos:
                file_path = Path(dto["file_path"])
                models_found = dto.pop("_models_found", ["Track", "AudioFile", "Album", "Artist", "Genre"])

                # Создаем граф объектов
                audio_obj, track_objs = self.obj_factory.create_objects(file_path, dto, models_found)
                if track_objs:
                    orm_tracks.extend(track_objs)

            if not orm_tracks:
                self.set_status("⚠️ Не удалось сформировать объекты для записи.")
                return False

            # Сохраняем в БД за одну транзакцию
            repo = Repo(self.configurator, self.cache)
            success = repo.save_data(orm_tracks)

            if success:
                self.set_status(f"✅ Успешно сохранено {len(orm_tracks)} треков!")
                self.staged_dtos.clear()
                self.cache.clear()  # Очищаем ОЗУ
            else:
                self.set_status("❌ Ошибка при записи в БД (см. логи).")

            return success

        except Exception as e:
            self.logger.error(f"❌ Exception при сохранении данных: {e}", exc_info=True)
            self.set_status("❌ Сбой при записи в БД.")
            return False
