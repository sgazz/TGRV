from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from touchprint_lab.ui.main_window import MainWindow
from touchprint_lab.utils.logging_config import configure_logging
from touchprint_lab.utils.paths import TouchprintPaths


def main() -> int:
    configure_logging()
    paths = TouchprintPaths.create_default()
    paths.ensure_directories()

    app = QApplication(sys.argv)
    app.setApplicationName("Touchprint Analyzer v1")
    app.setOrganizationName("Touchprint Lab")

    window = MainWindow(paths)
    window.resize(1680, 980)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

