from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QMouseEvent,
    QPalette,
    QPainter,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListView,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import DEFAULT_CLIP_TAB_NAME, DEFAULT_IMAGE_TAB_NAME
from app.version import __version__
from app.models.clip_item import CLIP_KIND_IMAGE, CLIP_KIND_TEXT, ClipItem

try:
    from shiboken6 import isValid as _shiboken_is_valid
except Exception:  # pragma: no cover - fallback only when shiboken6 is unavailable.
    def _shiboken_is_valid(_obj: object) -> bool:
        return True

ROLE_ITEM_KEY = int(Qt.ItemDataRole.UserRole)
ROLE_PINNED = int(Qt.ItemDataRole.UserRole + 1)
ROLE_KIND = int(Qt.ItemDataRole.UserRole + 2)
ROLE_SEARCH_TEXT = int(Qt.ItemDataRole.UserRole + 3)
ROLE_IMAGE_PATH = int(Qt.ItemDataRole.UserRole + 4)
ROLE_NOTE = int(Qt.ItemDataRole.UserRole + 5)
ROLE_NOTE_EDITABLE = int(Qt.ItemDataRole.UserRole + 6)

TAB_SIDE_BUTTON_SIZE = 18
TAB_SIDE_BUTTON_EDGE_PADDING = 4
TAB_SIDE_BUTTON_TEXT_GAP = 2
TAB_SIDE_BUTTON_SLOT_WIDTH = (
    TAB_SIDE_BUTTON_SIZE + TAB_SIDE_BUTTON_EDGE_PADDING + TAB_SIDE_BUTTON_TEXT_GAP
)


def _is_live_widget(value: object | None) -> bool:
    return isinstance(value, QWidget) and _shiboken_is_valid(value)


