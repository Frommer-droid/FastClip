from __future__ import annotations

import ctypes
import unittest
from ctypes import wintypes

from app.services.window_service import WindowService


class WindowServiceHwndTests(unittest.TestCase):
    def test_hwnd_value_accepts_plain_int(self) -> None:
        self.assertEqual(12345, WindowService._hwnd_value(12345))

    def test_hwnd_value_accepts_ctypes_hwnd(self) -> None:
        self.assertEqual(12345, WindowService._hwnd_value(wintypes.HWND(12345)))

    def test_hwnd_value_accepts_empty_values(self) -> None:
        self.assertEqual(0, WindowService._hwnd_value(None))
        self.assertEqual(0, WindowService._hwnd_value(wintypes.HWND(0)))
        self.assertEqual(0, WindowService._hwnd_value(ctypes.c_void_p(None)))


if __name__ == "__main__":
    unittest.main()
