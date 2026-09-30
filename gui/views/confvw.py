import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui.views.basevw import BaseView


class ConfiguratorView(BaseView):
    """
    Окно конфигурации.
    Чистое MVVM-представление: не импортирует БД, схемы или сервисы.
    Вся логика делегирована в ConfiguratorViewModel.
    """

    def __init__(self, root: tk.Tk, parent: ttk.Frame, viewmodel, status_callback=None):
        # Привязка UI к ViewModel
        super().__init__(root, parent, viewmodel, status_callback)

        # Получаем текущий конфиг через VM
        current_config = self.viewmodel.get_current_config()
        self.selected_db_type = tk.StringVar(value=current_config.get("db_type", "csv"))

        self.setup_ui()

    def setup_ui(self):
        self.clear_content_frame()
        frame = ttk.Frame(self.content_frame, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Настройки системы (Configurator)", font=("Arial", 12, "bold")).pack(
            pady=10
        )

        # Выбор типа БД
        ttk.Label(frame, text="Движок базы данных:").pack()

        # Получаем доступные типы БД из ViewModel
        available_db_types = self.viewmodel.get_db_types()
        self.db_combobox = ttk.Combobox(
            frame, textvariable=self.selected_db_type, values=available_db_types, state="readonly"
        )
        self.db_combobox.pack(pady=5)
        self.db_combobox.bind("<<ComboboxSelected>>", self.on_db_type_selected)

        # Кнопка проверки соединения (логика скрыта в VM)
        self.test_button = ttk.Button(
            frame, text="Проверить соединение", command=self.viewmodel.test_connection
        )
        self.test_button.pack(pady=5)

        # Управление схемой БД (Делегировано в VM)
        diag_frame = ttk.LabelFrame(frame, text="Управление схемой БД", padding=10)
        diag_frame.pack(fill=tk.X, pady=10)

        ttk.Button(
            diag_frame, text="Инициализировать схему (Create)", command=self.create_schema
        ).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(diag_frame, text="Очистить БД (Drop)", command=self.confirm_drop_schema).pack(
            side=tk.RIGHT, padx=5, expand=True
        )

        # Настройка директорий (Делегировано в VM)
        dirs_frame = ttk.LabelFrame(frame, text="Директории (I/O)", padding=10)
        dirs_frame.pack(fill=tk.X, pady=10)

        ttk.Button(
            dirs_frame, text="Выбрать папку хранилища (Data)", command=self.choose_output_dir
        ).pack(pady=5, fill=tk.X)
        ttk.Button(
            dirs_frame, text="Выбрать папку SQL-скриптов", command=self.choose_sql_scripts_dir
        ).pack(pady=5, fill=tk.X)

        ttk.Button(frame, text="Показать текущую конфигурацию", command=self.show_config).pack(
            pady=15
        )

        self.update_buttons_state()

    def on_db_type_selected(self, event=None):
        """Передает выбор пользователя во ViewModel для безопасного сохранения."""
        db_type = self.selected_db_type.get()
        self.viewmodel.set_db_type(db_type)
        self.update_buttons_state()

    def update_buttons_state(self):
        """UI-логика: дизейблим тест коннекта для локальных БД."""
        db_type = self.selected_db_type.get()
        if db_type == "postgresql":
            self.test_button.config(state=tk.NORMAL)
        else:
            self.test_button.config(state=tk.DISABLED)

    def create_schema(self):
        """Делегирует создание схемы в VM."""
        if messagebox.askyesno(
            "Подтверждение",
            "Инициализировать схему БД? Если таблицы существуют, они будут перезаписаны!",
        ):
            self.viewmodel.create_database()

    def confirm_drop_schema(self):
        """Делегирует удаление схемы в VM."""
        if messagebox.askyesno(
            "Критическое действие",
            "Очистить БД? ВНИМАНИЕ: Все ваши плейлисты, метаданные и треки будут удалены навсегда!",
        ):
            self.viewmodel.drop_database()

    def choose_output_dir(self):
        """Опрашивает пользователя и отправляет результат в VM."""
        directory = filedialog.askdirectory(title="Выберите корневую папку для данных PlaylistAI")
        if directory:
            self.viewmodel.set_output_dir(directory)

    def choose_sql_scripts_dir(self):
        """Опрашивает пользователя и отправляет результат в VM."""
        directory = filedialog.askdirectory(title="Выберите папку для SQL-скриптов")
        if directory:
            self.viewmodel.set_sql_scripts_dir(directory)

    def show_config(self):
        """Отрисовывает модальное окно с конфигурацией (ReadOnly)."""
        config_window = tk.Toplevel(self.root)
        config_window.title("Dump конфигурации (config.json)")
        config_window.geometry("600x400")

        frame = ttk.Frame(config_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tree = ttk.Treeview(frame, columns=("param", "value"), show="headings")
        tree.heading("param", text="Ключ / Параметр")
        tree.heading("value", text="Значение")
        tree.column("param", width=150)
        tree.column("value", width=400)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)

        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)

        config_data = self.viewmodel.get_current_config()
        for key, value in config_data.items():
            tree.insert("", tk.END, values=(str(key), str(value)))
