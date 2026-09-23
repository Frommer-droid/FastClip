from __future__ import annotations

import unittest

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME
from app.ui.popup_window import TwoLineTabBar
from app.ui.popup_window import ClipItemDelegate
from app.ui.popup_window import PopupWindow


class TabVisibilityTests(unittest.TestCase):
    def test_system_tabs_always_visible_when_width_is_limited(self) -> None:
        visible, overflow = TwoLineTabBar._split_visible_overflow(
            tab_widths=[110, 130, 120, 120, 120],
            available_width=300,
            overflow_button_width=32,
            min_partial_width=56,
            spacing=4,
            always_visible_indices=[0, 1],
        )

        self.assertEqual([0, 1], visible[:2])
        self.assertIn(0, visible)
        self.assertIn(1, visible)
        self.assertEqual([2, 3, 4], overflow)

    def test_system_tabs_stay_visible_with_preferred_overflow_tab(self) -> None:
        visible, overflow = TwoLineTabBar._split_visible_overflow(
            tab_widths=[110, 130, 120, 120, 140],
            available_width=420,
            overflow_button_width=32,
            preferred_index=4,
            min_partial_width=56,
            spacing=4,
            always_visible_indices=[0, 1],
        )

        self.assertEqual([0, 1], visible[:2])
        self.assertIn(4, visible)
        self.assertEqual([2, 3], overflow)

    def test_system_tabs_not_hidden_when_available_width_is_zero(self) -> None:
        visible, overflow = TwoLineTabBar._split_visible_overflow(
            tab_widths=[100, 100, 100],
            available_width=0,
            overflow_button_width=32,
            min_partial_width=56,
            spacing=4,
            always_visible_indices=[0, 1],
        )

        self.assertEqual([0, 1], visible)
        self.assertEqual([2], overflow)

    def test_required_tab_cannot_be_partially_visible(self) -> None:
        fits = TwoLineTabBar._selection_fits_width(
            tab_widths=[120, 120],
            selected_indices=[0, 1],
            visible_limit=200,
            min_partial_width=56,
            spacing=4,
            required_indices={0, 1},
        )

        self.assertFalse(fits)

    def test_partial_width_allowed_for_non_required_tab(self) -> None:
        fits = TwoLineTabBar._selection_fits_width(
            tab_widths=[100, 100, 150],
            selected_indices=[0, 1, 2],
            visible_limit=270,
            min_partial_width=56,
            spacing=4,
            required_indices={0, 1},
        )

        self.assertTrue(fits)


class ClipItemTextAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_short_text_is_centered_vertically(self) -> None:
        flags = ClipItemDelegate._text_paint_flags(
            QFontMetrics(self._app.font()),
            QRect(0, 0, 300, 80),
            "Короткий текст",
        )

        self.assertEqual(
            int(Qt.AlignmentFlag.AlignVCenter),
            flags & int(Qt.AlignmentFlag.AlignVertical_Mask),
        )

    def test_overflowing_text_starts_at_top(self) -> None:
        flags = ClipItemDelegate._text_paint_flags(
            QFontMetrics(self._app.font()),
            QRect(0, 0, 160, 1),
            "Это длинный текст, который не может поместиться по высоте.",
        )

        self.assertEqual(
            int(Qt.AlignmentFlag.AlignTop),
            flags & int(Qt.AlignmentFlag.AlignVertical_Mask),
        )


class RequiredTabUiRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_required_tabs_not_elided_when_user_tab_can_be_hidden(self) -> None:
        popup = PopupWindow()
        popup.resize(390, 420)
        popup.set_tabs(
            tab_states=[
                {
                    "name": DEFAULT_CLIP_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": True,
                    "is_images": False,
                    "is_system": True,
                },
                {
                    "name": DEFAULT_IMAGE_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": True,
                    "is_system": True,
                },
                {
                    "name": "ФКР",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "Лермонтов",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
            ],
            active_tab=DEFAULT_CLIP_TAB_NAME,
        )
        popup.show()
        self._app.processEvents()

        required = popup._tab_bar._required_visible_indices()
        self.assertTrue(
            popup._tab_bar._required_tabs_have_full_width(
                required_indices=required,
                visible_indices=popup._tab_bar._visible_indices,
            )
        )
        self.assertEqual([0, 1], popup._tab_bar._visible_indices[:2])

        popup.close()

    def test_required_tabs_not_elided_with_visible_overflow_and_user_tab(self) -> None:
        popup = PopupWindow()
        popup.resize(540, 420)
        popup.set_tabs(
            tab_states=[
                {
                    "name": DEFAULT_CLIP_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": True,
                    "is_images": False,
                    "is_system": True,
                },
                {
                    "name": DEFAULT_IMAGE_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": True,
                    "is_system": True,
                },
                {
                    "name": "ChatGPT-krazyvo-dlinnoe-nazvanie",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "ФКР",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "Лермонтов",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
            ],
            active_tab=DEFAULT_CLIP_TAB_NAME,
        )
        popup.show()
        self._app.processEvents()

        required = popup._tab_bar._required_visible_indices()
        self.assertTrue(popup._tab_bar._overflow_button.isVisible())
        self.assertTrue(
            popup._tab_bar._required_tabs_have_full_width(
                required_indices=required,
                visible_indices=popup._tab_bar._visible_indices,
            )
        )
        self.assertEqual([0, 1], popup._tab_bar._visible_indices[:2])

        popup.close()

    def test_user_tab_gradually_elides_before_overflow_hiding(self) -> None:
        popup = PopupWindow()
        popup.resize(520, 420)
        popup.set_tabs(
            tab_states=[
                {
                    "name": DEFAULT_CLIP_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": True,
                    "is_images": False,
                    "is_system": True,
                },
                {
                    "name": DEFAULT_IMAGE_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": True,
                    "is_system": True,
                },
                {
                    "name": "ChatGPT-krazyvo-dlinnoe-nazvanie",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "ФКР",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
            ],
            active_tab=DEFAULT_CLIP_TAB_NAME,
        )
        popup.show()
        self._app.processEvents()

        tab_bar = popup._tab_bar
        required = tab_bar._required_visible_indices()
        self.assertTrue(
            tab_bar._required_tabs_have_full_width(
                required_indices=required,
                visible_indices=tab_bar._visible_indices,
            )
        )
        self.assertTrue(tab_bar._overflow_button.isVisible())
        self.assertIn(2, tab_bar._visible_indices)

        local_index = tab_bar._visible_indices.index(2)
        shown_text = tab_bar._bar.tabText(local_index)
        self.assertNotEqual("ChatGPT-krazyvo-dlinnoe-nazvanie", shown_text)
        self.assertTrue(shown_text)

        popup.close()

    def test_active_tab_is_preferred_when_overflow_preference_is_empty(self) -> None:
        popup = PopupWindow()
        popup.resize(572, 420)
        popup.set_tabs(
            tab_states=[
                {
                    "name": DEFAULT_CLIP_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": True,
                    "is_images": False,
                    "is_system": True,
                },
                {
                    "name": DEFAULT_IMAGE_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": True,
                    "is_system": True,
                },
                {
                    "name": "ФКР",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "Лермонтов",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "ChatGPT-Konand",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "PX6-Privat",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
            ],
            active_tab="Лермонтов",
        )
        popup.show()
        self._app.processEvents()

        self.assertEqual("Лермонтов", popup._tab_bar.preferredOverflowTabName())
        self.assertEqual([0, 1, 3], popup._tab_bar._visible_indices)
        self.assertEqual([2, 4, 5], popup._tab_bar._overflow_indices)

        popup.close()

    def test_explicit_preferred_tab_is_used_when_active_is_system_tab(self) -> None:
        popup = PopupWindow()
        popup.resize(572, 420)
        popup.set_tabs(
            tab_states=[
                {
                    "name": DEFAULT_CLIP_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": True,
                    "is_images": False,
                    "is_system": True,
                },
                {
                    "name": DEFAULT_IMAGE_TAB_NAME,
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": True,
                    "is_system": True,
                },
                {
                    "name": "ФКР",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "Лермонтов",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "ChatGPT-Konand",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
                {
                    "name": "PX6-Privat",
                    "capture_locked": False,
                    "is_buffer": False,
                    "is_images": False,
                    "is_system": False,
                },
            ],
            active_tab=DEFAULT_CLIP_TAB_NAME,
            preferred_overflow_tab="Лермонтов",
        )
        popup.show()
        self._app.processEvents()

        self.assertEqual("Лермонтов", popup.preferred_overflow_tab_name())
        self.assertEqual([0, 1, 3], popup._tab_bar._visible_indices)
        self.assertEqual([2, 4, 5], popup._tab_bar._overflow_indices)

        popup.close()


if __name__ == "__main__":
    unittest.main()
