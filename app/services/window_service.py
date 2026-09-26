from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

SW_RESTORE = 9
SW_SHOW = 5
GA_ROOT = 2
DESKTOP_CLASSES = {"WorkerW", "Progman"}

logger = logging.getLogger(__name__)


class WindowService:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._get_foreground_window = self._user32.GetForegroundWindow
        self._get_foreground_window.argtypes = ()
        self._get_foreground_window.restype = wintypes.HWND

        self._set_foreground_window = self._user32.SetForegroundWindow
        self._set_foreground_window.argtypes = (wintypes.HWND,)
        self._set_foreground_window.restype = wintypes.BOOL

        self._show_window = self._user32.ShowWindow
        self._show_window.argtypes = (wintypes.HWND, ctypes.c_int)
        self._show_window.restype = wintypes.BOOL

        self._is_iconic = self._user32.IsIconic
        self._is_iconic.argtypes = (wintypes.HWND,)
        self._is_iconic.restype = wintypes.BOOL

        self._bring_window_to_top = self._user32.BringWindowToTop
        self._bring_window_to_top.argtypes = (wintypes.HWND,)
        self._bring_window_to_top.restype = wintypes.BOOL

        self._set_active_window = self._user32.SetActiveWindow
        self._set_active_window.argtypes = (wintypes.HWND,)
        self._set_active_window.restype = wintypes.HWND

        self._set_focus = self._user32.SetFocus
        self._set_focus.argtypes = (wintypes.HWND,)
        self._set_focus.restype = wintypes.HWND

        self._get_focus = self._user32.GetFocus
        self._get_focus.argtypes = ()
        self._get_focus.restype = wintypes.HWND

        self._get_class_name = self._user32.GetClassNameW
        self._get_class_name.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        self._get_class_name.restype = ctypes.c_int

        self._find_window_ex = self._user32.FindWindowExW
        self._find_window_ex.argtypes = (
            wintypes.HWND,
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
        )
        self._find_window_ex.restype = wintypes.HWND

        self._find_window = self._user32.FindWindowW
        self._find_window.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        self._find_window.restype = wintypes.HWND

        self._get_shell_window = self._user32.GetShellWindow
        self._get_shell_window.argtypes = ()
        self._get_shell_window.restype = wintypes.HWND

        self._get_ancestor = self._user32.GetAncestor
        self._get_ancestor.argtypes = (wintypes.HWND, wintypes.UINT)
        self._get_ancestor.restype = wintypes.HWND

        self._is_window = self._user32.IsWindow
        self._is_window.argtypes = (wintypes.HWND,)
        self._is_window.restype = wintypes.BOOL

        self._get_window_thread_process_id = self._user32.GetWindowThreadProcessId
        self._get_window_thread_process_id.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        self._get_window_thread_process_id.restype = wintypes.DWORD

        self._attach_thread_input = self._user32.AttachThreadInput
        self._attach_thread_input.argtypes = (
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.BOOL,
        )
        self._attach_thread_input.restype = wintypes.BOOL

        self._get_current_thread_id = self._kernel32.GetCurrentThreadId
        self._get_current_thread_id.argtypes = ()
        self._get_current_thread_id.restype = wintypes.DWORD

    def get_foreground_window(self) -> int:
        return self._hwnd_value(self._get_foreground_window())

    def window_class_name(self, hwnd: int) -> str:
        return self._class_name(hwnd)

    def desktop_paste_target(self) -> int:
        focus_handle = self._desktop_list_view_for(wintypes.HWND(0))
        if focus_handle:
            root_handle = self._root_window(focus_handle)
            if root_handle:
                logger.info(
                    "desktop_paste_target root=%s focus=%s",
                    root_handle,
                    focus_handle,
                )
                return root_handle

        shell_window = self._hwnd_value(self._get_shell_window())
        if shell_window:
            logger.info("desktop_paste_target shell_window=%s", shell_window)
            return shell_window

        progman = self._hwnd_value(self._find_window("Progman", None))
        logger.info("desktop_paste_target progman=%s", progman)
        return progman

    def focus_window_for(self, hwnd: int) -> int:
        if not hwnd:
            return 0

        target_handle = int(hwnd)
        target_thread = self._window_thread_id(wintypes.HWND(target_handle))
        current_thread = int(self._get_current_thread_id())

        attached_target = False
        try:
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    self._attach_thread_input(current_thread, target_thread, True)
                )
            focus_handle = self._hwnd_value(self._get_focus())
        finally:
            if attached_target:
                self._attach_thread_input(current_thread, target_thread, False)

        if not self._is_valid_focus_for_target(target_handle, focus_handle):
            logger.info(
                "focus_window_for target=%s focus=%s valid=False",
                target_handle,
                focus_handle,
            )
            return 0

        logger.info(
            "focus_window_for target=%s focus=%s focus_class=%s",
            target_handle,
            focus_handle,
            self._class_name(focus_handle),
        )
        return focus_handle

    def activate_window(self, hwnd: int) -> bool:
        if not hwnd:
            logger.info("activate_window skipped: empty hwnd")
            return False

        target_handle = int(hwnd)
        target = wintypes.HWND(target_handle)
        # Восстанавливаем только действительно свернутое окно:
        # безусловный SW_RESTORE может выбивать приложение из полноэкранного режима.
        if bool(self._is_iconic(target)):
            self._show_window(target, SW_RESTORE)
        else:
            self._show_window(target, SW_SHOW)

        foreground = self._get_foreground_window()
        foreground_thread = self._window_thread_id(foreground)
        target_thread = self._window_thread_id(target)
        current_thread = int(self._get_current_thread_id())

        attached_foreground = False
        attached_target = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(
                    self._attach_thread_input(
                        current_thread,
                        foreground_thread,
                        True,
                    )
                )
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    self._attach_thread_input(
                        current_thread,
                        target_thread,
                        True,
                    )
                )

            self._bring_window_to_top(target)
            self._set_active_window(target)
            set_result = bool(self._set_foreground_window(target))
            foreground_after = self._hwnd_value(self._get_foreground_window())
            activated = foreground_after == target_handle
            logger.info(
                "activate_window target=%s set_result=%s foreground_after=%s activated=%s",
                target_handle,
                set_result,
                foreground_after,
                activated,
            )
            return activated
        finally:
            if attached_target:
                self._attach_thread_input(current_thread, target_thread, False)
            if attached_foreground:
                self._attach_thread_input(current_thread, foreground_thread, False)

    def activate_for_paste(self, hwnd: int, focus_hwnd: int = 0) -> bool:
        if not hwnd:
            logger.info("activate_for_paste skipped: empty hwnd")
            return False

        target_handle = int(hwnd)
        target_class = self._class_name(target_handle)
        if target_class not in DESKTOP_CLASSES:
            activated = self.activate_window(target_handle)
            focused = self._focus_preferred_child(target_handle, int(focus_hwnd))
            logger.info(
                "activate_for_paste target=%s class=%s default_activation=%s preferred_focus=%s focused=%s",
                target_handle,
                target_class,
                activated,
                int(focus_hwnd),
                focused,
            )
            return activated

        focus_handle = self._desktop_list_view_for(wintypes.HWND(target_handle))
        if not focus_handle and self._is_desktop_focus(int(focus_hwnd)):
            focus_handle = int(focus_hwnd)
        root_handle = self._root_window(focus_handle) or target_handle
        activated = self.activate_window(root_handle)
        if not focus_handle:
            logger.info(
                "activate_for_paste desktop target=%s class=%s list_view_not_found activated=%s",
                target_handle,
                target_class,
                activated,
            )
            return activated

        previous_focus = self._set_focus_with_thread_attach(focus_handle)
        logger.info(
            "activate_for_paste target=%s root=%s focus=%s focus_class=%s activated=%s previous_focus=%s",
            target_handle,
            root_handle,
            focus_handle,
            self._class_name(focus_handle),
            activated,
            previous_focus,
        )
        return activated

    def _focus_preferred_child(self, target_handle: int, focus_handle: int) -> int:
        if not self._is_valid_focus_for_target(target_handle, focus_handle):
            return 0
        return self._set_focus_with_thread_attach(focus_handle)

    def _set_focus_with_thread_attach(self, focus_handle: int) -> int:
        if not focus_handle:
            return 0

        focus_target = wintypes.HWND(focus_handle)
        foreground = self._get_foreground_window()
        foreground_thread = self._window_thread_id(foreground)
        focus_thread = self._window_thread_id(focus_target)
        current_thread = int(self._get_current_thread_id())

        attached_foreground = False
        attached_focus = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(
                    self._attach_thread_input(current_thread, foreground_thread, True)
                )
            if focus_thread and focus_thread != current_thread:
                attached_focus = bool(
                    self._attach_thread_input(current_thread, focus_thread, True)
                )
            return self._hwnd_value(self._set_focus(focus_target))
        finally:
            if attached_focus:
                self._attach_thread_input(current_thread, focus_thread, False)
            if attached_foreground:
                self._attach_thread_input(current_thread, foreground_thread, False)

    def _desktop_list_view_for(self, desktop_window: wintypes.HWND) -> int:
        shell_view = self._hwnd_value(
            self._find_window_ex(
                desktop_window,
                wintypes.HWND(0),
                "SHELLDLL_DefView",
                None,
            )
        )
        if not shell_view:
            progman = self._find_window_ex(wintypes.HWND(0), wintypes.HWND(0), "Progman", None)
            if progman:
                shell_view = self._hwnd_value(
                    self._find_window_ex(
                        progman,
                        wintypes.HWND(0),
                        "SHELLDLL_DefView",
                        None,
                    )
                )
        if not shell_view:
            worker = wintypes.HWND(0)
            while True:
                worker = self._find_window_ex(wintypes.HWND(0), worker, "WorkerW", None)
                if not worker:
                    break
                shell_view = self._hwnd_value(
                    self._find_window_ex(
                        worker,
                        wintypes.HWND(0),
                        "SHELLDLL_DefView",
                        None,
                    )
                )
                if shell_view:
                    break
        if not shell_view:
            logger.info("desktop_list_view_for shell view not found")
            return 0

        list_view = self._hwnd_value(
            self._find_window_ex(
                wintypes.HWND(shell_view),
                wintypes.HWND(0),
                "SysListView32",
                None,
            )
        )
        logger.info(
            "desktop_list_view_for desktop=%s shell_view=%s list_view=%s",
            self._hwnd_value(desktop_window),
            shell_view,
            list_view,
        )
        return list_view

    def _is_valid_focus_for_target(self, target_handle: int, focus_handle: int) -> bool:
        if not target_handle or not focus_handle:
            return False
        if not self._is_window(wintypes.HWND(target_handle)):
            return False
        if not self._is_window(wintypes.HWND(focus_handle)):
            return False

        target_root = self._root_window(target_handle)
        focus_root = self._root_window(focus_handle)
        return bool(target_root and focus_root and target_root == focus_root)

    def _is_desktop_focus(self, focus_handle: int) -> bool:
        if not focus_handle or not self._is_window(wintypes.HWND(focus_handle)):
            return False
        return self._class_name(focus_handle) == "SysListView32"

    def _root_window(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return self._hwnd_value(
            self._get_ancestor(wintypes.HWND(hwnd), GA_ROOT)
        ) or int(hwnd)

    @staticmethod
    def _hwnd_value(hwnd: object) -> int:
        value = getattr(hwnd, "value", hwnd)
        if value is None:
            return 0
        return int(value or 0)

    def _class_name(self, hwnd: int) -> str:
        if not hwnd:
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        if not self._get_class_name(wintypes.HWND(hwnd), buffer, len(buffer)):
            return ""
        return buffer.value

    def _window_thread_id(self, hwnd: wintypes.HWND) -> int:
        if not hwnd:
            return 0
        process_id = wintypes.DWORD(0)
        return int(self._get_window_thread_process_id(hwnd, ctypes.byref(process_id)))
