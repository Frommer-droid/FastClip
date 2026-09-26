from __future__ import annotations

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME
from app.models.clip_item import CLIP_KIND_IMAGE, CLIP_KIND_TEXT, ClipItem

LEGACY_DEFAULT_CLIP_TAB_NAME = "Все"
LEGACY_DEFAULT_IMAGE_TAB_NAME = "Изображения"


class ClipboardStore:
    def __init__(
        self,
        max_items: int,
        default_tab_name: str = DEFAULT_CLIP_TAB_NAME,
        image_tab_name: str = DEFAULT_IMAGE_TAB_NAME,
    ) -> None:
        self._max_items = max_items
        self._default_tab_name = default_tab_name
        self._image_tab_name = image_tab_name
        self._tabs: dict[str, list[ClipItem]] = {}
        self._tab_order: list[str] = []
        self._tab_capture_locked: dict[str, bool] = {}
        self._active_tab = self._default_tab_name
        self._ensure_tab(self._default_tab_name)
        self._ensure_tab(self._image_tab_name)
        self._enforce_system_tab_order()

    def add_text(self, text: str) -> bool:
        prepared = text.strip()
        if not prepared:
            return False

        item = ClipItem(
            key=self._text_item_key(prepared),
            kind=CLIP_KIND_TEXT,
            text=prepared,
        )
        return self._add_text_to_targets(item)

    def add_image(
        self,
        image_path: str,
        width: int,
        height: int,
        image_name: str = "",
    ) -> bool:
        prepared_path = image_path.strip()
        if not prepared_path:
            return False

        item = ClipItem(
            key=self._image_item_key(prepared_path),
            kind=CLIP_KIND_IMAGE,
            text="",
            image_path=prepared_path,
            image_name=self._prepare_image_name(image_name),
            image_width=max(0, int(width)),
            image_height=max(0, int(height)),
        )
        return self._add_image_to_targets(item)

    def load(
        self,
        tabs: list[dict[str, object]],
        active_tab: str,
    ) -> None:
        self._tabs.clear()
        self._tab_order.clear()
        self._tab_capture_locked.clear()

        for raw_tab in tabs:
            if not isinstance(raw_tab, dict):
                continue

            tab_name = self._prepare_tab_name(raw_tab.get("name"))
            if tab_name is None:
                continue
            tab_name = self._normalize_loaded_tab_name(tab_name)
            if self._tab_exists(tab_name):
                continue

            self._ensure_tab(tab_name)
            self._set_tab_items(tab_name, raw_tab.get("items"))
            self._tab_capture_locked[tab_name] = bool(raw_tab.get("capture_locked", False))

        self._ensure_tab(self._default_tab_name)
        self._ensure_tab(self._image_tab_name)
        self._tab_capture_locked[self._default_tab_name] = False
        self._tab_capture_locked[self._image_tab_name] = False
        self._enforce_system_tab_order()

        resolved_active = self._resolve_tab_name(active_tab)
        if (
            resolved_active is None
            and isinstance(active_tab, str)
            and active_tab.strip().casefold() == LEGACY_DEFAULT_CLIP_TAB_NAME.casefold()
        ):
            resolved_active = self._resolve_tab_name(self._default_tab_name)
        if (
            resolved_active is None
            and isinstance(active_tab, str)
            and active_tab.strip().casefold() == LEGACY_DEFAULT_IMAGE_TAB_NAME.casefold()
        ):
            resolved_active = self._resolve_tab_name(self._image_tab_name)
        self._active_tab = resolved_active or self._tab_order[0]

    def clear(self) -> None:
        active_items = self._items_for(self._active_tab)
        self._tabs[self._active_tab] = [item for item in active_items if item.pinned]

    def remove_many(self, item_keys: list[str]) -> int:
        targets = {value.strip() for value in item_keys if isinstance(value, str) and value.strip()}
        if not targets:
            return 0

        items = self._items_for(self._active_tab)
        before = len(items)
        filtered = [item for item in items if item.pinned or item.key not in targets]
        self._tabs[self._active_tab] = filtered
        return before - len(filtered)

    def all_items(self) -> list[ClipItem]:
        return [self._clone_item(item) for item in self._items_for(self._active_tab)]

    def find_in_active_tab(self, key: str) -> ClipItem | None:
        prepared = key.strip()
        if not prepared:
            return None
        for item in self._items_for(self._active_tab):
            if item.key == prepared:
                return self._clone_item(item)
        return None

    def promote_in_active_tab(self, item_key: str) -> bool:
        prepared = item_key.strip()
        if not prepared:
            return False

        items = self._items_for(self._active_tab)
        for index, item in enumerate(items):
            if item.key != prepared:
                continue

            promoted = items.pop(index)
            if promoted.pinned:
                items.insert(0, promoted)
            else:
                insert_index = self._pinned_prefix_size(items)
                items.insert(insert_index, promoted)
            return True
        return False

    def toggle_pinned(self, item_key: str) -> bool:
        prepared = item_key.strip()
        if not prepared:
            return False

        items = self._items_for(self._active_tab)
        for item in items:
            if item.key == prepared:
                item.pinned = not item.pinned
                self._tabs[self._active_tab] = self._order_pinned_first(items)
                return True
        return False

    def set_note_in_active_tab(self, item_key: str, note: str) -> bool:
        prepared_key = item_key.strip()
        if not prepared_key:
            return False
        prepared_note = self._prepare_note(note)
        for item in self._items_for(self._active_tab):
            if item.key == prepared_key:
                if item.note == prepared_note:
                    return False
                item.note = prepared_note
                return True
        return False

    def add_tab(self, name: str) -> bool:
        prepared = self._prepare_tab_name(name)
        if prepared is None:
            return False
        if self._tab_exists(prepared):
            return False
        self._ensure_tab(prepared)
        self._tab_capture_locked[prepared] = False
        self._active_tab = prepared
        return True

    def remove_tab(self, name: str) -> bool:
        resolved = self._resolve_tab_name(name)
        if resolved is None:
            return False
        if len(self._tab_order) <= 1:
            return False
        if self._is_system_tab(resolved):
            return False

        self._tab_order.remove(resolved)
        self._tabs.pop(resolved, None)
        self._tab_capture_locked.pop(resolved, None)

        if self._active_tab == resolved:
            self._active_tab = self._default_tab_name
            if not self._tab_exists(self._active_tab):
                self._active_tab = self._tab_order[0]
        return True

    def rename_tab(self, source_name: str, target_name: str) -> bool:
        resolved_source = self._resolve_tab_name(source_name)
        prepared_target = self._prepare_tab_name(target_name)
        if resolved_source is None or prepared_target is None:
            return False
        if self._is_system_tab(resolved_source):
            return False

        resolved_target = self._resolve_tab_name(prepared_target)
        if resolved_target is not None and resolved_target != resolved_source:
            return False

        if prepared_target == resolved_source:
            return True

        items = self._tabs.pop(resolved_source, [])
        locked = self._tab_capture_locked.pop(resolved_source, False)
        self._tabs[prepared_target] = items
        self._tab_capture_locked[prepared_target] = locked

        for index, tab_name in enumerate(self._tab_order):
            if tab_name == resolved_source:
                self._tab_order[index] = prepared_target
                break

        if self._active_tab == resolved_source:
            self._active_tab = prepared_target
        return True

    def toggle_tab_capture_lock(self, name: str) -> bool:
        resolved = self._resolve_tab_name(name)
        if resolved is None:
            return False
        if self._is_system_tab(resolved):
            return False
        self._tab_capture_locked[resolved] = not self._tab_capture_locked.get(resolved, False)
        return True

    def is_tab_capture_locked(self, name: str) -> bool:
        resolved = self._resolve_tab_name(name)
        if resolved is None:
            return False
        return self._tab_capture_locked.get(resolved, False)

    def set_active_tab(self, name: str) -> bool:
        resolved = self._resolve_tab_name(name)
        if resolved is None:
            return False
        self._active_tab = resolved
        return True

    def active_tab_name(self) -> str:
        return self._active_tab

    def tab_states(self) -> list[dict[str, object]]:
        states: list[dict[str, object]] = []
        for name in self._tab_order:
            states.append(
                {
                    "name": name,
                    "capture_locked": self._tab_capture_locked.get(name, False),
                    "is_buffer": self._is_buffer_tab(name),
                    "is_images": self._is_image_tab(name),
                    "is_system": self._is_system_tab(name),
                }
            )
        return states

    def snapshot(self) -> tuple[list[dict[str, object]], str]:
        tabs: list[dict[str, object]] = []
        for name in self._tab_order:
            items = [self._item_to_payload(item) for item in self._items_for(name)]
            tabs.append(
                {
                    "name": name,
                    "capture_locked": self._tab_capture_locked.get(name, False),
                    "items": items,
                }
            )
        return tabs, self._active_tab

    def referenced_image_paths(self) -> set[str]:
        paths: set[str] = set()
        for tab_name in self._tab_order:
            for item in self._items_for(tab_name):
                if item.kind == CLIP_KIND_IMAGE and item.image_path:
                    paths.add(item.image_path)
        return paths

    def _set_tab_items(self, tab_name: str, raw_items: object) -> None:
        if not isinstance(raw_items, list):
            self._tabs[tab_name] = []
            return

        items: list[ClipItem] = []
        seen_text: set[str] = set()
        seen_image: set[str] = set()
        for raw_item in raw_items:
            normalized = self._normalize_loaded_item(raw_item)
            if normalized is None:
                continue
            if self._is_image_tab(tab_name) and normalized.kind != CLIP_KIND_IMAGE:
                continue

            if normalized.kind == CLIP_KIND_TEXT:
                text_key = self._dedup_text_key(normalized.text)
                if text_key in seen_text:
                    continue
                seen_text.add(text_key)
                normalized.key = self._text_item_key(normalized.text)
            else:
                image_key = self._dedup_image_key(normalized.image_path)
                if image_key in seen_image:
                    continue
                seen_image.add(image_key)
                normalized.key = self._image_item_key(normalized.image_path)

            items.append(normalized)
            if len(items) >= self._max_items:
                break
        self._tabs[tab_name] = self._order_pinned_first(items)

    def _normalize_loaded_item(self, raw_item: object) -> ClipItem | None:
        if isinstance(raw_item, str):
            prepared_text = raw_item.strip()
            if not prepared_text:
                return None
            return ClipItem(
                key=self._text_item_key(prepared_text),
                kind=CLIP_KIND_TEXT,
                text=prepared_text,
                pinned=False,
            )

        if not isinstance(raw_item, dict):
            return None

        kind = str(raw_item.get("kind", CLIP_KIND_TEXT)).strip().casefold()
        pinned = bool(raw_item.get("pinned", False))
        if kind == CLIP_KIND_IMAGE:
            image_path = raw_item.get("image_path")
            if not isinstance(image_path, str):
                return None
            prepared_path = image_path.strip()
            if not prepared_path:
                return None
            width = self._as_non_negative_int(raw_item.get("image_width"))
            height = self._as_non_negative_int(raw_item.get("image_height"))
            return ClipItem(
                key=self._image_item_key(prepared_path),
                kind=CLIP_KIND_IMAGE,
                text="",
                image_path=prepared_path,
                image_name=self._prepare_image_name(raw_item.get("image_name")),
                image_width=width,
                image_height=height,
                pinned=pinned,
                note=self._prepare_note(raw_item.get("note")),
            )

        text_value = raw_item.get("text")
        if not isinstance(text_value, str):
            return None
        prepared_text = text_value.strip()
        if not prepared_text:
            return None
        return ClipItem(
            key=self._text_item_key(prepared_text),
            kind=CLIP_KIND_TEXT,
            text=prepared_text,
            pinned=pinned,
            note=self._prepare_note(raw_item.get("note")),
        )

    def _item_to_payload(self, item: ClipItem) -> dict[str, object]:
        if item.kind == CLIP_KIND_IMAGE:
            return {
                "kind": CLIP_KIND_IMAGE,
                "key": item.key,
                "pinned": item.pinned,
                "image_path": item.image_path,
                "image_name": item.image_name,
                "image_width": item.image_width,
                "image_height": item.image_height,
                "note": item.note,
            }
        return {
            "kind": CLIP_KIND_TEXT,
            "key": item.key,
            "text": item.text,
            "pinned": item.pinned,
            "note": item.note,
        }

    def _add_text_to_targets(self, source_item: ClipItem) -> bool:
        added_to_buffer = self._add_to_tab(
            self._default_tab_name,
            self._clone_item(source_item),
        )
        added_to_active = False
        if (
            not self._is_system_tab(self._active_tab)
            and not self._tab_capture_locked.get(self._active_tab, False)
        ):
            added_to_active = self._add_to_tab(self._active_tab, self._clone_item(source_item))
        return added_to_buffer or added_to_active

    def _add_image_to_targets(self, source_item: ClipItem) -> bool:
        added_to_buffer = self._add_to_tab(
            self._default_tab_name,
            self._clone_item(source_item),
        )
        added_to_images = self._add_to_tab(
            self._image_tab_name,
            self._clone_item(source_item),
        )
        added_to_active = False
        if (
            not self._is_system_tab(self._active_tab)
            and not self._tab_capture_locked.get(self._active_tab, False)
        ):
            added_to_active = self._add_to_tab(self._active_tab, self._clone_item(source_item))
        return added_to_buffer or added_to_images or added_to_active

    def _add_to_tab(self, tab_name: str, incoming: ClipItem) -> bool:
        items = self._items_for(tab_name)
        existing_pinned = False
        existing_note = ""

        if incoming.kind == CLIP_KIND_TEXT:
            incoming_key = self._dedup_text_key(incoming.text)
            for index, item in enumerate(items):
                if item.kind != CLIP_KIND_TEXT:
                    continue
                if self._dedup_text_key(item.text) == incoming_key:
                    existing_pinned = item.pinned
                    existing_note = item.note
                    items.pop(index)
                    break
        elif incoming.kind == CLIP_KIND_IMAGE:
            incoming_key = self._dedup_image_key(incoming.image_path)
            for index, item in enumerate(items):
                if item.kind != CLIP_KIND_IMAGE:
                    continue
                if self._dedup_image_key(item.image_path) == incoming_key:
                    existing_pinned = item.pinned
                    existing_note = item.note
                    items.pop(index)
                    break

        incoming.pinned = existing_pinned or incoming.pinned
        incoming.note = existing_note or incoming.note
        items = self._order_pinned_first(items)
        if incoming.pinned:
            items.insert(0, incoming)
        else:
            insert_index = self._pinned_prefix_size(items)
            items.insert(insert_index, incoming)

        self._tabs[tab_name] = items[: self._max_items]
        return True

    def _prepare_tab_name(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        prepared = value.strip()
        if not prepared:
            return None
        return prepared

    def _tab_exists(self, name: str) -> bool:
        return self._resolve_tab_name(name) is not None

    def _resolve_tab_name(self, name: str) -> str | None:
        target = name.casefold()
        for tab_name in self._tab_order:
            if tab_name.casefold() == target:
                return tab_name
        return None

    def _ensure_tab(self, name: str) -> None:
        if name not in self._tabs:
            self._tabs[name] = []
        if name not in self._tab_order:
            self._tab_order.append(name)
        if name not in self._tab_capture_locked:
            self._tab_capture_locked[name] = False
        if self._is_system_tab(name):
            self._tab_capture_locked[name] = False

    def _enforce_system_tab_order(self) -> None:
        buffer_tab = self._resolve_tab_name(self._default_tab_name)
        image_tab = self._resolve_tab_name(self._image_tab_name)
        user_tabs = [name for name in self._tab_order if not self._is_system_tab(name)]

        ordered: list[str] = []
        if buffer_tab is not None:
            ordered.append(buffer_tab)
        if image_tab is not None and image_tab not in ordered:
            ordered.append(image_tab)
        ordered.extend(user_tabs)
        self._tab_order = ordered

    def _items_for(self, tab_name: str) -> list[ClipItem]:
        self._ensure_tab(tab_name)
        return self._tabs[tab_name]

    def _is_buffer_tab(self, name: str) -> bool:
        return name.casefold() == self._default_tab_name.casefold()

    def _is_image_tab(self, name: str) -> bool:
        return name.casefold() == self._image_tab_name.casefold()

    def _is_system_tab(self, name: str) -> bool:
        return self._is_buffer_tab(name) or self._is_image_tab(name)

    def _normalize_loaded_tab_name(self, tab_name: str) -> str:
        casefold_name = tab_name.casefold()
        if casefold_name == LEGACY_DEFAULT_CLIP_TAB_NAME.casefold():
            return self._default_tab_name
        if casefold_name == self._default_tab_name.casefold():
            return self._default_tab_name
        if casefold_name == LEGACY_DEFAULT_IMAGE_TAB_NAME.casefold():
            return self._image_tab_name
        if casefold_name == self._image_tab_name.casefold():
            return self._image_tab_name
        return tab_name

    @staticmethod
    def _order_pinned_first(items: list[ClipItem]) -> list[ClipItem]:
        pinned_items = [item for item in items if item.pinned]
        regular_items = [item for item in items if not item.pinned]
        return pinned_items + regular_items

    @staticmethod
    def _pinned_prefix_size(items: list[ClipItem]) -> int:
        index = 0
        while index < len(items) and items[index].pinned:
            index += 1
        return index

    @staticmethod
    def _clone_item(item: ClipItem) -> ClipItem:
        return ClipItem(
            key=item.key,
            kind=item.kind,
            text=item.text,
            image_path=item.image_path,
            image_name=item.image_name,
            image_width=item.image_width,
            image_height=item.image_height,
            pinned=item.pinned,
            note=item.note,
        )

    @staticmethod
    def _as_non_negative_int(value: object) -> int:
        if not isinstance(value, int):
            return 0
        return max(0, value)

    @staticmethod
    def _prepare_image_name(value: object) -> str:
        if not isinstance(value, str):
            return ""
        prepared = " ".join(value.replace("\r", " ").replace("\n", " ").split())
        return prepared[:260]

    @staticmethod
    def _prepare_note(value: object) -> str:
        if not isinstance(value, str):
            return ""
        prepared = " ".join(value.replace("\r", " ").replace("\n", " ").split())
        return prepared[:120]

    @staticmethod
    def _dedup_text_key(text: str) -> str:
        normalized_linebreaks = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized_linebreaks.split("\n")]
        return "\n".join(lines).strip()

    @staticmethod
    def _dedup_image_key(image_path: str) -> str:
        return image_path.strip().casefold()

    @classmethod
    def _text_item_key(cls, text: str) -> str:
        return f"txt:{cls._dedup_text_key(text)}"

    @classmethod
    def _image_item_key(cls, image_path: str) -> str:
        return f"img:{cls._dedup_image_key(image_path)}"
