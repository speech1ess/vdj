import tkinter as tk
from collections import defaultdict
from tkinter import ttk

from gui.views.basevw import BaseView


class ManagerView(BaseView):
    """
    Представление для управления медиатекой.
    Оптимизировано для больших баз данных (100k+ треков).
    """

    def __init__(self, root, parent, viewmodel, status_callback=None):
        super().__init__(
            root=root, parent=parent, viewmodel=viewmodel, status_callback=status_callback
        )
        # Кэш треков текущего фильтра, чтобы не дергать БД при каждом клике
        self.current_tracks: list[dict[str, str]] = []
        self.create_view()

    def create_view(self):
        self.clear_content_frame()

        ttk.Label(self.content_frame, text="Менеджер медиатеки", font=("Arial", 16, "bold")).pack(
            pady=10
        )

        # --- Панель Фильтров ---
        filter_frame = ttk.Frame(self.content_frame)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(filter_frame, text="Жанр:").pack(side=tk.LEFT, padx=(0, 5))
        self.genre_combo = ttk.Combobox(
            filter_frame, values=[""] + self.viewmodel.get_genres(), state="readonly"
        )
        self.genre_combo.pack(side=tk.LEFT, padx=5)
        self.genre_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        ttk.Label(filter_frame, text="Артист:").pack(side=tk.LEFT, padx=(0, 5))
        self.artist_combo = ttk.Combobox(
            filter_frame, values=[""] + self.viewmodel.get_artists(), state="readonly"
        )
        self.artist_combo.pack(side=tk.LEFT, padx=5)
        self.artist_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        ttk.Button(filter_frame, text="Сбросить фильтры", command=self.reset_filters).pack(
            side=tk.LEFT, padx=15
        )

        # --- Основная рабочая область ---
        main_frame = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Левая панель: Дерево структуры (Жанр -> Артист -> Альбом)
        left_frame = ttk.Frame(main_frame)
        main_frame.add(left_frame, weight=1)

        self.structure_tree = ttk.Treeview(left_frame, show="tree", selectmode="browse")
        self.structure_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar_left = ttk.Scrollbar(
            left_frame, orient=tk.VERTICAL, command=self.structure_tree.yview
        )
        scrollbar_left.pack(side=tk.RIGHT, fill=tk.Y)
        self.structure_tree.configure(yscrollcommand=scrollbar_left.set)

        self.structure_tree.bind("<<TreeviewSelect>>", self.on_structure_select)

        # Правая панель: Таблица треков и детали
        right_frame = ttk.Frame(main_frame)
        main_frame.add(right_frame, weight=3)

        tracks_frame = ttk.Frame(right_frame)
        tracks_frame.pack(fill=tk.BOTH, expand=True)

        self.tracks_table = ttk.Treeview(tracks_frame, show="headings", selectmode="extended")
        self.tracks_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar_right = ttk.Scrollbar(
            tracks_frame, orient=tk.VERTICAL, command=self.tracks_table.yview
        )
        scrollbar_right.pack(side=tk.RIGHT, fill=tk.Y)
        self.tracks_table.configure(yscrollcommand=scrollbar_right.set)

        self.tracks_table.bind("<<TreeviewSelect>>", self.on_track_select)

        # Детали трека
        details_frame = ttk.LabelFrame(right_frame, text="Детали файла", padding=5)
        details_frame.pack(fill=tk.X, pady=(5, 0))

        self.details_label = ttk.Label(
            details_frame, text="Выберите трек из списка", wraplength=500, justify=tk.LEFT
        )
        self.details_label.pack(pady=5, anchor=tk.W)

        # Action Buttons
        btn_frame = ttk.Frame(details_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Редактировать метаданные", command=self.edit_track).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Добавить в плейлист", command=self.add_to_playlist).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_frame, text="Удалить из медиатеки", command=self.delete_track).pack(
            side=tk.RIGHT, padx=2
        )

        # Начальная инициализация (1 запрос к БД)
        self.refresh_data_from_db()

    def refresh_data_from_db(self):
        """Единая точка выгрузки данных. Защита от дублирующих запросов."""
        genre_filter = self.genre_combo.get() or None
        artist_filter = self.artist_combo.get() or None

        self.update_status("⏳ Загрузка медиатеки...")
        self.root.update()

        # Один запрос в БД
        self.current_tracks = self.viewmodel.get_tracks(genre=genre_filter, artist=artist_filter)

        self._build_tree_structure(artist_filter, genre_filter)
        self._render_tracks_table(self.current_tracks, artist_filter=artist_filter)

        self.update_status(f"✅ Загружено треков: {len(self.current_tracks)}")

    def _build_tree_structure(self, artist_filter: str, genre_filter: str):
        """Оптимизированное (O(N)) построение дерева через вложенные словари."""
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)

        if not self.current_tracks:
            return

        if artist_filter and not genre_filter:
            # Структура: Артист -> Альбомы
            tree_data = defaultdict(set)
            for track in self.current_tracks:
                tree_data[artist_filter].add(track["album"])

            artist_node = self.structure_tree.insert("", tk.END, text=artist_filter, open=True)
            for album in sorted(tree_data[artist_filter]):
                self.structure_tree.insert(
                    artist_node, tk.END, text=album, values=(artist_filter, album)
                )
        else:
            # Структура: Жанр -> Артист -> Альбом
            tree_data = defaultdict(lambda: defaultdict(set))
            for track in self.current_tracks:
                genre = track["genre"] or "Unknown"
                artist = track["artist"] or "Unknown"
                album = track["album"] or "Unknown"
                tree_data[genre][artist].add(album)

            for genre in sorted(tree_data.keys()):
                genre_node = self.structure_tree.insert("", tk.END, text=genre, open=False)
                for artist in sorted(tree_data[genre].keys()):
                    artist_node = self.structure_tree.insert(
                        genre_node, tk.END, text=artist, open=False
                    )
                    for album in sorted(tree_data[genre][artist]):
                        self.structure_tree.insert(
                            artist_node, tk.END, text=album, values=(genre, artist, album)
                        )

    def _render_tracks_table(
        self,
        tracks_to_render: list[dict[str, str]],
        artist_filter: str = None,
        album_filter: str = None,
    ):
        """Отрисовывает таблицу. Хранит полный DTO в скрытом поле IID."""
        for item in self.tracks_table.get_children():
            self.tracks_table.delete(item)

        # Определяем колонки (со скрытым file_path для быстрого доступа)
        all_columns = [
            ("title", "Название", 250),
            ("artist", "Артист", 150),
            ("album", "Альбом", 150),
            ("duration", "Время", 60),
            ("bpm", "BPM", 50),
            ("genre", "Жанр", 100),
            ("key", "Тон", 50),
            (
                "_file_path",
                "Путь (Скрыто)",
                0,
            ),  # Скрытая колонка (или можно хранить в индексном словаре)
        ]

        active_columns = []
        for col_id, col_name, col_width in all_columns:
            if artist_filter and col_id == "artist":
                continue
            if album_filter and col_id == "album":
                continue
            active_columns.append((col_id, col_name, col_width))

        # Настраиваем UI колонок
        self.tracks_table["columns"] = [
            col[0] for col in active_columns if not col[0].startswith("_")
        ]
        for col_id, col_name, col_width in active_columns:
            if col_id.startswith("_"):
                continue
            self.tracks_table.heading(col_id, text=col_name, anchor=tk.W)
            self.tracks_table.column(
                col_id,
                width=col_width,
                anchor=tk.W if col_id not in ("bpm", "key", "duration") else tk.CENTER,
            )

        # Отрисовка
        for idx, track in enumerate(tracks_to_render):
            values = tuple(
                track[col_id] for col_id, _, _ in active_columns if not col_id.startswith("_")
            )

            # Сохраняем физический путь файла в тегах (tags) самого элемента (или как iid),
            # чтобы при клике не обращаться к базе данных.
            self.tracks_table.insert(
                "", tk.END, iid=f"track_{idx}", values=values, tags=(track["file"], track["genre"])
            )

    def apply_filters(self):
        self.refresh_data_from_db()

    def reset_filters(self):
        self.genre_combo.set("")
        self.artist_combo.set("")
        self.refresh_data_from_db()

    def on_structure_select(self, event):
        """Фильтрует кэш в памяти (RAM), без обращений к БД."""
        selected = self.structure_tree.selection()
        if not selected:
            return

        item = self.structure_tree.item(selected[0])
        parent = self.structure_tree.parent(selected[0])
        grandparent = self.structure_tree.parent(parent) if parent else ""

        filtered_tracks = self.current_tracks
        album_filter = None
        artist_filter = self.artist_combo.get() or None

        if grandparent:  # Выбран Альбом
            genre = self.structure_tree.item(grandparent)["text"]
            artist = self.structure_tree.item(parent)["text"]
            album = item["text"]
            album_filter = album
            filtered_tracks = [
                t
                for t in filtered_tracks
                if t["genre"] == genre and t["artist"] == artist and t["album"] == album
            ]

        elif parent:  # Выбран Артист
            if not self.artist_combo.get():
                genre = self.structure_tree.item(parent)["text"]
                artist = item["text"]
                filtered_tracks = [
                    t for t in filtered_tracks if t["genre"] == genre and t["artist"] == artist
                ]
                artist_filter = artist

        else:  # Выбран Жанр (или Артист, если жанр скрыт)
            if self.artist_combo.get():
                filtered_tracks = [t for t in filtered_tracks if t["artist"] == item["text"]]
                artist_filter = item["text"]
            else:
                filtered_tracks = [t for t in filtered_tracks if t["genre"] == item["text"]]

        self._render_tracks_table(
            filtered_tracks, artist_filter=artist_filter, album_filter=album_filter
        )

    def on_track_select(self, event):
        """Мгновенное отображение деталей O(1). Никаких запросов в БД!"""
        selected = self.tracks_table.selection()
        if selected:
            item_id = selected[0]
            item = self.tracks_table.item(item_id)
            values = item["values"]
            columns = self.tracks_table["columns"]

            # Путь к файлу мы предусмотрительно сохранили в tags при рендеринге таблицы!
            file_path = item["tags"][0] if item["tags"] else "Неизвестно"

            details_text = "\n".join(
                f"{self.tracks_table.heading(col)['text']}: {val}"
                for col, val in zip(columns, values, strict=False)
            )
            details_text += f"\n\n📂 Путь к файлу: {file_path}"

            self.details_label.config(text=details_text)
        else:
            self.details_label.config(text="Выберите трек из списка")

    def edit_track(self):
        if self.tracks_table.selection():
            self.update_status("Редактирование трека (в разработке)")

    def delete_track(self):
        if self.tracks_table.selection():
            self.update_status("Удаление трека (в разработке)")

    def add_to_playlist(self):
        if self.tracks_table.selection():
            self.update_status("Добавление в плейлист (в разработке)")
