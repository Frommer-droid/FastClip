from __future__ import annotations

from dataclasses import dataclass


CLIP_KIND_TEXT = "text"
CLIP_KIND_IMAGE = "image"


@dataclass(slots=True)
class ClipItem:
    key: str = ""
    kind: str = CLIP_KIND_TEXT
    text: str = ""
    image_path: str = ""
    image_name: str = ""
    image_width: int = 0
    image_height: int = 0
    pinned: bool = False
    note: str = ""

    def is_image(self) -> bool:
        return self.kind == CLIP_KIND_IMAGE

    def preview_title(self) -> str:
        if self.is_image():
            if self.image_name.strip():
                return self.image_name.strip()
            if self.image_width > 0 and self.image_height > 0:
                return f"Изображение {self.image_width}x{self.image_height}"
            return "Изображение"
        return self.text

    def search_text(self) -> str:
        if self.is_image():
            return f"{self.preview_title()} {self.image_name} {self.image_path} {self.note}".strip()
        return f"{self.text} {self.note}".strip()

