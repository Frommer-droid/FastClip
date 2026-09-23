from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.config.constants import HOTKEY_TEXT
from app.version import __version__


class TrayService(QObject):
    request_open_popup = Signal()
    request_open_settings = Signal()
    request_hotkeys_paused_changed = Signal(bool)
    request_exit = Signal()

    def __init__(self, parent: QObject, icon: QIcon) -> None:
        super().__init__(parent)
        self._tray_icon = QSystemTrayIcon(parent)
        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip(f"FastClip v{__version__}")
        self._tray_icon.activated.connect(self._on_activated)

        menu = QMenu()
        menu.setStyleSheet(self._build_menu_stylesheet())
        open_popup_action = QAction("Показать буфер", menu)
        open_settings_action = QAction("Настройки", menu)
        pause_action = QAction("Пауза", menu)
        pause_action.setCheckable(True)
        quit_action = QAction("Выход", menu)

        open_popup_action.triggered.connect(self.request_open_popup.emit)
        open_settings_action.triggered.connect(self.request_open_settings.emit)
        pause_action.toggled.connect(self.request_hotkeys_paused_changed.emit)
        quit_action.triggered.connect(self.request_exit.emit)

        menu.addAction(open_popup_action)
        menu.addAction(open_settings_action)
        menu.addAction(pause_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray_icon.setContextMenu(menu)

    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        self._tray_icon.show()
        self._tray_icon.showMessage(
            f"FastClip v{__version__}",
            f"Приложение запущено. Нажмите {HOTKEY_TEXT} для вызова буфера.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    def hide(self) -> None:
        self._tray_icon.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.request_open_popup.emit()

    @staticmethod
    def _build_menu_stylesheet() -> str:
        return """
            QMenu {
                background-color: #282C34;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                border-radius: 6px;
                padding: 7px 22px;
                margin: 2px 0;
            }
            QMenu::item:selected {
                background-color: #1E3A5F;
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background: #3E4451;
                margin: 4px 6px;
            }
        """
