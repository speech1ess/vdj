import os
import tempfile
import warnings
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Any, Optional

from core.models.enums import MusicalKey
from core.services.logging import get_logger


def _init_dsp_worker():
    """
    Инициализатор дочернего процесса (Warm Start).
    ГАРАНТИЯ ПОТОКОБЕЗОПАСНОСТИ IPC:
    Изолирует C-контекст Numba/LLVM для каждого процесса ОС.
    """
    # 1. Глушим OpenMP (защита от CPU Thrashing)
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    os.environ["NUMBA_NUM_THREADS"] = "1"

    # 2. Уникальный JIT-кэш для обхода блокировок файлов в Windows
    worker_id = os.getpid()
    cache_dir = Path(tempfile.gettempdir()) / f"playlist_ai_numba_{worker_id}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache_dir)


def _worker_dsp_task(dto: dict[str, Any], duration: int = 60) -> tuple[str, float, Optional[str], str]:
    """
    Изолированная CPU Bound задача (Heavy Math).
    Работает в отдельном адресном пространстве ОС. Возвращает примитивы.
    """
    file_path = dto.get("file_path")
    if not file_path:
        return "", 0.0, None, "Skip: Пустой путь"

    try:
        # Lazy Import: загружаем тяжелую C-библиотеку только внутри форка
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import librosa
            import numpy as np

        # Сводим в моно и делаем ресэмпл до 22050Hz (Оптимизация RAM)
        y, sr = librosa.load(file_path, sr=22050, mono=True, duration=duration)

        # Защита от битых кадров и цифровой тишины (Numba Zero-Division Protection)
        y = np.nan_to_num(y.astype(np.float32))
        if np.max(np.abs(y)) < 1e-4:
            return file_path, 0.0, None, "ok"

        # Трекинг бита
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = round(float(tempo[0] if isinstance(tempo, (list, tuple)) or hasattr(tempo, "shape") else tempo), 1)

        # Хромаграмма (тональность)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        key_idx = int(chroma.mean(axis=1).argmax())

        # Маппинг тональности
        key_order = [k for k in MusicalKey if not k.name.endswith("_alt")]
        key_str = key_order[key_idx].value if 0 <= key_idx < len(key_order) else None

        return file_path, bpm, key_str, "ok"

    except Exception as e:
        return file_path, 0.0, None, f"Error: {e}"


class DSPEnrichmentService:
    """
    Оркестратор математического анализа (Stage 2: Heavy CPU).
    Принимает плоские DTO, прогоняет их через ProcessPoolExecutor
    и возвращает обогащенные DTO.
    """

    def __init__(self, stop_event: Optional[Event] = None, max_workers: int = 4):
        self.logger = get_logger("PlaylistAI.DSPService")
        self.stop_event = stop_event or Event()
        # Для CPU Bound задач потоков не должно быть больше физических ядер (обычно 4-6)
        self.max_workers = max_workers
        self.progress_callback = None
        self.logger.info(f"DSPEnrichmentService инициализирован. Ядра: {self.max_workers}")

    def set_callbacks(self, progress_callback: Optional[Callable]) -> None:
        self.progress_callback = progress_callback

    def process_dtos(self, dtos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Прогоняет DTO через математический аппарат.
        Мутирует исходные словари, обогащая их расчетами.
        """
        # Фильтруем треки: берем только те, где нет BPM
        # (или если ты решишь всегда принудительно пересчитывать, можно убрать условие)
        tasks = [dto for dto in dtos if not dto.get("bpm")]
        total_tasks = len(tasks)

        if total_tasks == 0:
            self.logger.info("Нет задач для DSP анализа.")
            return dtos

        self.logger.info(f"🚀 Старт DSP анализа (Warm Pool). Задач: {total_tasks}")
        processed = 0

        # Индексируем DTO по пути для быстрого O(1) обновления
        dto_map = {dto["file_path"]: dto for dto in dtos}

        with ProcessPoolExecutor(max_workers=self.max_workers, initializer=_init_dsp_worker) as executor:
            futures = [executor.submit(_worker_dsp_task, dto) for dto in tasks]

            for future in as_completed(futures):
                if self.stop_event.is_set():
                    self.logger.warning("⏹ DSP Анализ прерван пользователем.")
                    break

                try:
                    file_path, bpm, key, status = future.result()
                    processed += 1

                    if status == "ok" and file_path in dto_map:
                        # Обогащаем (мутируем) DTO в Staging Area
                        dto_map[file_path]["bpm"] = bpm
                        dto_map[file_path]["key"] = key
                    elif status != "ok":
                        self.logger.warning(f"Сбой DSP для {Path(file_path).name}: {status}")

                except Exception as e:
                    self.logger.error(f"Сбой future в пуле DSP: {e}", exc_info=True)

                self._report_progress(processed, total_tasks)

        self.logger.info("🏁 DSP Анализ успешно завершен.")
        return dtos

    def _report_progress(self, current: int, total: int) -> None:
        if self.progress_callback:
            try:
                progress = (current / total) if total > 0 else 0
                self.progress_callback({"processed_files": current, "total_files": total, "progress": progress, "stage": "DSP Math"})
            except Exception as e:
                self.logger.error(f"UI Callback Error: {e}")
