from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.version import __version__


class SettingsWindow(QWidget):
    closed = Signal()
    autostart_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setWindowTitle(f"FastClip v{__version__} - Настройки")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(760, 460)

        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self._tab_widget.setTabShape(QTabWidget.TabShape.Rounded)

        self._autostart_checkbox = QCheckBox("Запускать при старте Windows")
        self._autostart_checkbox.toggled.connect(self.autostart_changed.emit)

        system_page = QWidget()
        system_layout = QVBoxLayout(system_page)
        system_layout.setContentsMargins(14, 14, 14, 14)
        system_layout.setSpacing(10)
        system_layout.addWidget(self._autostart_checkbox)

        autostart_hint = QLabel(
            "При включении создаётся ярлык FastClip в стандартной папке автозагрузки Windows."
        )
        autostart_hint.setObjectName("settingsHint")
        autostart_hint.setWordWrap(True)
        system_layout.addWidget(autostart_hint)
        system_layout.addStretch(1)

        self._tab_widget.addTab(system_page, "System")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._tab_widget)

        self._settings_stylesheet = self._build_settings_stylesheet()
        self.setStyleSheet(self._settings_stylesheet)

    def set_autostart_enabled(self, enabled: bool) -> None:
        blocked = self._autostart_checkbox.blockSignals(True)
        self._autostart_checkbox.setChecked(enabled)
        self._autostart_checkbox.blockSignals(blocked)

    def show_window(self, center: bool) -> None:
        if center:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                rect = screen.availableGeometry()
                x = rect.x() + (rect.width() - self.width()) // 2
                y = rect.y() + (rect.height() - self.height()) // 2
                self.move(x, y)

        self.setStyleSheet(self._settings_stylesheet)
        self.style().polish(self)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_error(self, message: str) -> None:
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("FastClip")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setStyleSheet(self._build_message_box_stylesheet())
        msg_box.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        event.accept()

    @staticmethod
    def _build_settings_stylesheet() -> str:
        return """
            QWidget#settingsRoot {
                background: #282C34;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                border-radius: 12px;
            }
            QWidget#settingsRoot QTabWidget::pane {
                border: 1px solid #3E4451;
                border-radius: 8px;
                top: -1px;
                background: #21252B;
            }
            QWidget#settingsRoot QTabBar::tab {
                background: #252C38;
                color: #ABB2BF;
                border: 1px solid #3B414D;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 7px 14px;
                margin-right: 4px;
                min-width: 90px;
            }
            QWidget#settingsRoot QTabBar::tab:selected {
                background: #1E3A5F;
                color: #3AE2CE;
                border: 1px solid #2A4B75;
            }
            QWidget#settingsRoot QTabBar::tab:!selected {
                margin-top: 2px;
            }
            QWidget#settingsRoot QCheckBox {
                color: #ABB2BF;
                spacing: 10px;
                font-size: 15px;
            }
            QWidget#settingsRoot QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #3B414D;
                border-radius: 5px;
                background: #1F2530;
            }
            QWidget#settingsRoot QCheckBox::indicator:checked {
                border: 1px solid #2A4B75;
                background: #3E5F8A;
            }
            QWidget#settingsRoot QLabel#settingsHint {
                color: #93A0B8;
            }
        """

    @staticmethod
    def _build_message_box_stylesheet() -> str:
        return """
            QMessageBox {
                background: #282C34;
                color: #ABB2BF;
            }
            QMessageBox QLabel {
                color: #ABB2BF;
            }
            QMessageBox QPushButton {
                background: #3E5F8A;
                color: #FFFFFF;
                border: 1px solid #2F4D73;
                border-radius: 8px;
                padding: 6px 12px;
                min-width: 90px;
                font-weight: 700;
            }
            QMessageBox QPushButton:hover {
                background: #4A74A8;
            }
            QMessageBox QPushButton:pressed {
                background: #2F4D73;
            }
        """
