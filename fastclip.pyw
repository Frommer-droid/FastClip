from __future__ import annotations

import subprocess
import sys
import logging
from pathlib import Path


def _ensure_windowless_venv_runtime() -> None:
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return

    project_dir = Path(__file__).resolve().parent
    scripts_dir = project_dir / ".venv" / "Scripts"
    pythonw_path = scripts_dir / "pythonw.exe"
    if not pythonw_path.exists():
        return

    current_executable = Path(sys.executable).resolve()
    target_executable = pythonw_path.resolve()
    if str(current_executable).casefold() == str(target_executable).casefold():
        return

    subprocess.Popen(
        [str(target_executable), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(project_dir),
        close_fds=True,
    )
    raise SystemExit(0)


if __name__ == "__main__":
    _ensure_windowless_venv_runtime()

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

from app.core.app_controller import AppController
from app.services.logging_service import setup_logging
from app.version import __version__

logger = logging.getLogger(__name__)


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    app_id = "frommer.fastclip.desktop.v1"
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _resolve_app_icon(app: QApplication) -> QIcon:
    logo_path = _runtime_base_dir() / "logo.ico"
    if logo_path.exists():
        return QIcon(str(logo_path))
    return app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)


def _create_application() -> tuple[QApplication, QIcon]:
    app = QApplication(sys.argv)
    app.setApplicationName("FastClip")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    app_icon = _resolve_app_icon(app)
    app.setWindowIcon(app_icon)

    return app, app_icon


def main() -> int:
    log_path = setup_logging()
    logger.info("FastClip starting version=%s executable=%s log_path=%s", __version__, sys.executable, log_path)
    _set_windows_app_id()
    app, app_icon = _create_application()
    controller = AppController(app, app_icon)

    try:
        controller.start()
    except RuntimeError as error:
        logger.exception("FastClip startup failed")
        print(f"Ошибка запуска: {error}")
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
