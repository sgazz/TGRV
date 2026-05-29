from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from touchprint_lab.analyzer.dataset import DatasetManager

logger = logging.getLogger(__name__)


class IngestionService(QObject):
    sessionImported = pyqtSignal(object)

    def __init__(self, dataset_manager: DatasetManager, incoming_dir: Path):
        super().__init__()
        self.dataset_manager = dataset_manager
        self.incoming_dir = incoming_dir
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(str(self.incoming_dir))
        self.watcher.directoryChanged.connect(self._schedule_scan)

        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.scan_now)
        self.timer.start()

        self._scan_pending = False

    def scan_now(self) -> None:
        imported = self.dataset_manager.scan_incoming()
        for session in imported:
            self.sessionImported.emit(session)

    def _schedule_scan(self) -> None:
        if self._scan_pending:
            return
        self._scan_pending = True
        QTimer.singleShot(400, self._perform_scheduled_scan)

    def _perform_scheduled_scan(self) -> None:
        self._scan_pending = False
        self.scan_now()

