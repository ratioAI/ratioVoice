"""Programmstart."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()  # nötig für die gepackte .exe (PyInstaller)
    from PySide6.QtWidgets import QApplication

    from .config import APP_NAME
    from .ui.main_window import MainWindow
    from .ui.theme import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
