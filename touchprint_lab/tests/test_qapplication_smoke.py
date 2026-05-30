from __future__ import annotations

import unittest

try:
    from PyQt6.QtWidgets import QLabel
except Exception:  # pragma: no cover - optional dependency
    QLabel = None  # type: ignore[assignment]

from touchprint_lab.tests.qt_test_utils import get_or_create_qapplication


@unittest.skipUnless(QLabel is not None, "PyQt6 is not available")
class QApplicationSmokeTests(unittest.TestCase):
    def test_create_label_with_shared_qapplication(self) -> None:
        app = get_or_create_qapplication()
        label = QLabel("touchprint smoke")
        label.close()
        label.deleteLater()
        app.processEvents()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

