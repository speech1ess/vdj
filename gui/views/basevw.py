import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any, Optional


class BaseView:
    """
    Чистый базовый класс для представлений (View).
    Не содержит бизнес-логики, не подписывается на системные логгеры напрямую.
    Вся связь с бекендом идет СТРОГО через viewmodel.
    """

    def __init__(
        self,
        root: tk.Tk,
        parent: ttk.Frame,
        viewmodel: Any = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self.root = root
        self.parent = parent
        self.viewmodel = viewmodel

        # Колбэк для вывода сообщений в статус-бар главного окна
        self.status_callback = status_callback or (lambda msg: None)

        # Контейнер для содержимого конкретного View
        self.content_frame = ttk.Frame(self.parent)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Передаем коллбэк во ViewModel (VM сама решит, как и какие логи сюда слать)
        if self.viewmodel and hasattr(self.viewmodel, "attach_log_callback"):
            self.viewmodel.attach_log_callback(self.update_status)

    def update_status(self, message: str) -> None:
        """Потокобезопасное обновление статуса в UI."""
        # Оборачиваем в after, чтобы безопасно принимать сообщения из фоновых потоков ViewModel
        self.root.after(0, lambda: self.status_callback(message))

    def force_update_status(self, message: str) -> None:
        """Принудительное обновление UI."""
        self.update_status(f"⚠️ {message}")

    def clear_content_frame(self) -> None:
        """Очищает фрейм от старых виджетов перед перерисовкой."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def create_nav_button(self, text: str, command: Callable) -> ttk.Button:
        """Хелпер для создания кнопок."""
        btn = ttk.Button(self.parent, text=text, command=command)
        btn.pack(fill=tk.X, padx=10, pady=5)
        return btn

    def destroy(self) -> None:
        """Очистка ресурсов при закрытии View."""
        if self.viewmodel and hasattr(self.viewmodel, "detach_log_callback"):
            self.viewmodel.detach_log_callback()
        self.clear_content_frame()
        self.content_frame.destroy()
