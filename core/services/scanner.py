from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Optional, Union

from core.models.audiofile import AudioFile
from core.models.enums import AudioFormat
from core.models.track import Track
from core.services.audio_processor import AudioProcessor
from core.services.cache import CacheManager, ObjFactory
from core.services.logging import get_logger
from core.services.metadata_tools import MetadataNormalizer, MetadataValidator


def _worker_process_file(file_path: Path, track_data: Optional[list[dict]] = None) -> Union[tuple[Path, Optional[dict], list[dict]], str, None]:
    """
    Изолированная функция для ProcessPool.
    Выполняет тяжелый I/O (чтение заголовков) и CPU (librosa) анализ вне главного потока.
    Возвращает сырые словари, которые легко сериализуются (Pickle) между процессами.
    """
    processor = AudioProcessor()
    normalizer = MetadataNormalizer()
    validator = MetadataValidator()

    try:
        # Извлечение
        if track_data and len(track_data) > 1:
            # Мультитрек (CUE)
            # Внимание: для мультитрека мы передаем track_data в AudioProcessor
            audio_file_dto, track_dtos = processor.process_audio_file(file_path, track_data, contains_multiple_tracks=True)
            # Сериализуем обратно в словари для IPC передачи
            return (
                file_path,
                vars(audio_file_dto) if audio_file_dto else None,
                [vars(t) for t in track_dtos],
                "ok",
            )

        else:
            # Сингл файл
            metadata = processor.extract_unified_metadata(file_path)

            # Валидация
            models_found, errors = validator.validate(metadata, file_path)
            if not models_found:
                return file_path, None, None, f"Skip: {errors}"

            # Нормализация
            norm_metadata = normalizer.normalize(metadata, file_path)

            # Упаковываем метаданные и список найденных моделей
            norm_metadata["_models_found"] = models_found
            return file_path, norm_metadata, None, "ok"

    except Exception as e:
        return file_path, None, None, f"Error: {e}"


class ScannerService:
    """
    Высокопроизводительный сервис сканирования файловой системы.
    Использует ProcessPoolExecutor для обхода GIL и утилизации всех ядер CPU.
    """

    AUDIO_EXTENSIONS = {fmt.value for fmt in AudioFormat}

    def __init__(self, cue_analyze: bool = True, stop_event: Optional[Event] = None, max_workers: int = 4):
        self.logger = get_logger("PlaylistAI.ScannerService")
        self.cue_analyze = cue_analyze
        self.stop_event = stop_event or Event()
        self.max_workers = max_workers

        # Объекты, работающие только в главном процессе
        self.processor = AudioProcessor()  # Для парсинга CUE в главном потоке
        self.cache_manager = CacheManager()
        self.obj_factory = ObjFactory(self.cache_manager)

        self.progress_callback = None
        self.completion_callback = None
        self.logger.info(f"ScannerService готов. Ядра (workers): {self.max_workers}")

    def set_callbacks(self, progress_callback: Optional[Callable], completion_callback: Optional[Callable]) -> None:
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

    def _collect_cue(self, directory: Path) -> dict[Path, list[dict]]:
        """Ищет CUE файлы и парсит их структуру (легковесная задача, главный поток)."""
        if not self.cue_analyze:
            return {}

        cue_data = {}
        for cue_file in directory.rglob("*.cue"):
            try:
                tracks, _, _, _, _ = self.processor.cue_parser.parse_cue(cue_file)
                if not tracks:
                    continue

                # Группируем треки по физическим аудиофайлам
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
        """Собирает все аудиофайлы, исключая те, что уже попали в мультитреки."""
        files = []
        for audio_file in directory.rglob("*"):
            if audio_file.suffix.upper().lstrip(".") in self.AUDIO_EXTENSIONS:
                if audio_file in cue_data:
                    continue  # Пропускаем, так как файл пойдет как мультитрек
                files.append(audio_file)
        return files

    def scan_directory(self, directory: Path) -> dict[Path, list[Track]]:
        """
        Главный оркестратор.
        Раздает задачи в ProcessPool, агрегирует результаты и собирает ORM кэш.
        """
        self.logger.info(f"Начало сканирования: {directory}")

        # 1. Инвентаризация
        cue_data = self._collect_cue(directory)
        single_files = self._collect_files(directory, cue_data)

        total_tasks = len(cue_data) + len(single_files)
        self.logger.info(f"Найдено: {len(single_files)} одиночных файлов, {len(cue_data)} мультитреков (Всего задач: {total_tasks})")

        if total_tasks == 0:
            return {}

        results: dict[Path, list[Track]] = {}
        processed_files = 0
        processed_tracks = 0

        # 2. Выполнение в пуле процессов (ProcessPoolExecutor для обхода GIL)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            # Запускаем мультитреки
            for file_path, tracks_data in cue_data.items():
                if file_path.exists():
                    futures.append(executor.submit(_worker_process_file, file_path, tracks_data))

            # Запускаем синглы
            for file_path in single_files:
                futures.append(executor.submit(_worker_process_file, file_path, None))

            # 3. Асинхронный сбор результатов в главном потоке
            for future in as_completed(futures):
                if self.stop_event.is_set():
                    self.logger.info("⏹ Сканирование прервано пользователем. Очистка пула...")
                    for f in futures:
                        f.cancel()
                    break

                try:
                    file_path, audio_data, track_list, status = future.result()
                    processed_files += 1

                    if status != "ok":
                        self.logger.warning(f"Файл {file_path.name} пропущен: {status}")
                        self._report_progress(processed_files, total_tasks, processed_tracks)
                        continue

                    # 4. Сборка ORM-объектов в главном потоке (сохраняем консистентность кэша)
                    if track_list is not None:
                        # Мультитрек (уже предсобран в DTO словари воркером)
                        # В данной архитектуре мы просто конвертируем словари обратно в объекты
                        # TODO: Проработать загрузку мультитреков в кэш более элегантно
                        audio_obj = AudioFile.from_dict(audio_data)
                        track_objs = [Track.from_dict(t) for t in track_list]
                        for t in track_objs:
                            t.audiofile = audio_obj

                        results[file_path] = track_objs
                        processed_tracks += len(track_objs)
                    else:
                        # Сингл файл (сырые метаданные пришли из воркера)
                        models_found = audio_data.pop("_models_found", ["Track", "AudioFile", "Album", "Artist", "Genre"])

                        audio_obj, track_objs = self.obj_factory.create_objects(file_path, audio_data, models_found)
                        results[file_path] = track_objs
                        processed_tracks += len(track_objs)

                except Exception as e:
                    self.logger.error(f"Сбой при обработке future результата: {e}")

                self._report_progress(processed_files, total_tasks, processed_tracks)

        self.logger.info(f"✅ Сканирование завершено. Обработано {processed_files} файлов, сгенерировано {processed_tracks} треков.")

        if self.completion_callback and not self.stop_event.is_set():
            # Формируем плоский список треков для UI
            flat_tracks = [track for track_list in results.values() for track in track_list]
            self.completion_callback(flat_tracks)

        return results

    def _report_progress(self, current: int, total: int, total_tracks: int) -> None:
        """Отправка прогресса без блокирующих мьютексов."""
        if self.progress_callback:
            try:
                progress = (current / total) if total > 0 else 0
                self.progress_callback(
                    {
                        "processed_files": current,
                        "total_files": total,
                        "processed_tracks": total_tracks,
                        "progress": progress,
                    }
                )
            except Exception as e:
                self.logger.error(f"UI Callback Error: {e}")
