from __future__ import annotations

import unittest

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME
from app.core.tab_state_resolver import merge_tabs_state


class TabStateResolverTests(unittest.TestCase):
    @staticmethod
    def _tab_names(tabs: list[dict[str, object]]) -> list[str]:
        return [str(tab.get("name", "")) for tab in tabs]

    @staticmethod
    def _find_tab(tabs: list[dict[str, object]], name: str) -> dict[str, object]:
        for tab in tabs:
            if str(tab.get("name", "")).casefold() == name.casefold():
                return tab
        raise AssertionError(f"Вкладка не найдена: {name}")

    def test_system_tabs_are_always_buffer_then_photo(self) -> None:
        history_tabs = [
            {"name": "Лермонтов", "capture_locked": True, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "ФКР", "capture_locked": True, "items": []},
        ]

        tabs, _ = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="ФКР",
            settings_tab_order=[DEFAULT_IMAGE_TAB_NAME, DEFAULT_CLIP_TAB_NAME, "ФКР", "Лермонтов"],
            settings_active_tab="ФКР",
        )

        self.assertEqual(
            [DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "ФКР", "Лермонтов"],
            self._tab_names(tabs),
        )

    def test_tab_from_settings_is_created_when_missing_in_history(self) -> None:
        history_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "ФКР", "capture_locked": True, "items": [{"kind": "text", "text": "x"}]},
        ]

        tabs, active = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="ФКР",
            settings_tab_order=[DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "Лермонтов", "ФКР"],
            settings_active_tab="Лермонтов",
        )

        self.assertEqual(
            [DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "Лермонтов", "ФКР"],
            self._tab_names(tabs),
        )
        created_tab = self._find_tab(tabs, "Лермонтов")
        self.assertEqual([], created_tab.get("items"))
        self.assertFalse(bool(created_tab.get("capture_locked", False)))
        self.assertEqual("Лермонтов", active)

    def test_tabs_absent_in_settings_are_appended_from_history(self) -> None:
        history_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "ФКР", "capture_locked": True, "items": []},
            {"name": "Шиллер", "capture_locked": False, "items": []},
        ]

        tabs, _ = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="ФКР",
            settings_tab_order=[DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "ФКР"],
            settings_active_tab="ФКР",
        )

        self.assertEqual(
            [DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "ФКР", "Шиллер"],
            self._tab_names(tabs),
        )

    def test_active_tab_prefers_settings_when_present(self) -> None:
        history_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "ФКР", "capture_locked": True, "items": []},
            {"name": "Лермонтов", "capture_locked": True, "items": []},
        ]

        _, active = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="ФКР",
            settings_tab_order=[DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "ФКР", "Лермонтов"],
            settings_active_tab="Лермонтов",
        )

        self.assertEqual("Лермонтов", active)

    def test_active_tab_falls_back_to_history_when_settings_active_invalid(self) -> None:
        history_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "ФКР", "capture_locked": True, "items": []},
        ]

        _, active = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="ФКР",
            settings_tab_order=[DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "ФКР"],
            settings_active_tab="Несуществующая",
        )

        self.assertEqual("ФКР", active)

    def test_durable_user_tabs_take_priority_over_legacy_history_tabs(self) -> None:
        history_tabs = [
            {"name": DEFAULT_CLIP_TAB_NAME, "capture_locked": False, "items": []},
            {"name": DEFAULT_IMAGE_TAB_NAME, "capture_locked": False, "items": []},
            {"name": "Старое", "capture_locked": False, "items": [{"text": "legacy"}]},
        ]
        settings_user_tabs = [
            {"name": "Логины", "capture_locked": True, "items": [{"text": "alice", "note": "Логин"}]}
        ]

        tabs, active = merge_tabs_state(
            history_tabs=history_tabs,
            history_active_tab="Старое",
            settings_tab_order=[DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "Логины"],
            settings_active_tab="Логины",
            settings_user_tabs=settings_user_tabs,
        )

        self.assertEqual(
            [DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME, "Логины"],
            self._tab_names(tabs),
        )
        self.assertEqual("Логины", active)
        self.assertEqual("alice", self._find_tab(tabs, "Логины")["items"][0]["text"])


if __name__ == "__main__":
    unittest.main()
