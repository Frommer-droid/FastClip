from __future__ import annotations

import hashlib
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from app.config.constants import CLIP_IMAGES_DIR

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StoredImage:
    relative_path: str
    width: int
    height: int


class ClipImageService:
    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            self._root_dir = Path(sys.executable).resolve().parent
        else:
            self._root_dir = Path(__file__).resolve().parents[2]
        self._images_dir = self._root_dir / CLIP_IMAGES_DIR
        self._exports_dir = self._images_dir / "_paste_exports"
        self._images_dir.mkdir(parents=True, exist_ok=True)

    def save_image(self, image: QImage) -> StoredImage | None:
        if image.isNull():
            return None

        png_data = self._encode_png(image)
        if png_data is None:
            return None

        digest = hashlib.sha256(png_data).hexdigest()
        filename = f"{digest}.png"
        full_path = self._images_dir / filename
        if not full_path.exists():
            full_path.write_bytes(png_data)

        relative_path = full_path.relative_to(self._root_dir).as_posix()
        return StoredImage(
            relative_path=relative_path,
            width=max(0, image.width()),
            height=max(0, image.height()),
        )

    def load_image(self, relative_path: str) -> QImage | None:
        resolved = self.resolve_path(relative_path)
        if resolved is None or not resolved.exists() or not resolved.is_file():
            return None
        image = QImage(str(resolved))
        if image.isNull():
            return None
        return image

    def export_for_clipboard(
        self,
        relative_path: str,
        image: QImage,
        image_name: str,
    ) -> Path | None:
        if image.isNull():
            return None

        source_path = self.resolve_path(relative_path)
        source_stem = source_path.stem if source_path is not None else ""
        export_dir_name = self._export_dir_name(source_stem=source_stem, image=image)
        export_dir = self._exports_dir / export_dir_name
        export_dir.mkdir(parents=True, exist_ok=True)

        fallback_name = source_path.name if source_path is not None else "image.png"
        export_name = self._prepare_export_file_name(image_name, fallback_name=fallback_name)
        export_path = export_dir / export_name
        if image.save(str(export_path)):
            logger.info(
                "export_for_clipboard relative_path=%s image_name=%r export_path=%s",
                relative_path,
                image_name,
                export_path,
            )
            return export_path

        fallback_path = export_dir / self._prepare_export_file_name(
            Path(export_name).stem,
            fallback_name="image.png",
        )
        if image.save(str(fallback_path), "PNG"):
            logger.info(
                "export_for_clipboard fallback relative_path=%s image_name=%r export_path=%s",
                relative_path,
                image_name,
                fallback_path,
            )
            return fallback_path
        logger.error(
            "export_for_clipboard failed relative_path=%s image_name=%r export_dir=%s",
            relative_path,
            image_name,
            export_dir,
        )
        return None

    def resolve_path(self, relative_path: str) -> Path | None:
        prepared = relative_path.strip()
        if not prepared:
            return None
        path = Path(prepared)
        if path.is_absolute():
            return path
        return (self._root_dir / path).resolve()

    def cleanup_unreferenced(self, referenced_paths: set[str]) -> None:
        referenced = {value.strip().casefold() for value in referenced_paths if value.strip()}
        referenced_stems = {
            Path(value.strip()).stem.casefold()
            for value in referenced_paths
            if value.strip()
        }
        for candidate in self._images_dir.glob("*.png"):
            relative = candidate.relative_to(self._root_dir).as_posix()
            if relative.casefold() in referenced:
                continue
            try:
                candidate.unlink()
            except OSError:
                continue
        self._cleanup_export_dirs(referenced_stems)

    def _cleanup_export_dirs(self, referenced_stems: set[str]) -> None:
        if not self._exports_dir.exists():
            return
        for candidate in self._exports_dir.iterdir():
            if not candidate.is_dir():
                continue
            if candidate.name.casefold() in referenced_stems:
                continue
            try:
                shutil.rmtree(candidate)
            except OSError:
                continue

    @staticmethod
    def _encode_png(image: QImage) -> bytes | None:
        buffer_data = QByteArray()
        buffer = QBuffer(buffer_data)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return None
        try:
            if not image.save(buffer, "PNG"):
                return None
            return bytes(buffer_data)
        finally:
            buffer.close()

    @classmethod
    def _export_dir_name(cls, *, source_stem: str, image: QImage) -> str:
        prepared = cls._sanitize_file_stem(source_stem)
        if prepared:
            return prepared

        png_data = cls._encode_png(image) or b""
        return hashlib.sha256(png_data).hexdigest()

    @classmethod
    def _prepare_export_file_name(cls, image_name: str, *, fallback_name: str) -> str:
        prepared = cls._sanitize_file_name(image_name)
        if not prepared:
            prepared = cls._sanitize_file_name(fallback_name)
        if not prepared:
            prepared = "image.png"

        if not Path(prepared).suffix:
            prepared = f"{prepared}.png"

        suffix = Path(prepared).suffix
        stem = cls._sanitize_file_stem(Path(prepared).stem) or "image"
        max_stem_length = max(1, 180 - len(suffix))
        return f"{stem[:max_stem_length]}{suffix}"

    @classmethod
    def _sanitize_file_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return ""
        name = Path(value.strip()).name.strip(" .")
        if not name:
            return ""
        sanitized = "".join("_" if cls._is_invalid_file_char(char) else char for char in name)
        sanitized = " ".join(sanitized.split()).strip(" .")
        if not sanitized:
            return ""
        if cls._is_reserved_windows_name(Path(sanitized).stem):
            sanitized = f"_{sanitized}"
        return sanitized

    @classmethod
    def _sanitize_file_stem(cls, value: str) -> str:
        if not isinstance(value, str):
            return ""
        sanitized = "".join("_" if cls._is_invalid_file_char(char) else char for char in value)
        sanitized = " ".join(sanitized.split()).strip(" .")
        if cls._is_reserved_windows_name(sanitized):
            sanitized = f"_{sanitized}"
        return sanitized

    @staticmethod
    def _is_invalid_file_char(char: str) -> bool:
        return ord(char) < 32 or char in '<>:"/\\|?*'

    @staticmethod
    def _is_reserved_windows_name(stem: str) -> bool:
        return stem.casefold() in {
            "con",
            "prn",
            "aux",
            "nul",
            "com1",
            "com2",
            "com3",
            "com4",
            "com5",
            "com6",
            "com7",
            "com8",
            "com9",
            "lpt1",
            "lpt2",
            "lpt3",
            "lpt4",
            "lpt5",
            "lpt6",
            "lpt7",
            "lpt8",
            "lpt9",
        }

