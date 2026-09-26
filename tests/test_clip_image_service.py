from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QImage

from app.config.constants import CLIP_IMAGES_DIR
from app.services.clip_image_service import ClipImageService


class ClipImageServiceExportTests(unittest.TestCase):
    def test_export_for_clipboard_uses_original_image_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service_for(Path(temp_dir))
            image = self._image()
            stored = service.save_image(image)
            self.assertIsNotNone(stored)

            export_path = service.export_for_clipboard(
                relative_path=stored.relative_path,
                image=image,
                image_name="зима.png",
            )

            self.assertIsNotNone(export_path)
            self.assertEqual("зима.png", export_path.name)
            self.assertTrue(export_path.exists())
            self.assertIn("_paste_exports", export_path.parts)

    def test_export_for_clipboard_adds_png_suffix_when_name_has_no_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service_for(Path(temp_dir))
            image = self._image()
            stored = service.save_image(image)
            self.assertIsNotNone(stored)

            export_path = service.export_for_clipboard(
                relative_path=stored.relative_path,
                image=image,
                image_name="зима",
            )

            self.assertIsNotNone(export_path)
            self.assertEqual("зима.png", export_path.name)

    @staticmethod
    def _service_for(root_dir: Path) -> ClipImageService:
        service = ClipImageService.__new__(ClipImageService)
        service._root_dir = root_dir
        service._images_dir = root_dir / CLIP_IMAGES_DIR
        service._exports_dir = service._images_dir / "_paste_exports"
        service._images_dir.mkdir(parents=True, exist_ok=True)
        return service

    @staticmethod
    def _image() -> QImage:
        image = QImage(2, 2, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        return image


if __name__ == "__main__":
    unittest.main()