class ClipListWidget(QListWidget):
    item_choose_requested = Signal(str)
    tab_step_requested = Signal(int)
    enter_pressed = Signal(str)
    delete_pressed = Signal(list)
    index_input_changed = Signal(str)
    pin_toggle_requested = Signal(str)
    alt_item_choose_requested = Signal(str)
    find_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pending_index_input = ""
        self._emit_index_input_changed()

    def keyPressEvent(self, event) -> None:
        if (
            event.modifiers() == Qt.KeyboardModifier.NoModifier
            and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        ):
            self.tab_step_requested.emit(-1 if event.key() == Qt.Key.Key_Left else 1)
            event.accept()
            return

        if event.matches(QKeySequence.StandardKey.Find):
            self.find_requested.emit()
            event.accept()
            return

        if self._handle_index_input(event):
            return

        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.selectAll()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Delete:
            selected = self.selectedItems()
            if selected:
                texts = [
                    str(item.data(ROLE_ITEM_KEY))
                    for item in selected
                ]
                self.delete_pressed.emit(texts)
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item is None:
                selected = self.selectedItems()
                item = selected[0] if selected else None
            if item is not None:
                item_key = item.data(ROLE_ITEM_KEY)
                self.enter_pressed.emit(str(item_key))
            return
        super().keyPressEvent(event)
        if self._is_ctrl_edge_navigation(event):
            self._highlight_current_item()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.RightButton
            and index.isValid()
        ):
            text_value = index.data(ROLE_ITEM_KEY)
            if isinstance(text_value, str) and text_value.strip():
                self.delete_pressed.emit([text_value])
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and self._is_number_area_clicked(index, event.position().toPoint())
        ):
            text_value = index.data(ROLE_ITEM_KEY)
            if isinstance(text_value, str) and text_value.strip():
                self.setCurrentIndex(index)
                self._highlight_current_item()
                self.pin_toggle_requested.emit(text_value)
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and self._is_note_area_clicked(index, event.position().toPoint())
        ):
            self.setCurrentIndex(index)
            self._highlight_current_item()
            self.edit(index)
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            and not bool(
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ShiftModifier
                    | Qt.KeyboardModifier.MetaModifier
                )
            )
        ):
            text_value = index.data(ROLE_ITEM_KEY)
            if isinstance(text_value, str) and text_value.strip():
                self.setCurrentIndex(index)
                self._highlight_current_item()
                self.alt_item_choose_requested.emit(text_value)
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            text_value = index.data(ROLE_ITEM_KEY)
            if isinstance(text_value, str) and text_value.strip():
                self.setCurrentIndex(index)
                self._highlight_current_item()
                self.item_choose_requested.emit(text_value)
                event.accept()
                return
        super().mousePressEvent(event)

    def clear_index_input(self) -> None:
        self._pending_index_input = ""
        self._emit_index_input_changed()

    def select_row(self, row: int) -> None:
        if row < 0 or row >= self.count():
            return
        self.setCurrentRow(row)
        self._highlight_current_item()

    def _handle_index_input(self, event) -> bool:
        modifiers = event.modifiers()
        has_forbidden_modifier = bool(
            modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        )
        has_meta_modifier = bool(modifiers & Qt.KeyboardModifier.MetaModifier)
        if has_forbidden_modifier or has_meta_modifier:
            return False

        key = event.key()
        text = event.text()

        if text.isdigit():
            self._pending_index_input += text
            self._emit_index_input_changed()
            event.accept()
            return True

        if key == Qt.Key.Key_Backspace and self._pending_index_input:
            self._pending_index_input = self._pending_index_input[:-1]
            self._emit_index_input_changed()
            event.accept()
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._pending_index_input:
            index = int(self._pending_index_input) - 1
            self._pending_index_input = ""
            self._emit_index_input_changed()

            if 0 <= index < self.count():
                self.setCurrentRow(index)
                item = self.item(index)
                text_value = item.data(ROLE_ITEM_KEY)
                self.enter_pressed.emit(str(text_value))
            event.accept()
            return True

        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Tab):
            self._pending_index_input = ""
            self._emit_index_input_changed()
        return False

    def _emit_index_input_changed(self) -> None:
        self.index_input_changed.emit(self._pending_index_input)

    @staticmethod
    def _is_ctrl_edge_navigation(event) -> bool:
        if event.key() not in (Qt.Key.Key_Home, Qt.Key.Key_End):
            return False

        modifiers = event.modifiers()
        has_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        has_forbidden = bool(
            modifiers
            & (
                Qt.KeyboardModifier.ShiftModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        )
        return has_ctrl and not has_forbidden

    def _highlight_current_item(self) -> None:
        index = self.currentIndex()
        if not index.isValid():
            return

        selection_model = self.selectionModel()
        if selection_model is None:
            return

        selection_model.select(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )

    def _is_number_area_clicked(self, index, point) -> bool:
        delegate = self.itemDelegate()
        if not isinstance(delegate, ClipItemDelegate):
            return False

        option = QStyleOptionViewItem()
        option.initFrom(self)
        option.rect = self.visualRect(index)
        number_rect = delegate.number_rect_for_option(option)
        return number_rect.contains(point)

    def _is_note_area_clicked(self, index, point) -> bool:
        if not bool(index.data(ROLE_NOTE_EDITABLE)):
            return False
        delegate = self.itemDelegate()
        if not isinstance(delegate, ClipItemDelegate):
            return False

        option = QStyleOptionViewItem()
        option.initFrom(self)
        option.rect = self.visualRect(index)
        return delegate.note_rect_for_option(option).contains(point)


class SearchLineEdit(QLineEdit):
    escape_pressed = Signal()
    down_pressed = Signal()
    enter_pressed = Signal()
    tab_pressed = Signal()
    backtab_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_switch_enabled = False

    def set_tab_switch_enabled(self, enabled: bool) -> None:
        self._tab_switch_enabled = bool(enabled)

    def event(self, event) -> bool:
        if self._tab_switch_enabled and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab:
                self.tab_pressed.emit()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Backtab:
                self.backtab_pressed.emit()
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Down:
            self.down_pressed.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ClipItemDelegate(QStyledItemDelegate):
    note_changed = Signal(str, str)
    def __init__(
        self,
        parent: QWidget,
        max_preview_lines: int,
        row_vertical_padding: int,
    ) -> None:
        super().__init__(parent)
        self._max_preview_lines = max_preview_lines
        self._row_vertical_padding = row_vertical_padding
        self._number_box_width = 52
        self._number_box_height = 24
        self._note_box_height = 24
        self._note_box_gap = 8
        self._item_margin_h = 2
        self._item_margin_v = 3
        self._content_padding_h = 12
        self._content_padding_v = 8
        self._number_gap_y = 8
        self._number_color = QColor("#3AE2CE")
        self._number_color_pinned = QColor("#FFFFFF")
        self._text_color = QColor("#ABB2BF")
        self._text_color_selected = QColor("#FFFFFF")
        self._number_box_bg = QColor("#252C38")
        self._number_box_bg_pinned = QColor("#BF8255")
        self._number_box_border = QColor("#3B414D")
        self._number_box_border_pinned = QColor("#A86E43")
        self._note_box_bg = QColor("#2C313C")
        self._note_box_border = QColor("#3B414D")
        self._note_color = QColor("#D7DEE9")
        self._item_bg = QColor("#2C313C")
        self._item_border = QColor("#3B414D")
        self._item_selected_bg = QColor("#1E3A5F")
        self._item_selected_border = QColor("#2A4B75")
        self._number_box_radius = 6
        self._thumb_border = QColor("#3B414D")
        self._thumb_bg = QColor("#222A36")
        self._thumb_missing_text = QColor("#7F8AA0")
        self._thumb_max_width = 220
        self._thumb_max_height = 124
        self._thumb_title_gap_y = 8
        self._thumb_cache: dict[str, QPixmap] = {}

    def paint(self, painter, option, index) -> None:
        styled_option = QStyleOptionViewItem(option)
        styled_option.state &= ~QStyle.StateFlag.State_HasFocus
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        number_text = str(index.row() + 1)
        is_selected = bool(styled_option.state & QStyle.StateFlag.State_Selected)
        is_pinned = bool(index.data(ROLE_PINNED))
        item_kind = str(index.data(ROLE_KIND) or CLIP_KIND_TEXT).strip().casefold()
        item_rect, number_rect, note_rect, content_rect = self._layout_rects(styled_option)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self._item_selected_border if is_selected else self._item_border)
        painter.setBrush(self._item_selected_bg if is_selected else self._item_bg)
        painter.drawRoundedRect(
            item_rect,
            self._number_box_radius,
            self._number_box_radius,
        )
        painter.setPen(self._number_box_border_pinned if is_pinned else self._number_box_border)
        painter.setBrush(self._number_box_bg_pinned if is_pinned else self._number_box_bg)
        painter.drawRoundedRect(
            number_rect,
            self._number_box_radius,
            self._number_box_radius,
        )
        painter.setPen(self._number_color_pinned if is_pinned else self._number_color)
        painter.drawText(
            number_rect,
            int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            number_text,
        )

        if bool(index.data(ROLE_NOTE_EDITABLE)):
            note = str(index.data(ROLE_NOTE) or "")
            painter.setPen(self._note_box_border)
            painter.setBrush(self._item_selected_bg if is_selected else self._note_box_bg)
            painter.drawRoundedRect(note_rect, self._number_box_radius, self._number_box_radius)
            if note:
                painter.setPen(self._note_color)
                painter.drawText(
                    note_rect.adjusted(8, 0, -8, 0),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    note,
                )

        if item_kind == CLIP_KIND_IMAGE:
            self._paint_image_content(
                painter=painter,
                content_rect=content_rect,
                number_rect=number_rect,
                text=text,
                image_path=str(index.data(ROLE_IMAGE_PATH) or ""),
                is_selected=is_selected,
            )
        else:
            text_rect = self._text_rect(content_rect, number_rect)
            painter.setPen(self._text_color_selected if is_selected else self._text_color)
            painter.drawText(
                text_rect,
                self._text_paint_flags(painter.fontMetrics(), text_rect, text),
                text,
            )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        metrics = option.fontMetrics
        item_kind = str(index.data(ROLE_KIND) or CLIP_KIND_TEXT).strip().casefold()
        if item_kind == CLIP_KIND_IMAGE:
            thumb_size = self._thumbnail_target_size(option)
            row_height = (
                (self._item_margin_v * 2)
                + (self._content_padding_v * 2)
                + self._number_box_height
                + self._number_gap_y
                + thumb_size.height()
                + self._thumb_title_gap_y
                + metrics.lineSpacing()
                + self._row_vertical_padding
            )
        else:
            line_height = metrics.lineSpacing()
            text_width = self._text_column_width(option)

            required_rect = metrics.boundingRect(
                0,
                0,
                text_width,
                10000,
                int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs),
                text,
            )
            required_lines = max(1, (required_rect.height() + line_height - 1) // line_height)
            visible_lines = min(self._max_preview_lines, required_lines)
            row_height = (
                (self._item_margin_v * 2)
                + (self._content_padding_v * 2)
                + self._number_box_height
                + self._number_gap_y
                + (visible_lines * line_height)
                + self._row_vertical_padding
            )

        row_width = self._row_width(option)
        return QSize(row_width, row_height)

    def number_rect_for_option(self, option: QStyleOptionViewItem) -> QRect:
        _, number_rect, _, _ = self._layout_rects(option)
        return number_rect

    def note_rect_for_option(self, option: QStyleOptionViewItem) -> QRect:
        _, _, note_rect, _ = self._layout_rects(option)
        return note_rect

    def createEditor(self, parent, option, index):
        if not bool(index.data(ROLE_NOTE_EDITABLE)):
            return None
        editor = QLineEdit(parent)
        editor.setMaxLength(120)
        editor.setStyleSheet(
            "QLineEdit { color: #D7DEE9; background: #2C313C; "
            "border: 1px solid #3AE2CE; border-radius: 6px; padding: 0 8px; }"
        )
        return editor

    def setEditorData(self, editor, index) -> None:
        if isinstance(editor, QLineEdit):
            editor.setText(str(index.data(ROLE_NOTE) or ""))
            editor.selectAll()

    def setModelData(self, editor, model, index) -> None:
        if not isinstance(editor, QLineEdit):
            return
        note = " ".join(editor.text().replace("\r", " ").replace("\n", " ").split())
        if note != str(index.data(ROLE_NOTE) or ""):
            model.setData(index, note, ROLE_NOTE)
            self.note_changed.emit(str(index.data(ROLE_ITEM_KEY) or ""), note)

    def updateEditorGeometry(self, editor, option, index) -> None:
        if isinstance(editor, QLineEdit):
            editor.setGeometry(self.note_rect_for_option(option))

    def _row_width(self, option: QStyleOptionViewItem) -> int:
        if option.widget is not None:
            viewport_width = option.widget.viewport().width()
            return max(120, viewport_width - 8)
        if option.rect.width() > 0:
            return max(120, option.rect.width() - 8)
        return 120

    def _text_column_width(self, option: QStyleOptionViewItem) -> int:
        return max(
            100,
            self._row_width(option)
            - (self._item_margin_h * 2)
            - (self._content_padding_h * 2)
        )

    def _layout_rects(self, option: QStyleOptionViewItem) -> tuple[QRect, QRect, QRect, QRect]:
        item_rect = option.rect.adjusted(
            self._item_margin_h,
            self._item_margin_v,
            -self._item_margin_h,
            -self._item_margin_v,
        )

        content_rect = item_rect.adjusted(
            self._content_padding_h,
            self._content_padding_v,
            -self._content_padding_h,
            -self._content_padding_v,
        )

        number_width = min(self._number_box_width, max(36, content_rect.width()))
        number_x = content_rect.left()
        number_rect = QRect(
            number_x,
            content_rect.top(),
            number_width,
            min(self._number_box_height, content_rect.height()),
        )
        note_x = number_rect.right() + 1 + self._note_box_gap
        note_rect = QRect(
            note_x,
            content_rect.top(),
            max(0, content_rect.right() - note_x + 1),
            min(self._note_box_height, content_rect.height()),
        )
        return item_rect, number_rect, note_rect, content_rect

    def _text_rect(self, content_rect: QRect, number_rect: QRect) -> QRect:
        text_top = number_rect.bottom() + 1 + self._number_gap_y
        return QRect(
            content_rect.left(),
            text_top,
            content_rect.width(),
            max(0, content_rect.bottom() - text_top + 1),
        )

    @staticmethod
    def _text_paint_flags(metrics: QFontMetrics, text_rect: QRect, text: str) -> int:
        base_flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
        required_height = metrics.boundingRect(text_rect, base_flags, text).height()
        vertical_alignment = (
            Qt.AlignmentFlag.AlignVCenter
            if required_height <= text_rect.height()
            else Qt.AlignmentFlag.AlignTop
        )
        return base_flags | int(vertical_alignment)

    def _thumbnail_target_size(self, option: QStyleOptionViewItem) -> QSize:
        width = min(self._thumb_max_width, max(120, self._text_column_width(option)))
        height = min(self._thumb_max_height, max(72, int(width * 0.56)))
        return QSize(width, height)

    def _paint_image_content(
        self,
        painter: QPainter,
        content_rect: QRect,
        number_rect: QRect,
        text: str,
        image_path: str,
        is_selected: bool,
    ) -> None:
        thumb_size = self._thumbnail_target_size_for_content(content_rect)
        thumb_top = number_rect.bottom() + 1 + self._number_gap_y
        thumb_rect = QRect(
            content_rect.left(),
            thumb_top,
            min(thumb_size.width(), content_rect.width()),
            min(thumb_size.height(), max(0, content_rect.bottom() - thumb_top + 1)),
        )
        text_rect = QRect(
            content_rect.left(),
            thumb_rect.bottom() + 1 + self._thumb_title_gap_y,
            content_rect.width(),
            max(0, content_rect.bottom() - (thumb_rect.bottom() + 1 + self._thumb_title_gap_y) + 1),
        )

        painter.setPen(self._thumb_border)
        painter.setBrush(self._thumb_bg)
        painter.drawRoundedRect(QRectF(thumb_rect), 6, 6)

        scaled_thumb = self._load_thumbnail(image_path=image_path, target_size=thumb_rect.size())
        if scaled_thumb is not None:
            centered_x = thumb_rect.left() + (thumb_rect.width() - scaled_thumb.width()) // 2
            centered_y = thumb_rect.top() + (thumb_rect.height() - scaled_thumb.height()) // 2
            painter.drawPixmap(centered_x, centered_y, scaled_thumb)
        else:
            painter.setPen(self._thumb_missing_text)
            painter.drawText(
                thumb_rect,
                int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
                "Нет превью",
            )

        painter.setPen(self._text_color_selected if is_selected else self._text_color)
        painter.drawText(
            text_rect,
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            text,
        )

    def _thumbnail_target_size_for_content(self, content_rect: QRect) -> QSize:
        width = min(self._thumb_max_width, max(120, content_rect.width()))
        height = min(self._thumb_max_height, max(72, int(width * 0.56)))
        return QSize(width, height)

    def _load_thumbnail(self, image_path: str, target_size: QSize) -> QPixmap | None:
        prepared = image_path.strip()
        if not prepared:
            return None

        cached = self._thumb_cache.get(prepared)
        if cached is None:
            loaded = QPixmap(prepared)
            self._thumb_cache[prepared] = loaded
            cached = loaded
        if cached.isNull():
            return None
        return cached.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )


