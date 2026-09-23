from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

WH_KEYBOARD_LL = 13
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

LLKHF_EXTENDED = 0x01

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

logger = logging.getLogger(__name__)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class HotkeyService(QObject):
    hotkey_pressed = Signal()

    def __init__(self, modifier_scancode: int, trigger_scancode: int) -> None:
        super().__init__()
        self._modifier_scancode = modifier_scancode
        self._trigger_scancode = trigger_scancode
        self._hook_handle: wintypes.HANDLE | None = None
        self._is_modifier_pressed = False
        self._trigger_latched = False
        self._suppress_trigger_key = False

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._hook_proc = HOOKPROC(self._keyboard_proc)

        self._set_windows_hook_ex = self._user32.SetWindowsHookExW
        self._set_windows_hook_ex.argtypes = (
            ctypes.c_int,
            HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        self._set_windows_hook_ex.restype = wintypes.HANDLE

        self._call_next_hook_ex = self._user32.CallNextHookEx
        self._call_next_hook_ex.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._call_next_hook_ex.restype = LRESULT

        self._unhook_windows_hook_ex = self._user32.UnhookWindowsHookEx
        self._unhook_windows_hook_ex.argtypes = (wintypes.HANDLE,)
        self._unhook_windows_hook_ex.restype = wintypes.BOOL

        self._get_module_handle = self._kernel32.GetModuleHandleW
        self._get_module_handle.argtypes = (wintypes.LPCWSTR,)
        self._get_module_handle.restype = wintypes.HMODULE

    def register(self, app: QApplication) -> bool:
        del app
        if self._hook_handle is not None:
            return True

        module_handle = self._get_module_handle(None)
        hook_handle = self._set_windows_hook_ex(
            WH_KEYBOARD_LL,
            self._hook_proc,
            module_handle,
            0,
        )
        if not hook_handle:
            logger.error("hotkey hook registration failed error=%s", ctypes.get_last_error())
            return False

        self._hook_handle = hook_handle
        logger.info(
            "hotkey hook registered modifier_scancode=%s trigger_scancode=%s",
            self._modifier_scancode,
            self._trigger_scancode,
        )
        return True

    def unregister(self, app: QApplication) -> None:
        del app
        if self._hook_handle is None:
            return

        self._unhook_windows_hook_ex(self._hook_handle)
        self._hook_handle = None
        self._is_modifier_pressed = False
        self._trigger_latched = False
        self._suppress_trigger_key = False

    def _keyboard_proc(self, code, w_param, l_param):
        if code == HC_ACTION:
            msg = int(w_param)
            hook_data_ptr = ctypes.cast(
                ctypes.c_void_p(int(l_param)),
                ctypes.POINTER(KBDLLHOOKSTRUCT),
            )
            hook_data = hook_data_ptr.contents
            scan_code = int(hook_data.scanCode)
            is_extended = bool(int(hook_data.flags) & LLKHF_EXTENDED)

            if msg in (WM_KEYUP, WM_SYSKEYUP):
                if scan_code == self._modifier_scancode and not is_extended:
                    self._is_modifier_pressed = False
                if scan_code == self._trigger_scancode:
                    if self._suppress_trigger_key:
                        self._suppress_trigger_key = False
                        self._trigger_latched = False
                        return 1
                    self._trigger_latched = False
            elif msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if scan_code == self._modifier_scancode and not is_extended:
                    self._is_modifier_pressed = True
                if scan_code == self._trigger_scancode and self._is_modifier_pressed:
                    self._suppress_trigger_key = True
                    if not self._trigger_latched:
                        self._trigger_latched = True
                        logger.info(
                            "hotkey emitted modifier_scancode=%s trigger_scancode=%s",
                            self._modifier_scancode,
                            self._trigger_scancode,
                        )
                        self.hotkey_pressed.emit()
                    # Блокируем дальнейшую обработку нажатия триггер-клавиши.
                    return 1

        return int(self._call_next_hook_ex(self._hook_handle, code, w_param, l_param))
