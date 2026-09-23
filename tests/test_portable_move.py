from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_move_module():
    script_path = Path(__file__).resolve().parents[1] / "00_Move.pyw"
    spec = importlib.util.spec_from_file_location("fastclip_portable_move", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Не удалось загрузить 00_Move.pyw")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableMoveRuntimeDataTests(unittest.TestCase):
    def test_runtime_data_is_preserved_and_restored(self) -> None:
        module = _load_move_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_portable = root / "old"
            backup = root / "backup"
            new_portable = root / "new"
            old_portable.mkdir()
            backup.mkdir()
            (old_portable / "settings.json").write_text("{}", encoding="utf-8")
            (old_portable / "clipboard_history.txt").write_text("{}", encoding="utf-8")
            image_dir = old_portable / "clipboard_images"
            image_dir.mkdir()
            (image_dir / "saved.png").write_bytes(b"image")
            new_portable.mkdir()

            preserved = module.preserve_runtime_data(old_portable, backup)
            module.restore_runtime_data(backup, new_portable, preserved)

            self.assertEqual(
                ["settings.json", "clipboard_history.txt", "clipboard_images"],
                preserved,
            )
            self.assertTrue((new_portable / "settings.json").is_file())
            self.assertTrue((new_portable / "clipboard_history.txt").is_file())
            self.assertEqual(b"image", (new_portable / "clipboard_images" / "saved.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