class TwoLineTabBar(QWidget):
    currentChanged = Signal(int)
    customContextMenuRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[dict[str, object]] = []
        self._current_index = -1
        self._wrapper_signals_blocked = False
        self._internal_update = False
        self._visible_indices: list[int] = []
        self._overflow_indices: list[int] = []
        self._preferred_overflow_index: int | None = None
        self._minimum_partial_tab_width = 56
        self._tab_buttons_factory = None
        self._draw_base = False
        self._expanding = False
        self._movable = False
        self._elide_mode = Qt.TextElideMode.ElideNone
        self._prefer_scroll_buttons = False
        self._context_menu_policy = Qt.ContextMenuPolicy.CustomContextMenu

        self._bar = QTabBar(self)
        self._bar.setObjectName("clipTabBar")
        self._bar.setDrawBase(self._draw_base)
        self._bar.setExpanding(self._expanding)
        self._bar.setMovable(self._movable)
        self._bar.setElideMode(self._elide_mode)
        self._bar.setUsesScrollButtons(self._prefer_scroll_buttons)
        self._bar.setContextMenuPolicy(self._context_menu_policy)
        self._bar.currentChanged.connect(self._on_bar_current_changed)
        self._bar.customContextMenuRequested.connect(self._on_bar_context_menu_requested)

        self._overflow_button = QToolButton(self)
        self._overflow_button.setObjectName("tabOverflowButton")
        self._overflow_button.setText("▼")
        self._overflow_button.setAutoRaise(True)
        self._overflow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._overflow_button.setToolTip("Показать скрытые вкладки")
        self._overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._overflow_menu = QMenu(self._overflow_button)
        self._overflow_menu.triggered.connect(self._on_overflow_action_triggered)
        self._overflow_button.setMenu(self._overflow_menu)
        self._overflow_button.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._bar, 1)
        layout.addWidget(self._overflow_button, 0, Qt.AlignmentFlag.AlignTop)

    def setObjectName(self, name: str) -> None:  # noqa: N802
        super().setObjectName(name)
        self._bar.setObjectName(name)

    def setDrawBase(self, value: bool) -> None:
        self._draw_base = value
        self._bar.setDrawBase(value)

    def setExpanding(self, value: bool) -> None:
        self._expanding = value
        self._bar.setExpanding(value)

    def setMovable(self, value: bool) -> None:
        self._movable = value
        self._bar.setMovable(value)

    def setElideMode(self, value: Qt.TextElideMode) -> None:
        self._elide_mode = value
        self._bar.setElideMode(value)

    def setUsesScrollButtons(self, value: bool) -> None:
        self._prefer_scroll_buttons = value
        self._rebuild_tabs()

    def setContextMenuPolicy(self, policy: Qt.ContextMenuPolicy) -> None:
        self._context_menu_policy = policy
        self._bar.setContextMenuPolicy(policy)

    def setTabButtonsFactory(self, factory) -> None:  # noqa: N802
        self._tab_buttons_factory = factory
        self._rebuild_tabs()

    def setOverflowMenuStyleSheet(self, stylesheet: str) -> None:  # noqa: N802
        self._overflow_menu.setStyleSheet(stylesheet)

    def overflowButtonTargetSize(self) -> QSize:  # noqa: N802
        width = max(28, self._overflow_button.sizeHint().width())
        tab_height = self._bar.sizeHint().height()
        if self._bar.count() > 0:
            tab_rect = self._bar.tabRect(0)
            if tab_rect.isValid() and tab_rect.height() > 0:
                tab_height = tab_rect.height()
        return QSize(width, max(24, tab_height))

    def blockSignals(self, block: bool) -> bool:  # noqa: A003
        previous = self._wrapper_signals_blocked
        self._wrapper_signals_blocked = bool(block)
        self._bar.blockSignals(block)
        self._overflow_menu.blockSignals(block)
        return previous

    def preferredOverflowTabName(self) -> str | None:  # noqa: N802
        index = self._preferred_overflow_index
        if index is None or index < 0 or index >= len(self._tabs):
            return None
        value = self.tabText(index).strip()
        return value or None

    def setPreferredOverflowTabName(  # noqa: N802
        self,
        tab_name: str | None,
        *,
        rebuild: bool = True,
    ) -> None:
        prepared = str(tab_name or "").strip()
        if not prepared:
            self._preferred_overflow_index = None
            if rebuild:
                self._rebuild_tabs()
            return

        target_index: int | None = None
        for index, tab_state in enumerate(self._tabs):
            if str(tab_state.get("text", "")).strip() == prepared:
                target_index = index
                break

        self._preferred_overflow_index = target_index
        if rebuild:
            self._rebuild_tabs()

    def count(self) -> int:
        return len(self._tabs)

    def stepVisible(self, delta: int) -> None:  # noqa: N802
        if delta == 0 or not self._visible_indices:
            return

        if self._current_index in self._visible_indices:
            current_visible_pos = self._visible_indices.index(self._current_index)
        else:
            current_visible_pos = 0 if delta > 0 else len(self._visible_indices) - 1

        target_visible_pos = (current_visible_pos + delta) % len(self._visible_indices)
        target_index = self._visible_indices[target_visible_pos]
        self.setCurrentIndex(target_index)

    def addTab(self, text: str) -> int:
        self._tabs.append(
            {
                "text": text,
                "data": None,
            }
        )
        if self._current_index < 0:
            self._current_index = 0
        self._rebuild_tabs()
        return len(self._tabs) - 1

    def removeTab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            return

        self._tabs.pop(index)
        if self._preferred_overflow_index is not None:
            if self._preferred_overflow_index == index:
                self._preferred_overflow_index = None
            elif index < self._preferred_overflow_index:
                self._preferred_overflow_index -= 1

        if not self._tabs:
            self._current_index = -1
        elif index < self._current_index:
            self._current_index -= 1
        elif index == self._current_index:
            self._current_index = min(index, len(self._tabs) - 1)
        self._rebuild_tabs()

    def setTabData(self, index: int, data: object) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        self._tabs[index]["data"] = data
        self._rebuild_tabs()

    def tabData(self, index: int) -> object | None:
        if index < 0 or index >= len(self._tabs):
            return None
        return self._tabs[index].get("data")

    def setTabButton(
        self,
        index: int,
        position: QTabBar.ButtonPosition,
        button: QWidget | None,
    ) -> None:
        # Совместимость с API QTabBar: в TwoLineTabBar кнопки задаются фабрикой.
        del index, position, button

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        if not self._tabs:
            self._current_index = -1
            self._sync_current_selection()
            return

        target_index = max(0, min(index, len(self._tabs) - 1))
        changed = target_index != self._current_index
        self._current_index = target_index
        self._rebuild_tabs()
        if changed and not self._wrapper_signals_blocked:
            self.currentChanged.emit(target_index)

    def tabText(self, index: int) -> str:
        if index < 0 or index >= len(self._tabs):
            return ""
        return str(self._tabs[index].get("text", ""))

    def tabAt(self, pos) -> int:
        local_pos = self._bar.mapFrom(self, pos)
        local_index = self._bar.tabAt(local_pos)
        if local_index < 0:
            return -1
        if local_index >= len(self._visible_indices):
            return -1
        return self._visible_indices[local_index]

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rebuild_tabs()

    def _on_bar_current_changed(self, local_index: int) -> None:
        if self._internal_update or self._wrapper_signals_blocked:
            return
        if local_index < 0:
            return

        if local_index >= len(self._visible_indices):
            return

        global_index = self._visible_indices[local_index]
        if global_index == self._current_index:
            return

        self._current_index = global_index
        self._sync_current_selection()
        self._rebuild_overflow_menu()
        if not self._wrapper_signals_blocked:
            self.currentChanged.emit(global_index)

    def _on_bar_context_menu_requested(self, pos) -> None:
        mapped_pos = self.mapFromGlobal(self._bar.mapToGlobal(pos))
        if not self._wrapper_signals_blocked:
            self.customContextMenuRequested.emit(mapped_pos)

    def _on_overflow_action_triggered(self, action: QAction) -> None:
        data = action.data()
        try:
            index = int(data)
        except (TypeError, ValueError):
            return
        if index < 0 or index >= len(self._tabs):
            return
        self._preferred_overflow_index = index
        self.setCurrentIndex(index)

    def _rebuild_tabs(self) -> None:
        if self._internal_update:
            return

        self._internal_update = True
        try:
            if self._tabs and (self._current_index < 0 or self._current_index >= len(self._tabs)):
                self._current_index = 0
            if not self._tabs:
                self._current_index = -1
            if self._preferred_overflow_index is not None and (
                self._preferred_overflow_index < 0
                or self._preferred_overflow_index >= len(self._tabs)
            ):
                self._preferred_overflow_index = None

            available_width = max(1, self.contentsRect().width())
            tab_widths = [self._estimate_tab_width(tab) for tab in self._tabs]
            overflow_button_width = self._estimate_overflow_button_width()
            always_visible_indices = self._required_visible_indices()
            self._sync_minimum_width_for_required_tabs(
                tab_widths=tab_widths,
                required_indices=always_visible_indices,
                overflow_button_width=overflow_button_width,
            )
            visible_indices, overflow_indices = self._split_visible_overflow(
                tab_widths,
                available_width,
                overflow_button_width,
                preferred_index=self._preferred_overflow_index,
                min_partial_width=self._minimum_partial_tab_width,
                always_visible_indices=always_visible_indices,
            )
            candidate_visible = list(visible_indices)
            candidate_overflow = list(overflow_indices)
            required_set = set(always_visible_indices)

            previous_block = self._bar.blockSignals(True)
            while True:
                while self._bar.count() > 0:
                    self._bar.removeTab(0)

                visible_limit = max(
                    1,
                    available_width - (overflow_button_width if candidate_overflow else 0),
                )
                display_texts = self._build_visible_display_texts(
                    visible_indices=candidate_visible,
                    required_indices=always_visible_indices,
                    visible_limit=visible_limit,
                )

                for global_index in candidate_visible:
                    tab_state = self._tabs[global_index]
                    display_text = display_texts.get(
                        global_index,
                        str(tab_state.get("text", "")),
                    )
                    local_index = self._bar.addTab(display_text)
                    self._bar.setTabData(local_index, tab_state.get("data"))
                    left_button, right_button = self._create_tab_buttons(
                        self._bar,
                        global_index,
                        tab_state.get("data"),
                    )
                    self._bar.setTabButton(
                        local_index,
                        QTabBar.ButtonPosition.LeftSide,
                        left_button,
                    )
                    self._bar.setTabButton(
                        local_index,
                        QTabBar.ButtonPosition.RightSide,
                        right_button,
                    )

                # Сначала применяем финальное состояние overflow-кнопки и layout,
                # затем проверяем фактические размеры системных вкладок.
                self._overflow_button.setVisible(bool(candidate_overflow))
                self._bar.setUsesScrollButtons(
                    self._prefer_scroll_buttons and not candidate_overflow
                )
                self._sync_overflow_button_size()
                layout = self.layout()
                if layout is not None:
                    layout.activate()

                if not always_visible_indices or self._required_tabs_have_full_width(
                    required_indices=always_visible_indices,
                    visible_indices=candidate_visible,
                ):
                    break

                removable = [
                    index for index in reversed(candidate_visible) if index not in required_set
                ]
                if not removable:
                    break
                candidate_visible.remove(removable[0])
                candidate_overflow = [
                    index for index in range(len(self._tabs)) if index not in candidate_visible
                ]

            self._bar.blockSignals(previous_block)
            self._visible_indices = candidate_visible
            self._overflow_indices = candidate_overflow
            self._overflow_button.setVisible(bool(self._overflow_indices))
            self._rebuild_overflow_menu()
            self._bar.setUsesScrollButtons(self._prefer_scroll_buttons and not self._overflow_indices)

            self._sync_current_selection()
            self._sync_overflow_button_size()
        finally:
            self._internal_update = False

    def _sync_current_selection(self) -> None:
        previous_block = self._bar.blockSignals(True)
        if self._current_index in self._visible_indices:
            target_local_index = self._visible_indices.index(self._current_index)
        else:
            target_local_index = -1
        self._bar.setCurrentIndex(target_local_index)
        self._bar.blockSignals(previous_block)

    def _rebuild_overflow_menu(self) -> None:
        self._overflow_menu.clear()
        for global_index in self._overflow_indices:
            action = self._overflow_menu.addAction(self.tabText(global_index))
            action.setData(global_index)
            action.setCheckable(True)
            action.setChecked(global_index == self._current_index)

    def _estimate_overflow_button_width(self) -> int:
        # Ширина кнопки + запас под spacing layout.
        return max(28, self._overflow_button.sizeHint().width() + 6)

    def _sync_overflow_button_size(self) -> None:
        self._overflow_button.setFixedSize(self.overflowButtonTargetSize())

    def _estimate_tab_width(self, tab_state: dict[str, object]) -> int:
        text = str(tab_state.get("text", ""))
        font_metrics = QFontMetrics(self._bar.font())
        width = font_metrics.horizontalAdvance(text) + 34
        width += TAB_SIDE_BUTTON_SLOT_WIDTH  # Левая кнопка скрепки.

        tab_data = tab_state.get("data")
        is_system = False
        if isinstance(tab_data, dict):
            is_system = bool(tab_data.get("is_system", False))
        if not is_system:
            width += TAB_SIDE_BUTTON_SLOT_WIDTH  # Правая кнопка закрытия.

        return max(72, width)

    def _estimate_tab_base_width(self, tab_state: dict[str, object]) -> int:
        text = str(tab_state.get("text", ""))
        font_metrics = QFontMetrics(self._bar.font())
        return self._estimate_tab_width(tab_state) - font_metrics.horizontalAdvance(text)

    def _build_visible_display_texts(
        self,
        *,
        visible_indices: list[int],
        required_indices: list[int],
        visible_limit: int,
        spacing: int = 4,
    ) -> dict[int, str]:
        display_texts = {
            index: str(self._tabs[index].get("text", ""))
            for index in visible_indices
        }
        if len(visible_indices) <= 0:
            return display_texts

        required_set = set(required_indices)
        adjustable_index: int | None = None
        for index in reversed(visible_indices):
            if index not in required_set:
                adjustable_index = index
                break
        if adjustable_index is None:
            return display_texts

        full_widths = {
            index: self._estimate_tab_width(self._tabs[index])
            for index in visible_indices
        }
        total_width = sum(full_widths.values()) + (len(visible_indices) - 1) * spacing
        if total_width <= visible_limit:
            return display_texts

        adjustable_full = full_widths[adjustable_index]
        base_width = self._estimate_tab_base_width(self._tabs[adjustable_index])
        min_target_width = max(self._minimum_partial_tab_width, base_width + 8)
        target_width = max(min_target_width, adjustable_full - (total_width - visible_limit))
        if target_width >= adjustable_full:
            return display_texts

        full_text = str(self._tabs[adjustable_index].get("text", ""))
        font_metrics = QFontMetrics(self._bar.font())
        text_target_width = max(1, target_width - base_width)
        display_texts[adjustable_index] = font_metrics.elidedText(
            full_text,
            Qt.TextElideMode.ElideRight,
            text_target_width,
        )
        return display_texts

    def _create_tab_buttons(
        self,
        parent_bar: QTabBar,
        tab_index: int,
        tab_data: object,
    ) -> tuple[QWidget | None, QWidget | None]:
        factory = self._tab_buttons_factory
        if factory is None:
            return None, None
        try:
            produced = factory(tab_index, tab_data, parent_bar)
        except TypeError:
            try:
                # Поддержка старой фабрики с двумя аргументами.
                produced = factory(tab_index, tab_data)
            except Exception:
                return None, None
        except Exception:
            return None, None
        if not isinstance(produced, tuple) or len(produced) != 2:
            return None, None

        left_button, right_button = produced
        if not _is_live_widget(left_button):
            left_button = None
        elif left_button.parentWidget() is not parent_bar:
            left_button.setParent(parent_bar)
        if not _is_live_widget(right_button):
            right_button = None
        elif right_button.parentWidget() is not parent_bar:
            right_button.setParent(parent_bar)
        return left_button, right_button

    def _required_visible_indices(self) -> list[int]:
        required: list[int] = []
        for index, tab_state in enumerate(self._tabs):
            tab_data = tab_state.get("data")
            if not isinstance(tab_data, dict):
                continue
            if bool(tab_data.get("is_buffer", False)) or bool(tab_data.get("is_images", False)):
                required.append(index)
        return required

    def _required_tabs_have_full_width(
        self,
        *,
        required_indices: list[int],
        visible_indices: list[int],
        tolerance: int = 6,
    ) -> bool:
        if not required_indices:
            return True

        for global_index in required_indices:
            if global_index not in visible_indices:
                return False

            local_index = visible_indices.index(global_index)
            if local_index < 0 or local_index >= self._bar.count():
                return False

            tab_rect = self._bar.tabRect(local_index)
            if not tab_rect.isValid():
                return False

            expected_width = self._bar.tabSizeHint(local_index).width()
            if tab_rect.width() + tolerance < expected_width:
                return False
        return True

    def _sync_minimum_width_for_required_tabs(
        self,
        *,
        tab_widths: list[int],
        required_indices: list[int],
        overflow_button_width: int,
        spacing: int = 4,
    ) -> None:
        if not required_indices:
            self.setMinimumWidth(1)
            return

        required_width = 0
        for position, tab_index in enumerate(required_indices):
            if position > 0:
                required_width += spacing
            required_width += tab_widths[tab_index]

        if len(tab_widths) > len(required_indices):
            required_width += spacing + max(0, overflow_button_width)

        self.setMinimumWidth(max(1, required_width))

    @staticmethod
    def _split_visible_overflow(
        tab_widths: list[int],
        available_width: int,
        overflow_button_width: int,
        preferred_index: int | None = None,
        min_partial_width: int = 56,
        spacing: int = 4,
        always_visible_indices: list[int] | None = None,
    ) -> tuple[list[int], list[int]]:
        if not tab_widths:
            return [], []
        if len(tab_widths) == 1:
            return [0], []
        required_indices = TwoLineTabBar._sanitize_indices(
            always_visible_indices,
            len(tab_widths),
        )
        if available_width <= 0:
            visible_when_zero = required_indices if required_indices else [0]
            overflow_when_zero = [
                index
                for index in range(len(tab_widths))
                if index not in visible_when_zero
            ]
            return visible_when_zero, overflow_when_zero

        total_width = sum(tab_widths) + (len(tab_widths) - 1) * spacing
        if total_width <= available_width:
            return list(range(len(tab_widths))), []

        valid_preferred: int | None = None
        if preferred_index is not None and 0 <= preferred_index < len(tab_widths):
            valid_preferred = preferred_index

        if valid_preferred is not None:
            visible_indices, overflow_indices = TwoLineTabBar._split_with_preferred_overflow(
                tab_widths=tab_widths,
                available_width=available_width,
                overflow_button_width=overflow_button_width,
                preferred_index=valid_preferred,
                spacing=spacing,
            )
        else:
            visible_without_button = TwoLineTabBar._fit_prefix_with_partial_tail(
                tab_widths=tab_widths,
                visible_limit=available_width,
                min_partial_width=min_partial_width,
                spacing=spacing,
            )
            if len(visible_without_button) >= len(tab_widths):
                visible_indices = visible_without_button
                overflow_indices = []
            else:
                visible_limit = max(1, available_width - max(0, overflow_button_width))
                visible_indices = TwoLineTabBar._fit_prefix_with_partial_tail(
                    tab_widths=tab_widths,
                    visible_limit=visible_limit,
                    min_partial_width=min_partial_width,
                    spacing=spacing,
                )
                if len(visible_indices) >= len(tab_widths):
                    overflow_indices = []
                else:
                    overflow_indices = list(range(len(visible_indices), len(tab_widths)))

        if required_indices:
            visible_indices, overflow_indices = TwoLineTabBar._enforce_required_visible_indices(
                tab_widths=tab_widths,
                visible_indices=visible_indices,
                required_indices=required_indices,
                available_width=available_width,
                overflow_button_width=overflow_button_width,
                min_partial_width=min_partial_width,
                spacing=spacing,
                preferred_index=valid_preferred,
            )
        return visible_indices, overflow_indices

    @staticmethod
    def _fit_prefix_with_partial_tail(
        tab_widths: list[int],
        visible_limit: int,
        min_partial_width: int,
        spacing: int,
    ) -> list[int]:
        if not tab_widths:
            return []

        normalized_limit = max(1, visible_limit)
        visible_indices: list[int] = []
        used_width = 0

        for index, tab_width in enumerate(tab_widths):
            prefix_spacing = spacing if visible_indices else 0
            required_width = used_width + prefix_spacing + tab_width
            if required_width <= normalized_limit:
                visible_indices.append(index)
                used_width = required_width
                continue

            remaining_width = normalized_limit - used_width - prefix_spacing
            if remaining_width >= min_partial_width:
                visible_indices.append(index)
            break

        if not visible_indices:
            return [0]
        return visible_indices

    @staticmethod
    def _split_with_preferred_overflow(
        tab_widths: list[int],
        available_width: int,
        overflow_button_width: int,
        preferred_index: int,
        spacing: int,
    ) -> tuple[list[int], list[int]]:
        indices = list(range(len(tab_widths)))
        visible_limit = max(1, available_width - max(0, overflow_button_width))
        preferred_width = tab_widths[preferred_index]

        if preferred_width >= visible_limit:
            visible_indices = [preferred_index]
            overflow_indices = [idx for idx in indices if idx != preferred_index]
            return visible_indices, overflow_indices

        candidates = [idx for idx in indices if idx != preferred_index]
        visible_prefix: list[int] = []
        used_width = 0
        reserve_before_preferred = spacing

        for idx in candidates:
            next_width = tab_widths[idx]
            prefix_spacing = spacing if visible_prefix else 0
            required_prefix = used_width + prefix_spacing + next_width
            required_total = required_prefix + reserve_before_preferred + preferred_width
            if required_total > visible_limit:
                break
            visible_prefix.append(idx)
            used_width = required_prefix

        visible_indices = visible_prefix + [preferred_index]
        overflow_indices = [idx for idx in indices if idx not in visible_indices]
        return visible_indices, overflow_indices

    @staticmethod
    def _sanitize_indices(
        indices: list[int] | None,
        upper_bound: int,
    ) -> list[int]:
        if not indices or upper_bound <= 0:
            return []
        prepared: list[int] = []
        for raw_value in indices:
            try:
                index = int(raw_value)
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= upper_bound:
                continue
            if index in prepared:
                continue
            prepared.append(index)
        return prepared

    @staticmethod
    def _enforce_required_visible_indices(
        *,
        tab_widths: list[int],
        visible_indices: list[int],
        required_indices: list[int],
        available_width: int,
        overflow_button_width: int,
        min_partial_width: int,
        spacing: int,
        preferred_index: int | None,
    ) -> tuple[list[int], list[int]]:
        if not required_indices:
            overflow = [
                index
                for index in range(len(tab_widths))
                if index not in visible_indices
            ]
            return visible_indices, overflow

        required_set = set(required_indices)
        merged_visible = [index for index in range(len(tab_widths)) if index in required_set]
        for index in visible_indices:
            if index not in merged_visible:
                merged_visible.append(index)

        if len(merged_visible) >= len(tab_widths):
            return list(range(len(tab_widths))), []

        visible_limit = max(1, available_width - max(0, overflow_button_width))
        trimmed_visible = TwoLineTabBar._trim_visible_selection(
            tab_widths=tab_widths,
            selected_indices=merged_visible,
            required_indices=required_indices,
            visible_limit=visible_limit,
            min_partial_width=min_partial_width,
            spacing=spacing,
            preferred_index=preferred_index,
        )
        overflow = [
            index
            for index in range(len(tab_widths))
            if index not in trimmed_visible
        ]
        return trimmed_visible, overflow

    @staticmethod
    def _trim_visible_selection(
        *,
        tab_widths: list[int],
        selected_indices: list[int],
        required_indices: list[int],
        visible_limit: int,
        min_partial_width: int,
        spacing: int,
        preferred_index: int | None,
    ) -> list[int]:
        required_set = set(required_indices)
        visible = list(selected_indices)

        while (
            not TwoLineTabBar._selection_fits_width(
                tab_widths=tab_widths,
                selected_indices=visible,
                visible_limit=visible_limit,
                min_partial_width=min_partial_width,
                spacing=spacing,
                required_indices=required_set,
            )
            and len(visible) > len(required_set)
        ):
            removable = [index for index in reversed(visible) if index not in required_set]
            if not removable:
                break
            index_to_remove = removable[0]
            if preferred_index is not None and index_to_remove == preferred_index and len(removable) > 1:
                index_to_remove = removable[1]
            visible.remove(index_to_remove)

        if not visible:
            return required_indices[:1] if required_indices else [0]

        if TwoLineTabBar._selection_fits_width(
            tab_widths=tab_widths,
            selected_indices=visible,
            visible_limit=visible_limit,
            min_partial_width=min_partial_width,
            spacing=spacing,
            required_indices=required_set,
        ):
            return visible

        required_only = [index for index in visible if index in required_set]
        return required_only if required_only else visible

    @staticmethod
    def _selection_fits_width(
        *,
        tab_widths: list[int],
        selected_indices: list[int],
        visible_limit: int,
        min_partial_width: int,
        spacing: int,
        required_indices: set[int] | None = None,
    ) -> bool:
        if not selected_indices:
            return True

        normalized_limit = max(1, visible_limit)
        used_width = 0
        last_position = len(selected_indices) - 1
        required = required_indices or set()

        for position, tab_index in enumerate(selected_indices):
            tab_width = tab_widths[tab_index]
            prefix_spacing = spacing if position > 0 else 0
            required_width = used_width + prefix_spacing + tab_width
            if required_width <= normalized_limit:
                used_width = required_width
                continue

            remaining_width = normalized_limit - used_width - prefix_spacing
            if position == last_position and tab_index in required:
                return False
            return position == last_position and remaining_width >= min_partial_width

        return True


