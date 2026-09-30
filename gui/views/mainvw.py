import threading
import tkinter as tk
from tkinter import filedialog, ttk

from core.services.config import Configurator
from core.viewmodels.mainvwm import MainViewModel
from gui.views.basevw import BaseView
from gui.views.confvw import ConfiguratorView
from gui.views.managervw import ManagerView
from gui.views.metadatavw import MetadataQueryView
from gui.views.playlistvw import PlaylistView
from gui.views.scanvw import ScanView
from gui.views.statvw import StatisticsView


class MainView(BaseView):
    """
    Главное окно приложения Playlist AI.
    Оркестрирует переключение дочерних экранов (Views) на основе стейт-машины MainViewModel.
    """

    def __init__(self, root: tk.Tk = None, config: Configurator = None, log_callback=None):
        self.root = root or tk.Tk()

        # Главная ViewModel оркестратора
        viewmodel = MainViewModel(
            configurator=config or Configurator(), log_callback=self.force_update_status
        )
        super().__init__(
            root=self.root,
            parent=self.root,
            viewmodel=viewmodel,
            status_callback=self.force_update_status,
        )

        self.root.title("Playlist AI - Data-Driven Media Manager")
        self.root.geometry("1200x700")
        self.root.minsize(800, 500)

        self.current_child_view = None

        # Статус бар
        self.status_bar = ttk.Frame(self.root, relief=tk.SUNKEN, height=30, borderwidth=1)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)

        self.status_label = ttk.Label(
            self.status_bar, text="Готов к работе", anchor=tk.W, padding=(5, 2)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.db_status_canvas = tk.Canvas(
            self.status_bar, width=15, height=15, highlightthickness=0
        )
        self.db_status_canvas.pack(side=tk.RIGHT, padx=5)
        self.db_status_indicator = self.db_status_canvas.create_oval(
            2, 2, 13, 13, fill="gray", outline=""
        )

        self.create_main_layout()
        self.create_menu()

        # Запускаем начальный экран
        self.switch_view("statistics")
        self.update_db_status_async()

    def create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Открыть каталог...", command=self.select_directory)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        menubar.add_cascade(label="Файл", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Сканировать аудиофайлы", command=lambda: self.switch_view("scanner")
        )
        tools_menu.add_command(
            label="Управление плейлистами", command=lambda: self.switch_view("playlists")
        )
        tools_menu.add_command(
            label="Поиск метаданных", command=lambda: self.switch_view("metadata")
        )
        menubar.add_cascade(label="Инструменты", menu=tools_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(
            label="Конфигурация", command=lambda: self.switch_view("configurator")
        )
        menubar.add_cascade(label="Настройки", menu=settings_menu)

        self.root.config(menu=menubar)

    def create_main_layout(self):
        # Очищаем root от возможного мусора (кроме статус-бара)
        for widget in self.root.winfo_children():
            if widget not in (self.status_bar, self.content_frame):
                widget.pack_forget()

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Левое меню (Sidebar)
        self.sidebar = ttk.Frame(self.main_frame, width=200, relief=tk.RIDGE, borderwidth=1)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        ttk.Label(self.sidebar, text="Playlist AI", font=("Arial", 16, "bold")).pack(pady=20)

        self.create_nav_button("Статистика", lambda: self.switch_view("statistics"))
        self.create_nav_button("Сканер директорий", lambda: self.switch_view("scanner"))
        self.create_nav_button("Библиотека (Менеджер)", lambda: self.switch_view("manager"))
        self.create_nav_button("Плейлисты", lambda: self.switch_view("playlists"))
        self.create_nav_button("Метаданные (Web API)", lambda: self.switch_view("metadata"))

        ttk.Separator(self.sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        self.create_nav_button("Настройки", lambda: self.switch_view("configurator"))
        self.create_nav_button("Закрыть", self.root.quit)

        # Основная рабочая область
        self.content_area = ttk.Frame(self.main_frame)
        self.content_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def create_nav_button(self, text: str, command):
        btn = ttk.Button(self.sidebar, text=text, command=command)
        btn.pack(fill=tk.X, padx=10, pady=5)
        return btn

    def switch_view(self, view_name: str):
        """
        Маршрутизатор экранов (State Router).
        Запрашивает нужную ViewModel у MainViewModel и рендерит соответствующий View.
        """
        # 1. Запрашиваем ViewModel (Бизнес-логику) у оркестратора
        target_vm = self.viewmodel.get_view_model_for(view_name)
        if not target_vm:
            return

        # 2. Если оркестратор принудительно перенаправил (например, БД сломана)
        actual_view_name = (
            self.viewmodel.current_view_name
            if hasattr(self.viewmodel, "current_view_name")
            else view_name
        )

        # 3. Уничтожаем старый View (очистка памяти и отписка от логгеров)
        if self.current_child_view:
            self.current_child_view.destroy()
            self.current_child_view = None

        # 4. Рендерим новый View, прокидывая в него его ViewModel
        if actual_view_name == "statistics":
            self.current_child_view = StatisticsView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        elif actual_view_name == "configurator":
            self.current_child_view = ConfiguratorView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        elif actual_view_name == "scanner":
            self.current_child_view = ScanView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        elif actual_view_name == "manager":
            self.current_child_view = ManagerView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        elif actual_view_name == "playlists":
            self.current_child_view = PlaylistView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        elif actual_view_name == "metadata":
            self.current_child_view = MetadataQueryView(
                self.root, self.content_area, target_vm, self.force_update_status
            )
        else:
            self.force_update_status(f"⚠️ Ошибка UI: Экран '{actual_view_name}' не реализован.")
            return

        self.force_update_status(f"Открыт раздел: {actual_view_name.capitalize()}")
        self.update_db_status_async()

    def select_directory(self):
        directory = filedialog.askdirectory(title="Выберите каталог аудиофайлов")
        if directory:
            self.viewmodel.set_directory(directory)
            self.switch_view("scanner")

    def update_db_status_async(self):
        """Асинхронная (non-blocking) проверка статуса БД для UI."""

        def check_status():
            color = self.viewmodel.get_db_status_color()
            self.root.after(
                0, lambda: self.db_status_canvas.itemconfig(self.db_status_indicator, fill=color)
            )

        threading.Thread(target=check_status, daemon=True).start()

    def force_update_status(self, message: str):
        self.status_label.config(text=message)
        self.root.update_idletasks()
