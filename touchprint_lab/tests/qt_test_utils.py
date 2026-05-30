from __future__ import annotations

import sys


def get_or_create_qapplication():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app

