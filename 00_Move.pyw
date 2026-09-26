# -*- coding: utf-8 -*-
"""Copy the fresh FastClip portable release to the local portable directory."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path


APP_NAME = "FastClip"
DESTINATION_PARENT = Path(r"D:\Portable_soft")
PRESERVED_RUNTIME_ITEMS = (
    "settings.json",
    "clipboard_history.txt",
    "clipboard_images",
)


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as exc:
        print(f"[ERROR] Failed to remove {path}: {exc}")


def ensure_safe_target(target: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_target = target.resolve() if target.exists() else target.absolute()
    if resolved_target == resolved_parent:
        raise RuntimeError("Target directory matches destination parent.")
    try:
        resolved_target.relative_to(resolved_parent)
    except ValueError as exc:
        raise RuntimeError(f"Unsafe target path: {resolved_target}") from exc


def kill_process_by_path(process_name: str, path_filter: Path) -> None:
    process_name_no_ext = process_name.replace(".exe", "")
    escaped_path = str(path_filter).replace("'", "''")
    ps_command = (
        "powershell -NoProfile -ExecutionPolicy Bypass -Command "
        f"\"$target = [System.IO.Path]::GetFullPath('{escaped_path}'); "
        "if (-not $target.EndsWith([System.IO.Path]::DirectorySeparatorChar)) "
        "{ $target += [System.IO.Path]::DirectorySeparatorChar }; "
        f"Get-Process -Name '{process_name_no_ext}' -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -and "
        "([System.IO.Path]::GetFullPath($_.Path)).StartsWith($target, "
        "[System.StringComparison]::OrdinalIgnoreCase) } | "
        "Stop-Process -Force\""
    )
    for _ in range(3):
        subprocess.run(
            ps_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)


def preserve_runtime_data(source: Path, backup_dir: Path) -> list[str]:
    preserved: list[str] = []
    for name in PRESERVED_RUNTIME_ITEMS:
        item = source / name
        if item.is_file():
            shutil.copy2(item, backup_dir / name)
            preserved.append(name)
        elif item.is_dir():
            shutil.copytree(item, backup_dir / name)
            preserved.append(name)
    return preserved


def restore_runtime_data(backup_dir: Path, destination: Path, names: list[str]) -> None:
    for name in names:
        source = backup_dir / name
        target = destination / name
        if source.is_file():
            shutil.copy2(source, target)
        elif source.is_dir():
            shutil.copytree(source, target)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_folder = project_root / APP_NAME
    target_folder = DESTINATION_PARENT / APP_NAME
    exe_name = f"{APP_NAME}.exe"

    if not source_folder.is_dir():
        print(f"[ERROR] Source release directory not found: {source_folder}")
        return 1

    DESTINATION_PARENT.mkdir(parents=True, exist_ok=True)
    ensure_safe_target(target_folder, DESTINATION_PARENT)

    kill_process_by_path(exe_name, target_folder)
    time.sleep(1)

    backup_dir = Path(tempfile.mkdtemp(prefix=f"{APP_NAME}_runtime_"))
    preserved: list[str] = []
    if target_folder.exists():
        preserved = preserve_runtime_data(target_folder, backup_dir)

    try:
        if target_folder.exists():
            shutil.rmtree(target_folder, onerror=remove_readonly)
            print(f"[OK] Removed old portable directory: {target_folder}")

        shutil.copytree(source_folder, target_folder)
        restore_runtime_data(backup_dir, target_folder, preserved)
        print(f"[OK] Copied portable release: {source_folder} -> {target_folder}")
        if preserved:
            print(f"[OK] Restored runtime data: {', '.join(preserved)}")
    finally:
        shutil.rmtree(backup_dir, onerror=remove_readonly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
