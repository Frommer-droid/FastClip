from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class AutoStartService:
    def __init__(self, app_name: str = "FastClip") -> None:
        appdata = os.getenv("APPDATA", "")
        if not appdata:
            appdata = str(Path.home() / "AppData" / "Roaming")
        self._app_name = app_name
        self._startup_dir = (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        self._shortcut_path = self._startup_dir / f"{self._app_name}.lnk"

    def is_enabled(self) -> bool:
        return self._shortcut_path.exists()

    def set_enabled(self, enabled: bool) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Автозапуск поддерживается только на Windows.")
        if enabled:
            self._create_shortcut()
            return
        self._remove_shortcut()

    def _create_shortcut(self) -> None:
        self._startup_dir.mkdir(parents=True, exist_ok=True)
        target_path, arguments, working_directory, icon_location = (
            self._resolve_shortcut_fields()
        )

        command = self._build_shortcut_command(
            shortcut_path=str(self._shortcut_path),
            target_path=target_path,
            arguments=arguments,
            working_directory=working_directory,
            icon_location=icon_location,
        )
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=self._hidden_startup_info(),
            creationflags=self._no_window_creation_flags(),
        )
        if result.returncode == 0:
            return

        details = (result.stderr or result.stdout or "Неизвестная ошибка").strip()
        raise RuntimeError(details)

    def _remove_shortcut(self) -> None:
        if self._shortcut_path.exists():
            self._shortcut_path.unlink()

    def _resolve_shortcut_fields(self) -> tuple[str, str, str, str]:
        icon_location = self._resolve_icon_location()
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable).resolve()
            return (
                str(executable),
                "",
                str(executable.parent),
                icon_location,
            )

        project_root = Path(__file__).resolve().parents[2]
        entry_script = project_root / "fastclip.pyw"
        python_executable = self._resolve_dev_python_executable()
        return (
            str(python_executable),
            f'"{entry_script}"',
            str(project_root),
            icon_location,
        )

    def _resolve_icon_location(self) -> str:
        if getattr(sys, "frozen", False):
            root_dir = Path(sys.executable).resolve().parent
        else:
            root_dir = Path(__file__).resolve().parents[2]
        icon_path = root_dir / "logo.ico"
        if icon_path.exists():
            return str(icon_path)
        return str(Path(sys.executable).resolve())

    def _build_shortcut_command(
        self,
        shortcut_path: str,
        target_path: str,
        arguments: str,
        working_directory: str,
        icon_location: str,
    ) -> str:
        quoted_shortcut = self._quote_ps(shortcut_path)
        quoted_target = self._quote_ps(target_path)
        quoted_arguments = self._quote_ps(arguments)
        quoted_working_dir = self._quote_ps(working_directory)
        quoted_icon = self._quote_ps(icon_location)

        return (
            "$shell = New-Object -ComObject WScript.Shell; "
            f"$shortcut = $shell.CreateShortcut({quoted_shortcut}); "
            f"$shortcut.TargetPath = {quoted_target}; "
            f"$shortcut.Arguments = {quoted_arguments}; "
            f"$shortcut.WorkingDirectory = {quoted_working_dir}; "
            f"$shortcut.IconLocation = {quoted_icon}; "
            "$shortcut.Save();"
        )

    @staticmethod
    def _quote_ps(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _hidden_startup_info() -> subprocess.STARTUPINFO | None:
        if sys.platform != "win32":
            return None
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = 0
        return startup_info

    @staticmethod
    def _no_window_creation_flags() -> int:
        if sys.platform != "win32":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))

    @staticmethod
    def _resolve_dev_python_executable() -> Path:
        python_executable = Path(sys.executable).resolve()
        if sys.platform != "win32":
            return python_executable
        if python_executable.name.lower() != "python.exe":
            return python_executable

        pythonw_executable = python_executable.with_name("pythonw.exe")
        if pythonw_executable.exists():
            return pythonw_executable
        return python_executable

