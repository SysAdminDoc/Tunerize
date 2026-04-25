"""Tunerize entrypoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _bundle_ffmpeg_on_path() -> None:
    try:
        import imageio_ffmpeg
        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffmpeg_dir = str(ffmpeg_exe.parent)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def main() -> int:
    _set_dpi_awareness()
    _bundle_ffmpeg_on_path()

    from PySide6.QtWidgets import QApplication

    from app import __version__
    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_dark_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Tunerize")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SysAdminDoc")
    apply_dark_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
