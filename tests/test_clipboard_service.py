from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage

from app.models.clip_item import CLIP_KIND_IMAGE
from app.services.clipboard_service import (
    DROPEFFECT_COPY,
    PREFERRED_DROP_EFFECT_MIME,
    ClipboardService,
)


class _FakeClipboard:
    def __init__(self) -> None:
        self.mime_data = None
        self.mode = None

    def setMimeData(self, mime_data, mode) -> None:
        self.mime_data = mime_data
        self.mode = mode

    def mimeData(self, mode):
        self.mode = mode
        return self.mime_data

    def image(self, mode):
        self.mode = mode
        return QImage()


class ClipboardServiceWriteImageTests(unittest.TestCase):
    def test_write_image_includes_bitmap_and_local_file_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "зима.png"
            image_path.write_bytes(b"stored image placeholder")
            clipboard = _FakeClipboard()
            service = ClipboardService.__new__(ClipboardService)
            service._clipboard = clipboard

            service.write_image(self._image(), file_path=image_path)

            self.assertIsNotNone(clipboard.mime_data)
            self.assertTrue(clipboard.mime_data.hasImage())
            self.assertTrue(clipboard.mime_data.hasUrls())
            urls = clipboard.mime_data.urls()
            self.assertEqual(1, len(urls))
            self.assertEqual(image_path.resolve(), Path(urls[0].toLocalFile()).resolve())
            self.assertEqual("зима.png", Path(urls[0].toLocalFile()).name)
            self.assertTrue(clipboard.mime_data.hasFormat(PREFERRED_DROP_EFFECT_MIME))
            self.assertEqual(
                DROPEFFECT_COPY.to_bytes(4, "little"),
                bytes(clipboard.mime_data.data(PREFERRED_DROP_EFFECT_MIME)),
            )

    def test_write_image_keeps_bitmap_when_file_path_is_missing(self) -> None:
        clipboard = _FakeClipboard()
        service = ClipboardService.__new__(ClipboardService)
        service._clipboard = clipboard

        service.write_image(self._image(), file_path=Path("missing.png"))

        self.assertIsNotNone(clipboard.mime_data)
        self.assertTrue(clipboard.mime_data.hasImage())
        self.assertFalse(clipboard.mime_data.hasUrls())
        self.assertFalse(clipboard.mime_data.hasFormat(PREFERRED_DROP_EFFECT_MIME))

    def test_read_payload_preserves_local_image_file_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "Summer photo.png"
            self._image().save(str(image_path), "PNG")
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(str(image_path))])
            clipboard = _FakeClipboard()
            clipboard.mime_data = mime_data
            service = ClipboardService.__new__(ClipboardService)
            service._clipboard = clipboard

            payload = service.read_payload()

            self.assertIsNotNone(payload)
            self.assertEqual(CLIP_KIND_IMAGE, payload.kind)
            self.assertEqual("Summer photo.png", payload.image_name)
            self.assertIsNotNone(payload.image)
            self.assertFalse(payload.image.isNull())

    @staticmethod
    def _image() -> QImage:
        image = QImage(2, 2, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        return image


if __name__ == "__main__":
    unittest.main()
