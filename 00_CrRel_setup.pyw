# -*- coding: utf-8 -*-
"""Create the FastClip Windows installer with Inno Setup."""

from __future__ import annotations

import os
import shutil
import stat
import string
import subprocess
import tempfile
import time
from pathlib import Path


APP_NAME = "FastClip"
APP_PUBLISHER = "Frommer"
APP_ID = "{{0B60340C-C71C-4CC0-8F26-09AB478B47FA}"

KEEP_FOLDERS = ("_internal",)
REQUIRED_RELEASE_FILES = (
    "VERSION",
    "logo.ico",
    "LICENSE",
    "RUNTIME_MANIFEST.json",
)
RUNTIME_NOISE_FILES = (
    "settings.json",
    "clipboard_history.txt",
    "FastClip.log",
)
RUNTIME_NOISE_DIRS = (
    "clipboard_images",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
)


def resolve_desktop_dir() -> Path:
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    except Exception:
        pass
    return Path.home() / "Desktop"


def iter_fixed_drives() -> list[Path]:
    try:
        import ctypes

        drive_type_fixed = 3
        drives: list[Path] = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) == drive_type_fixed:
                drives.append(Path(root))
        if drives:
            return drives
    except Exception:
        pass
    return [Path("C:/")]


def resolve_default_install_base_dir() -> Path:
    fixed_drives = iter_fixed_drives()
    for drive in fixed_drives:
        if str(drive).upper().startswith("D:"):
            return drive / "Apps"
    for drive in fixed_drives:
        if not str(drive).upper().startswith("C:"):
            return drive / "Apps"
    return Path(r"C:\Apps")


INSTALLER_OUTPUT_DIR = resolve_desktop_dir()
DEFAULT_INSTALL_BASE_DIR = resolve_default_install_base_dir()
PRIVILEGES_REQUIRED = "admin"

ISCC_CANDIDATE_PATHS = (
    os.environ.get("INNO_SETUP_ISCC", ""),
    shutil.which("ISCC.exe") or "",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
)


def find_iscc_path() -> str:
    for path in ISCC_CANDIDATE_PATHS:
        if path and os.path.exists(path):
            return path
    return ""


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as exc:
        print(f"[ERROR] Failed to remove {path}: {exc}")


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


def should_remove_runtime_file(filename: str) -> bool:
    name_lower = filename.lower()
    return (
        name_lower in {item.lower() for item in RUNTIME_NOISE_FILES}
        or name_lower.endswith(".log")
        or ".log." in name_lower
    )


def get_missing_release_items(source_dir: Path, exe_name: str) -> list[str]:
    missing: list[str] = []
    for filename in (*REQUIRED_RELEASE_FILES, exe_name):
        if not (source_dir / filename).is_file():
            missing.append(filename)
    for folder in KEEP_FOLDERS:
        if not (source_dir / folder).is_dir():
            missing.append(folder + "/")
    return missing


def prepare_work_dir(source_dir: Path, work_dir: Path) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir, onerror=remove_readonly)
    shutil.copytree(source_dir, work_dir)

    keep_folders_lower = {folder.lower() for folder in KEEP_FOLDERS}
    runtime_noise_dirs_lower = {folder.lower() for folder in RUNTIME_NOISE_DIRS}
    for item in work_dir.iterdir():
        if item.is_dir():
            item_name = item.name.lower()
            if item_name not in keep_folders_lower or item_name in runtime_noise_dirs_lower:
                shutil.rmtree(item, onerror=remove_readonly)
                print(f"[OK] Removed non-release directory: {item.name}")
        elif item.is_file() and should_remove_runtime_file(item.name):
            item.unlink(missing_ok=True)
            print(f"[OK] Removed runtime file: {item.name}")

    for root, _dirs, files in os.walk(work_dir):
        for filename in files:
            name_lower = filename.lower()
            if name_lower.endswith(".log") or ".log." in name_lower:
                Path(root, filename).unlink(missing_ok=True)


def read_version(project_root: Path) -> str:
    version_path = project_root / "VERSION"
    if version_path.is_file():
        version = version_path.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "0.0.0"


def build_iss_script(
    *,
    version: str,
    exe_name: str,
    work_dir: Path,
    output_dir: Path,
    default_install_dir: Path,
    setup_icon_file: Path | None,
) -> str:
    setup_icon_line = f'SetupIconFile="{setup_icon_file}"' if setup_icon_file else ""
    return f"""; Auto-generated Inno Setup script.

#define MyAppName "{APP_NAME}"
#define MyAppVersion "{version}"
#define MyAppPublisher "{APP_PUBLISHER}"
#define MyAppExeName "{exe_name}"

[Setup]
AppId={APP_ID}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
DefaultDirName="{default_install_dir}"
UsePreviousAppDir=no
DefaultGroupName={{#MyAppName}}
DisableProgramGroupPage=yes
OutputDir="{output_dir}"
OutputBaseFilename={{#MyAppName}}_v{{#MyAppVersion}}_Setup
{setup_icon_line}
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired={PRIVILEGES_REQUIRED}
VersionInfoVersion={{#MyAppVersion}}.0
VersionInfoCompany={{#MyAppPublisher}}
VersionInfoDescription={{#MyAppName}} Setup
VersionInfoProductName={{#MyAppName}}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: checkedonce

[Files]
Source: "{work_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\logo.ico"
Name: "{{group}}\\Удалить {{#MyAppName}}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "Запустить {{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {{#MyAppExeName}}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
"""


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_dir = project_root / APP_NAME
    work_dir = Path(tempfile.mkdtemp(prefix=f"{APP_NAME}_installer_"))
    exe_name = f"{APP_NAME}.exe"
    iscc_path = find_iscc_path()

    if not iscc_path:
        print("[ERROR] ISCC.exe not found. Install Inno Setup or set INNO_SETUP_ISCC.")
        return 1
    if not source_dir.is_dir():
        print(f"[ERROR] Release directory not found: {source_dir}")
        return 1

    missing = get_missing_release_items(source_dir, exe_name)
    if missing:
        print("[ERROR] Release directory is incomplete:")
        for item in missing:
            print(f"- {item}")
        return 1

    kill_process_by_path(exe_name, source_dir)
    prepare_work_dir(source_dir, work_dir)

    version = read_version(project_root)
    setup_icon_file = work_dir / "logo.ico" if (work_dir / "logo.ico").is_file() else None
    iss_content = build_iss_script(
        version=version,
        exe_name=exe_name,
        work_dir=work_dir,
        output_dir=INSTALLER_OUTPUT_DIR,
        default_install_dir=DEFAULT_INSTALL_BASE_DIR / APP_NAME,
        setup_icon_file=setup_icon_file,
    )

    iss_path = Path(tempfile.gettempdir()) / f"{APP_NAME}_installer_temp.iss"
    iss_path.write_text(iss_content, encoding="utf-8-sig")

    try:
        subprocess.run([iscc_path, str(iss_path)], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Inno Setup failed: {exc}")
        return 1
    finally:
        iss_path.unlink(missing_ok=True)
        if work_dir.exists():
            shutil.rmtree(work_dir, onerror=remove_readonly)

    print(f"[OK] Installer ready: {INSTALLER_OUTPUT_DIR / f'{APP_NAME}_v{version}_Setup.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
