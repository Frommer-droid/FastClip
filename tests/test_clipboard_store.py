from __future__ import annotations

import unittest

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME
from app.core.clipboard_store import ClipboardStore
from app.models.clip_item import CLIP_KIND_IMAGE


class ClipboardStoreMigrationTests(unittest.TestCase):
    def test_legacy_image_tab_name_migrates_to_photo(self) -> None:
        store = ClipboardStore(max_items=10)
        legacy_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {
                "name": "Изображения",
                "capture_locked": False,
                "items": [
                    {
                        "kind": CLIP_KIND_IMAGE,
                        "image_path": "clipboard_images/test.png",
                        "image_width": 100,
                        "image_height": 80,
                    }
                ],
            },
        ]

        store.load(tabs=legacy_tabs, active_tab="Изображения")

        self.assertEqual(DEFAULT_IMAGE_TAB_NAME, store.active_tab_name())
        tab_names = [state["name"] for state in store.tab_states()]
        self.assertEqual([DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME], tab_names)
        self.assertEqual(1, len(store.all_items()))

    def test_image_name_is_saved_and_loaded_for_display(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_image(
            image_path="clipboard_images/hash.png",
            width=100,
            height=80,
            image_name="Summer photo.png",
        )

        self.assertEqual("Summer photo.png", store.all_items()[0].preview_title())
        tabs, active_tab = store.snapshot()
        image_tab = next(tab for tab in tabs if tab["name"] == DEFAULT_IMAGE_TAB_NAME)
        self.assertEqual("Summer photo.png", image_tab["items"][0]["image_name"])

        loaded = ClipboardStore(max_items=10)
        loaded.load(tabs=tabs, active_tab=active_tab)

        self.assertEqual("Summer photo.png", loaded.all_items()[0].preview_title())

    def test_system_tabs_order_is_buffer_then_photo(self) -> None:
        store = ClipboardStore(max_items=10)
        tabs = [
            {"name": "Пользовательская", "capture_locked": False, "items": []},
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
        ]

        store.load(tabs=tabs, active_tab="Пользовательская")

        tab_names = [state["name"] for state in store.tab_states()]
        self.assertEqual(
            [DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "Пользовательская"],
            tab_names,
        )


class ClipboardStorePromotionTests(unittest.TestCase):
    @staticmethod
    def _key_for_text(store: ClipboardStore, text: str) -> str:
        for item in store.all_items():
            if item.text == text:
                return item.key
        raise AssertionError(f"Не найден элемент с текстом: {text}")

    def test_promote_selected_item_to_top_in_regular_zone(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_text("Один")
        store.add_text("Два")
        store.add_text("Три")
        two_key = self._key_for_text(store, "Два")
        three_key = self._key_for_text(store, "Три")
        one_key = self._key_for_text(store, "Один")

        moved = store.promote_in_active_tab(two_key)

        self.assertTrue(moved)
        self.assertEqual(
            [two_key, three_key, one_key],
            [item.key for item in store.all_items()],
        )

    def test_promote_keeps_pinned_prefix_for_regular_item(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_text("Один")
        store.add_text("Два")
        store.add_text("Три")
        one_key = self._key_for_text(store, "Один")
        two_key = self._key_for_text(store, "Два")
        three_key = self._key_for_text(store, "Три")
        store.toggle_pinned(one_key)

        moved = store.promote_in_active_tab(two_key)

        self.assertTrue(moved)
        self.assertEqual(
            [one_key, two_key, three_key],
            [item.key for item in store.all_items()],
        )

    def test_promote_returns_false_for_unknown_key(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_text("Один")
        snapshot_before = [item.key for item in store.all_items()]

        moved = store.promote_in_active_tab("txt:нет")

        self.assertFalse(moved)
        self.assertEqual(snapshot_before, [item.key for item in store.all_items()])


class ClipboardStoreNoteTests(unittest.TestCase):
    def test_user_tab_note_is_saved_and_loaded(self) -> None:
        store = ClipboardStore(max_items=10)
        self.assertTrue(store.add_tab("Учётные данные"))
        self.assertTrue(store.add_text("alice@example.com"))
        item_key = store.all_items()[0].key

        self.assertTrue(store.set_note_in_active_tab(item_key, "  Логин\nосновной  "))
        tabs, active_tab = store.snapshot()
        saved_item = next(tab for tab in tabs if tab["name"] == "Учётные данные")["items"][0]
        self.assertEqual("Логин основной", saved_item["note"])

        loaded = ClipboardStore(max_items=10)
        loaded.load(tabs=tabs, active_tab=active_tab)
        self.assertEqual("Логин основной", loaded.all_items()[0].note)

    def test_system_tab_note_can_be_changed(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_text("Текст")

        self.assertTrue(store.set_note_in_active_tab(store.all_items()[0].key, "Заметка"))
        self.assertEqual("Заметка", store.all_items()[0].note)

    def test_duplicate_clip_keeps_note_in_user_tab(self) -> None:
        store = ClipboardStore(max_items=10)
        store.add_tab("Учётные данные")
        store.add_text("secret")
        item_key = store.all_items()[0].key
        store.set_note_in_active_tab(item_key, "Пароль")

        store.add_text("secret")

        self.assertEqual("Пароль", store.all_items()[0].note)


if __name__ == "__main__":
    unittest.main()
