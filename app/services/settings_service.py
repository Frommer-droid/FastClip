from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME


class SettingsService:
    def __init__(self, settings_path: Path | None = None) -> None:
        if settings_path is not None:
            self._settings_path = settings_path
            return

        if getattr(sys, "frozen", False):
            root_dir = Path(sys.executable).resolve().parent
        else:
            root_dir = Path(__file__).resolve().parents[2]
        self._settings_path = root_dir / "settings.json"

    def apply_window_geometry(self, widget: QWidget, key: str) -> bool:
        data = self._read_all()
        geometry = data.get(key, {})

        x = geometry.get("x")
        y = geometry.get("y")
        width = geometry.get("width")
        height = geometry.get("height")
        maximized = bool(geometry.get("maximized", False))

        has_geometry = all(isinstance(value, int) for value in [x, y, width, height])
        if has_geometry:
            widget.setGeometry(x, y, width, height)

        if maximized:
            widget.setWindowState(widget.windowState() | Qt.WindowState.WindowMaximized)
        return has_geometry

    def save_window_geometry(self, widget: QWidget, key: str) -> None:
        if widget.isMaximized():
            geometry = widget.normalGeometry()
            maximized = True
        else:
            geometry = widget.geometry()
            maximized = False

        data = self._read_all()
        data[key] = {
            "x": int(geometry.x()),
            "y": int(geometry.y()),
            "width": int(geometry.width()),
            "height": int(geometry.height()),
            "maximized": maximized,
        }
        self._write_all(data)

    def load_tabs_state(self) -> tuple[list[str], str | None, str | None]:
        data = self._read_all()
        tabs_node = data.get("tabs_state")
        if not isinstance(tabs_node, dict):
            return [], None, None

        tab_order = self._normalize_tab_order(tabs_node.get("order"))
        active_tab = self._normalize_tab_name(tabs_node.get("active_tab"))
        preferred_overflow_tab = self._normalize_tab_name(tabs_node.get("preferred_overflow_tab"))
        valid_tab_names = {name.casefold() for name in tab_order}
        if (
            preferred_overflow_tab is not None
            and preferred_overflow_tab.casefold() not in valid_tab_names
        ):
            preferred_overflow_tab = None
        return tab_order, active_tab, preferred_overflow_tab

    def save_tabs_state(
        self,
        tab_order: list[str],
        active_tab: str,
        preferred_overflow_tab: str | None = None,
    ) -> None:
        normalized_order = self._normalize_tab_order(tab_order)
        normalized_active = self._normalize_tab_name(active_tab)
        names_lookup = {name.casefold() for name in normalized_order}
        if normalized_active is None or normalized_active.casefold() not in names_lookup:
            normalized_active = normalized_order[0] if normalized_order else None
        normalized_preferred_overflow = self._normalize_tab_name(preferred_overflow_tab)
        if (
            normalized_preferred_overflow is None
            or normalized_preferred_overflow.casefold() not in names_lookup
        ):
            normalized_preferred_overflow = None

        data = self._read_all()
        if normalized_order:
            data["tabs_state"] = {
                "order": normalized_order,
                "active_tab": normalized_active,
                "preferred_overflow_tab": normalized_preferred_overflow,
            }
        else:
            data.pop("tabs_state", None)
        self._write_all(data)

    def load_user_tabs(self) -> list[dict[str, object]] | None:
        data = self._read_all()
        if "user_tabs" not in data:
            return None
        return self._normalize_user_tabs(data.get("user_tabs"))

    def save_user_tabs(self, tabs: list[dict[str, object]]) -> None:
        data = self._read_all()
        data["user_tabs"] = self._normalize_user_tabs(tabs)
        self._write_all(data)

    def _read_all(self) -> dict[str, Any]:
        if not self._settings_path.exists():
            return {}

        try:
            content = self._settings_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_all(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self._settings_path.write_text(payload, encoding="utf-8")

    @staticmethod
    def _normalize_tab_order(raw_value: object) -> list[str]:
        if not isinstance(raw_value, list):
            return []

        order: list[str] = []
        seen: set[str] = set()
        for value in raw_value:
            name = SettingsService._normalize_tab_name(value)
            if name is None:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            order.append(name)
        return order

    @staticmethod
    def _normalize_tab_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        prepared = value.strip()
        if not prepared:
            return None
        return prepared

    @classmethod
    def _normalize_user_tabs(cls, raw_tabs: object) -> list[dict[str, object]]:
        if not isinstance(raw_tabs, list):
            return []

        tabs: list[dict[str, object]] = []
        seen: set[str] = set()
        system_names = {
            DEFAULT_CLIP_TAB_NAME.casefold(),
            DEFAULT_IMAGE_TAB_NAME.casefold(),
        }
        for raw_tab in raw_tabs:
            if not isinstance(raw_tab, dict):
                continue
            name = cls._normalize_tab_name(raw_tab.get("name"))
            if name is None:
                continue
            key = name.casefold()
            if key in seen or key in system_names:
                continue
            raw_items = raw_tab.get("items")
            if not isinstance(raw_items, list):
                raw_items = []
            items = [dict(item) for item in raw_items if isinstance(item, dict)]
            seen.add(key)
            tabs.append(
                {
                    "name": name,
                    "capture_locked": bool(raw_tab.get("capture_locked", False)),
                    "items": items,
                }
            )
        return tabs