class PopupWindow(QWidget):
    item_chosen = Signal(str, bool)
    items_deleted = Signal(list)
    clear_all_requested = Signal()
    pin_toggle_requested = Signal(str)
    item_note_changed = Signal(str, str)
    tab_changed = Signal(str)
    tab_close_requested = Signal(str)
    tab_rename_requested = Signal(str, str)
    tab_capture_lock_toggle_requested = Signal(str)
    tab_create_requested = Signal(str)
    escape_pressed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._max_preview_lines = 5
        self._row_vertical_padding = 4
        self._all_items: list[ClipItem] = []
        self._active_tab_supports_notes = True
        self._tab_search_match_index: int | None = None
        self._search_tab_cycle_enabled = False
        self.setObjectName("popupRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setWindowTitle(f"FastClip v{__version__}")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(760, 420)

        self._clear_button = QPushButton("Очистить")
        self._clear_button.setObjectName("dangerButton")
        self._clear_button.setToolTip("Очистить буфер")
        self._index_input_view = QLineEdit()
        self._index_input_view.setReadOnly(True)
        self._index_input_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._index_input_view.setPlaceholderText("№")
        self._index_input_view.setMaxLength(3)
        index_metrics = self._index_input_view.fontMetrics()
        self._index_input_view.setFixedWidth(
            max(64, index_metrics.horizontalAdvance("500") + 28)
        )
        index_palette = self._index_input_view.palette()
        index_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#3AE2CE"))
        self._index_input_view.setPalette(index_palette)
        self._search_input = SearchLineEdit()
        self._search_input.setPlaceholderText("Поиск по ячейкам")
        self._tab_search_input = SearchLineEdit()
        self._tab_search_input.setPlaceholderText("Поиск по вкладкам")
        self._tab_search_input.hide()

        self._add_tab_button = QPushButton("+")
        self._add_tab_button.setObjectName("addTabButton")
        self._add_tab_button.setToolTip("Создать новую вкладку")

        self._tab_bar = TwoLineTabBar()
        self._tab_bar.setObjectName("clipTabBar")
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setMovable(False)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._tab_bar.setUsesScrollButtons(False)
        self._tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tab_bar.setTabButtonsFactory(self._build_tab_buttons)
        self._tab_bar.setOverflowMenuStyleSheet(self._build_tab_context_menu_stylesheet())

        self._list = ClipListWidget()
        self._setup_list()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self._index_input_view)
        header.addWidget(self._search_input, 1)
        header.addWidget(self._clear_button)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.addWidget(self._tab_search_input)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(6)
        tabs_row.addWidget(self._add_tab_button)
        tabs_row.addWidget(self._tab_bar, 1)
        tabs_row.setAlignment(self._add_tab_button, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header)
        layout.addLayout(search_row)
        layout.addLayout(tabs_row)
        layout.addWidget(self._list)

        self._list.enter_pressed.connect(
            lambda item_key: self.item_chosen.emit(item_key, False)
        )
        self._list.tab_step_requested.connect(self._step_tabs)
        self._list.item_choose_requested.connect(
            lambda item_key: self.item_chosen.emit(item_key, False)
        )
        self._list.delete_pressed.connect(self.items_deleted.emit)
        self._list.index_input_changed.connect(self._on_index_input_changed)
        self._list.pin_toggle_requested.connect(self.pin_toggle_requested.emit)
        delegate = self._list.itemDelegate()
        if isinstance(delegate, ClipItemDelegate):
            delegate.note_changed.connect(self.item_note_changed.emit)
        self._list.alt_item_choose_requested.connect(
            lambda item_key: self.item_chosen.emit(item_key, True)
        )
        self._list.find_requested.connect(self._activate_search)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.escape_pressed.connect(self._on_search_escape_pressed)
        self._search_input.down_pressed.connect(self._focus_list_from_search)
        self._search_input.enter_pressed.connect(self._choose_current_from_search)
        self._search_input.tab_pressed.connect(self._focus_tab_search_input)
        self._tab_search_input.textChanged.connect(self._on_tab_search_text_changed)
        self._tab_search_input.escape_pressed.connect(self._on_tab_search_escape_pressed)
        self._tab_search_input.enter_pressed.connect(self._choose_tab_from_search)
        self._tab_search_input.tab_pressed.connect(self._focus_clip_search_input)
        self._add_tab_button.clicked.connect(self._on_add_tab_clicked)
        self._tab_bar.currentChanged.connect(self._on_tab_bar_changed)
        self._tab_bar.customContextMenuRequested.connect(self._on_tab_bar_context_menu)
        self._clear_button.clicked.connect(self.clear_all_requested.emit)
        self._popup_stylesheet = self._build_popup_stylesheet()
        self.setStyleSheet(self._popup_stylesheet)
        self._sync_add_tab_button_size()

    def set_tabs(
        self,
        tab_states: list[dict[str, object]],
        active_tab: str,
        preferred_overflow_tab: str | None = None,
    ) -> None:
        if preferred_overflow_tab is None:
            preferred_overflow_tab = self._tab_bar.preferredOverflowTabName()
        if preferred_overflow_tab is None:
            prepared_active = active_tab.strip()
            if (
                prepared_active
                and prepared_active.casefold()
                not in {
                    DEFAULT_CLIP_TAB_NAME.casefold(),
                    DEFAULT_IMAGE_TAB_NAME.casefold(),
                }
            ):
                preferred_overflow_tab = prepared_active
        blocked = self._tab_bar.blockSignals(True)
        while self._tab_bar.count() > 0:
            self._tab_bar.removeTab(0)

        active_index = -1
        for tab_state in tab_states:
            if not isinstance(tab_state, dict):
                continue
            name = str(tab_state.get("name", "")).strip()
            if not name:
                continue
            capture_locked = bool(tab_state.get("capture_locked", False))
            is_buffer = bool(tab_state.get("is_buffer", False))
            is_images = bool(tab_state.get("is_images", False))
            is_system = bool(tab_state.get("is_system", False))

            index = self._tab_bar.addTab(name)
            self._tab_bar.setTabData(
                index,
                {
                    "tab_name": name,
                    "capture_locked": capture_locked,
                    "is_buffer": is_buffer,
                    "is_images": is_images,
                    "is_system": is_system,
                },
            )
            if name == active_tab:
                active_index = index

        if self._tab_bar.count() > 0:
            if active_index < 0:
                active_index = 0
            self._tab_bar.setCurrentIndex(active_index)

        self._tab_bar.setPreferredOverflowTabName(preferred_overflow_tab)
        self._tab_bar.blockSignals(blocked)
        self._sync_add_tab_button_size()
        self._tab_search_match_index = self._resolve_tab_search_match_index(
            self._tab_search_input.text()
        )

    def preferred_overflow_tab_name(self) -> str | None:
        return self._tab_bar.preferredOverflowTabName()

    def _build_tab_buttons(
        self,
        tab_index: int,
        tab_data: object,
        parent_bar: QWidget | None = None,
    ) -> tuple[QWidget | None, QWidget | None]:
        del tab_index
        if not isinstance(tab_data, dict):
            return None, None

        tab_name = str(tab_data.get("tab_name", "")).strip()
        if not tab_name:
            return None, None

        capture_locked = bool(tab_data.get("capture_locked", False))
        is_buffer = bool(tab_data.get("is_buffer", False))
        is_images = bool(tab_data.get("is_images", False))
        is_system = bool(tab_data.get("is_system", False))
        lock_button = self._create_tab_lock_button(
            tab_name=tab_name,
            capture_locked=capture_locked,
            is_buffer=is_buffer,
            is_images=is_images,
            is_system=is_system,
            parent=parent_bar,
        )
        close_button = self._create_tab_close_button(
            tab_name=tab_name,
            is_system=is_system,
            parent=parent_bar,
        )
        left_widget = self._wrap_tab_button(lock_button, side=QTabBar.ButtonPosition.LeftSide)
        right_widget = self._wrap_tab_button(close_button, side=QTabBar.ButtonPosition.RightSide)
        return left_widget, right_widget

    @staticmethod
    def _wrap_tab_button(
        button: QToolButton | None,
        *,
        side: QTabBar.ButtonPosition,
    ) -> QWidget | None:
        if button is None:
            return None

        wrapper = QWidget(button.parentWidget())
        wrapper.setObjectName("tabButtonPadding")
        wrapper.setFixedSize(TAB_SIDE_BUTTON_SLOT_WIDTH, TAB_SIDE_BUTTON_SIZE)
        wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QHBoxLayout(wrapper)
        if side == QTabBar.ButtonPosition.LeftSide:
            layout.setContentsMargins(
                TAB_SIDE_BUTTON_EDGE_PADDING,
                0,
                TAB_SIDE_BUTTON_TEXT_GAP,
                0,
            )
        else:
            layout.setContentsMargins(
                TAB_SIDE_BUTTON_TEXT_GAP,
                0,
                TAB_SIDE_BUTTON_EDGE_PADDING,
                0,
            )
        layout.setSpacing(0)
        layout.addWidget(button)
        return wrapper

    def _create_tab_lock_button(
        self,
        tab_name: str,
        capture_locked: bool,
        is_buffer: bool,
        is_images: bool,
        is_system: bool,
        parent: QWidget | None = None,
    ) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("tabLockButton")
        button.setText("📎")
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(TAB_SIDE_BUTTON_SIZE, TAB_SIDE_BUTTON_SIZE)
        if is_system:
            button.setEnabled(False)
            if is_buffer:
                button.setToolTip("Вкладка Буфер всегда принимает копирование")
                button.setStyleSheet(
                    "QToolButton { color: #3AE2CE; border: 1px solid #2A4B75; "
                    "border-radius: 5px; background: #1E3A5F; font-size: 11px; }"
                )
            elif is_images:
                button.setToolTip("Вкладка Фото принимает только изображения")
                button.setStyleSheet(
                    "QToolButton { color: #3AE2CE; border: 1px solid #3B414D; "
                    "border-radius: 5px; background: #2A3140; font-size: 11px; }"
                )
            return button

        if capture_locked:
            button.setToolTip("Скопированное содержимое направляется только в системные вкладки")
            button.setStyleSheet(
                "QToolButton { color: #FFFFFF; border: 1px solid #A86E43; "
                "border-radius: 5px; background: #BF8255; font-size: 11px; }"
                "QToolButton:hover { background: #A86E43; }"
            )
        else:
            button.setToolTip("Скопированное содержимое добавляется и в эту активную вкладку")
            button.setStyleSheet(
                "QToolButton { color: #3AE2CE; border: 1px solid #3B414D; "
                "border-radius: 5px; background: #252C38; font-size: 11px; }"
                "QToolButton:hover { background: #2D3644; }"
            )
        button.clicked.connect(
            lambda checked=False, name=tab_name: self.tab_capture_lock_toggle_requested.emit(name)
        )
        return button

    def _create_tab_close_button(
        self,
        tab_name: str,
        is_system: bool,
        parent: QWidget | None = None,
    ) -> QToolButton | None:
        if is_system:
            return None

        button = QToolButton(parent)
        button.setObjectName("tabCloseButton")
        button.setText("×")
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(TAB_SIDE_BUTTON_SIZE, TAB_SIDE_BUTTON_SIZE)
        button.setToolTip("Закрыть вкладку")
        button.setStyleSheet(
            "QToolButton { color: #ABB2BF; border: 1px solid #3B414D; "
            "border-radius: 5px; background: #252C38; font-size: 12px; }"
            "QToolButton:hover { color: #FFFFFF; background: #8F5D38; border: 1px solid #A86E43; }"
        )
        button.clicked.connect(
            lambda checked=False, name=tab_name: self.tab_close_requested.emit(name)
        )
        return button

    def set_items(self, items: list[ClipItem]) -> None:
        self._all_items = [
            ClipItem(
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
            for item in items
        ]
        self._render_filtered_items()
        self._clear_button.setEnabled(bool(items))

    def _render_filtered_items(self) -> None:
        previous_scroll_value = self._list.verticalScrollBar().value()
        previous_current_key = self._current_item_key()
        query_active = bool(self._search_input.text().strip())
        self._list.clear_index_input()
        self._list.clear()
        for clip_item in self._filtered_items():
            display = self._to_preview(clip_item.preview_title())
            item = QListWidgetItem(display)
            item.setData(ROLE_ITEM_KEY, clip_item.key)
            item.setData(ROLE_PINNED, clip_item.pinned)
            item.setData(ROLE_KIND, clip_item.kind)
            item.setData(ROLE_SEARCH_TEXT, clip_item.search_text())
            item.setData(ROLE_NOTE, clip_item.note)
            item.setData(ROLE_NOTE_EDITABLE, self._active_tab_supports_notes)
            if self._active_tab_supports_notes:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if clip_item.kind == CLIP_KIND_IMAGE:
                resolved_image_path = self._resolve_image_path(clip_item.image_path)
                item.setData(ROLE_IMAGE_PATH, resolved_image_path)
                dimensions = (
                    f"{clip_item.image_width}x{clip_item.image_height}"
                    if clip_item.image_width > 0 and clip_item.image_height > 0
                    else "неизвестно"
                )
                item.setToolTip(
                    f"{display}\nРазмер: {dimensions}\nПуть: {clip_item.image_path}"
                )
            else:
                text = clip_item.text
                item.setToolTip(text if len(text) < 500 else f"{text[:500]}...")
            self._list.addItem(item)

        if self._list.count() > 0:
            if query_active:
                # В режиме поиска первая найденная строка активируется сразу.
                self._list.select_row(0)
            else:
                restored = self._restore_current_item(previous_current_key)
                if not restored:
                    self._list.select_row(0)
        self._refresh_item_size_hints()
        if query_active:
            self._restore_scroll_position(0)
        else:
            self._restore_scroll_position(previous_scroll_value)

    def _filtered_items(self) -> list[ClipItem]:
        query = self._search_input.text().strip().casefold()
        if not query:
            return list(self._all_items)
        return [item for item in self._all_items if query in item.search_text().casefold()]

    def show_popup(self, center: bool) -> None:
        self._reset_search_on_open()
        if center:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                rect = screen.availableGeometry()
                x = rect.x() + (rect.width() - self.width()) // 2
                y = rect.y() + (rect.height() - self.height()) // 2
                self.move(x, y)

        self.setStyleSheet(self._popup_stylesheet)
        self.style().polish(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self._focus_first_item_on_open()
        self._list.setFocus()
        self._list.viewport().update()
        self.update()
        QTimer.singleShot(0, self._focus_first_item_on_open)

    def keyPressEvent(self, event) -> None:
        if (
            event.modifiers() == Qt.KeyboardModifier.NoModifier
            and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        ):
            self._step_tabs(-1 if event.key() == Qt.Key.Key_Left else 1)
            return
        if event.matches(QKeySequence.StandardKey.Find):
            self._activate_search()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)

    def _step_tabs(self, delta: int) -> None:
        if delta == 0:
            return
        self._tab_bar.stepVisible(delta)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_item_size_hints()
        self._sync_add_tab_button_size()

    def _sync_add_tab_button_size(self) -> None:
        target_size = self._tab_bar.overflowButtonTargetSize()
        self._add_tab_button.setFixedSize(target_size)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.escape_pressed.emit()
        event.accept()

    def _setup_list(self) -> None:
        self._list.setItemDelegate(
            ClipItemDelegate(
                parent=self._list,
                max_preview_lines=self._max_preview_lines,
                row_vertical_padding=self._row_vertical_padding,
            )
        )
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setViewMode(QListView.ViewMode.ListMode)
        self._list.setFlow(QListView.Flow.TopToBottom)
        self._list.setWrapping(False)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setWordWrap(True)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setSpacing(4)
        self._list.setUniformItemSizes(False)

    def _refresh_item_size_hints(self) -> None:
        width = self._row_width()
        for index in range(self._list.count()):
            item = self._list.item(index)
            item.setSizeHint(QSize(width, self._item_height(item)))

    def _row_width(self) -> int:
        return max(120, self._list.viewport().width() - 8)

    def _item_height(self, item: QListWidgetItem) -> int:
        delegate = self._list.itemDelegate()
        index = self._list.indexFromItem(item)
        if delegate is None or not index.isValid():
            return 44

        option = QStyleOptionViewItem()
        option.initFrom(self._list)
        option.rect = QRect(0, 0, self._row_width(), 0)
        size_hint = delegate.sizeHint(option, index)
        return max(44, size_hint.height())

    def _current_item_key(self) -> str | None:
        current_item = self._list.currentItem()
        if current_item is None:
            return None
        value = current_item.data(ROLE_ITEM_KEY)
        if isinstance(value, str):
            return value
        return None

    def _restore_current_item(self, item_key: str | None) -> bool:
        if item_key is None:
            return False
        for index in range(self._list.count()):
            item = self._list.item(index)
            value = item.data(ROLE_ITEM_KEY)
            if isinstance(value, str) and value == item_key:
                self._list.setCurrentRow(index)
                return True
        return False

    def _restore_scroll_position(self, scroll_value: int) -> None:
        scrollbar = self._list.verticalScrollBar()
        target_value = max(scrollbar.minimum(), min(scroll_value, scrollbar.maximum()))
        scrollbar.setValue(target_value)

        # Повторно применяем значение после перерасчета геометрии элементов.
        QTimer.singleShot(0, lambda value=target_value: self._set_vertical_scroll(value))

    def _set_vertical_scroll(self, value: int) -> None:
        scrollbar = self._list.verticalScrollBar()
        target_value = max(scrollbar.minimum(), min(value, scrollbar.maximum()))
        scrollbar.setValue(target_value)

    def _show_search_fields(self) -> None:
        self._tab_search_input.show()

    def _set_search_tab_cycle_enabled(self, enabled: bool) -> None:
        state = bool(enabled)
        self._search_tab_cycle_enabled = state
        self._search_input.set_tab_switch_enabled(state)
        self._tab_search_input.set_tab_switch_enabled(state)

    def _activate_search(self) -> None:
        self._set_search_tab_cycle_enabled(True)
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _on_search_text_changed(self, value: str) -> None:
        self._render_filtered_items()
        if value.strip() and self._list.count() > 0:
            # После ввода символа первая найденная строка должна быть активной сразу.
            QTimer.singleShot(0, lambda: self._list.select_row(0))

    def _on_search_escape_pressed(self) -> None:
        if self._search_input.text():
            self._search_input.clear()
            return
        if self._tab_search_input.text():
            self._tab_search_input.clear()
            self._tab_search_input.setFocus()
            return
        self._tab_search_input.hide()
        self._set_search_tab_cycle_enabled(False)
        self._tab_search_match_index = None
        self._list.setFocus()

    def _on_tab_search_text_changed(self, value: str) -> None:
        if value and not self._tab_search_input.isVisible():
            self._show_search_fields()
        self._tab_search_match_index = self._resolve_tab_search_match_index(value)

    def _on_tab_search_escape_pressed(self) -> None:
        if self._tab_search_input.text():
            self._tab_search_input.clear()
            return
        if self._search_input.text():
            self._search_input.clear()
            self._search_input.setFocus()
            return
        self._tab_search_input.hide()
        self._set_search_tab_cycle_enabled(False)
        self._tab_search_match_index = None
        self._list.setFocus()

    def _focus_tab_search_input(self) -> None:
        if not self._search_tab_cycle_enabled:
            return
        self._show_search_fields()
        self._tab_search_input.setFocus()
        self._tab_search_input.selectAll()

    def _focus_clip_search_input(self) -> None:
        if not self._search_tab_cycle_enabled:
            return
        self._show_search_fields()
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _focus_list_from_search(self) -> None:
        if self._list.count() <= 0:
            return
        current_row = self._list.currentRow()
        if current_row < 0:
            target_row = 0
        elif current_row < self._list.count() - 1:
            target_row = current_row + 1
        else:
            target_row = current_row
        self._list.select_row(target_row)
        self._list.setFocus()

    def _choose_current_from_search(self) -> None:
        if self._list.count() <= 0:
            return
        current_item = self._list.currentItem()
        if current_item is None:
            self._list.select_row(0)
            current_item = self._list.currentItem()
        if current_item is None:
            return
        item_key = current_item.data(ROLE_ITEM_KEY)
        self.item_chosen.emit(str(item_key), False)

    def _choose_tab_from_search(self) -> None:
        match_index = self._tab_search_match_index
        if match_index is None:
            match_index = self._resolve_tab_search_match_index(self._tab_search_input.text())
        if match_index is None:
            return

        tab_name = self._tab_bar.tabText(match_index).strip()
        if tab_name:
            self._tab_bar.setPreferredOverflowTabName(tab_name)
        self._tab_bar.setCurrentIndex(match_index)

    def _resolve_tab_search_match_index(self, query: str) -> int | None:
        prepared = query.strip().casefold()
        if not prepared:
            return None

        exact_index: int | None = None
        prefix_index: int | None = None
        contains_index: int | None = None

        for index in range(self._tab_bar.count()):
            name = self._tab_bar.tabText(index).strip()
            if not name:
                continue
            normalized = name.casefold()
            if normalized == prepared:
                exact_index = index
                break
            if prefix_index is None and normalized.startswith(prepared):
                prefix_index = index
            if contains_index is None and prepared in normalized:
                contains_index = index

        if exact_index is not None:
            return exact_index
        if prefix_index is not None:
            return prefix_index
        return contains_index

    def _reset_search_on_open(self) -> None:
        if self._search_input.text():
            blocked = self._search_input.blockSignals(True)
            self._search_input.clear()
            self._search_input.blockSignals(blocked)
            self._render_filtered_items()
        if self._tab_search_input.text():
            blocked = self._tab_search_input.blockSignals(True)
            self._tab_search_input.clear()
            self._tab_search_input.blockSignals(blocked)
        self._tab_search_match_index = None
        self._set_search_tab_cycle_enabled(False)
        self._tab_search_input.hide()

    def _on_index_input_changed(self, value: str) -> None:
        self._index_input_view.setText(value)

    def _on_tab_bar_changed(self, index: int) -> None:
        if index < 0:
            return
        tab_name = self._tab_bar.tabText(index).strip()
        if tab_name:
            self.tab_changed.emit(tab_name)

    def _on_tab_bar_context_menu(self, pos) -> None:
        tab_index = self._tab_bar.tabAt(pos)
        if tab_index < 0:
            return
        tab_name = self._tab_bar.tabText(tab_index).strip()
        if not tab_name:
            return

        tab_data = self._tab_bar.tabData(tab_index)
        is_system = False
        if isinstance(tab_data, dict):
            is_system = bool(tab_data.get("is_system", False))

        menu = QMenu(self)
        menu.setStyleSheet(self._build_tab_context_menu_stylesheet())
        rename_action = QAction("Переименовать", menu)
        rename_action.setEnabled(not is_system)
        menu.addAction(rename_action)
        chosen = menu.exec(self._tab_bar.mapToGlobal(pos))
        if chosen != rename_action:
            return
        if not rename_action.isEnabled():
            return
        self._show_tab_rename_dialog(tab_name)

    def _show_tab_rename_dialog(self, source_name: str) -> None:
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Переименование вкладки")
        dialog.setLabelText("Новое название вкладки:")
        dialog.setTextValue(source_name)
        dialog.setOkButtonText("OK")
        dialog.setCancelButtonText("Отмена")
        dialog.setStyleSheet(self._build_dialog_stylesheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target_name = dialog.textValue().strip()
        if not target_name:
            return
        self.tab_rename_requested.emit(source_name, target_name)

    def _on_add_tab_clicked(self) -> None:
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Новая вкладка")
        dialog.setLabelText("Название вкладки:")
        dialog.setTextValue("")
        dialog.setOkButtonText("OK")
        dialog.setCancelButtonText("Отмена")
        dialog.setStyleSheet(self._build_dialog_stylesheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        prepared = dialog.textValue().strip()
        if not prepared:
            return
        self.tab_create_requested.emit(prepared)

    def show_tab_error(self, message: str) -> None:
        QMessageBox.warning(self, "FastClip", message)

    @staticmethod
    def _build_popup_stylesheet() -> str:
        return """
            QWidget#popupRoot {
                background: #282C34;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                border-radius: 12px;
            }
            QWidget#popupRoot QListWidget {
                background: #21252B;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                border-radius: 10px;
                padding: 4px;
            }
            QWidget#popupRoot QScrollBar:vertical {
                background: #1C2027;
                width: 12px;
                margin: 2px;
                border-radius: 6px;
            }
            QWidget#popupRoot QScrollBar::handle:vertical {
                background: #3B414D;
                min-height: 28px;
                border-radius: 6px;
            }
            QWidget#popupRoot QScrollBar::handle:vertical:hover {
                background: #4A5160;
            }
            QWidget#popupRoot QScrollBar::add-line:vertical,
            QWidget#popupRoot QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }
            QWidget#popupRoot QScrollBar::add-page:vertical,
            QWidget#popupRoot QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QWidget#popupRoot QScrollBar:horizontal {
                background: #1C2027;
                height: 12px;
                margin: 2px;
                border-radius: 6px;
            }
            QWidget#popupRoot QScrollBar::handle:horizontal {
                background: #3B414D;
                min-width: 28px;
                border-radius: 6px;
            }
            QWidget#popupRoot QScrollBar::handle:horizontal:hover {
                background: #4A5160;
            }
            QWidget#popupRoot QScrollBar::add-line:horizontal,
            QWidget#popupRoot QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
                border: none;
            }
            QWidget#popupRoot QScrollBar::add-page:horizontal,
            QWidget#popupRoot QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            QWidget#popupRoot QListWidget::item {
                background: #2C313C;
                border: 1px solid #3B414D;
                border-radius: 6px;
                padding: 10px 12px;
                margin: 3px 2px;
            }
            QWidget#popupRoot QListWidget::item:selected {
                background: #1E3A5F;
                color: #ABB2BF;
                border: 1px solid #2A4B75;
            }
            QWidget#popupRoot QPushButton {
                background: #3E5F8A;
                color: #FFFFFF;
                border: 1px solid #2F4D73;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QWidget#popupRoot QPushButton:hover {
                background: #4A74A8;
            }
            QWidget#popupRoot QPushButton:pressed {
                background: #2F4D73;
            }
            QWidget#popupRoot QPushButton:disabled {
                background: #3E4451;
                border: 1px solid #3B414D;
            }
            QWidget#popupRoot QPushButton#dangerButton {
                background: #BF8255;
                border: 1px solid #A86E43;
            }
            QWidget#popupRoot QPushButton#dangerButton:hover {
                background: #A86E43;
            }
            QWidget#popupRoot QPushButton#dangerButton:pressed {
                background: #8F5D38;
            }
            QWidget#popupRoot QPushButton#addTabButton {
                min-width: 28px;
                padding: 2px 0;
            }
            QWidget#popupRoot QToolButton#tabOverflowButton {
                color: #ABB2BF;
                border: 1px solid #3B414D;
                border-radius: 8px;
                background: #252C38;
                padding: 4px 10px;
                font-size: 12px;
            }
            QWidget#popupRoot QToolButton#tabOverflowButton:hover {
                color: #FFFFFF;
                background: #2D3644;
            }
            QWidget#popupRoot QToolButton#tabOverflowButton::menu-indicator {
                image: none;
                width: 0px;
            }
            QWidget#popupRoot QLineEdit {
                background: #21252B;
                color: #3AE2CE;
                placeholder-text-color: #3AE2CE;
                border: 1px solid #3E4451;
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QWidget#popupRoot QLineEdit:disabled {
                color: #3AE2CE;
            }
            QWidget#popupRoot QTabBar::tab {
                background: #252C38;
                color: #ABB2BF;
                border: 1px solid #3B414D;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 6px 12px;
                margin-right: 4px;
                min-width: 36px;
            }
            QWidget#popupRoot QTabBar::tab:selected {
                background: #1E3A5F;
                color: #3AE2CE;
                border: 1px solid #2A4B75;
            }
            QWidget#popupRoot QTabBar::tab:!selected {
                margin-top: 2px;
            }
            """

    @staticmethod
    def _build_tab_context_menu_stylesheet() -> str:
        return """
            QMenu {
                background-color: #282C34;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                border-radius: 6px;
                padding: 7px 16px;
                margin: 2px 0;
            }
            QMenu::item:selected {
                background-color: #1E3A5F;
                color: #FFFFFF;
            }
            QMenu::item:disabled {
                color: #5A6475;
                background-color: transparent;
            }
        """

    @staticmethod
    def _build_dialog_stylesheet() -> str:
        return """
            QInputDialog {
                background: #282C34;
                color: #ABB2BF;
            }
            QInputDialog QLabel {
                color: #ABB2BF;
            }
            QInputDialog QLineEdit {
                background: #21252B;
                color: #ABB2BF;
                border: 1px solid #3E4451;
                border-radius: 8px;
                padding: 6px 10px;
            }
            QInputDialog QPushButton {
                background: #3E5F8A;
                color: #FFFFFF;
                border: 1px solid #2F4D73;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 700;
                min-width: 80px;
            }
            QInputDialog QPushButton:hover {
                background: #4A74A8;
            }
            QInputDialog QPushButton:pressed {
                background: #2F4D73;
            }
            """

    @staticmethod
    def _resolve_image_path(relative_path: str) -> str:
        prepared = relative_path.strip()
        if not prepared:
            return ""
        path = Path(prepared)
        if path.is_absolute():
            return str(path)
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parents[2]
        return str((base_dir / path).resolve())

    def _focus_first_item_on_open(self) -> None:
        if self._list.count() <= 0:
            self._set_vertical_scroll(0)
            return

        self._list.select_row(0)
        self._set_vertical_scroll(0)
        first_item = self._list.item(0)
        if first_item is not None:
            self._list.scrollToItem(
                first_item,
                QAbstractItemView.ScrollHint.PositionAtTop,
            )

    @staticmethod
    def _to_preview(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
