from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config.constants import (
    CLIP_HISTORY_FILE,
    DEFAULT_CLIP_TAB_NAME,
    DEFAULT_IMAGE_TAB_NAME,
)
from app.models.clip_item import CLIP_KIND_IMAGE, CLIP_KIND_TEXT


class ClipHistoryService:
    def __init__(self, max_items: int) -> None:
        self._max_items = max_items
        if getattr(sys, "frozen", False):
            root_dir = Path(sys.executable).resolve().parent
        else:
            root_dir = Path(__file__).resolve().parents[2]
        self._history_path = root_dir / CLIP_HISTORY_FILE

    def load_state(self) -> tuple[list[dict[str, object]], str]:
        if not self._history_path.exists():
            return [self._empty_default_tab()], DEFAULT_CLIP_TAB_NAME

        try:
            content = self._history_path.read_text(encoding="utf-8")
        except OSError:
            return [self._empty_default_tab()], DEFAULT_CLIP_TAB_NAME

        parsed_state = self._try_parse_structured_state(content)
        if parsed_state is not None:
            return parsed_state

        legacy_items = self._parse_legacy_items(content.splitlines())
        return [
            {
                "name": DEFAULT_CLIP_TAB_NAME,
                "capture_locked": False,
                "items": legacy_items,
            }
        ], DEFAULT_CLIP_TAB_NAME

    def save_state(
        self,
        tabs: list[dict[str, object]],
        active_tab: str,
    ) -> None:
        sanitized_tabs: list[dict[str, object]] = []
        seen_tabs: set[str] = set()
        tab_names: list[str] = []
        for raw_tab in tabs:
            if not isinstance(raw_tab, dict):
                continue

            normalized_name = self._normalize_tab_name(raw_tab.get("name"))
            if normalized_name is None:
                continue

            if normalized_name.casefold() not in {
                DEFAULT_CLIP_TAB_NAME.casefold(),
                DEFAULT_IMAGE_TAB_NAME.casefold(),
            }:
                continue

            casefold_name = normalized_name.casefold()
            if casefold_name in seen_tabs:
                continue
            seen_tabs.add(casefold_name)
            tab_names.append(normalized_name)
            sanitized_tabs.append(
                {
                    "name": normalized_name,
                    "capture_locked": bool(raw_tab.get("capture_locked", False)),
                    "items": self._normalize_items(raw_tab.get("items")),
                }
            )

        if not sanitized_tabs:
            tab_names = [DEFAULT_CLIP_TAB_NAME]
            sanitized_tabs = [self._empty_default_tab()]

        normalized_active = self._normalize_tab_name(active_tab)
        if normalized_active is None or normalized_active not in tab_names:
            normalized_active = tab_names[0]

        payload = json.dumps(
            {
                "version": 5,
                "active_tab": normalized_active,
                "tabs": sanitized_tabs,
            },
            ensure_ascii=False,
            indent=2,
        )
        self._history_path.write_text(payload, encoding="utf-8")

    def _try_parse_structured_state(
        self,
        content: str,
    ) -> tuple[list[dict[str, object]], str] | None:
        raw = content.strip()
        if not raw:
            return [self._empty_default_tab()], DEFAULT_CLIP_TAB_NAME

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        tabs_node = parsed.get("tabs")
        if not isinstance(tabs_node, list):
            return None

        tabs: list[dict[str, object]] = []
        seen_tabs: set[str] = set()
        for tab in tabs_node:
            if not isinstance(tab, dict):
                continue
            name = self._normalize_tab_name(tab.get("name"))
            if name is None:
                continue

            casefold_name = name.casefold()
            if casefold_name in seen_tabs:
                continue
            seen_tabs.add(casefold_name)

            normalized_items = self._normalize_items(tab.get("items"))
            tabs.append(
                {
                    "name": name,
                    "capture_locked": bool(tab.get("capture_locked", False)),
                    "items": normalized_items,
                }
            )

        if not tabs:
            return None

        active_tab = self._normalize_tab_name(parsed.get("active_tab"))
        tab_names = {str(tab["name"]) for tab in tabs}
        if active_tab is None or active_tab not in tab_names:
            active_tab = str(tabs[0]["name"])

        return tabs, active_tab

    def _parse_legacy_items(self, lines: list[str]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        seen: set[str] = set()
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized:
                continue

            dedup_key = self._item_dedup_key(normalized)
            if dedup_key in seen:
                continue

            seen.add(dedup_key)
            items.append(
                {
                    "kind": CLIP_KIND_TEXT,
                    "key": self._text_item_key(normalized),
                    "text": normalized,
                    "pinned": False,
                }
            )
            if len(items) >= self._max_items:
                break
        return items

    def _normalize_items(self, raw_items: object) -> list[dict[str, object]]:
        if not isinstance(raw_items, list):
            return []

        deduplicated: list[dict[str, object]] = []
        seen_text: set[str] = set()
        seen_image: set[str] = set()
        for value in raw_items:
            normalized = self._normalize_item(value)
            if normalized is None:
                continue

            kind = str(normalized.get("kind", CLIP_KIND_TEXT))
            if kind == CLIP_KIND_IMAGE:
                image_path = str(normalized.get("image_path", "")).strip()
                dedup_key = image_path.casefold()
                if dedup_key in seen_image:
                    continue
                seen_image.add(dedup_key)
            else:
                text_value = str(normalized.get("text", "")).strip()
                dedup_key = self._item_dedup_key(text_value)
                if dedup_key in seen_text:
                    continue
                seen_text.add(dedup_key)

            deduplicated.append(normalized)
            if len(deduplicated) >= self._max_items:
                break
        return deduplicated

    def _normalize_item(self, value: object) -> dict[str, object] | None:
        if isinstance(value, str):
            normalized_text = value.strip()
            if not normalized_text:
                return None
            return {
                "kind": CLIP_KIND_TEXT,
                "key": self._text_item_key(normalized_text),
                "text": normalized_text,
                "pinned": False,
            }

        if not isinstance(value, dict):
            return None

        kind = str(value.get("kind", CLIP_KIND_TEXT)).strip().casefold()
        pinned = bool(value.get("pinned", False))

        if kind == CLIP_KIND_IMAGE:
            image_path = value.get("image_path")
            if not isinstance(image_path, str):
                return None
            prepared_path = image_path.strip()
            if not prepared_path:
                return None
            width = self._as_non_negative_int(value.get("image_width"))
            height = self._as_non_negative_int(value.get("image_height"))
            return {
                "kind": CLIP_KIND_IMAGE,
                "key": self._image_item_key(prepared_path),
                "pinned": pinned,
                "image_path": prepared_path,
                "image_name": self._normalize_image_name(value.get("image_name")),
                "image_width": width,
                "image_height": height,
                "note": self._normalize_note(value.get("note")),
            }

        raw_text = value.get("text")
        if not isinstance(raw_text, str):
            return None
        normalized_text = raw_text.strip()
        if not normalized_text:
            return None
        return {
            "kind": CLIP_KIND_TEXT,
            "key": self._text_item_key(normalized_text),
            "text": normalized_text,
            "pinned": pinned,
            "note": self._normalize_note(value.get("note")),
        }

    @staticmethod
    def _as_non_negative_int(value: object) -> int:
        if not isinstance(value, int):
            return 0
        return max(0, value)

    @staticmethod
    def _normalize_image_name(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = " ".join(value.replace("\r", " ").replace("\n", " ").split())
        return normalized[:260]

    @staticmethod
    def _normalize_note(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = " ".join(value.replace("\r", " ").replace("\n", " ").split())
        return normalized[:120]

    @staticmethod
    def _item_dedup_key(text: str) -> str:
        normalized_linebreaks = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized_linebreaks.split("\n")]
        return "\n".join(lines).strip()

    @classmethod
    def _text_item_key(cls, text: str) -> str:
        return f"txt:{cls._item_dedup_key(text)}"

    @staticmethod
    def _image_item_key(image_path: str) -> str:
        return f"img:{image_path.strip().casefold()}"

    @staticmethod
    def _normalize_tab_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def _empty_default_tab() -> dict[str, object]:
        return {
            "name": DEFAULT_CLIP_TAB_NAME,
            "capture_locked": False,
            "items": [],
        }

