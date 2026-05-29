from __future__ import annotations

import json
import logging
import math
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, cast

try:  # pragma: no cover - optional YAML support
    import yaml  # type: ignore
except Exception:  # pragma: no cover - keep module importable
    yaml = None  # type: ignore

from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.protocols import ExperimentManager
from touchprint_lab.analyzer.studies import StudyManager, StudyPlan, StudySessionSpec, StudyStep, StudyTemplate
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)

WIZARD_VERSION = "v1"
WIZARD_PAGE_COUNT = 6

WIZARD_PROTOCOLS: tuple[str, ...] = (
    "random_tap",
    "intentional_tap",
    "signature_tap",
    "pin_entry",
    "line_drawing",
    "pressure_stabilization",
    "hold_and_release",
)

TIME_WINDOWS: dict[str, tuple[int, int]] = {
    "morning": (9, 0),
    "afternoon": (13, 30),
    "evening": (18, 15),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_yaml_dump(payload: dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return json.dumps(payload, indent=2, sort_keys=True)


def _stable_seed(*parts: Any) -> int:
    seed = 0
    for part in parts:
        for character in str(part):
            seed = (seed * 131 + ord(character)) % (2**32)
    return seed


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def _time_window_label_to_hour_minute(label: str) -> tuple[int, int]:
    return TIME_WINDOWS.get(label, TIME_WINDOWS["morning"])


@dataclass(slots=True)
class WizardScheduleRow:
    day_index: int
    day_label: str
    time_window: str
    planned_start_at: str
    step_id: str
    experiment_type: str
    repetition_index: int
    daily_repetition_index: int
    same_day_repetition_index: int
    labels: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dayIndex": self.day_index,
            "dayLabel": self.day_label,
            "timeWindow": self.time_window,
            "plannedStartAt": self.planned_start_at,
            "stepId": self.step_id,
            "experimentType": self.experiment_type,
            "repetitionIndex": self.repetition_index,
            "dailyRepetitionIndex": self.daily_repetition_index,
            "sameDayRepetitionIndex": self.same_day_repetition_index,
            "labels": self.labels,
        }


@dataclass(slots=True)
class LongitudinalWizardState:
    wizard_version: str = WIZARD_VERSION
    current_step_index: int = 0
    study_name: str = ""
    study_type: str = "baseline_identity_study"
    description: str = ""
    seed: int = 42
    participant_id: str = ""
    dominant_hand: str = "unknown"
    device_preference: str = "iPhone"
    selected_protocols: list[str] = field(default_factory=list)
    repetitions_per_protocol: int = 1
    intensity_level: str = "medium"
    schedule: dict[str, Any] = field(
        default_factory=lambda: {
            "dayCount": 3,
            "sameDayRepetitions": 1,
            "dailyRepetitions": 1,
            "delayMode": "24h",
            "customDelayHours": 24,
            "windows": ["morning", "afternoon", "evening"],
            "randomizeTimeDrift": True,
            "timeDriftMinutes": 10,
            "sessionSpacingMinutes": 20,
            "anchorStart": None,
        }
    )
    environment_labels: dict[str, Any] = field(
        default_factory=lambda: {
            "deviceType": "iPhone",
            "posture": "seated",
            "cognitiveState": "focused",
            "inputMode": "finger",
        }
    )
    participant_metadata: dict[str, Any] = field(default_factory=dict)
    protocol_manifest: dict[str, Any] = field(default_factory=dict)
    study_id: str = ""
    derived_template_id: str = ""
    template_version: str = ""
    study_calendar: list[dict[str, Any]] = field(default_factory=list)
    expected_session_count: int = 0
    exported_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wizardVersion": self.wizard_version,
            "currentStepIndex": self.current_step_index,
            "studyName": self.study_name,
            "studyType": self.study_type,
            "description": self.description,
            "seed": self.seed,
            "participantId": self.participant_id,
            "dominantHand": self.dominant_hand,
            "devicePreference": self.device_preference,
            "selectedProtocols": list(self.selected_protocols),
            "repetitionsPerProtocol": self.repetitions_per_protocol,
            "intensityLevel": self.intensity_level,
            "schedule": self.schedule,
            "environmentLabels": self.environment_labels,
            "participantMetadata": self.participant_metadata,
            "protocolManifest": self.protocol_manifest,
            "studyId": self.study_id,
            "derivedTemplateId": self.derived_template_id,
            "templateVersion": self.template_version,
            "studyCalendar": self.study_calendar,
            "expectedSessionCount": self.expected_session_count,
            "exportedPaths": self.exported_paths,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LongitudinalWizardState":
        state = cls()
        state.wizard_version = str(payload.get("wizardVersion", WIZARD_VERSION))
        state.current_step_index = int(payload.get("currentStepIndex", 0))
        state.study_name = str(payload.get("studyName", ""))
        state.study_type = str(payload.get("studyType", "baseline_identity_study"))
        state.description = str(payload.get("description", ""))
        state.seed = int(payload.get("seed", 42))
        state.participant_id = str(payload.get("participantId", ""))
        state.dominant_hand = str(payload.get("dominantHand", "unknown"))
        state.device_preference = str(payload.get("devicePreference", "iPhone"))
        state.selected_protocols = list(payload.get("selectedProtocols") or [])
        state.repetitions_per_protocol = int(payload.get("repetitionsPerProtocol", 1))
        state.intensity_level = str(payload.get("intensityLevel", "medium"))
        state.schedule = dict(payload.get("schedule") or state.schedule)
        state.environment_labels = dict(payload.get("environmentLabels") or state.environment_labels)
        state.participant_metadata = dict(payload.get("participantMetadata") or {})
        state.protocol_manifest = dict(payload.get("protocolManifest") or {})
        state.study_id = str(payload.get("studyId", ""))
        state.derived_template_id = str(payload.get("derivedTemplateId", ""))
        state.template_version = str(payload.get("templateVersion", ""))
        state.study_calendar = list(payload.get("studyCalendar") or [])
        state.expected_session_count = int(payload.get("expectedSessionCount", 0))
        state.exported_paths = dict(payload.get("exportedPaths") or {})
        return state


class WizardStepPage(QWizardPage):
    def __init__(self, title: str, wizard_index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.wizard_index = wizard_index
        self.title_label = QLabel(title)
        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, WIZARD_PAGE_COUNT)
        self.progress_bar.setTextVisible(True)

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(self.title_label)
        root_layout.addWidget(self.progress_label)
        root_layout.addWidget(self.progress_bar)
        self.content_layout = QVBoxLayout()
        root_layout.addLayout(self.content_layout)
        root_layout.addStretch(1)

    def initializePage(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        self.progress_label.setText(f"Step {self.wizard_index + 1} of {WIZARD_PAGE_COUNT}")
        self.progress_bar.setValue(self.wizard_index + 1)
        wizard.set_current_step_index(self.wizard_index)
        self.load_state()

    def load_state(self) -> None:
        pass

    def store_state(self) -> None:
        pass

    def notify_change(self) -> None:
        wizard = self.wizard()
        if isinstance(wizard, LongitudinalStudyWizard):
            wizard.save_state()
            wizard.refresh_all_previews()


class StudyDefinitionPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Study Definition", 0, parent)
        form = QFormLayout()
        self.study_name = QLineEdit()
        self.study_name.setPlaceholderText("Study name")
        self.study_type = QComboBox()
        self.study_type.addItems(
            [
                "baseline_identity_study",
                "pin_behavior_study",
                "motor_fatigue_study",
                "pencil_precision_study",
                "replayability_study",
            ]
        )
        self.description = QLineEdit()
        self.description.setPlaceholderText("Optional description")
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_000_000_000)
        self.seed.setValue(42)
        form.addRow("Study name", self.study_name)
        form.addRow("Study type", self.study_type)
        form.addRow("Description", self.description)
        form.addRow("Random seed", self.seed)
        self.content_layout.addLayout(form)

        for widget in [self.study_name, self.description]:
            widget.textChanged.connect(self.notify_change)
        self.study_type.currentIndexChanged.connect(self.notify_change)
        self.seed.valueChanged.connect(self.notify_change)

    def load_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        state = wizard.state
        self.study_name.setText(state.study_name)
        index = self.study_type.findText(state.study_type)
        if index >= 0:
            self.study_type.setCurrentIndex(index)
        self.description.setText(state.description)
        self.seed.setValue(state.seed)

    def store_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.state.study_name = self.study_name.text().strip()
        wizard.state.study_type = self.study_type.currentText()
        wizard.state.description = self.description.text().strip()
        wizard.state.seed = self.seed.value()

    def validatePage(self) -> bool:
        self.store_state()
        if not self.study_name.text().strip():
            QMessageBox.warning(self, "Validation", "Study name is required.")
            return False
        return True


class ParticipantSetupPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Participant Setup", 1, parent)
        form = QFormLayout()
        self.participant_id = QLineEdit()
        self.participant_id.setPlaceholderText("participant_01")
        self.dominant_hand = QComboBox()
        self.dominant_hand.addItems(["unknown", "left", "right", "ambidextrous"])
        self.device_preference = QComboBox()
        self.device_preference.addItems(["iPhone", "iPad", "Pencil"])
        form.addRow("Participant ID", self.participant_id)
        form.addRow("Dominant hand", self.dominant_hand)
        form.addRow("Device preference", self.device_preference)
        self.content_layout.addLayout(form)
        self.participant_id.textChanged.connect(self.notify_change)
        self.dominant_hand.currentIndexChanged.connect(self.notify_change)
        self.device_preference.currentIndexChanged.connect(self.notify_change)

    def load_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        self.participant_id.setText(wizard.state.participant_id)
        index = self.dominant_hand.findText(wizard.state.dominant_hand)
        if index >= 0:
            self.dominant_hand.setCurrentIndex(index)
        index = self.device_preference.findText(wizard.state.device_preference)
        if index >= 0:
            self.device_preference.setCurrentIndex(index)

    def store_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.state.participant_id = self.participant_id.text().strip()
        wizard.state.dominant_hand = self.dominant_hand.currentText()
        wizard.state.device_preference = self.device_preference.currentText()
        wizard.state.participant_metadata = {
            "dominantHand": wizard.state.dominant_hand,
            "devicePreference": wizard.state.device_preference,
        }

    def validatePage(self) -> bool:
        self.store_state()
        if not self.participant_id.text().strip():
            QMessageBox.warning(self, "Validation", "Participant ID is required.")
            return False
        return True


class ProtocolSelectionPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Protocol Selection", 2, parent)
        self.protocol_checkboxes: dict[str, QCheckBox] = {}

        checklist_box = QGroupBox("Protocols")
        checklist_layout = QGridLayout(checklist_box)
        for index, protocol in enumerate(WIZARD_PROTOCOLS):
            checkbox = QCheckBox(protocol)
            self.protocol_checkboxes[protocol] = checkbox
            row, column = divmod(index, 2)
            checklist_layout.addWidget(checkbox, row, column)
            checkbox.stateChanged.connect(self.notify_change)

        options_form = QFormLayout()
        self.repetitions = QSpinBox()
        self.repetitions.setRange(1, 100)
        self.repetitions.setValue(1)
        self.intensity = QComboBox()
        self.intensity.addItems(["low", "medium", "high"])
        options_form.addRow("Repetitions per protocol", self.repetitions)
        options_form.addRow("Intensity level", self.intensity)
        self.content_layout.addWidget(checklist_box)
        self.content_layout.addLayout(options_form)

        self.repetitions.valueChanged.connect(self.notify_change)
        self.intensity.currentIndexChanged.connect(self.notify_change)

    def load_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        state = wizard.state
        selected = set(state.selected_protocols or [])
        for protocol, checkbox in self.protocol_checkboxes.items():
            checkbox.setChecked(protocol in selected)
        self.repetitions.setValue(max(1, state.repetitions_per_protocol))
        index = self.intensity.findText(state.intensity_level)
        if index >= 0:
            self.intensity.setCurrentIndex(index)

    def store_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.state.selected_protocols = [protocol for protocol, checkbox in self.protocol_checkboxes.items() if checkbox.isChecked()]
        wizard.state.repetitions_per_protocol = self.repetitions.value()
        wizard.state.intensity_level = self.intensity.currentText()

    def validatePage(self) -> bool:
        self.store_state()
        if not self.repetitions.value() or not wizard_selected_protocols(self):
            QMessageBox.warning(self, "Validation", "Select at least one protocol.")
            return False
        return True


class ScheduleBuilderPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Schedule Builder", 3, parent)
        form = QFormLayout()
        self.anchor_start = QDateTimeEdit()
        self.anchor_start.setCalendarPopup(True)
        self.anchor_start.setDateTime(QDateTime.currentDateTime())
        self.day_count = QSpinBox()
        self.day_count.setRange(1, 30)
        self.day_count.setValue(3)
        self.same_day_repetitions = QSpinBox()
        self.same_day_repetitions.setRange(1, 20)
        self.same_day_repetitions.setValue(1)
        self.daily_repetitions = QSpinBox()
        self.daily_repetitions.setRange(1, 20)
        self.daily_repetitions.setValue(1)
        self.delay_mode = QComboBox()
        self.delay_mode.addItems(["24h", "7d", "custom"])
        self.custom_delay_hours = QSpinBox()
        self.custom_delay_hours.setRange(1, 720)
        self.custom_delay_hours.setValue(24)
        self.session_spacing = QSpinBox()
        self.session_spacing.setRange(1, 240)
        self.session_spacing.setValue(20)
        self.randomize_drift = QCheckBox("Allow random time drift")
        self.randomize_drift.setChecked(True)
        self.time_drift_minutes = QSpinBox()
        self.time_drift_minutes.setRange(0, 180)
        self.time_drift_minutes.setValue(10)

        self.morning = QCheckBox("Morning")
        self.morning.setChecked(True)
        self.afternoon = QCheckBox("Afternoon")
        self.afternoon.setChecked(True)
        self.evening = QCheckBox("Evening")
        self.evening.setChecked(True)

        form.addRow("Anchor start", self.anchor_start)
        form.addRow("Day count", self.day_count)
        form.addRow("Same-day repetitions", self.same_day_repetitions)
        form.addRow("Daily repetitions", self.daily_repetitions)
        form.addRow("Delay mode", self.delay_mode)
        form.addRow("Custom delay hours", self.custom_delay_hours)
        form.addRow("Session spacing (minutes)", self.session_spacing)
        form.addRow(self.randomize_drift)
        form.addRow("Time drift (minutes)", self.time_drift_minutes)

        windows_box = QGroupBox("Time windows")
        windows_layout = QHBoxLayout(windows_box)
        windows_layout.addWidget(self.morning)
        windows_layout.addWidget(self.afternoon)
        windows_layout.addWidget(self.evening)

        self.preview_table = QTableWidget(0, 6)
        self.preview_table.setHorizontalHeaderLabels(
            ["Day", "Window", "Planned Start", "Protocol", "Rep", "Session ID"]
        )
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.summary_label = QLabel("Schedule will update as settings change.")
        self.content_layout.addLayout(form)
        self.content_layout.addWidget(windows_box)
        self.content_layout.addWidget(self.summary_label)
        self.content_layout.addWidget(self.preview_table, 1)

        for widget in [
            self.anchor_start,
            self.day_count,
            self.same_day_repetitions,
            self.daily_repetitions,
            self.delay_mode,
            self.custom_delay_hours,
            self.session_spacing,
            self.time_drift_minutes,
            self.morning,
            self.afternoon,
            self.evening,
        ]:
            if isinstance(widget, QDateTimeEdit):
                widget.dateTimeChanged.connect(self.notify_change)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self.notify_change)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.notify_change)
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self.notify_change)

    def load_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        state = wizard.state
        anchor = state.schedule.get("anchorStart")
        if anchor:
            self.anchor_start.setDateTime(QDateTime.fromString(str(anchor), Qt.DateFormat.ISODate))
        self.day_count.setValue(int(state.schedule.get("dayCount", 3)))
        self.same_day_repetitions.setValue(int(state.schedule.get("sameDayRepetitions", 1)))
        self.daily_repetitions.setValue(int(state.schedule.get("dailyRepetitions", 1)))
        index = self.delay_mode.findText(str(state.schedule.get("delayMode", "24h")))
        if index >= 0:
            self.delay_mode.setCurrentIndex(index)
        self.custom_delay_hours.setValue(int(state.schedule.get("customDelayHours", 24)))
        self.session_spacing.setValue(int(state.schedule.get("sessionSpacingMinutes", 20)))
        self.randomize_drift.setChecked(bool(state.schedule.get("randomizeTimeDrift", True)))
        self.time_drift_minutes.setValue(int(state.schedule.get("timeDriftMinutes", 10)))
        windows = set(state.schedule.get("windows") or [])
        self.morning.setChecked("morning" in windows or not windows)
        self.afternoon.setChecked("afternoon" in windows or not windows)
        self.evening.setChecked("evening" in windows or not windows)
        self.refresh_preview()

    def store_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.state.schedule = {
            "dayCount": self.day_count.value(),
            "sameDayRepetitions": self.same_day_repetitions.value(),
            "dailyRepetitions": self.daily_repetitions.value(),
            "delayMode": self.delay_mode.currentText(),
            "customDelayHours": self.custom_delay_hours.value(),
            "windows": self._selected_windows(),
            "randomizeTimeDrift": self.randomize_drift.isChecked(),
            "timeDriftMinutes": self.time_drift_minutes.value(),
            "sessionSpacingMinutes": self.session_spacing.value(),
            "anchorStart": self.anchor_start.dateTime().toString(Qt.DateFormat.ISODate),
        }

    def refresh_preview(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        state = wizard.state
        rows = wizard.generate_schedule_preview()
        state.study_calendar = [row.to_dict() for row in rows]
        state.expected_session_count = len(rows)
        self.preview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [row.day_label, row.time_window, row.planned_start_at, row.experiment_type, str(row.repetition_index), row.labels.get("sessionId", "")]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.preview_table.setItem(row_index, column_index, item)
        self.summary_label.setText(
            f"Expected session count: {len(rows)} | Windows: {', '.join(state.schedule.get('windows') or []) or 'none'}"
        )

    def validatePage(self) -> bool:
        self.store_state()
        self.refresh_preview()
        return True

    def _selected_windows(self) -> list[str]:
        windows = []
        if self.morning.isChecked():
            windows.append("morning")
        if self.afternoon.isChecked():
            windows.append("afternoon")
        if self.evening.isChecked():
            windows.append("evening")
        return windows


class EnvironmentLabelsPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Environment Labels", 4, parent)
        form = QFormLayout()
        self.device_type = QComboBox()
        self.device_type.addItems(["iPhone", "iPad", "Pencil"])
        self.posture = QComboBox()
        self.posture.addItems(["seated", "standing"])
        self.cognitive_state = QComboBox()
        self.cognitive_state.addItems(["focused", "distracted", "fatigued", "rushed"])
        self.input_mode = QComboBox()
        self.input_mode.addItems(["finger", "stylus"])
        form.addRow("Device type", self.device_type)
        form.addRow("Posture", self.posture)
        form.addRow("Cognitive state", self.cognitive_state)
        form.addRow("Input mode", self.input_mode)
        self.content_layout.addLayout(form)
        for widget in [self.device_type, self.posture, self.cognitive_state, self.input_mode]:
            widget.currentIndexChanged.connect(self.notify_change)

    def load_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        state = wizard.state
        for combo, key in [
            (self.device_type, "deviceType"),
            (self.posture, "posture"),
            (self.cognitive_state, "cognitiveState"),
            (self.input_mode, "inputMode"),
        ]:
            index = combo.findText(str(state.environment_labels.get(key, combo.currentText())))
            if index >= 0:
                combo.setCurrentIndex(index)

    def store_state(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.state.environment_labels = {
            "deviceType": self.device_type.currentText(),
            "posture": self.posture.currentText(),
            "cognitiveState": self.cognitive_state.currentText(),
            "inputMode": self.input_mode.currentText(),
        }


class ReviewLaunchPage(WizardStepPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Review & Launch", 5, parent)
        self.summary_box = QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(180)
        self.timeline_table = QTableWidget(0, 6)
        self.timeline_table.setHorizontalHeaderLabels(
            ["Day", "Window", "Planned Start", "Protocol", "Rep", "Session ID"]
        )
        self.timeline_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start Study")
        self.start_button.clicked.connect(self._start_clicked)
        self.save_button = QPushButton("Save Draft")
        self.save_button.clicked.connect(self._save_draft_clicked)
        self.export_button = QPushButton("Export JSON/YAML")
        self.export_button.clicked.connect(self._export_clicked)
        for button in [self.start_button, self.save_button, self.export_button]:
            button_row.addWidget(button)

        self.content_layout.addWidget(self.summary_box)
        self.content_layout.addWidget(QLabel("Schedule Preview"))
        self.content_layout.addWidget(self.timeline_table, 1)
        self.content_layout.addLayout(button_row)

    def load_state(self) -> None:
        self.refresh_review()

    def refresh_review(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        self.summary_box.setPlainText(json.dumps(wizard.build_summary_payload(), indent=2, sort_keys=True))
        rows = wizard.generate_schedule_preview()
        self.timeline_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [row.day_label, row.time_window, row.planned_start_at, row.experiment_type, str(row.repetition_index), row.labels.get("sessionId", "")]
            for column_index, value in enumerate(values):
                self.timeline_table.setItem(row_index, column_index, QTableWidgetItem(str(value)))

    def validatePage(self) -> bool:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        self.refresh_review()
        return wizard.launch_study_from_wizard()

    def _start_clicked(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        if wizard.launch_study_from_wizard():
            wizard.accept()

    def _save_draft_clicked(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        wizard.save_state()
        wizard.export_current_bundle(launch=False)
        QMessageBox.information(self, "Draft Saved", "Longitudinal study draft saved.")

    def _export_clicked(self) -> None:
        wizard = cast("LongitudinalStudyWizard", self.wizard())
        bundle = wizard.export_current_bundle(launch=False, include_yaml=True)
        QMessageBox.information(self, "Exported", "\n".join(bundle.values()))


class LongitudinalStudyWizard(QWizard):
    def __init__(
        self,
        paths: TouchprintPaths,
        study_manager: StudyManager,
        experiment_manager: ExperimentManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.study_manager = study_manager
        self.experiment_manager = experiment_manager
        self.state_path = self.paths.studies / "wizard_state.json"
        self.paths.studies.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
        self.created_study: StudyPlan | None = None
        self.setWindowTitle("Longitudinal Study Wizard")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)
        self.setButtonText(QWizard.WizardButton.FinishButton, "Start Study")
        self.setStartId(self.state.current_step_index if 0 <= self.state.current_step_index < WIZARD_PAGE_COUNT else 0)

        self.pages: dict[int, QWizardPage] = {
            0: StudyDefinitionPage(),
            1: ParticipantSetupPage(),
            2: ProtocolSelectionPage(),
            3: ScheduleBuilderPage(),
            4: EnvironmentLabelsPage(),
            5: ReviewLaunchPage(),
        }
        for page_id, page in self.pages.items():
            self.setPage(page_id, page)

        self.currentIdChanged.connect(self._handle_page_changed)
        self.finished.connect(self._handle_finished)

    def _load_state(self) -> LongitudinalWizardState:
        if not self.state_path.exists():
            return LongitudinalWizardState()
        try:
            return LongitudinalWizardState.from_dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Invalid wizard state; starting fresh.")
            return LongitudinalWizardState()

    def save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def set_current_step_index(self, index: int) -> None:
        self.state.current_step_index = index
        self.save_state()

    def _handle_page_changed(self, page_id: int) -> None:
        self.state.current_step_index = page_id if page_id >= 0 else 0
        self.save_state()
        self.refresh_all_previews()

    def refresh_all_previews(self) -> None:
        if 3 in self.pages and isinstance(self.pages[3], ScheduleBuilderPage):
            self.pages[3].refresh_preview()
        if 5 in self.pages and isinstance(self.pages[5], ReviewLaunchPage):
            self.pages[5].refresh_review()

    def build_summary_payload(self) -> dict[str, Any]:
        self._sync_state_from_pages()
        return {
            "wizardVersion": self.state.wizard_version,
            "studyName": self.state.study_name,
            "studyType": self.state.study_type,
            "description": self.state.description,
            "seed": self.state.seed,
            "participantId": self.state.participant_id,
            "dominantHand": self.state.dominant_hand,
            "devicePreference": self.state.device_preference,
            "selectedProtocols": self.state.selected_protocols,
            "repetitionsPerProtocol": self.state.repetitions_per_protocol,
            "intensityLevel": self.state.intensity_level,
            "schedule": self.state.schedule,
            "environmentLabels": self.state.environment_labels,
            "studyId": self.state.study_id or self._compute_study_id(),
            "derivedTemplateId": self.state.derived_template_id or self._derived_template_id(),
            "expectedSessionCount": len(self.generate_schedule_preview()),
        }

    def _sync_state_from_pages(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "store_state"):
                page.store_state()  # type: ignore[misc]
        self.save_state()

    def _compute_study_id(self) -> str:
        return _stable_id(
            "study",
            self.state.study_name or self.state.study_type,
            self.state.study_type,
            self.state.participant_id,
            self.state.seed,
        )

    def _derived_template_id(self) -> str:
        return _stable_id(
            "template",
            self.state.study_type,
            self.state.study_name or self.state.study_type,
            self.state.participant_id,
            self.state.seed,
        )

    def _intensity_factor(self) -> float:
        return {"low": 0.85, "medium": 1.0, "high": 1.2}.get(self.state.intensity_level, 1.0)

    def _selected_windows(self) -> list[str]:
        windows = list(self.state.schedule.get("windows") or [])
        return windows or ["morning"]

    def _anchor_datetime(self) -> datetime:
        raw = self.state.schedule.get("anchorStart")
        if raw:
            try:
                parsed = datetime.fromisoformat(str(raw))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _day_spacing(self) -> timedelta:
        delay_mode = str(self.state.schedule.get("delayMode", "24h"))
        if delay_mode == "7d":
            return timedelta(days=7)
        if delay_mode == "custom":
            return timedelta(hours=int(self.state.schedule.get("customDelayHours", 24)))
        return timedelta(days=1)

    def _selected_protocols(self) -> list[str]:
        return list(self.state.selected_protocols) or ["random_tap"]

    def _derived_steps(self) -> list[StudyStep]:
        intensity_factor = self._intensity_factor()
        protocol_steps: list[StudyStep] = []
        for index, protocol in enumerate(self._selected_protocols()):
            repetitions = max(1, int(self.state.repetitions_per_protocol))
            base_pause = max(1, int(round((3 + index) * intensity_factor)))
            interval = max(1, int(round((5 + index) * intensity_factor)))
            pacing_mode = "adaptive" if self.state.schedule.get("randomizeTimeDrift") else "fixed"
            protocol_steps.append(
                StudyStep(
                    step_id=f"{protocol}_step_{index:02d}",
                    experiment_type=protocol,
                    repetitions=repetitions,
                    pause_seconds=base_pause,
                    pacing_mode=pacing_mode,
                    interval_seconds=interval,
                    labels={
                        "protocolType": protocol,
                        "intensityLevel": self.state.intensity_level,
                        "studyType": self.state.study_type,
                    },
                    required_metadata={
                        "participantId": True,
                        "deviceType": True,
                        "inputMode": True,
                    },
                )
            )
        return protocol_steps

    def _derived_template(self) -> StudyTemplate:
        base_template = self.study_manager.get_template(self.state.study_type)
        return StudyTemplate(
            template_id=self._derived_template_id(),
            version=base_template.version,
            name=self.state.study_name or base_template.name,
            description=self.state.description or base_template.description,
            steps=self._derived_steps(),
            session_schedule={
                "sameDaySessions": max(1, int(self.state.schedule.get("sameDayRepetitions", 1))),
                "multiDaySessions": max(1, int(self.state.schedule.get("dayCount", 1))),
                "delayedRetestHours": max(1, int(round(self._day_spacing().total_seconds() / 3600.0))),
            },
            pacing_rules={
                "mode": "deterministic",
                "intervalSeconds": max(1, int(self.state.schedule.get("sessionSpacingMinutes", 20))),
                "mandatoryPauseSeconds": 5,
                "randomizeTimeDrift": bool(self.state.schedule.get("randomizeTimeDrift", True)),
                "timeDriftMinutes": int(self.state.schedule.get("timeDriftMinutes", 10)),
            },
            required_metadata={
                "participantId": True,
                "deviceType": True,
                "inputMode": True,
                "posture": True,
                "cognitiveState": True,
            },
            labels={
                "studyWizard": True,
                "studyType": self.state.study_type,
                "intensityLevel": self.state.intensity_level,
            },
            deterministic_seed=self.state.seed,
        )

    def generate_schedule_preview(self) -> list[WizardScheduleRow]:
        self._sync_state_from_pages()
        study_id = self.state.study_id or self._compute_study_id()
        template = self._derived_template()
        selected_protocols = self._selected_protocols()
        day_count = max(1, int(self.state.schedule.get("dayCount", 1)))
        same_day_repetitions = max(1, int(self.state.schedule.get("sameDayRepetitions", 1)))
        daily_repetitions = max(1, int(self.state.schedule.get("dailyRepetitions", 1)))
        spacing_minutes = max(1, int(self.state.schedule.get("sessionSpacingMinutes", 20)))
        drift_minutes = max(0, int(self.state.schedule.get("timeDriftMinutes", 10)))
        randomize = bool(self.state.schedule.get("randomizeTimeDrift", True))
        windows = self._selected_windows()
        anchor = self._anchor_datetime()
        day_spacing = self._day_spacing()
        rng = random.Random(_stable_seed(study_id, self.state.participant_id, self.state.seed, self.state.study_type))

        rows: list[WizardScheduleRow] = []
        session_counter = 0
        for day_index in range(day_count):
            day_date = anchor + day_spacing * day_index
            for daily_repeat in range(daily_repetitions):
                for protocol_index, protocol in enumerate(selected_protocols):
                    for repetition_index in range(max(1, self.state.repetitions_per_protocol)):
                        for same_day_index in range(same_day_repetitions):
                            window = windows[session_counter % len(windows)]
                            hour, minute = _time_window_label_to_hour_minute(window)
                            planned = day_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            planned += timedelta(minutes=same_day_index * spacing_minutes)
                            planned += timedelta(minutes=daily_repeat * spacing_minutes)
                            if randomize and drift_minutes:
                                planned += timedelta(minutes=rng.randint(-drift_minutes, drift_minutes))
                            session_id = _stable_id(
                                "study_session",
                                study_id,
                                day_index,
                                daily_repeat,
                                protocol_index,
                                repetition_index,
                                same_day_index,
                                protocol,
                            )
                            labels = {
                                "studyId": study_id,
                                "studyType": self.state.study_type,
                                "studyName": self.state.study_name or template.name,
                                "stepId": f"{protocol}_step_{protocol_index:02d}",
                                "timeWindow": window,
                                "intensityLevel": self.state.intensity_level,
                                "dailyRepeatIndex": daily_repeat,
                                "sameDayRepeatIndex": same_day_index,
                                "sessionId": session_id,
                            }
                            rows.append(
                                WizardScheduleRow(
                                    day_index=day_index,
                                    day_label=f"Day {day_index + 1}",
                                    time_window=window,
                                    planned_start_at=planned.astimezone(timezone.utc).isoformat(),
                                    step_id=f"{protocol}_step_{protocol_index:02d}",
                                    experiment_type=protocol,
                                    repetition_index=repetition_index,
                                    daily_repetition_index=daily_repeat,
                                    same_day_repetition_index=same_day_index,
                                    labels=labels,
                                )
                            )
                            session_counter += 1
        self.state.study_id = study_id
        self.state.derived_template_id = template.template_id
        self.state.template_version = template.version
        self.state.study_calendar = [row.to_dict() for row in rows]
        self.state.expected_session_count = len(rows)
        return rows

    def export_current_bundle(self, *, launch: bool, include_yaml: bool = False) -> dict[str, str]:
        self._sync_state_from_pages()
        study_id = self.state.study_id or self._compute_study_id()
        template = self._derived_template()
        schedule_rows = self.generate_schedule_preview()
        study_dir = self.paths.studies / study_id
        study_dir.mkdir(parents=True, exist_ok=True)

        draft_payload = self.build_summary_payload()
        files = {
            "draftJson": str(study_dir / "longitudinal_wizard_draft.json"),
        }
        (study_dir / "longitudinal_wizard_draft.json").write_text(json.dumps(draft_payload, indent=2, sort_keys=True), encoding="utf-8")
        if include_yaml:
            yaml_path = study_dir / "longitudinal_wizard_draft.yaml"
            yaml_path.write_text(_safe_yaml_dump(draft_payload), encoding="utf-8")
            files["draftYaml"] = str(yaml_path)
        if launch:
            study = self._build_study_object(template, schedule_rows, study_id)
            files.update(
                self.study_manager.export_study_bundle(
                    study,
                    participant_metadata=self.state.participant_metadata,
                    protocol_manifest=self._protocol_manifest(template, schedule_rows),
                    environment_labels=self.state.environment_labels,
                    output_dir=study_dir,
                )
            )
        self.state.exported_paths = files
        self.save_state()
        return files

    def _build_study_object(self, template: StudyTemplate, schedule_rows: list[WizardScheduleRow], study_id: str) -> StudyPlan:
        schedule = [
            StudySessionSpec(
                study_id=study_id,
                study_template_id=template.template_id,
                study_template_version=template.version,
                session_id=str(row.labels["sessionId"]),
                participant_id=self.state.participant_id,
                step_id=row.step_id,
                step_index=protocol_index_from_step_id(row.step_id),
                experiment_type=row.experiment_type,
                planned_start_at=row.planned_start_at,
                pause_before_seconds=int(self.state.schedule.get("sessionSpacingMinutes", 20)),
                interval_seconds=max(1, int(self.state.schedule.get("sessionSpacingMinutes", 20))),
                pacing_mode="adaptive" if self.state.schedule.get("randomizeTimeDrift", True) else "fixed",
                repetition_index=row.repetition_index,
                day_index=row.day_index,
                labels=row.labels,
                required_metadata={
                    "participantId": True,
                    "deviceType": True,
                    "inputMode": True,
                    "posture": True,
                    "cognitiveState": True,
                },
            )
            for row in schedule_rows
        ]
        study = StudyPlan(
            study_id=study_id,
            template_id=template.template_id,
            template_version=template.version,
            participant_id=self.state.participant_id,
            created_at=_utc_now(),
            start_at=self._anchor_datetime().isoformat(),
            status="created",
            template_name=template.name,
            template_description=template.description,
            schedule=schedule,
        )
        return study

    def _protocol_manifest(self, template: StudyTemplate, schedule_rows: list[WizardScheduleRow]) -> dict[str, Any]:
        return {
            "studyId": self.state.study_id or self._compute_study_id(),
            "studyName": self.state.study_name,
            "studyType": self.state.study_type,
            "studyTemplateId": template.template_id,
            "studyTemplateVersion": template.version,
            "participantId": self.state.participant_id,
            "selectedProtocols": self.state.selected_protocols,
            "repetitionsPerProtocol": self.state.repetitions_per_protocol,
            "intensityLevel": self.state.intensity_level,
            "scheduleConfig": self.state.schedule,
            "environmentLabels": self.state.environment_labels,
            "participantMetadata": self.state.participant_metadata,
            "sessionCount": len(schedule_rows),
        }

    def launch_study_from_wizard(self) -> bool:
        self._sync_state_from_pages()
        if not self.state.study_name.strip():
            QMessageBox.warning(self, "Validation", "Study name is required.")
            return False
        if not self.state.participant_id.strip():
            QMessageBox.warning(self, "Validation", "Participant ID is required.")
            return False
        if not self.state.selected_protocols:
            QMessageBox.warning(self, "Validation", "Select at least one protocol.")
            return False

        study_id = self._compute_study_id()
        self.state.study_id = study_id
        template = self._derived_template()
        self.study_manager.register_template(template)
        schedule_rows = self.generate_schedule_preview()
        study = self._build_study_object(template, schedule_rows, study_id)
        study.template_name = self.state.study_name or template.name
        study.template_description = self.state.description or template.description
        self.study_manager.active_study = study
        self.study_manager.save_active_study()
        export_files = self.study_manager.export_study_bundle(
            study,
            participant_metadata=self.state.participant_metadata,
            protocol_manifest=self._protocol_manifest(template, schedule_rows),
            environment_labels=self.state.environment_labels,
        )
        self.experiment_manager.queue_study_sessions(
            [row.to_dict() for row in schedule_rows],
            study_id=study.study_id,
            template_id=template.template_id,
            participant_id=study.participant_id,
        )
        self.experiment_manager.study_manager = self.study_manager
        self.created_study = study
        self.state.exported_paths = export_files
        self.save_state()
        return True

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.save_state()
        super().closeEvent(event)

    def _handle_finished(self, result: int) -> None:
        self.save_state()
        if result == QDialog.DialogCode.Accepted and self.created_study is not None:
            logger.info("Launched longitudinal study %s", self.created_study.study_id)


def protocol_index_from_step_id(step_id: str) -> int:
    if "_step_" not in step_id:
        return 0
    try:
        return int(step_id.rsplit("_step_", 1)[1])
    except ValueError:
        return 0


def wizard_selected_protocols(page: ProtocolSelectionPage) -> list[str]:
    return [protocol for protocol, checkbox in page.protocol_checkboxes.items() if checkbox.isChecked()]
