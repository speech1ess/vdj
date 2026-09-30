import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.repositories.repo import Repo
from core.services.scanner import ScannerService
from core.viewmodels.basevwm import BaseViewModel


class ScanViewModel(BaseViewModel):
    """
    ViewModel для экрана сканирования.
    Управляет процессом фонового сканирования без жесткой привязки к Tkinter.
    """

    def __init__(self, configurator, log_callback=None):
        super().__init__(configurator=configurator, log_callback=log_callback)
        self.folder_path: Optional[Path] = None

        # Сканер инициализируется без GUI-коллбэков
        self.scanner = ScannerService(cue_analyze=True, stop_event=threading.Event())
        self.scanning_thread = None
        self.scan_event = self.scanner.stop_event
        self.is_scanning = False

        self.results_raw = {}
        self.result_tracks = []

        # Ссылка на кэш фабрики
        self.cache = self.scanner.obj_factory.cache

        self.progress_callback = None
        self.completion_callback = None

    def set_callbacks(
        self,
        progress_callback: Callable[[dict[str, Any]], None],
        completion_callback: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        """
        Установка коллбэков для UI.
        ВНИМАНИЕ: Слой View должен сам оборачивать свои коллбэки в root.after(0, ...),
        чтобы обеспечить потокобезопасность Tkinter. ViewModel этим не занимается.
        """
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self.scanner.set_callbacks(self._on_scanner_progress, None)

    def _on_scanner_progress(self, progress_data: dict[str, Any]) -> None:
        """Перехватчик прогресса из сервиса сканера."""
        if self.progress_callback:
            try:
                self.progress_callback(progress_data)
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

            # Сбрасываем прогресс-бар в UI
            if self.progress_callback:
                self.progress_callback(
                    {
                        "progress": 0,
                        "processed_files": 0,
                        "total_files": 0,
                        "processed_tracks": 0,
                        "total_tracks": 0,
                    }
                )

    def save_results(self) -> bool:
        """Сохранение результатов сканирования через паттерн Unit of Work."""
        if not self.result_tracks:
            self.set_status("⚠️ Нет данных для сохранения")
            return False

        try:
            self.set_status("⏳ Идет сохранение в базу данных...")
            self.logger.info(f"Передаём {len(self.result_tracks)} треков в Repo для атомарного сохранения.")

            # Repo отвечает за сохранение ORM графа за одну транзакцию
            repo = Repo(self.configurator, self.cache)
            success = repo.save_data(self.result_tracks)

            if success:
                self.set_status("✅ Результаты успешно сохранены в БД!")
                self.cache.clear()  # Очищаем ОЗУ после успешного коммита
            else:
                self.set_status("❌ Критическая ошибка сохранения (см. логи).")

            return success

        except Exception as e:
            self.logger.error(f"❌ Exception при сохранении данных: {e}", exc_info=True)
            self.set_status("❌ Сбой при записи в БД.")
            return False

    def start_scan(self):
        if not self.folder_path or not self.folder_path.is_dir():
            self.set_status("❌ Не выбрана или недоступна папка для сканирования.")
            if self.progress_callback:
                self.progress_callback(
                    {
                        "progress": 0,
                        "processed_files": 0,
                        "total_files": 0,
                        "processed_tracks": 0,
                        "total_tracks": 0,
                    }
                )
            return

        self.set_status(f"🔍 Сканирование: {self.folder_path.name}...")
        self.is_scanning = True
        self.results_raw = {}
        self.scan_event.clear()

        def scan_worker():
            """Фоновый воркер для оркестрации сканера."""
            try:
                self.results_raw = self.scanner.scan_directory(self.folder_path)
            except Exception as e:
                self.logger.error(f"⚠️ Критический сбой сканирования: {e}", exc_info=True)
            finally:
                self.is_scanning = False

                # Плоский список ORM-объектов треков (нужен для сохранения)
                self.result_tracks = [track for tracks in self.results_raw.values() for track in tracks]

                # Трансляция в DTO для безопасной отрисовки в UI
                display_data = self._prepare_display_data()

                if self.completion_callback and not self.scan_event.is_set():
                    try:
                        self.completion_callback(display_data)
                    except Exception as e:
                        self.logger.error(f"UI Completion Callback Error: {e}")

        # Запускаем оркестратор в отдельном потоке,
        # внутри которого ScannerService поднимет ProcessPoolExecutor
        self.scanning_thread = threading.Thread(target=scan_worker, daemon=True)
        self.scanning_thread.start()

    def _prepare_display_data(self) -> list[dict[str, Any]]:
        """Транслирует ORM объекты в плоские DTO словари (Data Transfer Objects) для UI."""
        display_data = []
        for file_path, tracks in self.results_raw.items():
            for track in tracks:
                # Берем связи напрямую из объектов (избавление от O(N^2) поиска по кэшу)
                artist_names = ", ".join(a.name for a in track.artists) if hasattr(track, "artists") and track.artists else "Unknown Artist"
                album_titles = ", ".join(a.title for a in track.albums) if hasattr(track, "albums") and track.albums else "Unknown Album"
                genre_names = ", ".join(g.name for g in track.genres) if hasattr(track, "genres") and track.genres else "Unknown Genre"

                key_val = track.key.value if hasattr(track.key, "value") else str(track.key or "")

                display_data.append(
                    {
                        "id": track.id,
                        "title": track.title or "Unknown",
                        "duration": track.duration or 0,
                        "bpm": track.bpm or "",
                        "key": key_val,
                        "disc_number": track.disc_number or 1,
                        "track_number": track.track_number or 1,
                        "artists": artist_names,
                        "albums": album_titles,
                        "genres": genre_names,
                        "file_path": str(file_path),
                    }
                )
        return display_data
