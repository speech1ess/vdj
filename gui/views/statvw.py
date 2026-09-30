# gui/views/statvw.py
import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core.viewmodels.statvwm import StatisticsViewModel
from gui.views.basevw import BaseView


class StatisticsView(BaseView):
    def __init__(self, root, parent, viewmodel: StatisticsViewModel, log_callback=None):
        super().__init__(root=root, parent=parent, viewmodel=viewmodel, log_callback=log_callback)
        # Храним ссылки на графики для ручной очистки памяти (Garbage Collection)
        self._figures = []
        self.create_view()

    def destroy(self) -> None:
        """Очищаем C++ ресурсы Matplotlib при переключении экрана."""
        import matplotlib.pyplot as plt

        for fig in self._figures:
            plt.close(fig)
        self._figures.clear()
        super().destroy()

    def create_bpm_density_chart(self, parent, bpm_values):
        if not bpm_values:
            bpm_values = [120]

        bg_color = "#f0f0f0"
        fig = Figure(figsize=(8, 3), dpi=100)
        self._figures.append(fig)  # Сохраняем для GC

        fig.patch.set_facecolor(bg_color)
        ax = fig.add_subplot(111)
        ax.set_facecolor(bg_color)

        ax.hist(bpm_values, bins=20, color="skyblue", alpha=0.7, edgecolor="black")
        ax.set_title("BPM", fontsize=10)
        ax.set_xlabel("BPM")
        ax.set_ylabel("Треки")

        for spine in ax.spines.values():
            spine.set_color("#cccccc")

        ax.tick_params(colors="#666666")
        ax.title.set_color("#333333")
        ax.xaxis.label.set_color("#666666")
        ax.yaxis.label.set_color("#666666")

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.Y, expand=False, pady=10, padx=10)

    def create_genre_barchart(self, parent, genres):
        if not genres:
            genres = {"Нет данных": 1}

        bg_color = "#f0f0f0"
        fig = Figure(figsize=(16, 4), dpi=100)
        self._figures.append(fig)  # Сохраняем для GC

        fig.patch.set_facecolor(bg_color)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.2)

        ax = fig.add_subplot(111)
        ax.set_facecolor(bg_color)

        # Сортируем жанры для красивого вывода
        sorted_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:15]
        genre_names = [g[0] for g in sorted_genres]
        genre_counts = [g[1] for g in sorted_genres]

        colors = [
            "#3DCBA9",
            "#09FF78",
            "#FB9893",
            "#A5AFE9",
            "#EAE0A4",
            "#EB47BC",
            "#89A99B",
            "#97C1C9",
            "#E6EF71",
        ]
        bars = ax.bar(
            genre_names,
            genre_counts,
            width=0.8,
            color=colors * (len(genre_names) // len(colors) + 1),
        )

        ax.set_ylabel("Треки")
        max_count = max(genre_counts) if genre_counts else 1
        ax.set_ylim(0, max_count * 1.2)

        # Подписи столбцов
        ax.set_xticks(range(len(genre_names)))
        ax.set_xticklabels(genre_names, rotation=45, ha="right", fontsize=8, color="black")

        for bar, count in zip(bars, genre_counts, strict=False):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max_count * 0.02),
                str(count),
                ha="center",
                va="bottom",
                fontsize=8,
                color="black",
            )

        for spine in ax.spines.values():
            spine.set_color("#cccccc")

        ax.tick_params(axis="y", colors="#666666")
        ax.title.set_color("#333333")
        ax.yaxis.label.set_color("#666666")

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=5, padx=0)

    def create_no_data_view(self, message):
        """
        Создает представление с сообщением об отсутствии данных.
        """
        self.frame = ttk.Frame(self.content_frame, padding=20)  # Используем self.content_frame
        self.frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(self.frame, text="Статистика", font=("Arial", 20, "bold")).pack(pady=10)

        ttk.Label(self.frame, text=message, font=("Arial", 12)).pack(pady=50)

    def create_welcome_view(self):
        """Создает приветственное представление."""
        self.frame = ttk.Frame(self.content_frame, padding=20)
        self.frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            self.frame, text="Добро пожаловать в Playlist AI", font=("Arial", 24, "bold")
        ).pack(pady=20)

        description = """
        Playlist AI — это инструмент для создания персонализированных музыкальных плейлистов.

        Программа сканирует каталог аудиофайлов, извлекает метаданные, такие как BPM,
        жанр и музыкальный ключ, и генерирует плейлисты на основе ваших предпочтений.

        Для начала работы выберите один из разделов в меню слева.
        """
        ttk.Label(self.frame, text=description, wraplength=600, justify=tk.LEFT).pack(pady=10)

        actions_frame = ttk.LabelFrame(self.frame, text="Быстрые действия", padding=10)
        actions_frame.pack(fill=tk.X, pady=20)

        ttk.Button(actions_frame, text="Сканировать аудиофайлы", command=self.on_scan_click).pack(
            side=tk.LEFT, padx=10, pady=10
        )

        ttk.Button(
            actions_frame, text="Управление плейлистами", command=self.on_playlists_click
        ).pack(side=tk.LEFT, padx=10, pady=10)

        ttk.Button(actions_frame, text="Настройки", command=self.on_settings_click).pack(
            side=tk.LEFT, padx=10, pady=10
        )

    def on_scan_click(self):
        """Обработчик нажатия кнопки 'Сканировать аудиофайлы'."""
        # Переключаем на экран сканера через MainViewModel
        self.viewmodel.switch_view("scanner")

    def on_playlists_click(self):
        """Обработчик нажатия кнопки 'Управление плейлистами'."""
        self.viewmodel.switch_view("playlists")

    def on_settings_click(self):
        """Обработчик нажатия кнопки 'Настройки'."""
        self.viewmodel.switch_view("configurator")

    def create_view(self):
        self.clear_content_frame()
        has_data_source, db_connection_status = self.viewmodel.check_data_source()

        if not has_data_source:
            self.create_welcome_view()
            self.update_status("Добро пожаловать в Playlist AI")
            return

        stats_data = self.viewmodel.get_statistics_data()
        if stats_data is None:
            self.create_no_data_view("Не удалось получить данные статистики")
            self.update_status("Не удалось загрузить статистику")
        elif "schema_error" in stats_data:
            self.create_welcome_view()
            self.update_status("Схема БД неконсистентна, проверьте настройки")
        else:
            self.create_statistics_view(stats_data, db_connection_status)
            self.update_status("Статистика успешно загружена")

    def create_statistics_view(self, stats_data, db_connection_status):
        """
        Создает представление с данными статистики.
        """
        self.frame = ttk.Frame(self.content_frame, padding=10)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 10))

        ttk.Label(self.frame, text="Статистика", font=("Arial", 16, "bold")).pack(
            pady=10, anchor="w"
        )

        top_frame = ttk.Frame(self.frame)
        top_frame.pack(fill=tk.X, pady=10)

        left_frame = ttk.Frame(top_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_frame = ttk.Frame(top_frame, width=550)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)
        right_frame.pack_propagate(False)

        db_status_frame = ttk.Frame(left_frame)
        db_status_frame.pack(fill=tk.X, pady=5, anchor="w")

        ttk.Label(db_status_frame, text="Статус БД:", font=("Arial", 12)).pack(
            side=tk.LEFT, padx=(0, 10)
        )

        db_status_canvas = tk.Canvas(db_status_frame, width=15, height=15, highlightthickness=0)
        db_status_canvas.pack(side=tk.LEFT)

        color = "green" if db_connection_status else "red"
        db_status_canvas.create_oval(2, 2, 13, 13, fill=color, outline="")

        bpm_values = stats_data.get("bpm_values", [])
        genres = stats_data.get("genres", {})
        totals = stats_data.get("totals", {})

        stats_frame = ttk.LabelFrame(left_frame, text="Медиатека")
        stats_frame.pack(fill=tk.X, pady=10, anchor="w")

        ttk.Label(stats_frame, text=f"Размер медиатеки: {totals.get('total_size', '0 Б')}").pack(
            anchor="w", padx=10, pady=2
        )
        ttk.Label(
            stats_frame, text=f"Общая длительность: {totals.get('total_duration', '0:00:00')}"
        ).pack(anchor="w", padx=10, pady=2)
        ttk.Label(stats_frame, text=f"Всего артистов: {totals.get('total_artists', 0)}").pack(
            anchor="w", padx=10, pady=2
        )
        ttk.Label(stats_frame, text=f"Всего жанров: {totals.get('total_genres', 0)}").pack(
            anchor="w", padx=10, pady=2
        )
        ttk.Label(stats_frame, text=f"Всего альбомов: {totals.get('total_albums', 0)}").pack(
            anchor="w", padx=10, pady=2
        )
        ttk.Label(stats_frame, text=f"Всего треков: {totals.get('total_tracks', 0)}").pack(
            anchor="w", padx=10, pady=2
        )
        ttk.Label(stats_frame, text=f"Всего плейлистов: {totals.get('total_playlists', 0)}").pack(
            anchor="w", padx=10, pady=2
        )

        if bpm_values:
            self.create_bpm_density_chart(right_frame, bpm_values)
        else:
            ttk.Label(right_frame, text="Нет данных для отображения графика BPM").pack(pady=50)

        genre_frame = ttk.LabelFrame(self.frame, text="Жанры")
        genre_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        if genres:
            self.create_genre_barchart(genre_frame, genres)
        else:
            ttk.Label(genre_frame, text="Нет данных для отображения графика жанров").pack(pady=50)

    def update_log_status(self, message):
        """Логирует и обновляет статус."""
        self.update_status(message)
