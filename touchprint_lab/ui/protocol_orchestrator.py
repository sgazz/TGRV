from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.protocols import EXPERIMENT_TYPES, ExperimentManager
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class ProtocolOrchestratorWidget(QWidget):
    def __init__(self, paths: TouchprintPaths, dataset_manager: DatasetManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.paths = paths
        self.dataset_manager = dataset_manager
        self.experiment_manager = dataset_manager.experiment_manager or ExperimentManager(paths)
        self.dataset_manager.experiment_manager = self.experiment_manager
        self.sessions: list[TouchSessionRecord] = []
        self.current_session: TouchSessionRecord | None = None
        self.remaining_seconds: int = 0

        self.participant_id = QLineEdit("participant_01")
        self.experiment_id = QLineEdit("")
        self.protocol_seed = QSpinBox()
        self.protocol_seed.setRange(0, 999999)
        self.protocol_seed.setValue(42)
        self.repetitions = QSpinBox()
        self.repetitions.setRange(1, 20)
        self.repetitions.setValue(1)
        self.same_day_repetitions = QSpinBox()
        self.same_day_repetitions.setRange(1, 20)
        self.same_day_repetitions.setValue(1)
        self.multi_day_repetitions = QSpinBox()
        self.multi_day_repetitions.setRange(1, 20)
        self.multi_day_repetitions.setValue(1)
        self.delayed_retest_hours = QSpinBox()
        self.delayed_retest_hours.setRange(1, 240)
        self.delayed_retest_hours.setValue(24)

        self.device_type = QLineEdit("iPhone")
        self.input_modality = QComboBox()
        self.input_modality.addItems(["finger", "pencil"])
        self.dominant_hand = QComboBox()
        self.dominant_hand.addItems(["unknown", "left", "right"])
        self.posture = QComboBox()
        self.posture.addItems(["unknown", "seated", "standing"])
        self.fatigue_state = QComboBox()
        self.fatigue_state.addItems(["unknown", "fresh", "moderate", "fatigued"])
        self.stress_level = QComboBox()
        self.stress_level.addItems(["unknown", "low", "medium", "high"])
        self.attention_mode = QComboBox()
        self.attention_mode.addItems(["unknown", "focused", "distracted", "dual_task"])
        self.time_of_day = QComboBox()
        self.time_of_day.addItems(["auto", "morning", "afternoon", "evening", "night"])

        self.protocol_types = QListWidget()
        self.protocol_types.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for experiment_type in EXPERIMENT_TYPES:
            item = QListWidgetItem(experiment_type)
            self.protocol_types.addItem(item)
        self.protocol_types.selectAll()

        self.instructions_box = QPlainTextEdit()
        self.instructions_box.setReadOnly(True)
        self.instructions_box.setMinimumHeight(120)

        self.status_label = QLabel("Protocol idle.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.countdown_label = QLabel("Countdown: —")
        self.trial_status_label = QLabel("Trial status: —")
        self.feedback_label = QLabel("Live capture feedback: waiting")

        self.run_summary = QPlainTextEdit()
        self.run_summary.setReadOnly(True)
        self.run_summary.setMinimumHeight(160)

        self.protocol_history = QListWidget()
        self.participant_dashboard = QListWidget()

        self.create_button = QPushButton("Create Protocol")
        self.create_button.clicked.connect(self.create_protocol)
        self.start_button = QPushButton("Start Protocol")
        self.start_button.clicked.connect(self.start_protocol)
        self.complete_button = QPushButton("Mark Trial Complete")
        self.complete_button.clicked.connect(self.complete_current_trial)
        self.next_button = QPushButton("Next Trial")
        self.next_button.clicked.connect(self.next_trial)
        self.finish_button = QPushButton("Finish Protocol")
        self.finish_button.clicked.connect(self.finish_protocol)
        self.export_button = QPushButton("Export Reports")
        self.export_button.clicked.connect(self.export_reports)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_state)

        setup_form = QFormLayout()
        setup_form.addRow("Participant ID", self.participant_id)
        setup_form.addRow("Experiment ID", self.experiment_id)
        setup_form.addRow("Protocol Seed", self.protocol_seed)
        setup_form.addRow("Repetitions", self.repetitions)
        setup_form.addRow("Same-day Repeats", self.same_day_repetitions)
        setup_form.addRow("Multi-day Repeats", self.multi_day_repetitions)
        setup_form.addRow("Retest Delay (h)", self.delayed_retest_hours)
        setup_form.addRow("Device Type", self.device_type)
        setup_form.addRow("Input Modality", self.input_modality)
        setup_form.addRow("Dominant Hand", self.dominant_hand)
        setup_form.addRow("Posture", self.posture)
        setup_form.addRow("Fatigue", self.fatigue_state)
        setup_form.addRow("Stress", self.stress_level)
        setup_form.addRow("Attention", self.attention_mode)
        setup_form.addRow("Time of Day", self.time_of_day)

        button_row = QHBoxLayout()
        for button in [self.create_button, self.start_button, self.complete_button, self.next_button, self.finish_button, self.export_button, self.refresh_button]:
            button_row.addWidget(button)

        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.Shape.StyledPanel)
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.addLayout(setup_form)
        controls_layout.addWidget(QLabel("Experiment Types"))
        controls_layout.addWidget(self.protocol_types)
        controls_layout.addLayout(button_row)
        controls_layout.addWidget(self.status_label)
        controls_layout.addWidget(self.progress_bar)
        controls_layout.addWidget(self.countdown_label)
        controls_layout.addWidget(self.trial_status_label)
        controls_layout.addWidget(self.feedback_label)
        controls_layout.addWidget(QLabel("Instructions"))
        controls_layout.addWidget(self.instructions_box)
        controls_layout.addWidget(QLabel("Current Run Summary"))
        controls_layout.addWidget(self.run_summary)

        dashboard_frame = QFrame()
        dashboard_frame.setFrameShape(QFrame.Shape.StyledPanel)
        dashboard_layout = QHBoxLayout(dashboard_frame)
        left = QVBoxLayout()
        left.addWidget(QLabel("Protocol History"))
        left.addWidget(self.protocol_history, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("Participant Dashboard"))
        right.addWidget(self.participant_dashboard, 1)
        dashboard_layout.addLayout(left, 1)
        dashboard_layout.addLayout(right, 1)

        root = QVBoxLayout(self)
        root.addWidget(controls_frame)
        root.addWidget(dashboard_frame, 1)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._tick_countdown)

        self.refresh_state()

    def set_sessions(self, sessions: list[TouchSessionRecord]) -> None:
        self.sessions = sessions
        self.refresh_state()

    def set_current_session(self, session: TouchSessionRecord | None) -> None:
        self.current_session = session
        if session is not None:
            self.feedback_label.setText(f"Live capture feedback: session {session.session_id} selected")

    def create_protocol(self) -> None:
        selected_types = [item.text() for item in self.protocol_types.selectedItems()] or list(EXPERIMENT_TYPES)
        participant_metadata = {
            "posture": self.posture.currentText(),
            "fatigueState": self.fatigue_state.currentText(),
            "stressLevel": self.stress_level.currentText(),
            "attentionMode": self.attention_mode.currentText(),
        }
        environment_labels = {
            "deviceType": self.device_type.text().strip() or "iPhone",
            "inputModality": self.input_modality.currentText(),
            "dominantHand": self.dominant_hand.currentText(),
            "timeOfDay": self.time_of_day.currentText() if self.time_of_day.currentText() != "auto" else "auto",
            "posture": self.posture.currentText(),
        }
        protocol_metadata = {
            "repeatabilityStudy": True,
            "standardizedFlow": True,
        }
        experiment_id = self.experiment_id.text().strip() or None
        run = self.experiment_manager.create_protocol(
            participant_id=self.participant_id.text().strip() or "participant_01",
            experiment_id=experiment_id,
            experiment_types=selected_types,
            participant_metadata=participant_metadata,
            environment_labels=environment_labels,
            protocol_metadata=protocol_metadata,
            repetitions=self.repetitions.value(),
            same_day_repetitions=self.same_day_repetitions.value(),
            multi_day_repetitions=self.multi_day_repetitions.value(),
            delayed_retest_hours=self.delayed_retest_hours.value(),
            device_type=self.device_type.text().strip() or "iPhone",
            input_modality=self.input_modality.currentText(),
            dominant_hand=self.dominant_hand.currentText(),
            seed=self.protocol_seed.value(),
        )
        self._show_run(run)
        self.status_label.setText(f"Protocol created: {run.protocol_session_id}")
        self.feedback_label.setText("Live capture feedback: protocol ready")
        QMessageBox.information(self, "Protocol Created", f"Protocol created for participant {run.participant_id}.")

    def start_protocol(self) -> None:
        run = self.experiment_manager.start_protocol()
        if run is None:
            QMessageBox.warning(self, "Protocol", "No active protocol exists. Create one first.")
            return
        self.status_label.setText(f"Protocol running: {run.protocol_session_id}")
        self._show_run(run)
        self._start_countdown()

    def complete_current_trial(self) -> None:
        session = self.current_session
        if session is None:
            QMessageBox.information(self, "Protocol", "Select or import a session to complete the current trial.")
            return
        self.experiment_manager.record_completed_session(session)
        self.feedback_label.setText(f"Live capture feedback: recorded {session.session_id}")
        self.refresh_state()

    def next_trial(self) -> None:
        trial = self.experiment_manager.advance_trial()
        if trial is None:
            self.countdown_timer.stop()
            self.feedback_label.setText("Live capture feedback: protocol complete")
        self.refresh_state()
        if trial is not None:
            self._start_countdown()

    def finish_protocol(self) -> None:
        finished = self.experiment_manager.finish_protocol()
        if finished is None:
            QMessageBox.information(self, "Protocol", "No active protocol to finish.")
            return
        self.countdown_timer.stop()
        self.status_label.setText(f"Protocol finished: {finished.protocol_session_id}")
        self.refresh_state()
        QMessageBox.information(self, "Protocol Finished", f"Protocol {finished.protocol_session_id} finished.")

    def export_reports(self) -> None:
        report = self.experiment_manager.export_protocol_report(self.sessions, self.paths.protocol_reports)
        self.run_summary.setPlainText(json.dumps(report, indent=2, sort_keys=True))
        QMessageBox.information(self, "Protocol Reports", f"Reports exported to:\n{self.paths.protocol_reports}")

    def refresh_state(self) -> None:
        run = self.experiment_manager.active_run
        self._show_run(run)
        self._refresh_history()
        self._refresh_dashboard()
        self._refresh_countdown()

    def _show_run(self, run: Any) -> None:
        if run is None:
            self.run_summary.setPlainText("No active protocol.")
            self.instructions_box.setPlainText("Create a protocol to begin.")
            self.trial_status_label.setText("Trial status: idle")
            self.progress_bar.setValue(0)
            return
        self.run_summary.setPlainText(json.dumps(run.to_dict(), indent=2, sort_keys=True))
        current_trial = run.current_trial()
        if current_trial is not None:
            self.instructions_box.setPlainText(current_trial.instructions)
            self.trial_status_label.setText(
                f"Trial status: {current_trial.experiment_type} / trial {current_trial.trial_index + 1} of {len(run.trials)}"
            )
            self.progress_bar.setValue(int(run.progress() * self.progress_bar.maximum()))
        else:
            self.instructions_box.setPlainText("Protocol complete.")
            self.trial_status_label.setText("Trial status: complete")
            self.progress_bar.setValue(self.progress_bar.maximum())

    def _refresh_history(self) -> None:
        self.protocol_history.clear()
        for entry in reversed(self.experiment_manager.protocol_history()[-100:]):
            item = QListWidgetItem(
                f"{entry.get('protocolSessionId', 'unknown')} • {entry.get('participantId', 'participant_01')} • {entry.get('status', 'unknown')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.protocol_history.addItem(item)

    def _refresh_dashboard(self) -> None:
        self.participant_dashboard.clear()
        for row in self.experiment_manager.experiment_dashboard(self.sessions):
            self.participant_dashboard.addItem(
                f"{row['participantId']} • sessions={row['sessionCount']} • repeatability={row['repeatabilityScore']:.4f} • drift={row['driftScore']:.4f}"
            )

    def _start_countdown(self) -> None:
        run = self.experiment_manager.active_run
        trial = run.current_trial() if run else None
        self.remaining_seconds = trial.expected_duration_seconds if trial else 0
        if self.remaining_seconds <= 0:
            self.countdown_label.setText("Countdown: —")
            self.countdown_timer.stop()
            return
        self.countdown_label.setText(f"Countdown: {self.remaining_seconds}s")
        self.countdown_timer.start()

    def _tick_countdown(self) -> None:
        if self.remaining_seconds <= 0:
            self.countdown_timer.stop()
            self.countdown_label.setText("Countdown: 0s")
            return
        self.remaining_seconds -= 1
        self.countdown_label.setText(f"Countdown: {self.remaining_seconds}s")
        if self.remaining_seconds <= 0:
            self.countdown_timer.stop()
            self.feedback_label.setText("Live capture feedback: trial window elapsed")

    def _refresh_countdown(self) -> None:
        if self.countdown_timer.isActive():
            self.countdown_label.setText(f"Countdown: {self.remaining_seconds}s")
        else:
            self.countdown_label.setText("Countdown: —")
