from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.studies import StudyManager, StudyPlan, StudyTemplate
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class StudyLibraryWidget(QWidget):
    def __init__(self, paths: TouchprintPaths, study_manager: StudyManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.paths = paths
        self.study_manager = study_manager
        self.sessions: list[TouchSessionRecord] = []
        self.current_session: TouchSessionRecord | None = None
        self.current_template: StudyTemplate | None = None
        self.current_study: StudyPlan | None = self.study_manager.active_study

        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._handle_template_selection)

        self.study_selector = QComboBox()
        self.study_selector.currentIndexChanged.connect(self._refresh_preview)

        self.participant_id = QLineEdit("participant_01")
        self.start_at = QLineEdit("")
        self.start_at.setPlaceholderText("ISO 8601 or leave blank for now")
        self.seed = QLineEdit("42")
        self.custom_label = QLineEdit("")
        self.custom_label.setPlaceholderText("labelKey=labelValue, anotherKey=value")

        self.create_button = QPushButton("Create Study")
        self.create_button.clicked.connect(self.create_study)
        self.start_button = QPushButton("Start Study")
        self.start_button.clicked.connect(self.start_study)
        self.pause_button = QPushButton("Pause Study")
        self.pause_button.clicked.connect(self.pause_study)
        self.resume_button = QPushButton("Resume Study")
        self.resume_button.clicked.connect(self.resume_study)
        self.clone_button = QPushButton("Clone Study")
        self.clone_button.clicked.connect(self.clone_study)
        self.export_button = QPushButton("Export Study")
        self.export_button.clicked.connect(self.export_study)

        self.status_label = QLabel("Study idle.")
        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setMinimumHeight(180)

        self.timeline_box = QListWidget()
        self.queue_box = QListWidget()
        self.dashboard_box = QListWidget()
        self.summary_box = QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(150)

        library_frame = QFrame()
        library_frame.setFrameShape(QFrame.Shape.StyledPanel)
        library_layout = QVBoxLayout(library_frame)
        library_layout.addWidget(QLabel("Study Library"))
        library_layout.addWidget(self.template_list, 1)

        control_form = QFormLayout()
        control_form.addRow("Participant ID", self.participant_id)
        control_form.addRow("Start At", self.start_at)
        control_form.addRow("Seed", self.seed)
        control_form.addRow("Custom Labels", self.custom_label)
        control_form.addRow("Selected Study", self.study_selector)

        control_buttons = QHBoxLayout()
        for button in [self.create_button, self.start_button, self.pause_button, self.resume_button, self.clone_button, self.export_button]:
            control_buttons.addWidget(button)

        preview_frame = QFrame()
        preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.addLayout(control_form)
        preview_layout.addLayout(control_buttons)
        preview_layout.addWidget(self.status_label)
        preview_layout.addWidget(QLabel("Study Preview"))
        preview_layout.addWidget(self.preview_box)
        preview_layout.addWidget(QLabel("Study Summary"))
        preview_layout.addWidget(self.summary_box)

        timeline_frame = QFrame()
        timeline_frame.setFrameShape(QFrame.Shape.StyledPanel)
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.addWidget(QLabel("Session Timeline"))
        timeline_layout.addWidget(self.timeline_box, 1)

        dashboard_frame = QFrame()
        dashboard_frame.setFrameShape(QFrame.Shape.StyledPanel)
        dashboard_layout = QVBoxLayout(dashboard_frame)
        dashboard_layout.addWidget(QLabel("Participant Progress Dashboard"))
        dashboard_layout.addWidget(self.dashboard_box, 1)

        queue_frame = QFrame()
        queue_frame.setFrameShape(QFrame.Shape.StyledPanel)
        queue_layout = QVBoxLayout(queue_frame)
        queue_layout.addWidget(QLabel("Upcoming Session Queue"))
        queue_layout.addWidget(self.queue_box, 1)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(preview_frame)
        right_splitter.addWidget(timeline_frame)
        right_splitter.addWidget(dashboard_frame)
        right_splitter.addWidget(queue_frame)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)
        right_splitter.setStretchFactor(2, 1)
        right_splitter.setStretchFactor(3, 1)

        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_splitter.addWidget(library_frame)
        root_splitter.addWidget(right_splitter)
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 3)

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(root_splitter)

        self._refresh_library()

    def set_sessions(self, sessions: list[TouchSessionRecord]) -> None:
        self.sessions = sessions
        self._refresh_dashboard_and_queue()

    def set_current_session(self, session: TouchSessionRecord | None) -> None:
        self.current_session = session
        self._refresh_dashboard_and_queue()

    def create_study(self) -> None:
        template = self.current_template or self._selected_template()
        if template is None:
            QMessageBox.warning(self, "Study", "Select a study template first.")
            return
        labels = self._parse_labels(self.custom_label.text())
        seed = self._parse_seed(self.seed.text())
        study = self.study_manager.create_study(
            template.template_id,
            participant_id=self.participant_id.text().strip() or "participant_01",
            start_at=self.start_at.text().strip() or None,
            custom_labels=labels,
            seed=seed,
        )
        self.current_study = study
        self.status_label.setText(f"Study created: {study.study_id}")
        self._refresh_controls()
        self._refresh_preview()
        self._refresh_dashboard_and_queue()
        QMessageBox.information(self, "Study Created", f"Study created from template {template.template_id}.")

    def start_study(self) -> None:
        study = self.study_manager.start_study()
        if study is None:
            QMessageBox.information(self, "Study", "Create a study first.")
            return
        self.current_study = study
        self.status_label.setText(f"Study running: {study.study_id}")
        self._refresh_preview()
        self._refresh_dashboard_and_queue()

    def pause_study(self) -> None:
        study = self.study_manager.pause_study()
        if study is None:
            return
        self.current_study = study
        self.status_label.setText(f"Study paused: {study.study_id}")
        self._refresh_preview()

    def resume_study(self) -> None:
        study = self.study_manager.resume_study()
        if study is None:
            return
        self.current_study = study
        self.status_label.setText(f"Study resumed: {study.study_id}")
        self._refresh_preview()

    def clone_study(self) -> None:
        cloned = self.study_manager.clone_study()
        if cloned is None:
            QMessageBox.information(self, "Study", "No active study to clone.")
            return
        self.current_study = cloned
        self.status_label.setText(f"Study cloned: {cloned.study_id}")
        self._refresh_library()
        self._refresh_preview()
        self._refresh_dashboard_and_queue()

    def export_study(self) -> None:
        report = self.study_manager.export_study(self.sessions)
        self.summary_box.setPlainText(json.dumps(report, indent=2, sort_keys=True))
        QMessageBox.information(self, "Study Export", f"Study report exported to:\n{self.paths.study_reports}")

    def _refresh_library(self) -> None:
        self.template_list.blockSignals(True)
        self.template_list.clear()
        templates = self.study_manager.list_templates()
        for template in templates:
            item = QListWidgetItem(f"{template.template_id} • {template.version} • {template.name}")
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            self.template_list.addItem(item)
        self.template_list.blockSignals(False)
        if self.template_list.count() > 0 and self.template_list.currentItem() is None:
            self.template_list.setCurrentRow(0)
        self._refresh_study_selector()
        self._refresh_preview()

    def _refresh_study_selector(self) -> None:
        self.study_selector.blockSignals(True)
        self.study_selector.clear()
        if self.study_manager.active_study is not None:
            self.study_selector.addItem(f"{self.study_manager.active_study.study_id}", self.study_manager.active_study.study_id)
        self.study_selector.blockSignals(False)
        if self.study_selector.count() == 0:
            self.study_selector.addItem("No active study", None)

    def _handle_template_selection(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            self.current_template = None
            self._refresh_preview()
            return
        template_id = current.data(Qt.ItemDataRole.UserRole)
        if not template_id:
            return
        self.current_template = self.study_manager.get_template(str(template_id))
        self._refresh_preview()

    def _selected_template(self) -> StudyTemplate | None:
        if self.current_template is not None:
            return self.current_template
        current_item = self.template_list.currentItem()
        if current_item is None:
            return None
        template_id = current_item.data(Qt.ItemDataRole.UserRole)
        if not template_id:
            return None
        return self.study_manager.get_template(str(template_id))

    def _refresh_preview(self, *_args: object) -> None:
        template = self._selected_template()
        if template is None:
            self.preview_box.setPlainText("No template selected.")
            return
        self.preview_box.setPlainText(json.dumps(template.to_dict(), indent=2, sort_keys=True))
        if self.current_study is not None:
            self.summary_box.setPlainText(json.dumps(self.current_study.to_dict(), indent=2, sort_keys=True))
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        study = self.study_manager.active_study
        if study is None:
            self.timeline_box.clear()
            self.queue_box.clear()
            self.dashboard_box.clear()
            return
        self.timeline_box.clear()
        for row in self.study_manager.session_timeline():
            item = QListWidgetItem(
                f"{row['plannedStartAt']} • {row['stepId']} • {row['experimentType']} • {row['status']} • day {row['dayIndex']}"
            )
            self.timeline_box.addItem(item)
        self.queue_box.clear()
        for row in self.study_manager.pending_sessions():
            item = QListWidgetItem(
                f"{row.planned_start_at} • {row.step_id} • {row.experiment_type} • rep {row.repetition_index}"
            )
            self.queue_box.addItem(item)
        self.dashboard_box.clear()
        for row in self.study_manager.progress_dashboard(self.sessions):
            self.dashboard_box.addItem(
                f"{row['participantId']} • sessions={row['sessionCount']} • drift={row['driftScore']:.4f} • consistency={row['consistencyEvolution']}"
            )

    def _refresh_dashboard_and_queue(self) -> None:
        self._refresh_controls()
        if self.current_session is not None:
            self.status_label.setText(f"Current session selected: {self.current_session.session_id}")

    @staticmethod
    def _parse_seed(raw: str) -> int | None:
        raw = raw.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    def _parse_labels(raw: str) -> dict[str, Any]:
        labels: dict[str, Any] = {}
        for chunk in raw.split(","):
            piece = chunk.strip()
            if not piece or "=" not in piece:
                continue
            key, value = piece.split("=", 1)
            labels[key.strip()] = value.strip()
        return labels
