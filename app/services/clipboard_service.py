from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QMimeData, QUrl
from PySide6.QtGui import QClipboard, QGuiApplication, QImage

from app.models.clip_item import CLIP_KIND_IMAGE, CLIP_KIND_TEXT

logger = logging.getLogger(__name__)

DROPEFFECT_COPY = 1
PREFERRED_DROP_EFFECT_MIME = 'application/x-qt-windows-mime;value="Preferred DropEffect"'

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".ico",
}

@dataclass(slots=True)
class ClipboardPayload:
    kind: str
    text: str = ""
    image: QImage | None = None
    image_name: str = ""


class ClipboardService:
    def __init__(self) -> None:
        self._clipboard = QGuiApplication.clipboard()

    def read_text(self) -> str:
        return self._clipboard.text(QClipboard.Mode.Clipboard)

    def write_text(self, text: str) -> None:
        self._clipboard.setText(text, QClipboard.Mode.Clipboard)

    def write_image(self, image: QImage, file_path: str | Path | None = None) -> None:
        if image.isNull():
            return

        mime = QMimeData()
        mime.setImageData(image)
        file_url = self._file_url(file_path)
        if file_url is not None:
            mime.setUrls([file_url])
            mime.setData(
                PREFERRED_DROP_EFFECT_MIME,
                QByteArray(struct.pack("<I", DROPEFFECT_COPY)),
            )
        self._clipboard.setMimeData(mime, QClipboard.Mode.Clipboard)
        logger.info(
            "write_image has_file_url=%s file_path=%s formats=%s",
            file_url is not None,
            file_path,
            mime.formats(),
        )

    def read_payload(self) -> ClipboardPayload | None:
        mime = self._clipboard.mimeData(QClipboard.Mode.Clipboard)
        if mime is None:
            return None

        urls = mime.urls() if mime.hasUrls() else []
        image_name = self._image_name_from_urls(urls)

        if mime.hasImage():
            image = self._clipboard.image(QClipboard.Mode.Clipboard)
            if not image.isNull():
                return ClipboardPayload(
                    kind=CLIP_KIND_IMAGE,
                    image=image,
                    image_name=image_name,
                )

        if urls:
            image = self._image_from_urls(urls)
            if image is not None and not image.isNull():
                return ClipboardPayload(
                    kind=CLIP_KIND_IMAGE,
                    image=image,
                    image_name=image_name,
                )
            if self._has_local_file_urls(urls):
                return None

        text = self.read_text().strip()
        if text:
            return ClipboardPayload(kind=CLIP_KIND_TEXT, text=text)
        return None

    def connect_data_changed(self, slot) -> None:
        self._clipboard.dataChanged.connect(slot)

    def _image_from_urls(self, urls: list[QUrl]) -> QImage | None:
        for url in urls:
            local_path = self._local_image_path_from_url(url)
            if local_path is None:
                continue
            image = QImage(str(local_path))
            if not image.isNull():
                return image
        return None

    def _image_name_from_urls(self, urls: list[QUrl]) -> str:
        for url in urls:
            local_path = self._local_image_path_from_url(url)
            if local_path is not None:
                return local_path.name.strip()
        return ""

    def _local_image_path_from_url(self, url: QUrl) -> Path | None:
        if not url.isLocalFile():
            return None
        local_path = Path(url.toLocalFile())
        if local_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return None
        return local_path

    def _has_local_file_urls(self, urls: list[QUrl]) -> bool:
        return any(url.isLocalFile() for url in urls)

    def _file_url(self, file_path: str | Path | None) -> QUrl | None:
        if file_path is None:
            return None
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None
        return QUrl.fromLocalFile(str(path))
