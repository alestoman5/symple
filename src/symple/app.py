"""Application entry point."""
from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication

    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Symple")
    app.setOrganizationName("Symple")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow()
    win.show()
    args = [a for a in sys.argv[1:] if a.endswith(".syw")]
    if args:
        win.open_file(args[0])
    return app.exec()
