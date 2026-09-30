import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from gui.views.basevw import BaseView


class PlaylistView(BaseView):
    """Представление для управления плейлистами (MVVM)."""

    def __init__(
        self,
        root: tk.Tk,
        parent: ttk.Frame,
        viewmodel=None,
        status_callback: Optional[Callable] = None,
    ):
        super().__init__(root, parent, viewmodel, status_callback)
        self.selected_playlist_id = None
        self._setup_ui()

    def _setup_ui(self):
        self.clear_content_frame()

        # Главный контейнер (PanedWindow позволяет пользователю менять размер панелей)
        self.main_frame = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ================= Левая панель: Плейлисты =================
        self.playlist_frame = ttk.Frame(self.main_frame)
        self.main_frame.add(self.playlist_frame, weight=1)

        ttk.Label(self.playlist_frame, text="Мои плейлисты", font=("Arial", 12, "bold")).pack(pady=5)

        btn_frame = ttk.Frame(self.playlist_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(btn_frame, text="➕ Создать", command=self._create_playlist).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="🗑 Удалить", command=self._delete_playlist).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=2)

        # Таблица плейлистов
        self.playlist_tree = ttk.Treeview(self.playlist_frame, columns=("name",), show="headings", selectmode="browse")
        self.playlist_tree.heading("name", text="Название")
        self.playlist_tree.column("name", width=200, anchor=tk.W)
        self.playlist_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.playlist_tree.bind("<<TreeviewSelect>>", self._on_playlist_select)

        # ================= Правая панель: Треки =================
        self.tracks_frame = ttk.Frame(self.main_frame)
        self.main_frame.add(self.tracks_frame, weight=3)

        ttk.Label(self.tracks_frame, text="Содержимое плейлиста", font=("Arial", 12, "bold")).pack(pady=5)

        # Контейнер для таблицы треков + Scrollbar
        tree_container = ttk.Frame(self.tracks_frame)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tracks_tree = ttk.Treeview(tree_container, columns=("title", "artist", "duration"), show="headings")
        self.tracks_tree.heading("title", text="Название трека")
        self.tracks_tree.heading("artist", text="Исполнитель")
        self.tracks_tree.heading("duration", text="Время")

        self.tracks_tree.column("title", width=250, anchor=tk.W)
        self.tracks_tree.column("artist", width=200, anchor=tk.W)
        self.tracks_tree.column("duration", width=80, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tracks_tree.yview)
        self.tracks_tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tracks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.add_track_btn = ttk.Button(
            self.tracks_frame,
            text="➕ Добавить трек из медиатеки",
            command=self._add_track,
            state=tk.DISABLED,
        )
        self.add_track_btn.pack(fill=tk.X, padx=5, pady=5)

        # Начальная инициализация данных
        self._load_playlists()

    def _load_playlists(self):
        if not self.viewmodel:
            return

        playlists = self.viewmodel.get_playlists()
        self.playlist_tree.delete(*self.playlist_tree.get_children())

        for playlist in playlists:
            self.playlist_tree.insert("", tk.END, iid=str(playlist["id"]), values=(playlist["name"],))

    def _on_playlist_select(self, event):
        """Мгновенно обновляет правую панель при смене активного плейлиста."""
        selection = self.playlist_tree.selection()
        if not selection:
            # Сбрасываем состояние, если выделение снято
            self.selected_playlist_id = None
            self.tracks_tree.delete(*self.tracks_tree.get_children())
            self.add_track_btn.config(state=tk.DISABLED)
            return

        self.selected_playlist_id = selection[0]
        self.add_track_btn.config(state=tk.NORMAL)
        self._load_tracks()

    def _load_tracks(self):
        if not self.viewmodel or not self.selected_playlist_id:
            return

        self.update_status("Загрузка треков плейлиста...")
        tracks = self.viewmodel.get_playlist_tracks(int(self.selected_playlist_id))

        self.tracks_tree.delete(*self.tracks_tree.get_children())
        for idx, track in enumerate(tracks):
            # Сохраняем скрытый ID трека в IID строки для будущих операций
            # Если в DTO нет ID, используем индекс в качестве фолбэка
            track_id = track.get("id", f"track_{idx}")
            self.tracks_tree.insert(
                "",
                tk.END,
                iid=str(track_id),
                values=(
                    track.get("title", "—"),
                    track.get("artist", "—"),
                    track.get("duration", "—"),
                ),
            )

    def _create_playlist(self):
        if not self.viewmodel:
            return

        # parent=self.root предотвращает скрытие модального окна за основным интерфейсом
        name = simpledialog.askstring("Новый плейлист", "Введите название плейлиста:", parent=self.root)
        if name and name.strip():
            if self.viewmodel.create_playlist(name.strip()):
                self._load_playlists()

    def _delete_playlist(self):
        if not self.selected_playlist_id:
            messagebox.showwarning("Внимание", "Сначала выберите плейлист слева для удаления.", parent=self.root)
            return

        confirm = messagebox.askyesno(
            "Удаление",
            "Точно удалить выбранный плейлист?\nТреки из медиатеки при этом НЕ будут удалены.",
            parent=self.root,
        )

        if confirm:
            if self.viewmodel.delete_playlist(int(self.selected_playlist_id)):
                self.selected_playlist_id = None
                self._load_playlists()
                self.tracks_tree.delete(*self.tracks_tree.get_children())
                self.add_track_btn.config(state=tk.DISABLED)

    def _add_track(self):
        if not self.selected_playlist_id:
            self.update_status("Сначала выберите плейлист.")
            return

        # TODO: Интеграция с ManagerView или модальным окном поиска треков
        messagebox.showinfo(
            "В разработке",
            "Здесь будет открываться окно выбора треков из библиотеки.",
            parent=self.root,
        )
