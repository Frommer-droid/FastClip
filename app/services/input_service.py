from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

SCAN_LEFT_CTRL = 0x1D
SCAN_C = 0x2E
SCAN_V = 0x2F

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

logger = logging.getLogger(__name__)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


class InputService:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._send_input = self._user32.SendInput
        self._send_input.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        )
        self._send_input.restype = wintypes.UINT

    def send_ctrl_c(self) -> None:
        self._send_combo(modifier_scancodes=[SCAN_LEFT_CTRL], main_scancode=SCAN_C)

    def send_ctrl_v(self) -> None:
        logger.info("send_ctrl_v requested")
        self._send_combo(modifier_scancodes=[SCAN_LEFT_CTRL], main_scancode=SCAN_V)

    def _send_combo(self, modifier_scancodes: list[int], main_scancode: int) -> None:
        pressed_modifiers: list[int] = []
        try:
            for scancode in modifier_scancodes:
                self._send_scancode(scancode, key_up=False)
                pressed_modifiers.append(scancode)
            self._send_scancode(main_scancode, key_up=False)
            self._send_scancode(main_scancode, key_up=True)
        finally:
            for scancode in reversed(pressed_modifiers):
                try:
                    self._send_scancode(scancode, key_up=True)
                except Exception:
                    pass
        time.sleep(0.01)

    def _send_scancode(self, scancode: int, key_up: bool, extended: bool = False) -> None:
        scan_code = int(scancode)
        is_extended = extended or scan_code > 0xFF
        flags = KEYEVENTF_SCANCODE
        if key_up:
            flags |= KEYEVENTF_KEYUP
        if is_extended:
            flags |= KEYEVENTF_EXTENDEDKEY

        keyboard_input = KEYBDINPUT(
            wVk=0,
            wScan=scan_code & 0xFF,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        )
        event = INPUT(type=INPUT_KEYBOARD, ki=keyboard_input)
        sent = self._send_input(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            error = ctypes.get_last_error()
            logger.error(
                "SendInput failed scancode=%s key_up=%s extended=%s error=%s",
                scancode,
                key_up,
                extended,
                error,
            )
            raise ctypes.WinError(error)
