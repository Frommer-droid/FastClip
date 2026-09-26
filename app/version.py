"""Чтение версии приложения из единого источника VERSION."""

from __future__ import annotations

import sys
from pathlib import Path


def _read_version() -> str:
    if getattr(sys, "frozen", False):
        try:
            bundled_version = Path(sys._MEIPASS) / "VERSION"  # type: ignore[attr-defined]
            if bundled_version.exists():
                value = bundled_version.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except Exception:
            pass

        # Резервный путь: VERSION рядом с exe.
        exe_version = Path(sys.executable).resolve().parent / "VERSION"
        if exe_version.exists():
            value = exe_version.read_text(encoding="utf-8").strip()
            if value:
                return value
        return "0.0.0"

    dev_version = Path(__file__).resolve().parent.parent / "VERSION"
    if dev_version.exists():
        value = dev_version.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "0.0.0"


__version__ = _read_version()
