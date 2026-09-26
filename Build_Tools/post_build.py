# -*- coding: utf-8 -*-
"""Post-build stage for the FastClip PyInstaller onedir release."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "FastClip"
RUNTIME_MANIFEST_FILENAME = "RUNTIME_MANIFEST.json"

EXTRA_ROOT_FILES = (
    "VERSION",
    "logo.ico",
    "LICENSE",
)
EXTRA_DIRECTORIES: tuple[tuple[str, str], ...] = ()
COPY_SETTINGS_JSON = False

RUNTIME_MANIFEST_PACKAGES = (
    "PySide6-Essentials",
    "shiboken6",
    "PyInstaller",
)


def get_installed_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception as exc:
        print(f"[ERROR] Failed to remove {path}: {exc}")


def copy_file_if_exists(source: Path, target: Path) -> bool:
    if not source.is_file():
        print(f"[SKIP] File not found: {source.name}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"[OK] Copied file: {source.name}")
    return True


def copy_directory_if_exists(source: Path, target: Path) -> bool:
    if not source.is_dir():
        print(f"[SKIP] Directory not found: {source.name}")
        return False
    if target.exists():
        shutil.rmtree(target, onerror=remove_readonly)
    shutil.copytree(source, target)
    print(f"[OK] Copied directory: {source.name} -> {target}")
    return True


def scan_qt_runtime(runtime_root: Path) -> dict[str, object]:
    if not runtime_root.exists():
        return {
            "scan_status": "target_missing",
            "scan_root": "_internal",
            "qt_dlls": [],
            "qt_plugin_directories": [],
        }

    qt_dlls: list[str] = []
    plugin_directories: set[str] = set()

    for root, dirs, files in os.walk(runtime_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(runtime_root)
        rel_root_text = rel_root.as_posix()

        for filename in files:
            if filename.startswith("Qt") and filename.lower().endswith(".dll"):
                qt_dlls.append((rel_root / filename).as_posix())

        if rel_root_text.lower().endswith("plugins") or rel_root_text == ".":
            for dirname in dirs:
                if dirname.lower() in {
                    "platforms",
                    "imageformats",
                    "styles",
                    "iconengines",
                    "tls",
                }:
                    plugin_directories.add((rel_root / dirname).as_posix())

    return {
        "scan_status": "detected" if qt_dlls or plugin_directories else "no_runtime_detected",
        "scan_root": "_internal",
        "qt_dlls": sorted(qt_dlls),
        "qt_plugin_directories": sorted(plugin_directories),
    }


def build_runtime_manifest(project_root: Path, target_dir: Path) -> dict[str, object]:
    version_path = project_root / "VERSION"
    release_version = None
    if version_path.is_file():
        release_version = version_path.read_text(encoding="utf-8").strip() or None

    packages = {
        package_name: get_installed_version(package_name)
        for package_name in RUNTIME_MANIFEST_PACKAGES
    }

    return {
        "manifest_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "application": {
            "name": APP_NAME,
            "release_version": release_version,
        },
        "build_environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "pyinstaller_version": packages.get("PyInstaller"),
        },
        "bundled_python_packages": packages,
        "qt_runtime": scan_qt_runtime(target_dir),
    }


def write_runtime_manifest(project_root: Path, target_dir: Path) -> None:
    manifest = build_runtime_manifest(project_root, target_dir)
    manifest_path = target_dir / RUNTIME_MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] Created {RUNTIME_MANIFEST_FILENAME}")


def cleanup_temp_dirs(script_dir: Path, project_root: Path, final_app_dir: Path) -> None:
    for folder in (
        script_dir / "build",
        script_dir / "dist",
        script_dir / "__pycache__",
        project_root / "build",
        project_root / "dist",
        project_root / "__pycache__",
        final_app_dir / "__pycache__",
    ):
        if folder.exists():
            shutil.rmtree(folder, onerror=remove_readonly)
            print(f"[OK] Removed temp directory: {folder}")


def main() -> int:
    print("=" * 60)
    print(f"POST-BUILD: {APP_NAME}")
    print("=" * 60)

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    dist_app_dir = script_dir / "dist" / APP_NAME
    final_app_dir = project_root / APP_NAME

    if not dist_app_dir.is_dir():
        print(f"[ERROR] Build directory not found: {dist_app_dir}")
        return 1

    for filename in EXTRA_ROOT_FILES:
        copy_file_if_exists(project_root / filename, dist_app_dir / filename)

    if COPY_SETTINGS_JSON:
        copy_file_if_exists(project_root / "settings.json", dist_app_dir / "settings.json")

    for source_name, target_name in EXTRA_DIRECTORIES:
        copy_directory_if_exists(project_root / source_name, dist_app_dir / target_name)

    if final_app_dir.exists():
        shutil.rmtree(final_app_dir, onerror=remove_readonly)
        print(f"[OK] Removed old directory: {final_app_dir}")

    shutil.move(str(dist_app_dir), str(final_app_dir))
    print(f"[OK] Moved build to: {final_app_dir}")

    write_runtime_manifest(project_root, final_app_dir)
    cleanup_temp_dirs(script_dir, project_root, final_app_dir)

    print("=" * 60)
    print(f"DONE: {final_app_dir}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
