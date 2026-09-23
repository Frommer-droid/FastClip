from __future__ import annotations

import ctypes
import logging
import sys
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config.constants import (
    DEFAULT_CLIP_TAB_NAME,
    DEFAULT_IMAGE_TAB_NAME,
    HOTKEY_MODIFIER_SCANCODE,
    HOTKEY_TEXT,
    HOTKEY_TRIGGER_SCANCODE,
    MAX_CLIP_ITEMS,
    POPUP_SETTINGS_KEY,
    SETTINGS_WINDOW_SETTINGS_KEY,
)
from app.core.clipboard_store import ClipboardStore
from app.core.tab_state_resolver import merge_tabs_state
from app.models.clip_item import CLIP_KIND_IMAGE
from app.services.auto_start_service import AutoStartService
from app.services.clip_history_service import ClipHistoryService
from app.services.clip_image_service import ClipImageService
from app.services.clipboard_service import ClipboardService
from app.services.hotkey_service import HotkeyService
from app.services.input_service import InputService
from app.services.settings_service import SettingsService
from app.services.tray_service import TrayService
from app.services.window_service import WindowService
from app.ui.popup_window import PopupWindow
from app.ui.settings_window import SettingsWindow

logger = logging.getLogger(__name__)


class AppController(QObject):
    def __init__(self, app: QApplication, app_icon: QIcon) -> None:
        super().__init__()
        self._app = app
        self._target_window: int = 0
        self._target_focus_window: int = 0
        self._suppress_clipboard_until: float = 0.0
        self._self_written_image_path: str | None = None
        self._hotkeys_paused = False

        self._clipboard_store = ClipboardStore(max_items=MAX_CLIP_ITEMS)
        self._clip_history_service = ClipHistoryService(max_items=MAX_CLIP_ITEMS)
        self._clip_image_service = ClipImageService()
        self._clipboard_service = ClipboardService()
        self._input_service = InputService()
        self._window_service = WindowService()
        self._settings_service = SettingsService()
        self._auto_start_service = AutoStartService()
        self._hotkey_service = HotkeyService(
            modifier_scancode=HOTKEY_MODIFIER_SCANCODE,
            trigger_scancode=HOTKEY_TRIGGER_SCANCODE,
        )
        self._popup = PopupWindow()
        # Создаем HWND заранее, чтобы первая активация по хоткею была стабильной.
        self._popup.winId()
        self._settings_window = SettingsWindow()
        self._tray_service = TrayService(parent=self._popup, icon=app_icon)
        history_tabs, history_active_tab = self._clip_history_service.load_state()
        (
            settings_tab_order,
            settings_active_tab,
            self._preferred_overflow_tab,
        ) = self._settings_service.load_tabs_state()
        settings_user_tabs = self._settings_service.load_user_tabs()
        tabs, active_tab = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab=history_active_tab,
            settings_tab_order=settings_tab_order,
            settings_active_tab=settings_active_tab,
            settings_user_tabs=settings_user_tabs,
        )
        self._clipboard_store.load(tabs=tabs, active_tab=active_tab)
        self._persist_clip_history()
        self._clip_image_service.cleanup_unreferenced(
            self._clipboard_store.referenced_image_paths()
        )
        self._has_saved_popup_geometry = self._settings_service.apply_window_geometry(
            self._popup, POPUP_SETTINGS_KEY
        )
        self._has_saved_settings_geometry = self._settings_service.apply_window_geometry(
            self._settings_window, SETTINGS_WINDOW_SETTINGS_KEY
        )

        self._popup.item_chosen.connect(self._on_item_chosen)
        self._popup.items_deleted.connect(self._on_items_deleted)
        self._popup.clear_all_requested.connect(self._on_clear_all_requested)
        self._popup.pin_toggle_requested.connect(self._on_pin_toggle_requested)
        self._popup.item_note_changed.connect(self._on_item_note_changed)
        self._popup.tab_changed.connect(self._on_tab_changed)
        self._popup.tab_close_requested.connect(self._on_tab_close_requested)
        self._popup.tab_rename_requested.connect(self._on_tab_rename_requested)
        self._popup.tab_capture_lock_toggle_requested.connect(
            self._on_tab_capture_lock_toggle_requested
        )
        self._popup.tab_create_requested.connect(self._on_tab_create_requested)
        self._popup.escape_pressed.connect(self._on_popup_dismissed)
        self._clipboard_service.connect_data_changed(self._on_clipboard_data_changed)
        self._hotkey_service.hotkey_pressed.connect(self._on_hotkey_pressed)
        self._tray_service.request_open_popup.connect(self._show_popup_only)
        self._tray_service.request_open_settings.connect(self._show_settings_window)
        self._tray_service.request_hotkeys_paused_changed.connect(self._on_hotkeys_paused_changed)
        self._tray_service.request_exit.connect(self._app.quit)
        self._settings_window.closed.connect(self._on_settings_window_closed)
        self._settings_window.autostart_changed.connect(self._on_autostart_changed)
        self._app.aboutToQuit.connect(self._shutdown)

    def start(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Поддерживается только Windows.")
        if not self._tray_service.is_available():
            raise RuntimeError("Системный трей недоступен на этом устройстве.")

        is_registered = self._hotkey_service.register(self._app)
        if not is_registered:
            raise RuntimeError(f"Не удалось зарегистрировать хоткей {HOTKEY_TEXT}.")

        self._tray_service.show()

    def _on_hotkey_pressed(self) -> None:
        if self._hotkeys_paused:
            return
        self._target_window = self._window_service.get_foreground_window()
        if not self._target_window:
            self._target_window = self._window_service.desktop_paste_target()
        self._target_focus_window = self._window_service.focus_window_for(
            self._target_window
        )
        logger.info(
            "hotkey_pressed target_window=%s target_class=%s target_focus=%s focus_class=%s",
            self._target_window,
            self._window_service.window_class_name(self._target_window),
            self._target_focus_window,
            self._window_service.window_class_name(self._target_focus_window),
        )
        # Показываем popup уже после возврата из low-level hook, чтобы фокус
        # стабильно переходил с первого нажатия глобального хоткея.
        QTimer.singleShot(0, self._show_popup_only)

    def _on_hotkeys_paused_changed(self, paused: bool) -> None:
        self._hotkeys_paused = bool(paused)

    def _show_popup_only(self) -> None:
        self._refresh_popup_content()
        self._popup.show_popup(center=not self._has_saved_popup_geometry)
        self._has_saved_popup_geometry = True
        popup_hwnd = int(self._popup.winId())
        if popup_hwnd:
            self._activate_popup_with_retries(popup_hwnd)

    def _activate_popup_with_retries(self, popup_hwnd: int) -> None:
        for delay_ms in (0, 40, 120):
            QTimer.singleShot(
                delay_ms,
                lambda hwnd=popup_hwnd: self._window_service.activate_window(hwnd),
            )

    def _show_settings_window(self) -> None:
        self._sync_autostart_state(show_error=True)
        self._settings_window.show_window(center=not self._has_saved_settings_geometry)
        self._has_saved_settings_geometry = True

    def _on_item_chosen(self, item_key: str, keep_open: bool) -> None:
        clip_item = self._clipboard_store.find_in_active_tab(item_key)
        if clip_item is None:
            logger.info("item_chosen ignored: item not found key=%s", item_key)
            return

        moved = self._clipboard_store.promote_in_active_tab(item_key)
        if moved:
            self._persist_clip_history()

        if clip_item.kind == CLIP_KIND_IMAGE:
            logger.info(
                "item_chosen image key=%s image_name=%r image_path=%s keep_open=%s target_window=%s",
                clip_item.key,
                clip_item.image_name,
                clip_item.image_path,
                keep_open,
                self._target_window,
            )
            image = self._clip_image_service.load_image(clip_item.image_path)
            if image is None:
                logger.error(
                    "item_chosen image load failed key=%s image_path=%s",
                    clip_item.key,
                    clip_item.image_path,
                )
                self._popup.show_tab_error("Не удалось загрузить изображение из локального хранилища.")
                return
            image_path = self._clip_image_service.export_for_clipboard(
                relative_path=clip_item.image_path,
                image=image,
                image_name=clip_item.image_name,
            )
            if image_path is None:
                image_path = self._clip_image_service.resolve_path(clip_item.image_path)
            logger.info(
                "item_chosen image clipboard_file=%s original_name=%r",
                image_path,
                clip_item.image_name,
            )
            self._mark_self_written_image(clip_item.image_path)
            self._suppress_clipboard_for(1.2)
            self._clipboard_service.write_image(image, file_path=image_path)
        else:
            logger.info(
                "item_chosen text key=%s keep_open=%s target_window=%s",
                clip_item.key,
                keep_open,
                self._target_window,
            )
            self._suppress_clipboard_for(0.35)
            self._clipboard_service.write_text(clip_item.text)

        if not keep_open:
            self._settings_service.save_window_geometry(self._popup, POPUP_SETTINGS_KEY)
            self._popup.hide()

        if keep_open:
            if moved:
                self._refresh_popup_content()
            QTimer.singleShot(80, lambda: self._send_paste_keep_popup_open(retry_count=0))
            return

        self._send_paste_to_target(paste_delay_ms=240)

    def _send_paste_keep_popup_open(self, retry_count: int) -> None:
        # Режим "как раньше": вставка только после отпускания Alt.
        if self._is_alt_pressed() and retry_count < 25:
            QTimer.singleShot(
                20,
                lambda count=retry_count + 1: self._send_paste_keep_popup_open(count),
            )
            return

        self._send_paste_to_target(paste_delay_ms=140)

    def _send_paste_to_target(self, paste_delay_ms: int) -> None:
        target_window = self._target_window
        target_focus_window = self._target_focus_window
        logger.info(
            "send_paste_to_target target_window=%s target_focus=%s paste_delay_ms=%s",
            target_window,
            target_focus_window,
            paste_delay_ms,
        )
        if target_window:
            for delay_ms in (0, 80, 160):
                QTimer.singleShot(
                    delay_ms,
                    lambda hwnd=target_window, focus=target_focus_window: (
                        self._activate_target_for_paste(hwnd, focus)
                    ),
                )
        QTimer.singleShot(max(0, paste_delay_ms), self._input_service.send_ctrl_v)

    def _activate_target_for_paste(self, hwnd: int, focus_hwnd: int) -> None:
        try:
            self._window_service.activate_for_paste(hwnd, focus_hwnd=focus_hwnd)
        except Exception:
            logger.exception(
                "activate_target_for_paste failed hwnd=%s focus_hwnd=%s",
                hwnd,
                focus_hwnd,
            )

    @staticmethod
    def _is_alt_pressed() -> bool:
        if sys.platform != "win32":
            return False
        vk_menu = 0x12
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_menu) & 0x8000)

    def _on_popup_dismissed(self) -> None:
        self._settings_service.save_window_geometry(self._popup, POPUP_SETTINGS_KEY)
        self._popup.hide()

    def _on_settings_window_closed(self) -> None:
        self._settings_service.save_window_geometry(
            self._settings_window, SETTINGS_WINDOW_SETTINGS_KEY
        )

    def _on_items_deleted(self, item_keys: list[str]) -> None:
        removed = self._clipboard_store.remove_many(item_keys)
        if removed <= 0:
            return

        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_clear_all_requested(self) -> None:
        self._clipboard_store.clear()
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_pin_toggle_requested(self, item_key: str) -> None:
        if not self._clipboard_store.toggle_pinned(item_key):
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_item_note_changed(self, item_key: str, note: str) -> None:
        if not self._clipboard_store.set_note_in_active_tab(item_key, note):
            return
        self._persist_clip_history()

    def _on_tab_changed(self, tab_name: str) -> None:
        changed = self._clipboard_store.set_active_tab(tab_name)
        if not changed:
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_tab_create_requested(self, tab_name: str) -> None:
        created = self._clipboard_store.add_tab(tab_name)
        if not created:
            self._popup.show_tab_error("Вкладка с таким именем уже существует.")
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_tab_close_requested(self, tab_name: str) -> None:
        removed = self._clipboard_store.remove_tab(tab_name)
        if not removed:
            self._popup.show_tab_error("Нельзя удалить системную или последнюю вкладку.")
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_tab_rename_requested(self, source_name: str, target_name: str) -> None:
        renamed = self._clipboard_store.rename_tab(source_name, target_name)
        if not renamed:
            self._popup.show_tab_error("Не удалось переименовать вкладку.")
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _on_tab_capture_lock_toggle_requested(self, tab_name: str) -> None:
        changed = self._clipboard_store.toggle_tab_capture_lock(tab_name)
        if not changed:
            return
        self._persist_clip_history()
        self._refresh_popup_content()

    def _persist_clip_history(self) -> None:
        tabs, active_tab = self._clipboard_store.snapshot()
        preferred_overflow_tab = self._popup.preferred_overflow_tab_name()
        if preferred_overflow_tab is not None:
            self._preferred_overflow_tab = preferred_overflow_tab
        self._clip_history_service.save_state(tabs=tabs, active_tab=active_tab)
        self._settings_service.save_tabs_state(
            tab_order=self._extract_tab_order(tabs),
            active_tab=active_tab,
            preferred_overflow_tab=self._preferred_overflow_tab,
        )
        self._settings_service.save_user_tabs(self._extract_user_tabs(tabs))
        self._clip_image_service.cleanup_unreferenced(
            self._clipboard_store.referenced_image_paths()
        )

    @staticmethod
    def _extract_tab_order(tabs: list[dict[str, object]]) -> list[str]:
        tab_order: list[str] = []
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            name = tab.get("name")
            if not isinstance(name, str):
                continue
            prepared = name.strip()
            if not prepared:
                continue
            tab_order.append(prepared)
        return tab_order

    @staticmethod
    def _extract_user_tabs(tabs: list[dict[str, object]]) -> list[dict[str, object]]:
        user_tabs: list[dict[str, object]] = []
        system_names = {
            DEFAULT_CLIP_TAB_NAME.casefold(),
            DEFAULT_IMAGE_TAB_NAME.casefold(),
        }
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            name = tab.get("name")
            if not isinstance(name, str) or name.casefold() in system_names:
                continue
            user_tabs.append(tab)
        return user_tabs

    def _on_clipboard_data_changed(self) -> None:
        if self._is_clipboard_suppressed():
            logger.info("clipboard_data_changed ignored: suppressed")
            return

        payload = self._clipboard_service.read_payload()
        if payload is None:
            logger.info("clipboard_data_changed ignored: empty payload")
            return

        changed = False
        if payload.kind == CLIP_KIND_IMAGE and payload.image is not None:
            logger.info("clipboard_data_changed image image_name=%r", payload.image_name)
            stored_image = self._clip_image_service.save_image(payload.image)
            if stored_image is None:
                logger.error("clipboard_data_changed image save failed")
                return
            if self._should_ignore_self_written_image(stored_image.relative_path):
                logger.info(
                    "clipboard_data_changed ignored self-written image path=%s",
                    stored_image.relative_path,
                )
                return
            changed = self._clipboard_store.add_image(
                image_path=stored_image.relative_path,
                width=stored_image.width,
                height=stored_image.height,
                image_name=payload.image_name,
            )
        else:
            logger.info("clipboard_data_changed text length=%s", len(payload.text))
            changed = self._clipboard_store.add_text(payload.text)

        if changed:
            self._persist_clip_history()
            if self._popup.isVisible():
                self._refresh_popup_content()

    def _suppress_clipboard_for(self, seconds: float) -> None:
        self._suppress_clipboard_until = time.monotonic() + max(0.0, seconds)

    def _is_clipboard_suppressed(self) -> bool:
        return time.monotonic() < self._suppress_clipboard_until

    def _mark_self_written_image(self, image_path: str) -> None:
        prepared = image_path.strip().casefold()
        if not prepared:
            return
        self._self_written_image_path = prepared
        QTimer.singleShot(
            2500,
            lambda expected=prepared: self._clear_self_written_image(expected),
        )

    def _clear_self_written_image(self, expected_path: str) -> None:
        if self._self_written_image_path == expected_path:
            self._self_written_image_path = None

    def _should_ignore_self_written_image(self, image_path: str) -> bool:
        prepared = image_path.strip().casefold()
        if prepared and prepared == self._self_written_image_path:
            self._self_written_image_path = None
            return True
        return False

    def _refresh_popup_content(self) -> None:
        self._popup.set_tabs(
            tab_states=self._clipboard_store.tab_states(),
            active_tab=self._clipboard_store.active_tab_name(),
            preferred_overflow_tab=self._preferred_overflow_tab,
        )
        self._preferred_overflow_tab = self._popup.preferred_overflow_tab_name()
        self._popup.set_items(self._clipboard_store.all_items())

    def _on_autostart_changed(self, enabled: bool) -> None:
        try:
            self._auto_start_service.set_enabled(enabled)
        except Exception as error:
            self._settings_window.set_autostart_enabled(not enabled)
            self._settings_window.show_error(
                f"Не удалось изменить параметр автозапуска Windows.\n{error}"
            )

    def _sync_autostart_state(self, show_error: bool) -> None:
        try:
            enabled = self._auto_start_service.is_enabled()
        except Exception as error:
            self._settings_window.set_autostart_enabled(False)
            if show_error:
                self._settings_window.show_error(
                    f"Не удалось проверить статус автозапуска.\n{error}"
                )
            return
        self._settings_window.set_autostart_enabled(enabled)

    def _shutdown(self) -> None:
        self._tray_service.hide()
        self._persist_clip_history()
        self._settings_service.save_window_geometry(self._popup, POPUP_SETTINGS_KEY)
        self._settings_service.save_window_geometry(
            self._settings_window, SETTINGS_WINDOW_SETTINGS_KEY
        )
        self._hotkey_service.unregister(self._app)
