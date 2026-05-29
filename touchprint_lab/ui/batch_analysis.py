from __future__ import annotations

import json
import logging
from typing import Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.analyzer.batch import AnalysisFilters, BatchAnalysisReport, BatchAnalyzer
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.plots.batch_plots import BatchPlotsWidget
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class BatchAnalysisWidget(QWidget):
    def __init__(self, paths: TouchprintPaths, parent: QWidget | None = None):
        super().__init__(parent)
        self.paths = paths
        self.analyzer = BatchAnalyzer()
        self.sessions: list[TouchSessionRecord] = []
        self.current_session: TouchSessionRecord | None = None
        self.current_report: BatchAnalysisReport | None = None

        self.user_filter = QLineEdit()
        self.user_filter.setPlaceholderText("user_01,user_02")
        self.device_filter = QLineEdit()
        self.device_filter.setPlaceholderText("iPhone,iPad")
        self.session_type_filter = QLineEdit()
        self.session_type_filter.setPlaceholderText("tap,pin,signature")
        self.started_after_filter = QLineEdit()
        self.started_after_filter.setPlaceholderText("unix timestamp")
        self.started_before_filter = QLineEdit()
        self.started_before_filter.setPlaceholderText("unix timestamp")
        self.exported_after_filter = QLineEdit()
        self.exported_after_filter.setPlaceholderText("unix timestamp")
        self.exported_before_filter = QLineEdit()
        self.exported_before_filter.setPlaceholderText("unix timestamp")

        self.run_button = QPushButton("Run Analysis")
        self.run_button.clicked.connect(self.run_analysis)
        self.export_button = QPushButton("Export Report")
        self.export_button.clicked.connect(self.export_report)
        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.clicked.connect(self.refresh_data)

        controls = QFormLayout()
        controls.addRow("Users", self.user_filter)
        controls.addRow("Device Types", self.device_filter)
        controls.addRow("Session Types", self.session_type_filter)
        controls.addRow("Started After", self.started_after_filter)
        controls.addRow("Started Before", self.started_before_filter)
        controls.addRow("Exported After", self.exported_after_filter)
        controls.addRow("Exported Before", self.exported_before_filter)

        buttons = QHBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.refresh_button)

        self.status_label = QLabel("Batch analysis idle.")
        self.summary_box = QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(160)

        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.Shape.StyledPanel)
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.addLayout(controls)
        controls_layout.addLayout(buttons)
        controls_layout.addWidget(self.status_label)
        controls_layout.addWidget(QLabel("Analysis Summary"))
        controls_layout.addWidget(self.summary_box)

        self.plots = BatchPlotsWidget()

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(controls_frame)
        root_layout.addWidget(self.plots, 1)

    def set_sessions(self, sessions: list[TouchSessionRecord]) -> None:
        self.sessions = sessions
        self.refresh_data()

    def set_current_session(self, session: TouchSessionRecord | None) -> None:
        self.current_session = session
        self._refresh_plots()

    def refresh_data(self) -> None:
        self.status_label.setText(f"Loaded {len(self.sessions)} sessions for batch analysis.")
        if self.sessions:
            self.run_analysis()
        else:
            self.current_report = None
            self.summary_box.setPlainText("No sessions available for analysis.")
            self.plots.update_report(None, None)

    def run_analysis(self) -> None:
        if not self.sessions:
            self.current_report = None
            self.summary_box.setPlainText("No sessions available for analysis.")
            self.plots.update_report(None, None)
            return

        filters = AnalysisFilters.from_strings(
            user_ids=self.user_filter.text(),
            device_types=self.device_filter.text(),
            session_types=self.session_type_filter.text(),
            started_after=self.started_after_filter.text(),
            started_before=self.started_before_filter.text(),
            exported_after=self.exported_after_filter.text(),
            exported_before=self.exported_before_filter.text(),
        )
        self.current_report = self.analyzer.analyze(self.sessions, filters)
        self._refresh_summary()
        self._refresh_plots()
        self.status_label.setText(
            f"Analyzed {self.current_report.sample_count} sessions, {len(self.current_report.pairwise_rows)} pairwise comparisons."
        )

    def export_report(self) -> None:
        if self.current_report is None:
            self.run_analysis()
        if self.current_report is None:
            return
        exported = self.analyzer.export_report(self.current_report, self.paths.reports)
        self.current_report = exported
        self._refresh_summary()
        self._refresh_plots()
        output_dir = Path(exported.files.get("summaryJson", self.paths.reports)).parent if exported.files else self.paths.reports
        QMessageBox.information(self, "Batch Analysis", f"Report exported to:\n{output_dir}")

    def _refresh_summary(self) -> None:
        if self.current_report is None:
            self.summary_box.setPlainText("No analysis report generated.")
            return
        self.summary_box.setPlainText(json.dumps(self.current_report.summary_dict(), indent=2, sort_keys=True))

    def _refresh_plots(self) -> None:
        self.plots.update_report(self.current_report, self.current_session.session_id if self.current_session else None)
