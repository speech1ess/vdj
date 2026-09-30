import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from core.viewmodels.metadatavwm import MetadataQueryViewModel
from gui.views.basevw import BaseView


class MetadataQueryView(BaseView):
    """
    Представление для поиска и обогащения метаданных через внешние сетевые API.
    Реализует неблокирующий I/O сетевого стека и потокобезопасный рендеринг.
    """

    # Data-Driven сопоставление фильтров UI с параметрами бизнес-логики
    TYPE_MAPPING = {"Трек": "track", "Альбом": "album", "Артист": "artist"}

    STATE_MAPPING = {
        "Без альбома": "album",
        "Без артиста": "artist",
        "Без лейбла": "label",
        "Без года": "year",
    }

    API_MAPPING = {"Discogs": "discogs", "MusicBrainz": "musicbrainz"}

    def __init__(
        self,
        root: tk.Tk,
        parent: ttk.Frame,
        viewmodel: MetadataQueryViewModel,
        status_callback=None,
    ):
        super().__init__(
            root=root, parent=parent, viewmodel=viewmodel, status_callback=status_callback
        )
        # Кэш результатов текущего поиска: iid -> Dict[str, Any]
        self._results_cache: dict[str, dict[str, Any]] = {}
        self._is_querying = False
        self.create_view()

    def create_view(self):
        self.clear_content_frame()

        ttk.Label(
            self.content_frame, text="Запрос метаданных (Web API)", font=("Arial", 16, "bold")
        ).pack(pady=10)

        # --- Панель фильтрации и параметров поиска ---
        filter_frame = ttk.LabelFrame(self.content_frame, text="Параметры поиска", padding=10)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        # Тип сущности
        ttk.Label(filter_frame, text="Тип:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.type_combo = ttk.Combobox(
            filter_frame, values=list(self.TYPE_MAPPING.keys()), state="readonly", width=10
        )
        self.type_combo.set("Трек")
        self.type_combo.grid(row=0, column=1, padx=5, pady=5)

        # Критерий выборки
        ttk.Label(filter_frame, text="Состояние:").grid(
            row=0, column=2, padx=5, pady=5, sticky=tk.W
        )
        self.state_combo = ttk.Combobox(
            filter_frame, values=list(self.STATE_MAPPING.keys()), state="readonly", width=14
        )
        self.state_combo.set("Без альбома")
        self.state_combo.grid(row=0, column=3, padx=5, pady=5)

        # Поисковый запрос
        ttk.Label(filter_frame, text="Запрос:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.name_entry = ttk.Entry(filter_frame, width=20)
        self.name_entry.grid(row=0, column=5, padx=5, pady=5)
        self.name_entry.bind("<Return>", lambda e: self.search())

        # Выбор провайдера API
        ttk.Label(filter_frame, text="Провайдер:").grid(
            row=0, column=6, padx=5, pady=5, sticky=tk.W
        )
        self.api_combo = ttk.Combobox(
            filter_frame, values=list(self.API_MAPPING.keys()), state="readonly", width=12
        )
        self.api_combo.set("Discogs")
        self.api_combo.grid(row=0, column=7, padx=5, pady=5)

        # Кнопки действий
        btn_box = ttk.Frame(filter_frame)
        btn_box.grid(row=0, column=8, padx=10, pady=5)

        self.search_btn = ttk.Button(btn_box, text="🔍 Поиск", command=self.search)
        self.search_btn.pack(side=tk.LEFT, padx=2)

        self.reset_btn = ttk.Button(btn_box, text="Сброс", command=self.reset)
        self.reset_btn.pack(side=tk.LEFT, padx=2)

        # --- Таблица результатов ---
        table_container = ttk.Frame(self.content_frame)
        table_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("title", "artist", "album", "label", "year", "source")
        self.results_table = ttk.Treeview(
            table_container, columns=columns, show="headings", selectmode="browse"
        )

        self.results_table.heading("title", text="Название")
        self.results_table.heading("artist", text="Исполнитель")
        self.results_table.heading("album", text="Альбом")
        self.results_table.heading("label", text="Лейбл")
        self.results_table.heading("year", text="Год")
        self.results_table.heading("source", text="Источник")

        self.results_table.column("title", width=220)
        self.results_table.column("artist", width=160)
        self.results_table.column("album", width=160)
        self.results_table.column("label", width=120)
        self.results_table.column("year", width=60, anchor=tk.CENTER)
        self.results_table.column("source", width=90, anchor=tk.CENTER)

        # Вертикальный скроллбар
        scrollbar = ttk.Scrollbar(
            table_container, orient=tk.VERTICAL, command=self.results_table.yview
        )
        self.results_table.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_table.bind("<<TreeviewSelect>>", self.on_select)

        # --- Детализация и применение ---
        details_frame = ttk.LabelFrame(
            self.content_frame, text="Сведения о выбранном релизе", padding=10
        )
        details_frame.pack(fill=tk.X, padx=10, pady=5)

        self.details_label = ttk.Label(
            details_frame,
            text="Выберите позицию в таблице для просмотра параметров.",
            justify=tk.LEFT,
        )
        self.details_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.apply_btn = ttk.Button(
            details_frame,
            text="✔ Применить метаданные",
            command=self.apply_metadata,
            state=tk.DISABLED,
        )
        self.apply_btn.pack(side=tk.RIGHT, padx=5)

    def search(self):
        """Неблокирующий запуск сетевого запроса."""
        if self._is_querying:
            return

        api_name = self.api_combo.get()
        filters = {
            "type": self.TYPE_MAPPING.get(self.type_combo.get(), "track"),
            "state": self.STATE_MAPPING.get(self.state_combo.get(), "album"),
            "name": self.name_entry.get().strip() or None,
            "api": self.API_MAPPING.get(api_name, "discogs"),
        }

        self._set_ui_state(busy=True)
        self.update_status(f"🌐 Сетевой запрос к {api_name} API...")

        def network_worker():
            try:
                # Сетевой I/O выполняется в изолированном системном потоке
                results = self.viewmodel.query_metadata(**filters)
                self.root.after(0, lambda: self._on_search_success(results))
            except Exception as e:
                # Фиксируем строку ошибки в локальной переменной до уничтожения объекта 'e'
                error_msg = str(e)
                # Передаем ее в лямбду через аргумент по умолчанию, чтобы избежать Late Binding
                self.root.after(0, lambda msg=error_msg: self._on_search_error(msg))

        threading.Thread(target=network_worker, daemon=True).start()

    def _on_search_success(self, results: list[dict[str, Any]]):
        """Обработка сетевого ответа в главном потоке."""
        self._set_ui_state(busy=False)
        self.load_results(results)
        count = len(results)
        self.update_status(f"✅ Получено ответов: {count}")
        if count == 0:
            self.details_label.config(text="По вашему запросу ничего не найдено.")

    def _on_search_error(self, error_msg: str):
        """Обработка сбоев сети / таймаутов сокетов."""
        self._set_ui_state(busy=False)
        self.update_status("❌ Ошибка выполнения сетевого запроса")
        messagebox.showerror(
            "Сетевая ошибка", f"Не удалось получить данные от внешнего сервиса:\n{error_msg}"
        )

    def _set_ui_state(self, busy: bool):
        """Управление состоянием контролов для предотвращения race conditions."""
        self._is_querying = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.search_btn.config(state=state)
        self.reset_btn.config(state=state)
        self.type_combo.config(state=tk.DISABLED if busy else "readonly")
        self.state_combo.config(state=tk.DISABLED if busy else "readonly")
        self.api_combo.config(state=tk.DISABLED if busy else "readonly")
        self.name_entry.config(state=state)

    def load_results(self, results: list[dict[str, Any]]):
        """Заполнение таблицы с сохранением сырого DTO в кэш."""
        self.results_table.delete(*self.results_table.get_children())
        self._results_cache.clear()
        self.apply_btn.config(state=tk.DISABLED)

        for idx, item in enumerate(results):
            iid = f"meta_{idx}"
            self._results_cache[iid] = item

            self.results_table.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    item.get("title", "—"),
                    item.get("artist", "—"),
                    item.get("album", "—"),
                    item.get("label", "—"),
                    item.get("year", "—"),
                    item.get("source", "—").upper(),
                ),
            )

    def reset(self):
        """Сброс полей ввода и таблицы к исходному состоянию."""
        if self._is_querying:
            return
        self.type_combo.set("Трек")
        self.state_combo.set("Без альбома")
        self.name_entry.delete(0, tk.END)
        self.api_combo.set("Discogs")
        self.results_table.delete(*self.results_table.get_children())
        self._results_cache.clear()
        self.details_label.config(text="Выберите позицию в таблице для просмотра параметров.")
        self.apply_btn.config(state=tk.DISABLED)
        self.update_status("Параметры сброшены")

    def on_select(self, event):
        """Отображение подробной информации из кэша по iid."""
        selection = self.results_table.selection()
        if not selection:
            self.apply_btn.config(state=tk.DISABLED)
            return

        iid = selection[0]
        raw_data = self._results_cache.get(iid)
        if not raw_data:
            return

        details = (
            f"Название: {raw_data.get('title', '—')} | Артист: {raw_data.get('artist', '—')}\n"
            f"Альбом: {raw_data.get('album', '—')} | Лейбл: {raw_data.get('label', '—')} | Год: {raw_data.get('year', '—')}\n"
            f"Источник данных: {raw_data.get('source', '—').upper()}"
        )
        self.details_label.config(text=details)
        self.apply_btn.config(state=tk.NORMAL)

    def apply_metadata(self):
        """Применение выбранных метаданных."""
        selection = self.results_table.selection()
        if not selection:
            return

        iid = selection[0]
        selected_payload = self._results_cache.get(iid)
        if not selected_payload:
            return

        try:
            self.viewmodel.apply_metadata(selected_payload)
            self.update_status(f"✅ Метаданные '{selected_payload.get('title')}' успешно применены")
            messagebox.showinfo("Успех", "Метаданные успешно синхронизированы с локальной базой.")
        except Exception as e:
            self.update_status(f"❌ Ошибка применения: {e}")
            messagebox.showerror("Ошибка", f"Не удалось применить метаданные: {e}")
