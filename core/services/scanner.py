from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Optional

from core.models.enums import AudioFormat
from core.services.audio_processor import AudioProcessor
from core.services.logging import get_logger
from core.services.metadata_extractor import CueParser  # Импортируем CueParser напрямую
from core.services.metadata_tools import MetadataNormalizer, MetadataValidator


class ScannerService:
    """
    Высокопроизводительный I/O-оркестратор (Stage 1: Fast Ingestion).
    Использует ThreadPoolExecutor, так как чтение тегов освобождает GIL (syscalls).
    Возвращает сырые DTO для размещения в Staging Area (RAM) перед валидацией.
    """

    AUDIO_EXTENSIONS = {fmt.value for fmt in AudioFormat}

    def __init__(self, cue_analyze: bool = True, stop_event: Optional[Event] = None, max_workers: int = 8):
        self.logger = get_logger("PlaylistAI.ScannerService")
        self.cue_analyze = cue_analyze
        self.stop_event = stop_event or Event()

        # Для I/O Bound задач количество потоков может превышать число ядер (N*2)
        self.max_workers = max_workers

        # Инстанцируем Thread-Safe компоненты в главном потоке
        self.processor = AudioProcessor()
        self.normalizer = MetadataNormalizer()
        self.validator = MetadataValidator()
        self.cue_parser = CueParser()  # Инициализируем парсер

        self.progress_callback = None
        self.completion_callback = None
        self.logger.info(f"ScannerService I/O готов. Потоков (threads): {self.max_workers}")

    def set_callbacks(self, progress_callback: Optional[Callable], completion_callback: Optional[Callable]) -> None:
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

    def _worker_extract_tags(self, file_path: Path, is_multi: bool = False) -> tuple[Path, Optional[dict], str]:
        """
        Изолированная I/O задача.
        Извлекает теги, нормализует и возвращает плоский DTO-словарь.
        """
        if self.stop_event.is_set():
            return file_path, None, "stopped"

        try:
            # 1. Syscall I/O (Освобождает GIL)
            metadata = self.processor.extract_unified_metadata(file_path)

            # 2. Быстрая CPU-валидация
            models_found, errors = self.validator.validate(metadata, file_path)
            if not models_found:
                return file_path, None, f"Skip: {errors}"

            # 3. Нормализация
            norm_metadata = self.normalizer.normalize(metadata, file_path)

            # 4. Сливаем данные: технические параметры (ID3) + чистые теги
            metadata.update(norm_metadata)
            metadata["_models_found"] = models_found
            metadata["_is_multi"] = is_multi

            return file_path, metadata, "ok"

        except ValueError as ve:
            return file_path, None, f"Unpack Error: {ve}"
        except Exception as e:
            return file_path, None, f"Error: {e}"

    def _collect_cue(self, directory: Path) -> dict[Path, list[dict]]:
        """Ищет CUE файлы и парсит их структуру."""
        if not self.cue_analyze:
            return {}

        cue_data = {}
        for cue_file in directory.rglob("*.cue"):
            if not cue_file.is_file():
                continue

            try:
                # Используем правильно инициализированный парсер
                tracks, _, _, _, _ = self.cue_parser.parse_cue(cue_file)
                if not tracks:
                    continue

                file_tracks = {}
                for track in tracks:
                    file_name = track.get("file")
                    if not file_name:
                        continue
                    audio_file = (cue_file.parent / file_name).resolve()
                    file_tracks.setdefault(audio_file, []).append(track)

                for audio_file, t_list in file_tracks.items():
                    if len(t_list) > 1:
                        cue_data[audio_file] = t_list

            except Exception as e:
                self.logger.error(f"Ошибка парсинга CUE {cue_file.name}: {e}")

        return cue_data

    def _collect_files(self, directory: Path, cue_data: dict[Path, list[dict]]) -> list[Path]:
        """Собирает все аудиофайлы, строго фильтруя директории-обманки."""
        files = []
        for audio_file in directory.rglob("*"):
            if audio_file.is_file() and audio_file.suffix.upper().lstrip(".") in self.AUDIO_EXTENSIONS:
                if audio_file in cue_data:
                    continue
                files.append(audio_file)
        return files

    def scan_directory(self, directory: Path) -> list[dict]:
        """
        Главный I/O оркестратор.
        ВОЗВРАЩАЕТ: Список плоских словарей (DTO) для помещения в Staging Area (ОЗУ).
        БАЗА ДАННЫХ ЗДЕСЬ НЕ ИСПОЛЬЗУЕТСЯ.
        """
        self.logger.info(f"Начало I/O сканирования: {directory}")

        cue_data = self._collect_cue(directory)
        single_files = self._collect_files(directory, cue_data)

        # Вычисляем бизнес-метрики (Файлы vs Треки)
        total_files = len(cue_data) + len(single_files)
        total_tracks = len(single_files) + sum(len(tracks) for tracks in cue_data.values())

        self.logger.info(f"Найдено: {len(single_files)} синглов, {len(cue_data)} мультитреков (Файлов: {total_files}, Треков: {total_tracks})")

        if total_files == 0:
            return []

        staged_dtos: list[dict] = []
        processed_files = 0
        processed_tracks = 0

        # Возвращаем ThreadPoolExecutor для максимального I/O Throughput
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            # Постановка задач
            for file_path in single_files:
                futures.append(executor.submit(self._worker_extract_tags, file_path, False))

            for file_path in cue_data.keys():
                if file_path.exists():
                    futures.append(executor.submit(self._worker_extract_tags, file_path, True))

            # Сбор DTO
            for future in as_completed(futures):
                if self.stop_event.is_set():
                    self.logger.info("⏹ I/O Сканирование прервано пользователем.")
                    break

                try:
                    file_path, metadata, status = future.result()
                    processed_files += 1

                    if status == "ok" and metadata:
                        # Временно сохраняем оригинальный track_data для CUE
                        if metadata.get("_is_multi"):
                            tracks_in_cue = cue_data.get(file_path, [])
                            metadata["_cue_tracks"] = tracks_in_cue
                            processed_tracks += len(tracks_in_cue)
                        else:
                            processed_tracks += 1

                        staged_dtos.append(metadata)
                    else:
                        self.logger.warning(f"Файл {file_path.name} пропущен: {status}")

                except Exception as e:
                    self.logger.error(f"Сбой future в I/O потоке: {e}", exc_info=True)

                self._report_progress(processed_files, total_files, processed_tracks, total_tracks)

        self.logger.info(f"✅ I/O Сканирование завершено. Подготовлено DTO: {len(staged_dtos)}")

        # Отдаем плоские данные в ViewModel (Staging Area)
        if self.completion_callback and not self.stop_event.is_set():
            self.completion_callback(staged_dtos)

        return staged_dtos

    def _report_progress(self, current_files: int, total_files: int, current_tracks: int, total_tracks: int) -> None:
        """Потокобезопасная отправка прогресса I/O операций с метриками треков."""
        if self.progress_callback:
            try:
                progress = (current_files / total_files) if total_files > 0 else 0
                self.progress_callback(
                    {
                        "processed_files": current_files,
                        "total_files": total_files,
                        "processed_tracks": current_tracks,
                        "total_tracks": total_tracks,
                        "progress": progress,
                        "stage": "I/O Ingestion",
                    }
                )
            except Exception as e:
                self.logger.error(f"UI Callback Error: {e}")
