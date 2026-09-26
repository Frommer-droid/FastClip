from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.settings_service import SettingsService


class SettingsServiceTabsStateTests(unittest.TestCase):
    def test_save_and_load_tabs_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            service = SettingsService(settings_path=settings_path)

            service.save_tabs_state(
                tab_order=["Буфер", "Фото", "Лермонтов"],
                active_tab="Лермонтов",
                preferred_overflow_tab="Лермонтов",
            )

            tab_order, active_tab, preferred_overflow_tab = service.load_tabs_state()
            self.assertEqual(["Буфер", "Фото", "Лермонтов"], tab_order)
            self.assertEqual("Лермонтов", active_tab)
            self.assertEqual("Лермонтов", preferred_overflow_tab)

    def test_save_tabs_state_keeps_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(
                json.dumps({"popup_window": {"x": 100, "y": 200}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            service = SettingsService(settings_path=settings_path)

            service.save_tabs_state(
                tab_order=["Буфер", "Фото", "ФКР"],
                active_tab="ФКР",
            )

            parsed = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertIn("popup_window", parsed)
            self.assertEqual({"x": 100, "y": 200}, parsed["popup_window"])
            self.assertIn("tabs_state", parsed)

    def test_load_tabs_state_ignores_unknown_preferred_tab(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "tabs_state": {
                            "order": ["Буфер", "Фото", "Лермонтов"],
                            "active_tab": "Буфер",
                            "preferred_overflow_tab": "ФКР",
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            service = SettingsService(settings_path=settings_path)

            _, _, preferred_overflow_tab = service.load_tabs_state()

            self.assertIsNone(preferred_overflow_tab)

    def test_user_tabs_are_saved_separately_from_tabs_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            service = SettingsService(settings_path=settings_path)

            service.save_user_tabs(
                [
                    {"name": "Буфер", "items": [{"text": "temporary"}]},
                    {
                        "name": "Логины",
                        "capture_locked": True,
                        "items": [{"kind": "text", "text": "alice", "note": "Логин"}],
                    },
                ]
            )

            self.assertEqual(
                [
                    {
                        "name": "Логины",
                        "capture_locked": True,
                        "items": [{"kind": "text", "text": "alice", "note": "Логин"}],
                    }
                ],
                service.load_user_tabs(),
            )


if __name__ == "__main__":
    unittest.main()
