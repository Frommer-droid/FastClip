from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.clip_history_service import ClipHistoryService


class ClipHistoryServiceNoteTests(unittest.TestCase):
    def test_note_survives_history_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ClipHistoryService(max_items=10)
            service._history_path = Path(temp_dir) / "clipboard_history.txt"
            tabs = [
                {
                    "name": "Буфер",
                    "capture_locked": False,
                    "items": [
                        {
                            "kind": "text",
                            "key": "txt:alice",
                            "text": "alice",
                            "pinned": False,
                            "note": "  Логин\nосновной  ",
                        }
                    ],
                }
            ]

            service.save_state(tabs=tabs, active_tab="Буфер")
            loaded_tabs, active_tab = service.load_state()

        self.assertEqual("Буфер", active_tab)
        self.assertEqual("Логин основной", loaded_tabs[0]["items"][0]["note"])

    def test_history_saves_only_system_tabs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ClipHistoryService(max_items=10)
            service._history_path = Path(temp_dir) / "clipboard_history.txt"
            service.save_state(
                tabs=[
                    {"name": "Буфер", "capture_locked": False, "items": []},
                    {"name": "Фото", "capture_locked": False, "items": []},
                    {"name": "Логины", "capture_locked": True, "items": [{"text": "alice"}]},
                ],
                active_tab="Логины",
            )
            loaded_tabs, _ = service.load_state()

        self.assertEqual(["Буфер", "Фото"], [tab["name"] for tab in loaded_tabs])


if __name__ == "__main__":
    unittest.main()
