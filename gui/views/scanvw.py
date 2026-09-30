import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from core.services.csv_svc import CSVService
from core.viewmodels.scanvwm import ScanViewModel
from gui.views.basevw import BaseView


class ScanView(BaseView):
    """Представление для сканирования аудиофайлов."""

    UI_UPDATE_THROTTLE = 0.05  # ~20 FPS для защиты Tkinter от перегрузки

    def __init__(self, root, parent, viewmodel: ScanViewModel, log_callback=None):
        super().__init__(
            root=root, parent=parent, viewmodel=viewmodel, status_callback=log_callback
        )
        self.last_update_time = 0.0

        self.viewmodel.set_callbacks(
            progress_callback=self._safe_update_progress,
            completion_callback=self._safe_on_scan_complete,
        )
        self.create_ui()

    def create_ui(self):
        """Создает элементы пользовательского интерфейса."""
        main_frame = ttk.Frame(self.content_frame, padding=10)
        main_frame.pack(expand=True, fill=tk.BOTH)

        results_frame = ttk.LabelFrame(main_frame, text="Результаты сканирования")
        results_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        columns = ("title", "artist", "album", "genre", "bpm", "key", "path")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", selectmode="none")

        self.tree.heading("title", text="Название")
        self.tree.heading("artist", text="Исполнитель")
        self.tree.heading("album", text="Альбом")
        self.tree.heading("genre", text="Жанр")
        self.tree.heading("bpm", text="BPM")
        self.tree.heading("key", text="Key")
        self.tree.heading("path", text="Путь к файлу")

        self.tree.column("bpm", width=50, anchor=tk.CENTER)
        self.tree.column("key", width=50, anchor=tk.CENTER)
        self.tree.column("path", width=300)

        tree_scroll_y = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(expand=True, fill=tk.BOTH)

        folder_frame = ttk.Frame(main_frame)
        folder_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(folder_frame, text="Выбранная папка:").pack(side=tk.LEFT, padx=5)
        self.folder_label = ttk.Label(folder_frame, text="Не выбрана", foreground="gray")
        self.folder_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=5)

        self.percent_label = ttk.Label(progress_frame, text="0.0%", width=8)
        self.percent_label.pack(side=tk.LEFT, padx=(0, 5))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, length=300, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.counter_label = ttk.Label(progress_frame, text="0 / 0 файлов")
        self.counter_label.pack(side=tk.RIGHT, padx=5)

        self.controls_frame = ttk.Frame(main_frame)
        self.controls_frame.pack(pady=10)

        self.select_folder_button = ttk.Button(
            self.controls_frame, text="Выбрать папку", command=self.select_folder
        )
        self.select_folder_button.grid(row=0, column=0, padx=5)

        self.scan_button = ttk.Button(
            self.controls_frame, text="▶ Сканировать", command=self.start_scan, state=tk.DISABLED
        )
        self.scan_button.grid(row=0, column=1, padx=5)

        self.cancel_button = ttk.Button(
            self.controls_frame, text="⏹ Отмена", command=self.cancel_scan, state=tk.DISABLED
        )
        self.cancel_button.grid(row=0, column=2, padx=5)

        self.clear_button = ttk.Button(
            self.controls_frame, text="🗑 Очистить", command=self.clear_results
        )
        self.clear_button.grid(row=0, column=3, padx=5)

        self.save_csv_button = ttk.Button(
            self.controls_frame, text="💾 Сохранить CSV", command=self.save_csv, state=tk.DISABLED
        )
        self.save_csv_button.grid(row=1, column=0, padx=5, pady=5)

        self.load_csv_button = ttk.Button(
            self.controls_frame, text="📂 Загрузить CSV", command=self.load_csv
        )
        self.load_csv_button.grid(row=1, column=1, padx=5, pady=5)

        self.save_button = ttk.Button(
            self.controls_frame,
            text="💾 Сохранить в БД",
            command=self.save_results,
            state=tk.DISABLED,
        )
        self.save_button.grid(row=1, column=3, padx=5, pady=5)

        if self.viewmodel.folder_path:
            self.folder_label.config(text=str(self.viewmodel.folder_path), foreground="black")
            self.scan_button.config(state=tk.NORMAL)

    def select_folder(self) -> None:
        folder = filedialog.askdirectory(title="Выберите каталог с музыкой", parent=self.root)
        if folder:
            self.viewmodel.set_folder(folder)
            self.folder_label.config(text=folder, foreground="black")
            self.scan_button.config(state=tk.NORMAL)
            self.update_status(f"Выбрана папка для сканирования: {folder}")

    def start_scan(self) -> None:
        self.scan_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.DISABLED)
        self.update_status("Начинаем сканирование...")
        self.viewmodel.start_scan()

    def cancel_scan(self) -> None:
        self.cancel_button.config(state=tk.DISABLED)
        self.update_status("Остановка сканера...")
        self.viewmodel.cancel_scan()

    def clear_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.progress_var.set(0)
        self.percent_label.config(text="0.0%")
        self.counter_label.config(text="0 / 0 файлов")
        self.save_button.config(state=tk.DISABLED)
        self.save_csv_button.config(state=tk.DISABLED)
        self.update_status("Результаты очищены")

    def save_csv(self):
        if not hasattr(self.viewmodel, "result_tracks") or not self.viewmodel.result_tracks:
            self.update_status("⚠️ Нет данных для сохранения!")
            return

        output_dir = getattr(self.viewmodel.configurator, "output_dir", "./data")
        file_path = os.path.join(output_dir, f"{time.strftime('%Y%m%d-%H%M%S')}_scan.csv")

        def _bg_save():
            os.makedirs(output_dir, exist_ok=True)
            csv_service = CSVService()
            # Конвертируем ORM-треки в словари для CSV
            success = csv_service.save_to_csv(self.viewmodel.result_tracks, file_path)
            self.root.after(0, lambda: self._on_csv_saved(success, file_path))

        threading.Thread(target=_bg_save, daemon=True).start()

    def _on_csv_saved(self, success: bool, path: str):
        if success:
            self.update_status(f"✅ CSV сохранён: {path}")
        else:
            self.update_status(f"❌ Ошибка при сохранении {path}")

    def load_csv(self):
        file_path = filedialog.askopenfilename(
            title="Выберите CSV-файл",
            filetypes=[("CSV файлы", "*.csv")],
            initialdir=getattr(self.viewmodel.configurator, "output_dir", "./data"),
            parent=self.root,
        )
        if not file_path:
            return

        def _bg_load():
            csv_service = CSVService()
            raw_tracks = csv_service.load_from_csv(file_path)
            self.root.after(0, lambda: self.display_results(raw_tracks))

        threading.Thread(target=_bg_load, daemon=True).start()

    def save_results(self) -> None:
        self.save_button.config(state=tk.DISABLED, text="⏳ Сохранение...")
        self.update_status("Начато сохранение в медиатеку...")

        def _bg_save_db():
            success = self.viewmodel.save_results()
            self.root.after(0, lambda: self._on_db_saved(success))

        threading.Thread(target=_bg_save_db, daemon=True).start()

    def _on_db_saved(self, success: bool):
        if success:
            self.save_button.config(text="✅ Сохранено в БД")
            self.update_status("Результаты успешно сохранены в БД.")
        else:
            self.save_button.config(state=tk.NORMAL, text="Сохранить в БД")
            self.update_status("Ошибка при сохранении данных в БД.")

    def _safe_update_progress(self, progress_data: dict) -> None:
        current_time = time.time()
        if (current_time - self.last_update_time > self.UI_UPDATE_THROTTLE) or (
            progress_data["progress"] >= 1.0
        ):
            self.last_update_time = current_time
            self.root.after(0, lambda: self._render_progress(progress_data))

    def _render_progress(self, progress_data: dict) -> None:
        try:
            progress = max(0, min(progress_data["progress"] * 100, 100))
            processed_files = progress_data["processed_files"]
            total_files = progress_data["total_files"]
            processed_tracks = progress_data["processed_tracks"]
            progress_data["total_tracks"]

            self.progress_var.set(progress)
            self.percent_label.config(text=f"{progress:.1f}%")

            if total_files > 0:
                self.counter_label.config(
                    text=f"{processed_files}/{total_files} файлов | {processed_tracks} треков"
                )
            else:
                self.counter_label.config(text="Идёт сканирование...")
        except tk.TclError:
            pass

    def finish_scan(self) -> None:
        try:
            self.scan_button.config(state=tk.NORMAL)
            self.cancel_button.config(state=tk.DISABLED)
            if getattr(self.viewmodel, "result_tracks", None):
                self.save_button.config(state=tk.NORMAL)
                self.save_csv_button.config(state=tk.NORMAL)
            else:
                self.save_button.config(state=tk.DISABLED)
                self.save_csv_button.config(state=tk.DISABLED)
            self.update_status("Сканирование завершено")
        except tk.TclError as e:
            self.logger.error(f"Ошибка финализации UI: {e}")

    def display_results(self, result: Any) -> None:
        """Отображение результатов с Fast Insert."""
        try:
            self.tree.delete(*self.tree.get_children())
        except tk.TclError as e:
            self.logger.error(f"Ошибка очистки Treeview: {e}")
            return

        if not result:
            self.update_status("Сканирование завершено. Треки не найдены.")
            self.finish_scan()
            return

        # Fast Insert (отключение перерисовки для мгновенного заполнения таблицы)
        self.tree.detach_children("")

        for track in result:
            # Поддерживаем как словари (из CSV), так и ORM объекты (из сканера)
            if isinstance(track, dict):
                path = track.get("file_path", "")
                artists = track.get("artists", "")
                albums = track.get("albums", "")
                title = track.get("title", "")
                genre = track.get("genres", "")
                bpm = track.get("bpm", 0)
                key = track.get("key", "")
            else:
                path = getattr(track, "audiofile", None)
                path = getattr(path, "file_path", "") if path else ""
                artists = ", ".join(a.name for a in getattr(track, "artists", []))
                albums = ", ".join(a.title for a in getattr(track, "albums", []))
                title = getattr(track, "title", "Unknown")
                genre = ", ".join(g.name for g in getattr(track, "genres", []))
                bpm = getattr(track, "bpm", 0) or 0
                key = getattr(track, "key", "")
                key = key.value if hasattr(key, "value") else str(key or "")

            self.tree.insert("", "end", values=(title, artists, albums, genre, bpm, key, path))

        self.finish_scan()
