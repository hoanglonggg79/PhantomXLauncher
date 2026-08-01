"""
PhantomX Launcher - Entry point
Run: python main.py
"""

from __future__ import annotations

import sys
import platform

from loguru import logger

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from core import APP_NAME, APP_VERSION, ICON_FILE
from ui_tabs import DARK_QSS
from main_window import MainWindow


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger.info(
        f"Python {sys.version}  |  Platform: {platform.system()} {platform.machine()}"
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(DARK_QSS)

    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        app.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    window = MainWindow()
    window.show()

    logger.info("UI shown — entering event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()
    main()
