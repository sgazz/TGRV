from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.analyzer.analysis import session_summary_metrics
from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.ingest import IngestionService
from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.protocols import ExperimentManager
from touchprint_lab.analyzer.studies import StudyManager
from touchprint_lab.plots.touch_plots import TouchPlotWidget
from touchprint_lab.ui.batch_analysis import BatchAnalysisWidget
from touchprint_lab.ui.feature_inspector import FeatureInspectorWidget
from touchprint_lab.ui.longitudinal_wizard import LongitudinalStudyWizard
from touchprint_lab.ui.protocol_orchestrator import ProtocolOrchestratorWidget
from touchprint_lab.ui.study_library import StudyLibraryWidget
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, paths: TouchprintPaths):
        super().__init__()
        self.paths = paths
        self.experiment_manager = ExperimentManager(paths)
        self.study_manager = StudyManager(paths, self.experiment_manager)
        self.experiment_manager.study_manager = self.study_manager
        self.dataset_manager = DatasetManager(paths, self.experiment_manager)
        self.ingestion_service = IngestionService(self.dataset_manager, paths.incoming)
        self.ingestion_service.sessionImported.connect(self._on_session_imported)

        self.sessions: list[TouchSessionRecord] = self.dataset_manager.load_all_sessions()
        self.feature_vectors: list[TouchFeatureVector] = self.dataset_manager.load_all_feature_vectors()
        self.current_session: TouchSessionRecord | None = None

        self.setWindowTitle("Touchprint Analyzer v1")
        self._build_ui()
        self._refresh_lists()
        self.ingestion_service.scan_now()

    def _build_ui(self) -> None:
        self.session_list = QListWidget()
        self.session_list.currentItemChanged.connect(self._handle_session_selection)

        self.user_list = QListWidget()
        self.user_list.currentItemChanged.connect(self._handle_user_selection)

        self.stats_box = QPlainTextEdit()
        self.stats_box.setReadOnly(True)

        self.metadata_box = QPlainTextEdit()
        self.metadata_box.setReadOnly(True)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Users"))
        left_layout.addWidget(self.user_list, 1)
        left_layout.addWidget(QLabel("Sessions"))
        left_layout.addWidget(self.session_list, 3)
        left_layout.addWidget(QLabel("Dataset Statistics"))
        left_layout.addWidget(self.stats_box, 1)
        left_layout.addWidget(QLabel("Current Session Metadata"))
        left_layout.addWidget(self.metadata_box, 2)

        self.plot_widget = TouchPlotWidget()

        self.sequence_display = QLineEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("Enter experimental sequence")

        self.tap_counter_value = QLabel("0")
        self.marker_counter_value = QLabel("0")

        keypad = QWidget()
        keypad_layout = QGridLayout(keypad)
        self.tap_count = 0
        self.marker_count = 0
        buttons: list[tuple[str, int, int]] = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("0", 3, 1),
        ]
        for label, row, column in buttons:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, digit=label: self._append_digit(digit))
            keypad_layout.addWidget(button, row, column)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._reset_simulator)
        self.marker_button = QPushButton("Session Marker")
        self.marker_button.clicked.connect(self._mark_session)

        controls_frame = QFrame()
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.addWidget(QLabel("Experimental Controls"))
        controls_layout.addWidget(QLabel("Entered Sequence"))
        controls_layout.addWidget(self.sequence_display)
        controls_layout.addWidget(QLabel("Tap Counter"))
        controls_layout.addWidget(self.tap_counter_value)
        controls_layout.addWidget(QLabel("Markers"))
        controls_layout.addWidget(self.marker_counter_value)
        controls_layout.addWidget(keypad)
        controls_layout.addWidget(self.marker_button)
        controls_layout.addWidget(self.reset_button)

        self.feature_inspector = FeatureInspectorWidget()
        self.batch_analysis = BatchAnalysisWidget(self.paths)
        self.protocol_orchestrator = ProtocolOrchestratorWidget(self.paths, self.dataset_manager)
        self.study_library = StudyLibraryWidget(
            self.paths,
            self.study_manager,
            self.experiment_manager,
            launch_wizard_callback=self.open_longitudinal_wizard,
        )
        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.addTab(self.feature_inspector, "Feature Inspector")
        self.analysis_tabs.addTab(self.batch_analysis, "Batch Analysis")
        self.analysis_tabs.addTab(self.protocol_orchestrator, "Experiment Protocol")
        self.analysis_tabs.addTab(self.study_library, "Study Library")

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(controls_frame)
        right_layout.addWidget(self.analysis_tabs, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _refresh_lists(self) -> None:
        selected_session_id = self.current_session.session_id if self.current_session else None

        self.user_list.blockSignals(True)
        self.session_list.blockSignals(True)
        self.user_list.clear()
        self.session_list.clear()

        for user_id in self.dataset_manager.list_users():
            item = QListWidgetItem(user_id)
            item.setData(Qt.ItemDataRole.UserRole, user_id)
            self.user_list.addItem(item)

        for record in self.dataset_manager.list_session_records():
            item = QListWidgetItem(
                f'{record["sessionId"]}  •  {record.get("sessionType", "unknown")}  •  {record.get("deviceType", "other")}  •  {record.get("eventCount", 0)} events'
            )
            item.setData(Qt.ItemDataRole.UserRole, record["sessionId"])
            self.session_list.addItem(item)

        self.user_list.blockSignals(False)
        self.session_list.blockSignals(False)
        self._refresh_statistics()
        self.feature_inspector.set_sessions(self.feature_vectors)
        self.batch_analysis.set_sessions(self.sessions)
        self.protocol_orchestrator.set_sessions(self.sessions)
        self.study_library.set_sessions(self.sessions)
        if selected_session_id:
            self._select_session_by_id(selected_session_id)
        else:
            self._refresh_metadata()

    def _refresh_statistics(self) -> None:
        stats = self.dataset_manager.dataset_statistics()
        self.stats_box.setPlainText(json.dumps(stats, indent=2, sort_keys=True))

    def _refresh_metadata(self) -> None:
        if self.current_session is None:
            self.metadata_box.setPlainText("No session selected.")
            self.feature_inspector.set_current_vector(None)
            return

        feature_vector = self._feature_vector_for_session(self.current_session.session_id)
        if feature_vector is None and self.current_session.feature_vector:
            feature_vector = TouchFeatureVector.from_dict(self.current_session.feature_vector)

        payload = {
            "session": self.current_session.session_id,
            "deviceType": self.current_session.device_type,
            "sessionType": self.current_session.session_type,
            "participantId": self.current_session.participant_id,
            "experimentId": self.current_session.experiment_id,
            "trialId": self.current_session.trial_id,
            "trialIndex": self.current_session.trial_index,
            "protocolSessionId": self.current_session.protocol_session_id,
            "protocolType": self.current_session.protocol_type,
            "participantMetadata": self.current_session.participant_metadata,
            "environmentLabels": self.current_session.environment_labels,
            "timingMetadata": self.current_session.timing_metadata,
            "eventCount": len(self.current_session.events),
            "summary": session_summary_metrics(self.current_session),
            "featureVector": feature_vector.to_dict() if feature_vector else None,
        }
        self.metadata_box.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
        self.feature_inspector.set_current_vector(feature_vector)
        self.batch_analysis.set_current_session(self.current_session)
        self.protocol_orchestrator.set_current_session(self.current_session)
        self.study_library.set_current_session(self.current_session)

    def _handle_user_selection(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        user_id = current.data(Qt.ItemDataRole.UserRole)
        if not user_id:
            return
        filtered = [session for session in self.sessions if session.user_id == user_id]
        self._populate_sessions(filtered)

    def _populate_sessions(self, sessions: list[TouchSessionRecord]) -> None:
        self.session_list.blockSignals(True)
        self.session_list.clear()
        for session in sessions:
            item = QListWidgetItem(
                f"{session.session_id}  •  {session.session_type}  •  {session.device_type}  •  {len(session.events)} events"
            )
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            self.session_list.addItem(item)
        self.session_list.blockSignals(False)
        self.current_session = sessions[0] if sessions else None
        self.plot_widget.set_session(self.current_session)
        self._refresh_metadata()

    def _handle_session_selection(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            self.current_session = None
            self.plot_widget.set_session(None)
            self._refresh_metadata()
            return
        session_id = current.data(Qt.ItemDataRole.UserRole)
        session = next((item for item in self.sessions if item.session_id == session_id), None)
        self.current_session = session
        self.plot_widget.set_session(session)
        self._refresh_metadata()

    def _on_session_imported(self, session: TouchSessionRecord) -> None:
        self.sessions.append(session)
        feature_vector = self.dataset_manager.feature_vector_for_session(session.session_id)
        if feature_vector is not None:
            self.feature_vectors.append(feature_vector)
        self._refresh_lists()
        self.protocol_orchestrator.refresh_state()
        self.study_library.set_sessions(self.sessions)
        logger.info("Session imported into UI: %s", session.session_id)

    def _append_digit(self, digit: str) -> None:
        self.tap_count += 1
        self.sequence_display.setText(self.sequence_display.text() + digit)
        self.tap_counter_value.setText(str(self.tap_count))

    def _reset_simulator(self) -> None:
        self.sequence_display.clear()
        self.tap_count = 0
        self.marker_count = 0
        self.tap_counter_value.setText("0")
        self.marker_counter_value.setText("0")

    def _mark_session(self) -> None:
        self.marker_count += 1
        self.marker_counter_value.setText(str(self.marker_count))
        logger.info("Session marker inserted at count=%s sequence=%s", self.marker_count, self.sequence_display.text())
        QMessageBox.information(self, "Session Marker", "Marker recorded for the current experimental sequence.")

    def open_longitudinal_wizard(self) -> None:
        wizard = LongitudinalStudyWizard(self.paths, self.study_manager, self.experiment_manager, parent=self)
        if wizard.exec() == QDialog.DialogCode.Accepted:
            self.sessions = self.dataset_manager.load_all_sessions()
            self.feature_vectors = self.dataset_manager.load_all_feature_vectors()
            self._refresh_lists()

    def _feature_vector_for_session(self, session_id: str) -> TouchFeatureVector | None:
        return next((vector for vector in self.feature_vectors if vector.session_id == session_id), None)

    def _select_session_by_id(self, session_id: str) -> None:
        for row in range(self.session_list.count()):
            item = self.session_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentItem(item)
                return
