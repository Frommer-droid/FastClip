from __future__ import annotations

import unittest

from app.core.app_controller import AppController


class _FakeClipboardStore:
    def __init__(self) -> None:
        self._tabs = [
            {"name": "Буфер", "capture_locked": False, "items": []},
            {"name": "Фото", "capture_locked": False, "items": []},
            {"name": "Лермонтов", "capture_locked": True, "items": []},
        ]
        self._active = "Лермонтов"

    def snapshot(self) -> tuple[list[dict[str, object]], str]:
        return self._tabs, self._active

    def referenced_image_paths(self) -> set[str]:
        return {"clipboard_images/example.png"}


class _FakeHistoryService:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, object]], str]] = []

    def save_state(self, tabs: list[dict[str, object]], active_tab: str) -> None:
        self.calls.append((tabs, active_tab))


class _FakeSettingsService:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str, str | None]] = []
        self.user_tabs_calls: list[list[dict[str, object]]] = []

    def save_tabs_state(
        self,
        tab_order: list[str],
        active_tab: str,
        preferred_overflow_tab: str | None = None,
    ) -> None:
        self.calls.append((tab_order, active_tab, preferred_overflow_tab))

    def save_user_tabs(self, tabs: list[dict[str, object]]) -> None:
        self.user_tabs_calls.append(tabs)


class _FakeClipImageService:
    def __init__(self) -> None:
        self.calls: list[set[str]] = []

    def cleanup_unreferenced(self, referenced_paths: set[str]) -> None:
        self.calls.append(referenced_paths)


class _FakePopup:
    @staticmethod
    def preferred_overflow_tab_name() -> str | None:
        return "Лермонтов"


class AppControllerPersistenceTests(unittest.TestCase):
    def test_persist_clip_history_also_persists_tabs_state(self) -> None:
        controller = AppController.__new__(AppController)
        controller._clipboard_store = _FakeClipboardStore()
        controller._clip_history_service = _FakeHistoryService()
        controller._settings_service = _FakeSettingsService()
        controller._clip_image_service = _FakeClipImageService()
        controller._popup = _FakePopup()
        controller._preferred_overflow_tab = None

        controller._persist_clip_history()

        self.assertEqual(1, len(controller._clip_history_service.calls))
        history_tabs, history_active = controller._clip_history_service.calls[0]
        self.assertEqual("Лермонтов", history_active)
        self.assertEqual(["Буфер", "Фото", "Лермонтов"], [tab["name"] for tab in history_tabs])

        self.assertEqual(
            [(["Буфер", "Фото", "Лермонтов"], "Лермонтов", "Лермонтов")],
            controller._settings_service.calls,
        )
        self.assertEqual(
            [[{"name": "Лермонтов", "capture_locked": True, "items": []}]],
            controller._settings_service.user_tabs_calls,
        )
        self.assertEqual(
            [{"clipboard_images/example.png"}],
            controller._clip_image_service.calls,
        )


if __name__ == "__main__":
    unittest.main()
