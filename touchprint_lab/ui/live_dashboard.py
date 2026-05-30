from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.analyzer.human_likeness import HumanLikenessMetrics, compute_human_likeness_metrics
from touchprint_lab.analyzer.readiness import ReadinessReport, run_system_readiness_check
from touchprint_lab.live.canvas_mirror import build_canvas_mirror_frame
from touchprint_lab.live.groove3d import build_groove3d_trace
from touchprint_lab.analyzer.human_likeness_calibration import run_human_likeness_calibration
from touchprint_lab.analyzer.human_vs_synthetic_validation import run_human_vs_synthetic_validation
from touchprint_lab.rendering.groove3d_renderer import Groove3DRendererBase, select_renderer
from touchprint_lab.live.telemetry_server import LiveTelemetryServer, TelemetrySnapshot
from touchprint_lab.live.research_metrics import (
    compute_groove_stability_metrics,
    compute_pin_rhythm_metrics,
    compute_pressure_fingerprint_metrics,
)
from touchprint_lab.ui.help_registry import (
    human_likeness_research_guide,
    live_telemetry_tooltip,
    panel_help_for_live_panel,
    panel_tooltip_for_live_panel,
)
from touchprint_lab.ui.live_workspace import LiveWorkspaceLayoutManager
from touchprint_lab.utils.numeric import safe_nanstd
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)
EMPTY_PIN_LABEL = "PIN: _ _ _ _"


@dataclass(slots=True)
class PanelSpec:
    priority: str
    minimum_height: int
    compact_height: int
    collapsible: bool = False


@dataclass(slots=True)
class PanelRenderContext:
    width: int
    height: int
    layout_mode: str
    compact_height: bool
    panel_mode: str


class LivePanelCard(QFrame):
    def __init__(
        self,
        dashboard: "LiveDashboardWidget",
        panel_id: str,
        title: str,
        content_widget: QWidget,
        *,
        compact_min_height: int = 180,
        collapsible: bool = False,
    ) -> None:
        super().__init__()
        self.dashboard = dashboard
        self.panel_id = panel_id
        self.title = title
        self.content_widget = content_widget
        self.compact_min_height = compact_min_height
        self.collapsible = collapsible
        self.collapsed = False
        self._focused = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_tip = panel_tooltip_for_live_panel(panel_id)
        focus_tip = live_telemetry_tooltip("panel_double_click_focus", "Double-click to open focus view.")
        self.setToolTip(f"{panel_tip}\n{focus_tip}")
        self.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.header = QFrame()
        self.header.setObjectName(f"LivePanelHeader_{panel_id}")
        self.header.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 9px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 11px; font-weight: 600;")
        self.title_label.setToolTip(panel_tip)
        header_layout.addWidget(self.title_label)
        self.help_button = QToolButton()
        self.help_button.setText("?")
        self.help_button.setToolTip(
            live_telemetry_tooltip("panel_help", "Open panel help.")
        )
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.clicked.connect(lambda: self.dashboard.show_panel_help(self.panel_id))
        self.help_button.setStyleSheet(
            """
            QToolButton {
                color: #f5f5f7;
                padding: 2px 6px;
                border-radius: 7px;
                background: rgba(255, 255, 255, 0.08);
                font-size: 10px;
                min-width: 16px;
                max-width: 18px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 0.16);
            }
            """
        )
        header_layout.addWidget(self.help_button)
        header_layout.addStretch(1)
        self.collapse_button = QToolButton()
        self.collapse_button.setText("▴")
        self.collapse_button.setToolTip(
            live_telemetry_tooltip("panel_collapse", "Collapse or expand panel body.")
        )
        self.collapse_button.clicked.connect(self._toggle_collapsed)
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_button.setVisible(self.collapsible)

        header_buttons = [self.collapse_button]
        self.layout_menu_button = QToolButton()
        self.layout_menu_button.setText("⋯")
        self.layout_menu_button.setToolTip("Panel layout actions")
        self.layout_menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.layout_menu = QMenu(self)
        self.action_move_left = self.layout_menu.addAction("Move Left")
        self.action_move_right = self.layout_menu.addAction("Move Right")
        self.action_move_up = self.layout_menu.addAction("Move Up")
        self.action_move_down = self.layout_menu.addAction("Move Down")
        self.layout_menu.addSeparator()
        self.action_expand = self.layout_menu.addAction("Expand")
        self.action_collapse = self.layout_menu.addAction("Collapse")
        self.layout_menu.addSeparator()
        self.action_height_up = self.layout_menu.addAction("Increase Height")
        self.action_height_down = self.layout_menu.addAction("Decrease Height")
        self.action_move_left.triggered.connect(lambda: self.dashboard.move_panel(self.panel_id, "left"))
        self.action_move_right.triggered.connect(lambda: self.dashboard.move_panel(self.panel_id, "right"))
        self.action_move_up.triggered.connect(lambda: self.dashboard.move_panel(self.panel_id, "up"))
        self.action_move_down.triggered.connect(lambda: self.dashboard.move_panel(self.panel_id, "down"))
        self.action_expand.triggered.connect(lambda: self.dashboard.set_panel_collapsed(self.panel_id, False))
        self.action_collapse.triggered.connect(lambda: self.dashboard.set_panel_collapsed(self.panel_id, True))
        self.action_height_up.triggered.connect(lambda: self.dashboard.adjust_panel_height(self.panel_id, +40))
        self.action_height_down.triggered.connect(lambda: self.dashboard.adjust_panel_height(self.panel_id, -40))
        self.layout_menu_button.setMenu(self.layout_menu)
        self.layout_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header_buttons.append(self.layout_menu_button)
        for button in header_buttons:
            button.setStyleSheet(
                """
                QToolButton {
                    color: #f5f5f7;
                    padding: 4px 8px;
                    border-radius: 7px;
                    background: rgba(255, 255, 255, 0.08);
                    font-size: 10px;
                }
                QToolButton:hover {
                    background: rgba(255, 255, 255, 0.16);
                }
                """
            )
            header_layout.addWidget(button)

        self.body = QFrame()
        self.body.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }
            """
        )
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.content_widget, 1)

        layout.addWidget(self.header)
        layout.addWidget(self.body, 1)
        self._apply_state(False)

    def set_compact_mode(self, enabled: bool) -> None:
        minimum_height = max(120, self.compact_min_height - 30) if enabled else self.compact_min_height
        self.content_widget.setMinimumHeight(minimum_height)
        if self.collapsed:
            self.content_widget.setMinimumHeight(0)

    def _apply_state(self, focused: bool) -> None:
        self._focused = focused
        if focused:
            self.title_label.setText(f"Focused: {self.title}")
            self.title_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #5ac8fa;")
            self.collapse_button.setVisible(False)
            self.header.setStyleSheet(
                """
                QFrame {
                    background: rgba(90, 200, 250, 0.14);
                    border: 1px solid rgba(90, 200, 250, 0.58);
                    border-radius: 9px;
                }
                QLabel {
                    color: #f5f5f7;
                }
                """
            )
        else:
            self.title_label.setText(self.title)
            self.title_label.setStyleSheet("font-size: 11px; font-weight: 600;")
            self.collapse_button.setVisible(self.collapsible)
            self.header.setStyleSheet(
                """
                QFrame {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 9px;
                }
                QLabel {
                    color: #f5f5f7;
                }
                """
            )

    def set_collapsed(self, collapsed: bool) -> None:
        if not self.collapsible:
            self.collapsed = False
            self.body.setVisible(True)
            return
        self.collapsed = collapsed
        self.body.setVisible(not collapsed)
        self.collapse_button.setText("Expand" if collapsed else "Collapse")

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not self.collapsed)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.dashboard.toggle_panel_focus_modal(self.panel_id)
        super().mouseDoubleClickEvent(event)

    def render_context(self, layout_mode: str, compact_height: bool) -> PanelRenderContext:
        width = max(self.width(), self.content_widget.width(), 1)
        height = max(self.height(), self.content_widget.height(), 1)
        if compact_height or height < 150:
            panel_mode = "mini"
        elif layout_mode == "small" or width < 360:
            panel_mode = "compact"
        else:
            panel_mode = "normal"
        return PanelRenderContext(
            width=width,
            height=height,
            layout_mode=layout_mode,
            compact_height=compact_height,
            panel_mode=panel_mode,
        )


class HumanLikenessDetailsDialog(QDialog):
    def __init__(self, metrics: HumanLikenessMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Human-Likeness Details")
        self.resize(560, 460)
        self.setModal(False)
        self._calibration_seed = 42
        self._calibration_pdf_path: Path | None = None
        self._current_session_id: str | None = None
        self._current_events: list[dict[str, Any]] = []
        self._current_last_timestamp: float | None = None
        self._research_guide_dialog: QDialog | None = None
        self.setStyleSheet(
            """
            QDialog {
                background: #121317;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        headline = QLabel(self._headline_text(metrics))
        headline.setStyleSheet("font-size: 14px; font-weight: 700; color: #5ac8fa;")
        header_row.addWidget(headline)
        header_row.addStretch(1)
        self.research_help_button = QToolButton()
        self.research_help_button.setText("?")
        self.research_help_button.setToolTip(
            live_telemetry_tooltip("human_likeness_research_help", "Open Human-Likeness Research Guide.")
        )
        self.research_help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.research_help_button.setStyleSheet(
            """
            QToolButton {
                color: #f5f5f7;
                padding: 4px 8px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.10);
                font-weight: 700;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 0.16);
            }
            """
        )
        self.research_help_button.clicked.connect(self._open_research_guide)
        header_row.addWidget(self.research_help_button)
        self.evaluate_current_button = QPushButton("Evaluate Current Session")
        self.evaluate_current_button.setToolTip(
            live_telemetry_tooltip("evaluate_current_session", "Evaluate buffered live session events.")
        )
        self.evaluate_current_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.evaluate_current_button.clicked.connect(self._evaluate_current_session)
        header_row.addWidget(self.evaluate_current_button)
        self.run_calibration_button = QPushButton("Run Calibration")
        self.run_calibration_button.setToolTip(
            live_telemetry_tooltip("run_calibration", "Run synthetic calibration.")
        )
        self.run_calibration_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_calibration_button.clicked.connect(self._run_calibration)
        header_row.addWidget(self.run_calibration_button)
        self.preview_pdf_button = QPushButton("Preview Calibration PDF")
        self.preview_pdf_button.setToolTip(
            live_telemetry_tooltip("preview_calibration_pdf", "Open calibration PDF report.")
        )
        self.preview_pdf_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_pdf_button.setEnabled(False)
        self.preview_pdf_button.clicked.connect(self._preview_calibration_pdf)
        header_row.addWidget(self.preview_pdf_button)
        self.run_validation_button = QPushButton("Run Human vs Synthetic Validation")
        self.run_validation_button.setToolTip(
            live_telemetry_tooltip("run_human_vs_synthetic_validation", "Run human vs synthetic validation.")
        )
        self.run_validation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_validation_button.clicked.connect(self._run_human_vs_synthetic_validation)
        header_row.addWidget(self.run_validation_button)
        layout.addLayout(header_row)

        disclaimer = QLabel("Research metric — not definitive bot detection.")
        disclaimer.setStyleSheet("font-size: 11px; color: #8e8e93;")
        layout.addWidget(disclaimer)

        self.current_header_label = QLabel()
        self.current_header_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.current_body_label = QLabel()
        self.current_body_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.current_body_label.setWordWrap(True)
        layout.addWidget(self.current_header_label)
        layout.addWidget(self.current_body_label)

        self.synthetic_header_label = QLabel()
        self.synthetic_header_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.synthetic_body_label = QLabel()
        self.synthetic_body_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.synthetic_body_label.setWordWrap(True)
        layout.addWidget(self.synthetic_header_label)
        layout.addWidget(self.synthetic_body_label)

        self.validation_header_label = QLabel()
        self.validation_header_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.validation_body_label = QLabel()
        self.validation_body_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.validation_body_label.setWordWrap(True)
        layout.addWidget(self.validation_header_label)
        layout.addWidget(self.validation_body_label)

        subscore_lines = [
            ("Timing Naturalness", metrics.timing_naturalness),
            ("Jitter Naturalness", metrics.jitter_naturalness),
            ("Pressure Naturalness", metrics.pressure_naturalness),
            ("Release Dynamics", metrics.release_dynamics),
            ("Repetition Diversity", metrics.repetition_diversity),
            ("Signal Quality", metrics.signal_quality),
        ]
        for label, value in subscore_lines:
            row = QLabel(f"{label}: {self._format_score(value)}")
            row.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
            layout.addWidget(row)

        interval_text = ", ".join(f"{value:.0f}ms" for value in metrics.recent_intervals_ms[-8:])
        intervals = QLabel(f"Recent PIN intervals: {interval_text if interval_text else 'collecting…'}")
        intervals.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px; color: #c7c7cc;")
        intervals.setWordWrap(True)
        layout.addWidget(intervals)

        variance = QLabel(
            "Variance: "
            f"force={self._format_optional(metrics.force_variance)}  "
            f"radius={self._format_optional(metrics.radius_variance)}"
        )
        variance.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px; color: #c7c7cc;")
        layout.addWidget(variance)

        flags = QPlainTextEdit()
        flags.setReadOnly(True)
        flags.setStyleSheet(
            """
            QPlainTextEdit {
                background: #0f1014;
                color: #f5f5f7;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                font-family: Menlo, Monaco, monospace;
                font-size: 11px;
            }
            """
        )
        text_lines = ["Explanation flags:"]
        if metrics.explanation_flags:
            text_lines.extend([f"- {value}" for value in metrics.explanation_flags])
        else:
            text_lines.append("- collecting live signal")
        if metrics.suspicious_flags:
            text_lines.append("")
            text_lines.append("Suspicious-pattern flags:")
            text_lines.extend([f"- {value}" for value in metrics.suspicious_flags])
        flags.setPlainText("\n".join(text_lines))
        layout.addWidget(flags, 1)

        self._reset_results()

    def _open_research_guide(self) -> None:
        payload = human_likeness_research_guide("en")
        dialog = QDialog(self)
        dialog.setWindowTitle(str(payload.get("title", "Human-Likeness Research Guide")))
        dialog.resize(760, 620)
        dialog.setModal(False)
        dialog.setStyleSheet(
            """
            QDialog {
                background: #121317;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        root_layout = QVBoxLayout(dialog)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        title_label = QLabel(str(payload.get("title", "Human-Likeness Research Guide")))
        title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #5ac8fa;")
        root_layout.addWidget(title_label)

        subtitle = str(payload.get("subtitle", "")).strip()
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
            root_layout.addWidget(subtitle_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(10)

        for section in payload.get("sections", []):
            heading = QLabel(str(section.get("heading", "Section")))
            heading.setStyleSheet("font-size: 13px; font-weight: 700; color: #5ac8fa;")
            body = QLabel(str(section.get("body", "")))
            body.setWordWrap(True)
            body.setStyleSheet("font-size: 11px; color: #f5f5f7;")
            content_layout.addWidget(heading)
            content_layout.addWidget(body)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        root_layout.addWidget(scroll, 1)

        close_button = QPushButton("Close")
        close_button.setToolTip(live_telemetry_tooltip("close_dialog", "Close this dialog window."))
        close_button.clicked.connect(dialog.close)
        root_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

        self._research_guide_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _headline_text(self, metrics: HumanLikenessMetrics) -> str:
        if metrics.human_likeness_score is None:
            return "Human-Likeness: collecting…"
        suspicion = self._suspicion_level(metrics.automation_suspicion_score)
        return (
            f"Human-Likeness {metrics.human_likeness_score:.0f}  |  "
            f"Suspicion {suspicion}  |  Confidence {metrics.confidence.title()}"
        )

    def _format_score(self, value: float | None) -> str:
        return "collecting…" if value is None else f"{value:.1f}/100"

    def _format_optional(self, value: float | None) -> str:
        return "—" if value is None else f"{value:.4f}"

    def _suspicion_level(self, value: float | None) -> str:
        if value is None:
            return "Collecting"
        if value >= 67.0:
            return "High"
        if value >= 34.0:
            return "Medium"
        return "Low"

    def sync_live_context(
        self,
        *,
        session_id: str | None,
        events: list[dict[str, Any]],
        last_timestamp: float | None,
    ) -> None:
        if self._current_session_id != session_id:
            self._current_session_id = session_id
            self._reset_results()
        self._current_events = [dict(event) for event in events]
        self._current_last_timestamp = last_timestamp
        if len(self._current_events) < 6:
            self._set_section(
                "current",
                "collecting",
                "Not enough live input to evaluate current session.",
                "#ff9f0a",
            )

    def evaluate_current_session_now(self) -> None:
        self._evaluate_current_session()

    def _reset_results(self) -> None:
        self._calibration_pdf_path = None
        self.preview_pdf_button.setEnabled(False)
        self._set_section("current", "not run", "Evaluate Current Session to analyze buffered live telemetry.", "#c7c7cc")
        self._set_section(
            "synthetic",
            "not run",
            "Run Calibration uses generated synthetic scenarios, not current live input.",
            "#c7c7cc",
        )
        self._set_section("validation", "not run", "Run Human vs Synthetic Validation to compare dataset sessions.", "#c7c7cc")

    def _set_section(self, section: str, state: str, body: str, color: str) -> None:
        title_map = {
            "current": "A. Current Live Session",
            "synthetic": "B. Synthetic Calibration",
            "validation": "C. Human vs Synthetic Validation",
        }
        header = f"{title_map[section]} — {state}"
        if section == "current":
            self.current_header_label.setText(header)
            self.current_header_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")
            self.current_body_label.setText(body)
        elif section == "synthetic":
            self.synthetic_header_label.setText(header)
            self.synthetic_header_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")
            self.synthetic_body_label.setText(body)
        else:
            self.validation_header_label.setText(header)
            self.validation_header_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color};")
            self.validation_body_label.setText(body)

    def _evaluate_current_session(self) -> None:
        touch_events = [event for event in self._current_events if event.get("messageType") == "touch_event"]
        if len(touch_events) < 6:
            self._set_section(
                "current",
                "collecting",
                "Not enough live input to evaluate current session.",
                "#ff9f0a",
            )
            return

        metrics = compute_human_likeness_metrics(touch_events)
        if metrics.human_likeness_score is None:
            self._set_section(
                "current",
                "collecting",
                "Not enough live input to evaluate current session.",
                "#ff9f0a",
            )
            return

        pin_events = [event for event in touch_events if event.get("digit") is not None]
        last_timestamp = self._current_last_timestamp
        if last_timestamp is None and touch_events:
            last_timestamp = float(touch_events[-1].get("timestamp", 0.0))
        body = (
            f"Current session evaluation complete\n"
            f"Session: {self._current_session_id or '—'}\n"
            f"Score: {metrics.human_likeness_score:.1f}  |  Suspicion: {metrics.automation_suspicion_score:.1f}  |  Confidence: {metrics.confidence.title()}\n"
            f"Events analyzed: {len(touch_events)}  |  PIN digit events: {len(pin_events)}\n"
            f"Last timestamp: {last_timestamp if last_timestamp is not None else '—'}"
        )
        self._set_section("current", "completed", body, "#34c759")

    def _run_calibration(self) -> None:
        self.run_calibration_button.setEnabled(False)
        self.run_calibration_button.setText("Running…")
        self.preview_pdf_button.setEnabled(False)
        self._calibration_pdf_path = None
        self._set_section("synthetic", "collecting", "Running synthetic calibration scenarios…", "#ff9f0a")
        try:
            report = run_human_likeness_calibration(seed=self._calibration_seed)
            summary = report.summary
            pdf_path_raw = report.files.get("pdfReport")
            pdf_path = Path(str(pdf_path_raw)) if pdf_path_raw else None
            pdf_warning = report.files.get("pdfWarning")
            pdf_exists = bool(pdf_path and pdf_path.exists())
            if pdf_exists:
                self._calibration_pdf_path = pdf_path
                self.preview_pdf_button.setEnabled(True)
            pdf_text = f"PDF: {pdf_path}" if pdf_path else "PDF: not generated"
            run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (
                "Synthetic calibration complete\n"
                "Uses generated synthetic scenarios, not current live input.\n"
                f"Run: {run_time}\n"
                f"Seed: {self._calibration_seed}\n"
                f"Simulated human-like avg: {summary['averageHumanLikeScore']:.1f}\n"
                f"Synthetic regular avg: {summary['averageSyntheticRegularScore']:.1f}\n"
                f"Margin: {summary['separationMargin']:.1f}\n"
                f"Detection rate: {summary['suspiciousPatternDetectionRate'] * 100.0:.0f}%\n"
                f"Reports: {report.output_dir}\n"
                f"{pdf_text}"
            )
            if not pdf_exists:
                body += "\nCalibration completed, but PDF export failed."
                self._set_section("synthetic", "completed", body, "#ff9f0a")
            elif pdf_warning:
                body += f"\nWarning: {pdf_warning}"
                self._set_section("synthetic", "completed", body, "#ff9f0a")
            else:
                self._set_section("synthetic", "completed", body, "#34c759")
        except Exception as error:
            logger.exception("Human-likeness calibration failed")
            self._set_section("synthetic", "failed", f"Synthetic calibration failed: {error}", "#ff453a")
        finally:
            self.run_calibration_button.setEnabled(True)
            self.run_calibration_button.setText("Run Calibration")

    def _preview_calibration_pdf(self) -> None:
        if self._calibration_pdf_path is None or not self._calibration_pdf_path.exists():
            self.preview_pdf_button.setEnabled(False)
            self._set_section(
                "synthetic",
                "completed",
                "Calibration completed, but PDF export failed.",
                "#ff9f0a",
            )
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._calibration_pdf_path)))
        if not opened:
            self._set_section(
                "synthetic",
                "completed",
                "PDF preview failed. Open manually:\n"
                f"{self._calibration_pdf_path}",
                "#ff9f0a",
            )

    def _run_human_vs_synthetic_validation(self) -> None:
        self.run_validation_button.setEnabled(False)
        self.run_validation_button.setText("Running…")
        self._set_section("validation", "collecting", "Running human vs synthetic validation…", "#ff9f0a")
        try:
            report = run_human_vs_synthetic_validation()
            summary = report.summary
            body = (
                "Human vs Synthetic validation complete\n"
                f"Real avg {summary['realHumanAverageScore']:.1f} • "
                f"Synthetic avg {summary['syntheticAverageScore']:.1f} • "
                f"Margin {summary['separationMargin']:.1f} • "
                f"False suspicious {summary['falseSuspiciousRate'] * 100.0:.0f}% • "
                f"Detection {summary['suspiciousDetectionRate'] * 100.0:.0f}%\n"
                f"{summary['message']}\n"
                f"Reports: {report.output_dir}"
            )
            if summary.get("noRealSessions", False):
                self._set_section("validation", "completed", body, "#ff9f0a")
            else:
                self._set_section("validation", "completed", body, "#34c759")
        except Exception as error:
            logger.exception("Human vs synthetic validation failed")
            self._set_section("validation", "failed", f"Human vs synthetic validation failed: {error}", "#ff453a")
        finally:
            self.run_validation_button.setEnabled(True)
            self.run_validation_button.setText("Run Human vs Synthetic Validation")

class LiveDashboardWidget(QWidget):
    def __init__(self, live_server: LiveTelemetryServer, paths: TouchprintPaths, parent: QWidget | None = None):
        super().__init__(parent)
        self.live_server = live_server
        self.paths = paths
        self._plot_error_keys: set[str] = set()
        self._pin_highlight_token = 0
        self._panel_cards: dict[str, LivePanelCard] = {}
        self._panel_specs: dict[str, PanelSpec] = {}
        self._focused_modal_panel_id: str | None = None
        self._focus_modal_dialog: QDialog | None = None
        self._closing_focus_modal = False
        self._layout_mode_override: str = "auto"
        self._responsive_mode: str = "large"
        self._compact_height_mode: bool = False
        self._latest_human_likeness_metrics: HumanLikenessMetrics | None = None
        self._human_likeness_dialog: HumanLikenessDetailsDialog | None = None
        self._panel_help_dialog: QDialog | None = None
        self._readiness_dialog: QDialog | None = None
        self._groove3d_last_update_monotonic = 0.0
        self._groove3d_update_interval_s = 1.0 / 20.0
        self._groove3d_max_points = 500
        self._workspace_settings_path = Path(__file__).resolve().parents[2] / "processed" / "settings" / "live_workspace_layout.json"
        self._workspace: LiveWorkspaceLayoutManager | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pg.setConfigOptions(antialias=True)

        self._build_ui()
        self._install_timer()
        self.refresh()

    def _build_ui(self) -> None:
        self.setObjectName("LiveTelemetryDashboard")
        self.setStyleSheet(
            """
            #LiveTelemetryDashboard {
                background: #0b0b0d;
            }
            """
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("LiveStatusBar")
        self.status_bar.setStyleSheet(
            """
            #LiveStatusBar {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.setSpacing(10)

        self.connection_chip = self._make_chip("disconnected")
        self.connection_chip.setToolTip(live_telemetry_tooltip("status_connection", "Live telemetry connection state."))
        self.device_chip = self._make_chip("device: —")
        self.device_chip.setToolTip(live_telemetry_tooltip("status_device", "Active source device."))
        self.input_chip = self._make_chip("input: —")
        self.input_chip.setToolTip(live_telemetry_tooltip("status_input", "Current input mode."))
        self.sample_rate_chip = self._make_chip("sample rate: 0.00 Hz")
        self.sample_rate_chip.setToolTip(live_telemetry_tooltip("status_sample_rate", "Current sample rate."))
        self.session_chip = self._make_chip("session: —")
        self.session_chip.setToolTip(live_telemetry_tooltip("status_session", "Current active session."))
        self.export_chip = self._make_chip("export: live_only")
        self.export_chip.setToolTip(live_telemetry_tooltip("status_export", "Current export verification status."))
        self.readiness_button = QPushButton("System Readiness")
        self.readiness_button.setToolTip("Run pre-study readiness checklist and generate readiness report.")
        self.readiness_button.clicked.connect(self._open_readiness_dialog)
        self.layout_preset_selector = QComboBox()
        self.layout_preset_selector.addItems(
            ["Research Cockpit", "PIN Study", "Human-Likeness Focus", "Groove Analysis", "Compact Screen", "Custom"]
        )
        self.layout_preset_selector.setToolTip("Select Live Telemetry workspace preset.")
        self.layout_save_button = QPushButton("Save Layout")
        self.layout_save_button.setToolTip("Save current custom panel arrangement.")
        self.layout_reset_button = QPushButton("Reset Layout")
        self.layout_reset_button.setToolTip("Reset layout to default preset.")
        self.debug_toggle = QToolButton()
        self.debug_toggle.setText("Debug")
        self.debug_toggle.setToolTip(
            live_telemetry_tooltip("debug_toggle", "Show or hide developer diagnostics.")
        )
        self.debug_toggle.clicked.connect(self._toggle_debug_panel)
        self.debug_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.debug_toggle.setStyleSheet(
            """
            QToolButton {
                color: #f5f5f7;
                padding: 6px 10px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.10);
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 0.16);
            }
            """
        )

        status_layout.addWidget(self.connection_chip)
        status_layout.addWidget(self.device_chip)
        status_layout.addWidget(self.input_chip)
        status_layout.addWidget(self.sample_rate_chip)
        status_layout.addWidget(self.session_chip)
        status_layout.addWidget(self.export_chip)
        status_layout.addWidget(self.readiness_button)
        status_layout.addWidget(QLabel("Layout:"))
        status_layout.addWidget(self.layout_preset_selector)
        status_layout.addWidget(self.layout_save_button)
        status_layout.addWidget(self.layout_reset_button)
        status_layout.addStretch(1)
        status_layout.addWidget(self.debug_toggle)

        root_layout.addWidget(self.status_bar)

        self.control_message_label = QLabel()
        self.control_message_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.control_message_label.setStyleSheet(
            """
            QLabel {
                color: #ff9f0a;
                background: rgba(255, 159, 10, 0.10);
                border: 1px solid rgba(255, 159, 10, 0.18);
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
            }
            """
        )
        self.control_message_label.setVisible(False)
        root_layout.addWidget(self.control_message_label)

        self.pin_mirror_frame = self.pin_rhythm_frame = QFrame()
        self.pin_mirror_frame.setObjectName("LivePinRhythm")
        self.pin_mirror_frame.setMinimumHeight(200)
        self.pin_mirror_frame.setStyleSheet(
            """
            #LivePinRhythm {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        pin_layout = QVBoxLayout(self.pin_mirror_frame)
        pin_layout.setContentsMargins(10, 8, 10, 8)
        pin_layout.setSpacing(6)

        pin_header = QHBoxLayout()
        pin_title = QLabel("PIN Rhythm Strip")
        pin_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.pin_sequence_label = QLabel(EMPTY_PIN_LABEL)
        self.pin_sequence_label.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 12px;")
        self.pin_sequence_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pin_rhythm_score_label = QLabel("Consistency: —")
        self.pin_rhythm_score_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        pin_header.addWidget(pin_title)
        pin_header.addStretch(1)
        pin_header.addWidget(self.pin_rhythm_score_label)
        pin_header.addWidget(self.pin_sequence_label)
        pin_layout.addLayout(pin_header)

        self.pin_rhythm_bar_label = QLabel("| collecting... |")
        self.pin_rhythm_bar_label.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 12px; color: #5ac8fa;")
        self.pin_rhythm_bar_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pin_detail_label = QLabel("Waiting for PIN input")
        self.pin_detail_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        self.pin_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pin_feedback_label = QLabel("Action: —")
        self.pin_feedback_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        pin_layout.addWidget(self.pin_rhythm_bar_label)
        pin_layout.addWidget(self.pin_detail_label)
        pin_layout.addWidget(self.pin_feedback_label)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.pin_cells = {}
        pin_rows: list[list[str | None]] = [
            ["1", "2", "3"],
            ["4", "5", "6"],
            ["7", "8", "9"],
            [None, "0", None],
        ]
        for row_index, row in enumerate(pin_rows):
            for column_index, value in enumerate(row):
                if value is None:
                    spacer = QLabel("")
                    spacer.setMinimumSize(16, 16)
                    grid.addWidget(spacer, row_index, column_index)
                    continue
                cell = self._make_pin_cell(value)
                self.pin_cells[value] = cell
                grid.addWidget(cell, row_index, column_index)
        pin_layout.addLayout(grid)

        self.trajectory_plot = self._make_plot("Touch Trajectory", minimum_height=240)
        self.force_plot = self._make_plot("Force / Radius Timeline", minimum_height=240)
        self.signature_plot = self._make_plot("Signature Layer", minimum_height=240)
        self.groove_plot = self._make_plot("Groove View", minimum_height=240)
        self.groove3d_frame = QFrame()
        self.groove3d_frame.setMinimumHeight(220)
        self.groove3d_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        groove3d_layout = QVBoxLayout(self.groove3d_frame)
        groove3d_layout.setContentsMargins(10, 8, 10, 8)
        groove3d_layout.setSpacing(6)

        groove3d_header = QHBoxLayout()
        groove3d_title = QLabel("Groove View 3D")
        groove3d_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.groove3d_mode_selector = QComboBox()
        self.groove3d_mode_selector.addItems(["Force", "Radius", "Layer Depth"])
        self.groove3d_mode_selector.setToolTip(
            live_telemetry_tooltip("groove3d_z_mode", "Choose Z mode.")
        )
        self.groove3d_mode_selector.setCurrentIndex(0)
        self.groove3d_renderer_selector = QComboBox()
        self.groove3d_renderer_selector.addItems(["Auto", "Metal", "OpenGL", "2D fallback"])
        self.groove3d_renderer_selector.setToolTip(
            live_telemetry_tooltip("groove3d_renderer_selector", "Select renderer backend.")
        )
        self.groove3d_reset_camera_button = QPushButton("Reset Camera")
        self.groove3d_reset_camera_button.setToolTip(
            live_telemetry_tooltip("groove3d_reset_camera", "Reset 3D camera.")
        )
        self.groove3d_auto_rotate_toggle = QToolButton()
        self.groove3d_auto_rotate_toggle.setText("Auto Rotate")
        self.groove3d_auto_rotate_toggle.setCheckable(True)
        self.groove3d_auto_rotate_toggle.setToolTip(
            live_telemetry_tooltip("groove3d_auto_rotate", "Auto rotate 3D view.")
        )
        self.groove3d_status_label = QLabel("Z mode: Force • Renderer: —")
        self.groove3d_status_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.groove3d_renderer_reason_label = QLabel("")
        self.groove3d_renderer_reason_label.setStyleSheet("font-size: 10px; color: #8e8e93;")
        self.groove3d_renderer_reason_label.setWordWrap(True)

        groove3d_header.addWidget(groove3d_title)
        groove3d_header.addStretch(1)
        groove3d_header.addWidget(self.groove3d_status_label)
        groove3d_header.addWidget(self.groove3d_mode_selector)
        groove3d_header.addWidget(self.groove3d_renderer_selector)
        groove3d_header.addWidget(self.groove3d_reset_camera_button)
        groove3d_header.addWidget(self.groove3d_auto_rotate_toggle)
        groove3d_layout.addLayout(groove3d_header)
        groove3d_layout.addWidget(self.groove3d_renderer_reason_label)

        self.groove3d_container = QFrame()
        groove3d_container_layout = QVBoxLayout(self.groove3d_container)
        groove3d_container_layout.setContentsMargins(0, 0, 0, 0)
        groove3d_container_layout.setSpacing(0)
        self.groove3d_fallback_label = QLabel("3D Groove View unavailable on this system.")
        self.groove3d_fallback_label.setWordWrap(True)
        self.groove3d_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.groove3d_fallback_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.groove3d_fallback_label.setVisible(False)
        self.groove3d_renderer: Groove3DRendererBase | None = None
        self._setup_groove3d_renderer(groove3d_container_layout, "auto")
        groove3d_layout.addWidget(self.groove3d_container, 1)

        self.groove3d_mode_selector.currentTextChanged.connect(self._on_groove3d_mode_changed)
        self.groove3d_renderer_selector.currentTextChanged.connect(self._on_groove3d_renderer_changed)
        self.groove3d_reset_camera_button.clicked.connect(self._reset_groove3d_camera)
        self.groove3d_auto_rotate_toggle.toggled.connect(self._on_groove3d_auto_rotate_toggled)
        self.phase_plot = self._make_plot("Phase Timeline", minimum_height=240)
        self.logger_canvas_frame = QFrame()
        self.logger_canvas_frame.setMinimumHeight(210)
        self.logger_canvas_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        logger_canvas_layout = QVBoxLayout(self.logger_canvas_frame)
        logger_canvas_layout.setContentsMargins(10, 8, 10, 8)
        logger_canvas_layout.setSpacing(6)
        logger_canvas_header = QHBoxLayout()
        logger_canvas_title = QLabel("Logger Canvas Mirror")
        logger_canvas_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.canvas_clear_button = QPushButton("Clear Mirror")
        self.canvas_clear_button.setToolTip(live_telemetry_tooltip("canvas_clear", "Clear mirrored canvas."))
        self.canvas_trails_toggle = QToolButton()
        self.canvas_trails_toggle.setText("Trails")
        self.canvas_trails_toggle.setCheckable(True)
        self.canvas_trails_toggle.setChecked(True)
        self.canvas_trails_toggle.setToolTip(live_telemetry_tooltip("canvas_trails", "Toggle touch trails."))
        self.canvas_force_toggle = QToolButton()
        self.canvas_force_toggle.setText("Force Thickness")
        self.canvas_force_toggle.setCheckable(True)
        self.canvas_force_toggle.setChecked(True)
        self.canvas_force_toggle.setToolTip(
            live_telemetry_tooltip("canvas_force_thickness", "Use force thickness.")
        )
        self.canvas_fit_button = QPushButton("Fit to Surface")
        self.canvas_fit_button.setToolTip(live_telemetry_tooltip("canvas_fit_surface", "Fit mirrored canvas bounds."))
        self.canvas_status_label = QLabel("bounds: inferred")
        self.canvas_status_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        logger_canvas_header.addWidget(logger_canvas_title)
        logger_canvas_header.addStretch(1)
        logger_canvas_header.addWidget(self.canvas_status_label)
        logger_canvas_header.addWidget(self.canvas_trails_toggle)
        logger_canvas_header.addWidget(self.canvas_force_toggle)
        logger_canvas_header.addWidget(self.canvas_fit_button)
        logger_canvas_header.addWidget(self.canvas_clear_button)
        logger_canvas_layout.addLayout(logger_canvas_header)
        self.logger_canvas_plot = self._make_plot("Logger Canvas", minimum_height=160)
        self.logger_canvas_plot.setAspectLocked(True, ratio=1.0)
        logger_canvas_layout.addWidget(self.logger_canvas_plot, 1)
        self._canvas_manual_clear_generation = 0
        self.canvas_clear_button.clicked.connect(self._clear_logger_canvas_mirror)
        self.canvas_fit_button.clicked.connect(self._fit_logger_canvas_mirror)

        self.pressure_frame = QFrame()
        self.pressure_frame.setMinimumHeight(190)
        self.pressure_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        pressure_layout = QVBoxLayout(self.pressure_frame)
        pressure_layout.setContentsMargins(10, 8, 10, 8)
        pressure_layout.setSpacing(6)
        pressure_title = QLabel("Pressure Fingerprint")
        pressure_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        pressure_layout.addWidget(pressure_title)
        self.pressure_hist_plot = self._make_plot("Pressure Histogram", minimum_height=120)
        pressure_layout.addWidget(self.pressure_hist_plot)
        self.pressure_summary_label = QLabel("Collecting...")
        self.pressure_summary_label.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
        self.pressure_summary_label.setWordWrap(True)
        pressure_layout.addWidget(self.pressure_summary_label)
        self.pressure_detail_label = QLabel("Force: —  Median: —  Std Dev: —  Radius Stability: —")
        self.pressure_detail_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        self.pressure_detail_label.setWordWrap(True)
        pressure_layout.addWidget(self.pressure_detail_label)

        self.groove_stability_frame = QFrame()
        self.groove_stability_frame.setMinimumHeight(190)
        self.groove_stability_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        groove_layout = QVBoxLayout(self.groove_stability_frame)
        groove_layout.setContentsMargins(10, 8, 10, 8)
        groove_layout.setSpacing(6)
        groove_title = QLabel("Groove Stability")
        groove_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        groove_layout.addWidget(groove_title)
        self.groove_stability_score_label = QLabel("Collecting...")
        self.groove_stability_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.groove_stability_score_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #5ac8fa;")
        groove_layout.addWidget(self.groove_stability_score_label)
        self.groove_stability_bar = QProgressBar()
        self.groove_stability_bar.setRange(0, 100)
        self.groove_stability_bar.setValue(0)
        self.groove_stability_bar.setTextVisible(True)
        self.groove_stability_bar.setFormat("%p%")
        self.groove_stability_bar.setStyleSheet(
            """
            QProgressBar {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                height: 18px;
                color: #f5f5f7;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #5ac8fa;
                border-radius: 8px;
            }
            """
        )
        groove_layout.addWidget(self.groove_stability_bar)
        self.groove_stability_detail_label = QLabel("Trajectory: —  Force: —  Timing: —  Layers: —")
        self.groove_stability_detail_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        self.groove_stability_detail_label.setWordWrap(True)
        groove_layout.addWidget(self.groove_stability_detail_label)
        self.groove_stability_status_label = QLabel("Waiting for live data")
        self.groove_stability_status_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        groove_layout.addWidget(self.groove_stability_status_label)

        self.human_likeness_frame = QFrame()
        self.human_likeness_frame.setMinimumHeight(190)
        self.human_likeness_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        hl_layout = QVBoxLayout(self.human_likeness_frame)
        hl_layout.setContentsMargins(10, 8, 10, 8)
        hl_layout.setSpacing(6)

        hl_header = QHBoxLayout()
        hl_title = QLabel("Human-Likeness")
        hl_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.human_likeness_details_button = QPushButton("Details")
        self.human_likeness_details_button.setToolTip(
            live_telemetry_tooltip("human_likeness_details", "Open Human-Likeness details.")
        )
        self.human_likeness_details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.human_likeness_details_button.clicked.connect(self._open_human_likeness_details)
        hl_header.addWidget(hl_title)
        hl_header.addStretch(1)
        hl_header.addWidget(self.human_likeness_details_button)
        hl_layout.addLayout(hl_header)

        self.human_likeness_score_label = QLabel("Collecting...")
        self.human_likeness_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.human_likeness_score_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #5ac8fa;")
        hl_layout.addWidget(self.human_likeness_score_label)

        self.human_likeness_meta_label = QLabel("Suspicion: —  |  Confidence: —")
        self.human_likeness_meta_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
        hl_layout.addWidget(self.human_likeness_meta_label)

        self.human_likeness_flags_label = QLabel("collecting live signal")
        self.human_likeness_flags_label.setStyleSheet("font-size: 11px; color: #c7c7cc;")
        self.human_likeness_flags_label.setWordWrap(True)
        hl_layout.addWidget(self.human_likeness_flags_label)

        self.human_likeness_disclaimer = QLabel("Research metric — not definitive bot detection.")
        self.human_likeness_disclaimer.setStyleSheet("font-size: 10px; color: #8e8e93;")
        hl_layout.addWidget(self.human_likeness_disclaimer)

        self._panel_specs = {
            "trajectory": PanelSpec("high", 210, 170, False),
            "force_radius": PanelSpec("high", 210, 170, False),
            "signature_layer": PanelSpec("medium", 200, 150, False),
            "groove_view": PanelSpec("medium", 200, 150, True),
            "groove_view_3d": PanelSpec("medium", 210, 160, True),
            "logger_canvas_mirror": PanelSpec("high", 210, 160, True),
            "phase_timeline": PanelSpec("low", 160, 100, True),
            "pin_keyboard_mirror": PanelSpec("high", 210, 170, False),
            "pressure_fingerprint": PanelSpec("medium", 190, 140, True),
            "groove_stability": PanelSpec("high", 190, 150, False),
            "human_likeness": PanelSpec("high", 190, 150, False),
        }
        panel_titles = {
            "trajectory": "Touch Trajectory",
            "force_radius": "Force / Radius Timeline",
            "signature_layer": "Signature Layer",
            "groove_view": "Groove View",
            "groove_view_3d": "Groove View 3D",
            "logger_canvas_mirror": "Logger Canvas Mirror",
            "phase_timeline": "Phase Timeline",
            "pin_keyboard_mirror": "PIN Keyboard Mirror",
            "pressure_fingerprint": "Pressure Fingerprint",
            "groove_stability": "Groove Stability",
            "human_likeness": "Human-Likeness",
        }
        panel_widgets = {
            "trajectory": self.trajectory_plot,
            "force_radius": self.force_plot,
            "signature_layer": self.signature_plot,
            "groove_view": self.groove_plot,
            "groove_view_3d": self.groove3d_frame,
            "logger_canvas_mirror": self.logger_canvas_frame,
            "phase_timeline": self.phase_plot,
            "pin_keyboard_mirror": self.pin_mirror_frame,
            "pressure_fingerprint": self.pressure_frame,
            "groove_stability": self.groove_stability_frame,
            "human_likeness": self.human_likeness_frame,
        }
        self.panel_cards = {}
        for panel_id, spec in self._panel_specs.items():
            self.panel_cards[panel_id] = LivePanelCard(
                self,
                panel_id,
                panel_titles[panel_id],
                panel_widgets[panel_id],
                compact_min_height=spec.compact_height + 40,
                collapsible=spec.collapsible,
            )
        self._workspace = LiveWorkspaceLayoutManager(self._workspace_settings_path, list(self.panel_cards.keys()))
        self.layout_preset_selector.setCurrentText(self._workspace.state.active_preset)
        self.layout_preset_selector.currentTextChanged.connect(self._on_layout_preset_changed)
        self.layout_save_button.clicked.connect(self._save_workspace_layout)
        self.layout_reset_button.clicked.connect(self._reset_workspace_layout)

        self.panel_root = QFrame()
        self.panel_root.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.panel_root_layout = QVBoxLayout(self.panel_root)
        self.panel_root_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_root_layout.setSpacing(8)

        self.focus_area = QFrame()
        self.focus_area.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.focus_area_layout = QVBoxLayout(self.focus_area)
        self.focus_area_layout.setContentsMargins(0, 0, 0, 0)
        self.focus_area_layout.setSpacing(8)

        self.overview_area = QFrame()
        self.overview_area.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.overview_grid = QGridLayout(self.overview_area)
        self.overview_grid.setContentsMargins(0, 0, 0, 0)
        self.overview_grid.setHorizontalSpacing(8)
        self.overview_grid.setVerticalSpacing(8)

        self.panel_root_layout.addWidget(self.focus_area)
        self.panel_root_layout.addWidget(self.overview_area, 1)
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_scroll.setWidget(self.panel_root)
        root_layout.addWidget(self.panel_scroll, 1)

        self._install_live_shortcuts()
        self._apply_live_layout()

        self.debug_panel = QFrame()
        self.debug_panel.setVisible(False)
        self.debug_panel.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        debug_layout = QVBoxLayout(self.debug_panel)
        debug_layout.setContentsMargins(12, 12, 12, 12)
        debug_layout.setSpacing(8)

        debug_header = QHBoxLayout()
        debug_title = QLabel("Debug / Telemetry")
        debug_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.debug_close_button = QPushButton("Close")
        self.debug_close_button.setToolTip(live_telemetry_tooltip("debug_close", "Close debug panel."))
        self.debug_close_button.clicked.connect(self._toggle_debug_panel)
        debug_header.addWidget(debug_title)
        debug_header.addStretch(1)
        debug_header.addWidget(self.debug_close_button)
        debug_layout.addLayout(debug_header)

        self.debug_summary = QLabel("Developer diagnostics are hidden here.")
        self.debug_summary.setWordWrap(True)
        debug_layout.addWidget(self.debug_summary)

        self.debug_server_info = QLabel("Server: —")
        self.debug_server_info.setWordWrap(True)
        debug_layout.addWidget(self.debug_server_info)

        self.debug_ip_row = QWidget()
        debug_ip_layout = QHBoxLayout(self.debug_ip_row)
        debug_ip_layout.setContentsMargins(0, 0, 0, 0)
        debug_ip_layout.setSpacing(8)
        self.debug_ip_label = QLabel("Use this IP on iOS Logger: —")
        self.debug_ip_label.setWordWrap(True)
        self.debug_copy_ip_button = QPushButton("Copy IP")
        self.debug_copy_ip_button.setToolTip(live_telemetry_tooltip("debug_copy_ip", "Copy detected Mac LAN IP."))
        self.debug_copy_ip_button.clicked.connect(self._copy_ip_to_clipboard)
        debug_ip_layout.addWidget(self.debug_ip_label, 1)
        debug_ip_layout.addWidget(self.debug_copy_ip_button)
        debug_layout.addWidget(self.debug_ip_row)

        self.debug_status_box = QPlainTextEdit()
        self.debug_status_box.setReadOnly(True)
        self.debug_status_box.setMinimumHeight(120)
        self.debug_status_box.setStyleSheet(
            """
            QPlainTextEdit {
                background: #101014;
                color: #f5f5f7;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                font-family: Menlo, Monaco, monospace;
                font-size: 11px;
            }
            """
        )
        debug_layout.addWidget(self.debug_status_box)
        root_layout.addWidget(self.debug_panel)
        self._update_responsive_mode(force=True)

    def _make_chip(self, text: str) -> QLabel:
        chip = QLabel(text)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(
            """
            QLabel {
                color: #f5f5f7;
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
            }
            """
        )
        return chip

    def _make_metric_chip(self, text: str) -> QLabel:
        chip = self._make_chip(text)
        chip.setStyleSheet(
            """
            QLabel {
                color: #f5f5f7;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
            }
            """
        )
        return chip

    def _make_pin_cell(self, text: str) -> QLabel:
        cell = QLabel(text)
        cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell.setMinimumSize(30, 28)
        cell.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        cell.setStyleSheet(
            """
            QLabel {
                color: #f5f5f7;
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                font-family: Menlo, Monaco, monospace;
                font-size: 13px;
                font-weight: 600;
            }
            """
        )
        return cell

    def _apply_pin_highlight(self, key: str | None) -> None:
        for digit, cell in getattr(self, "pin_cells", {}).items():
            highlighted = key == digit
            cell.setStyleSheet(
                """
                QLabel {
                    color: #f5f5f7;
                    background: rgba(52, 199, 89, 0.22);
                    border: 1px solid rgba(52, 199, 89, 0.95);
                    border-radius: 7px;
                    font-family: Menlo, Monaco, monospace;
                    font-size: 13px;
                    font-weight: 700;
                }
                """
                if highlighted
                else """
                QLabel {
                    color: #f5f5f7;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 7px;
                    font-family: Menlo, Monaco, monospace;
                    font-size: 13px;
                    font-weight: 600;
                }
                """
            )

    def _clear_pin_highlight(self, token: int) -> None:
        if getattr(self, "_pin_highlight_token", 0) != token:
            return
        self._apply_pin_highlight(None)

    def _flash_pin_action(self, action: str, color: str) -> None:
        self.pin_feedback_label.setText(f"Action: {action}")
        self.pin_feedback_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _setup_groove3d_renderer(self, layout: QVBoxLayout, requested_mode: str) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        selection = select_renderer(requested_mode)
        self.groove3d_renderer = selection.renderer
        layout.addWidget(selection.renderer.widget(), 1)
        self.groove3d_renderer_reason_label.setText(selection.reason)
        self.groove3d_status_label.setText(f"Z mode: {self._selected_groove3d_mode().title()} • Renderer: {selection.status}")
        self.groove3d_reset_camera_button.setEnabled(True)
        self.groove3d_auto_rotate_toggle.setEnabled(True)

    def _on_groove3d_mode_changed(self, _text: str) -> None:
        self._groove3d_last_update_monotonic = 0.0
        if self.groove3d_renderer is not None:
            renderer_name = getattr(self.groove3d_renderer, "name", "—")
            self.groove3d_status_label.setText(f"Z mode: {self._selected_groove3d_mode().title()} • Renderer: {renderer_name}")

    def _on_groove3d_renderer_changed(self, text: str) -> None:
        requested = str(text or "Auto").strip().lower()
        if requested == "2d fallback":
            requested = "2d"
        container_layout = self.groove3d_container.layout()
        if isinstance(container_layout, QVBoxLayout):
            self._setup_groove3d_renderer(container_layout, requested)
        self._groove3d_last_update_monotonic = 0.0

    def _on_groove3d_auto_rotate_toggled(self, enabled: bool) -> None:
        if self.groove3d_renderer is not None:
            self.groove3d_renderer.set_auto_rotate(bool(enabled))

    def _selected_groove3d_mode(self) -> str:
        label = self.groove3d_mode_selector.currentText().strip().lower()
        if label.startswith("radius"):
            return "radius"
        if label.startswith("layer"):
            return "layer"
        return "force"

    def _reset_groove3d_camera(self) -> None:
        if self.groove3d_renderer is not None:
            self.groove3d_renderer.reset_camera()

    def _make_plot(self, title: str, minimum_height: int = 240) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.setMinimumHeight(minimum_height)
        plot.setBackground("#0f1014")
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#8e8e93"))
        plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#8e8e93"))
        return plot

    def _install_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _install_live_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []

        def register(sequence: str, callback) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

        register("Escape", self._close_focus_modal)

    def set_layout_mode_override(self, mode: str) -> None:
        normalized = str(mode or "auto").strip().lower()
        if normalized not in {"auto", "large", "medium", "small"}:
            normalized = "auto"
        self._layout_mode_override = normalized
        self._update_responsive_mode(force=True)

    def layout_mode_override(self) -> str:
        return self._layout_mode_override

    def _on_layout_preset_changed(self, preset_name: str) -> None:
        if self._workspace is None:
            return
        self._workspace.apply_preset(preset_name)
        self._workspace.save()
        self._apply_live_layout()

    def _save_workspace_layout(self) -> None:
        if self._workspace is None:
            return
        self._workspace.save()
        self.control_message_label.setText(f"Live workspace saved to {self._workspace_settings_path}")
        self.control_message_label.setVisible(True)

    def _reset_workspace_layout(self) -> None:
        if self._workspace is None:
            return
        self._workspace.reset_default()
        self._workspace.save()
        self.layout_preset_selector.blockSignals(True)
        self.layout_preset_selector.setCurrentText(self._workspace.state.active_preset)
        self.layout_preset_selector.blockSignals(False)
        self._apply_live_layout()

    def move_panel(self, panel_id: str, direction: str) -> None:
        if self._workspace is None:
            return
        self._workspace.move_panel(panel_id, direction)
        self.layout_preset_selector.blockSignals(True)
        self.layout_preset_selector.setCurrentText(self._workspace.state.active_preset)
        self.layout_preset_selector.blockSignals(False)
        self._workspace.save()
        self._apply_live_layout()

    def set_panel_collapsed(self, panel_id: str, collapsed: bool) -> None:
        if self._workspace is None:
            return
        self._workspace.state.collapsed[panel_id] = bool(collapsed)
        self._workspace.state.active_preset = "Custom"
        self.layout_preset_selector.blockSignals(True)
        self.layout_preset_selector.setCurrentText("Custom")
        self.layout_preset_selector.blockSignals(False)
        self._workspace.save()
        self._apply_live_layout()

    def adjust_panel_height(self, panel_id: str, delta: int) -> None:
        if self._workspace is None:
            return
        spec = self._panel_specs.get(panel_id)
        if spec is None:
            return
        base = int(self._workspace.state.panel_heights.get(panel_id, spec.minimum_height))
        updated = max(80, min(640, base + int(delta)))
        self._workspace.state.panel_heights[panel_id] = updated
        self._workspace.state.active_preset = "Custom"
        self.layout_preset_selector.blockSignals(True)
        self.layout_preset_selector.setCurrentText("Custom")
        self.layout_preset_selector.blockSignals(False)
        self._workspace.save()
        self._apply_live_layout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_mode()
        self._apply_panel_content_responsiveness()

    def _resolve_responsive_mode(self) -> tuple[str, bool]:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        if self._layout_mode_override != "auto":
            mode = self._layout_mode_override
        elif width >= 1400:
            mode = "large"
        elif width >= 1000:
            mode = "medium"
        else:
            mode = "small"
        return mode, height < 760

    def _update_responsive_mode(self, force: bool = False) -> None:
        mode, compact_height = self._resolve_responsive_mode()
        if not force and mode == self._responsive_mode and compact_height == self._compact_height_mode:
            return
        self._responsive_mode = mode
        self._compact_height_mode = compact_height
        self._apply_live_layout()
        self._apply_panel_content_responsiveness()

    def _panel_positions_for_mode(self, mode: str) -> dict[str, tuple[int, int]]:
        panel_order = (
            self._workspace.state.panel_order
            if self._workspace is not None and self._workspace.state.panel_order
            else list(self.panel_cards.keys())
        )
        columns = 3 if mode == "large" else 2 if mode == "medium" else 1
        positions: dict[str, tuple[int, int]] = {}
        for index, panel_id in enumerate(panel_order):
            positions[panel_id] = (index // columns, index % columns)
        for panel_id in self.panel_cards:
            if panel_id not in positions:
                index = len(positions)
                positions[panel_id] = (index // columns, index % columns)
        return positions

    def _collapsed_panels_for_mode(self, mode: str) -> set[str]:
        collapsed: set[str] = set()
        if mode == "small":
            collapsed.update({"phase_timeline"})
            if self._compact_height_mode:
                collapsed.update({"pressure_fingerprint", "groove_view", "groove_view_3d"})
        elif mode == "medium" and self._compact_height_mode:
            collapsed.update({"phase_timeline", "groove_view_3d"})
        return collapsed

    def _clear_layout(self, layout: QGridLayout | QHBoxLayout | QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _apply_live_layout(self) -> None:
        focused_panel = self.panel_cards.get(self._focused_modal_panel_id) if self._focused_modal_panel_id else None
        mode = self._responsive_mode
        compact_mode = mode != "large" or self._compact_height_mode
        collapsed_panels = self._collapsed_panels_for_mode(mode)
        for panel_id, card in self.panel_cards.items():
            spec = self._panel_specs[panel_id]
            target_min_height = spec.compact_height if compact_mode else spec.minimum_height
            if self._workspace is not None:
                target_min_height = int(self._workspace.state.panel_heights.get(panel_id, target_min_height))
            card.content_widget.setMinimumHeight(max(80, target_min_height))
            card.set_compact_mode(compact_mode)
            card._apply_state(card is focused_panel)
            custom_collapsed = bool(self._workspace.state.collapsed.get(panel_id, False)) if self._workspace is not None else False
            card.setVisible(True if self._workspace is None else bool(self._workspace.state.visible_panels.get(panel_id, True)))
            card.set_collapsed((panel_id in collapsed_panels or custom_collapsed) and card is not focused_panel)

        self._clear_layout(self.focus_area_layout)
        self._clear_layout(self.overview_grid)

        default_positions = self._panel_positions_for_mode(mode)
        max_row = max(position[0] for position in default_positions.values())
        max_column = max(position[1] for position in default_positions.values())
        if mode == "small":
            self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.focus_area.setVisible(False)
        self.panel_root_layout.setStretch(0, 0)
        self.panel_root_layout.setStretch(1, 1)
        for panel_id, card in self.panel_cards.items():
            row, column = default_positions[panel_id]
            if focused_panel is not None and panel_id == self._focused_modal_panel_id:
                self.overview_grid.addWidget(self._focused_panel_placeholder(card.title), row, column)
            else:
                self.overview_grid.addWidget(card, row, column)
        for column in range(max_column + 1):
            self.overview_grid.setColumnStretch(column, 1)
        for row in range(max_row + 1):
            self.overview_grid.setRowStretch(row, 1)
        self._apply_panel_content_responsiveness()

    def _focused_panel_placeholder(self, title: str) -> QWidget:
        placeholder = QFrame()
        placeholder.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px dashed rgba(90, 200, 250, 0.45);
                border-radius: 10px;
            }
            QLabel {
                color: #8e8e93;
                font-size: 11px;
            }
            """
        )
        placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(12, 10, 12, 10)
        message = QLabel(f"{title} opened in focus view")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message, 1)
        return placeholder

    def toggle_panel_focus_modal(self, panel_id: str) -> None:
        if panel_id not in self.panel_cards:
            return
        if self._focused_modal_panel_id == panel_id:
            self._close_focus_modal()
            return
        if self._focused_modal_panel_id is not None:
            self._close_focus_modal()
        card = self.panel_cards[panel_id]
        self._focused_modal_panel_id = panel_id
        self._apply_live_layout()

        dialog = QDialog(self)
        dialog.setModal(False)
        dialog.setWindowTitle(f"{card.title} — Focus")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.resize(max(760, int(self.width() * 0.70)), max(520, int(self.height() * 0.72)))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(card)
        escape_shortcut = QShortcut(QKeySequence("Escape"), dialog)
        escape_shortcut.activated.connect(dialog.close)
        dialog.finished.connect(self._handle_focus_modal_closed)
        self._focus_modal_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _close_focus_modal(self) -> None:
        if self._focus_modal_dialog is None:
            return
        if self._closing_focus_modal:
            return
        self._closing_focus_modal = True
        try:
            self._focus_modal_dialog.close()
        finally:
            self._closing_focus_modal = False

    def _handle_focus_modal_closed(self, _result: int) -> None:
        self._focus_modal_dialog = None
        self._focused_modal_panel_id = None
        self._apply_live_layout()

    def _apply_panel_content_responsiveness(self) -> None:
        for panel_id, card in self.panel_cards.items():
            context = card.render_context(self._responsive_mode, self._compact_height_mode)
            self._apply_header_responsiveness(card, context)
            self._apply_panel_body_responsiveness(panel_id, context)

    def _apply_header_responsiveness(self, card: LivePanelCard, context: PanelRenderContext) -> None:
        title_size = "11px"
        if context.panel_mode == "compact":
            title_size = "10px"
        elif context.panel_mode == "mini":
            title_size = "9px"
        card.title_label.setStyleSheet(f"font-size: {title_size}; font-weight: 600;")
        card.help_button.setText("?" if context.panel_mode != "mini" else "ⓘ")
        if card.collapsible:
            card.collapse_button.setText("▾" if card.collapsed else "▴")

    def _apply_panel_body_responsiveness(self, panel_id: str, context: PanelRenderContext) -> None:
        if panel_id == "phase_timeline":
            self.phase_plot.setMinimumHeight(80 if context.panel_mode == "mini" else 110 if context.panel_mode == "compact" else 150)
        if panel_id in {"trajectory", "force_radius", "signature_layer", "groove_view", "pressure_fingerprint", "phase_timeline", "logger_canvas_mirror"}:
            self._apply_plot_responsiveness(context)
        if panel_id == "pin_keyboard_mirror":
            self._apply_pin_panel_responsiveness(context)
        elif panel_id == "groove_view_3d":
            self._apply_groove3d_panel_responsiveness(context)
        elif panel_id == "logger_canvas_mirror":
            self._apply_canvas_panel_responsiveness(context)
        elif panel_id == "pressure_fingerprint":
            self._apply_pressure_panel_responsiveness(context)
        elif panel_id == "groove_stability":
            self._apply_groove_stability_panel_responsiveness(context)
        elif panel_id == "human_likeness":
            self._apply_human_likeness_panel_responsiveness(context)

    def _apply_plot_responsiveness(self, context: PanelRenderContext) -> None:
        hide_axes = context.panel_mode == "mini"
        tick_alpha = 0.10 if context.panel_mode == "mini" else 0.14 if context.panel_mode == "compact" else 0.18
        for plot in [self.trajectory_plot, self.force_plot, self.signature_plot, self.groove_plot, self.phase_plot, self.pressure_hist_plot, self.logger_canvas_plot]:
            plot.showGrid(x=True, y=True, alpha=tick_alpha)
            left_axis = plot.getPlotItem().getAxis("left")
            bottom_axis = plot.getPlotItem().getAxis("bottom")
            left_axis.setStyle(showValues=not hide_axes, tickTextWidth=24 if not hide_axes else 0)
            bottom_axis.setStyle(showValues=not hide_axes, tickTextOffset=2 if not hide_axes else 0)

    def _apply_canvas_panel_responsiveness(self, context: PanelRenderContext) -> None:
        if context.panel_mode == "mini":
            self.canvas_status_label.setVisible(False)
            self.canvas_trails_toggle.setVisible(False)
            self.canvas_force_toggle.setVisible(False)
            self.canvas_fit_button.setVisible(False)
            self.canvas_clear_button.setVisible(False)
            self.logger_canvas_plot.setMinimumHeight(90)
        elif context.panel_mode == "compact":
            self.canvas_status_label.setVisible(True)
            self.canvas_trails_toggle.setVisible(True)
            self.canvas_force_toggle.setVisible(True)
            self.canvas_fit_button.setVisible(False)
            self.canvas_clear_button.setVisible(False)
            self.logger_canvas_plot.setMinimumHeight(130)
        else:
            self.canvas_status_label.setVisible(True)
            self.canvas_trails_toggle.setVisible(True)
            self.canvas_force_toggle.setVisible(True)
            self.canvas_fit_button.setVisible(True)
            self.canvas_clear_button.setVisible(True)
            self.logger_canvas_plot.setMinimumHeight(160)

    def _apply_pin_panel_responsiveness(self, context: PanelRenderContext) -> None:
        tiny = context.panel_mode == "mini"
        compact = context.panel_mode == "compact"
        show_details = not tiny
        self.pin_detail_label.setVisible(show_details)
        self.pin_feedback_label.setVisible(show_details and not compact)
        if tiny:
            cell_w, cell_h = 24, 20
            font_size = 10
        elif compact:
            cell_w, cell_h = 30, 24
            font_size = 11
        else:
            cell_w, cell_h = 36, 32
            font_size = 13
        for cell in self.pin_cells.values():
            cell.setMinimumSize(cell_w, cell_h)
            cell.setMaximumHeight(cell_h + 2)
            cell.setStyleSheet(
                f"""
                QLabel {{
                    color: #f5f5f7;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 7px;
                    font-family: Menlo, Monaco, monospace;
                    font-size: {font_size}px;
                    font-weight: 600;
                }}
                """
            )

    def _apply_pressure_panel_responsiveness(self, context: PanelRenderContext) -> None:
        if context.panel_mode == "mini":
            self.pressure_summary_label.setVisible(True)
            self.pressure_detail_label.setVisible(False)
            self.pressure_hist_plot.setMinimumHeight(70)
        elif context.panel_mode == "compact":
            self.pressure_summary_label.setVisible(True)
            self.pressure_detail_label.setVisible(False)
            self.pressure_hist_plot.setMinimumHeight(95)
        else:
            self.pressure_summary_label.setVisible(True)
            self.pressure_detail_label.setVisible(True)
            self.pressure_hist_plot.setMinimumHeight(120)

    def _apply_groove3d_panel_responsiveness(self, context: PanelRenderContext) -> None:
        if context.panel_mode == "mini":
            self.groove3d_status_label.setVisible(False)
            self.groove3d_mode_selector.setVisible(False)
            self.groove3d_renderer_selector.setVisible(False)
            self.groove3d_reset_camera_button.setVisible(False)
            self.groove3d_auto_rotate_toggle.setVisible(False)
            self.groove3d_renderer_reason_label.setVisible(False)
            self.groove3d_container.setMinimumHeight(100)
        elif context.panel_mode == "compact":
            self.groove3d_status_label.setVisible(True)
            self.groove3d_mode_selector.setVisible(True)
            self.groove3d_renderer_selector.setVisible(True)
            self.groove3d_reset_camera_button.setVisible(False)
            self.groove3d_auto_rotate_toggle.setVisible(False)
            self.groove3d_renderer_reason_label.setVisible(False)
            self.groove3d_container.setMinimumHeight(140)
        else:
            self.groove3d_status_label.setVisible(True)
            self.groove3d_mode_selector.setVisible(True)
            self.groove3d_renderer_selector.setVisible(True)
            self.groove3d_reset_camera_button.setVisible(True)
            self.groove3d_auto_rotate_toggle.setVisible(True)
            self.groove3d_renderer_reason_label.setVisible(True)
            self.groove3d_container.setMinimumHeight(170)

    def _apply_groove_stability_panel_responsiveness(self, context: PanelRenderContext) -> None:
        if context.panel_mode == "mini":
            self.groove_stability_detail_label.setVisible(False)
            self.groove_stability_status_label.setVisible(False)
            self.groove_stability_bar.setVisible(False)
        elif context.panel_mode == "compact":
            self.groove_stability_detail_label.setVisible(True)
            self.groove_stability_status_label.setVisible(False)
            self.groove_stability_bar.setVisible(True)
        else:
            self.groove_stability_detail_label.setVisible(True)
            self.groove_stability_status_label.setVisible(True)
            self.groove_stability_bar.setVisible(True)

    def _apply_human_likeness_panel_responsiveness(self, context: PanelRenderContext) -> None:
        if context.panel_mode == "mini":
            self.human_likeness_meta_label.setVisible(True)
            self.human_likeness_flags_label.setVisible(False)
            self.human_likeness_disclaimer.setVisible(False)
        elif context.panel_mode == "compact":
            self.human_likeness_meta_label.setVisible(True)
            self.human_likeness_flags_label.setVisible(False)
            self.human_likeness_disclaimer.setVisible(False)
        else:
            self.human_likeness_meta_label.setVisible(True)
            self.human_likeness_flags_label.setVisible(True)
            self.human_likeness_disclaimer.setVisible(True)

    def show_panel_help(self, panel_id: str) -> None:
        payload = panel_help_for_live_panel(panel_id)
        dialog = QDialog(self)
        dialog.setModal(True)
        dialog.setWindowTitle(f"{payload.get('title', 'Panel Help')} — Help")
        dialog.resize(560, 520)
        wrapper = QVBoxLayout(dialog)
        wrapper.setContentsMargins(12, 12, 12, 12)
        wrapper.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)

        def add_section(title: str, text: str) -> None:
            section_title = QLabel(title)
            section_title.setStyleSheet("font-size: 12px; font-weight: 700;")
            section_text = QLabel(text or "N/A")
            section_text.setWordWrap(True)
            section_text.setStyleSheet("font-size: 11px; color: #c7c7cc;")
            content_layout.addWidget(section_title)
            content_layout.addWidget(section_text)

        name_label = QLabel(str(payload.get("title", panel_id)))
        name_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #5ac8fa;")
        content_layout.addWidget(name_label)
        add_section("What is it?", str(payload.get("short_description", "N/A")))
        add_section("Why does it matter?", str(payload.get("why_it_matters", "N/A")))
        add_section("How is it calculated?", str(payload.get("calculation_summary", "N/A")))
        add_section("How should I interpret it?", str(payload.get("interpretation_notes", "N/A")))
        tips = payload.get("optional_tips")
        if tips:
            add_section("Tips", str(tips))
        content_layout.addStretch(1)
        scroll.setWidget(container)
        wrapper.addWidget(scroll, 1)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        wrapper.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

        self._panel_help_dialog = dialog
        dialog.exec()

    def _open_readiness_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("System Readiness Check")
        dialog.resize(760, 520)
        dialog.setModal(False)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Run this checklist before collecting real research data.")
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #f5f5f7;")
        layout.addWidget(title)

        self.readiness_summary_label = QLabel("Not run yet.")
        self.readiness_summary_label.setStyleSheet("font-size: 12px; color: #c7c7cc;")
        layout.addWidget(self.readiness_summary_label)

        self.readiness_results_box = QPlainTextEdit()
        self.readiness_results_box.setReadOnly(True)
        self.readiness_results_box.setStyleSheet(
            """
            QPlainTextEdit {
                background: #0f1014;
                color: #f5f5f7;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                font-family: Menlo, Monaco, monospace;
                font-size: 11px;
            }
            """
        )
        layout.addWidget(self.readiness_results_box, 1)

        button_row = QHBoxLayout()
        run_button = QPushButton("Run Readiness Test")
        run_button.clicked.connect(self._run_readiness_test)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        button_row.addWidget(run_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._readiness_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _run_readiness_test(self) -> None:
        snapshot = self.live_server.snapshot()
        report = run_system_readiness_check(self.paths, snapshot)
        self._render_readiness_report(report)

    def _render_readiness_report(self, report: ReadinessReport) -> None:
        status = "PASS" if report.overall_passed else "FAIL"
        self.readiness_summary_label.setText(
            f"Readiness: {status}  •  Session: {report.active_session_id or '—'}  •  Generated: {report.generated_at}"
        )
        lines = []
        for row in report.checks:
            badge = "PASS" if row.passed else "FAIL"
            lines.append(f"[{badge}] {row.label}")
            lines.append(f"  {row.detail}")
        lines.append("")
        lines.append(f"JSON: {report.report_json_path}")
        lines.append(f"Markdown: {report.report_md_path}")
        self.readiness_results_box.setPlainText("\n".join(lines))

    def refresh(self) -> None:
        snapshot = self.live_server.snapshot()
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        try:
            active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
            self.connection_chip.setText(snapshot.connection_status)
            self.device_chip.setText(f"device: {(active_session or {}).get('deviceType', snapshot.export_summary.get('deviceType', '—')) or '—'}")
            self.input_chip.setText(f"Input: {self._pretty_input_mode((active_session or {}).get('inputType', snapshot.export_summary.get('inputType', 'unknown')))}")
            self.sample_rate_chip.setText(f"sample rate: {snapshot.sample_rate_hz:.2f} Hz")
            self.session_chip.setText(f"session: {self._short_session_id(snapshot.active_session_id)}")
            self.export_chip.setText(f"export: {snapshot.export_status}")

            self._update_plot_surfaces(snapshot, active_session)
            self._update_debug_panel(snapshot)
            self._update_control_message(snapshot)
        except Exception as error:  # defensive: keep refresh loop alive
            error_key = f"{type(error).__name__}:{error}"
            if error_key not in self._plot_error_keys:
                self._plot_error_keys.add(error_key)
                logger.warning("Live telemetry render warning: %s", error)

    def _update_debug_panel(self, snapshot: TelemetrySnapshot) -> None:
        diagnostics = {
            "connectionStatus": snapshot.connection_status,
            "serverState": snapshot.server_state,
            "host": snapshot.host,
            "port": snapshot.port,
            "suggestedLanIp": snapshot.suggested_lan_ip,
            "activeSessionId": snapshot.active_session_id,
            "inputType": (next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), {}) or {}).get(
                "inputType",
                (snapshot.export_summary or {}).get("inputType", "unknown"),
            ),
            "eventCount": snapshot.event_count,
            "touchCount": snapshot.touch_count,
            "tapCount": snapshot.tap_count,
            "markerCount": snapshot.marker_count,
            "sampleRateHz": snapshot.sample_rate_hz,
            "lastEventTimestamp": snapshot.last_event_timestamp,
            "lastError": snapshot.last_error,
            "droppedMessages": snapshot.dropped_messages,
            "malformedMessages": snapshot.malformed_messages,
            "exportStatus": snapshot.export_status,
            "exportSummary": snapshot.export_summary,
            "warnings": snapshot.warnings,
        }
        self.debug_summary.setText(
            "Live telemetry remains best-effort. Export is the scientific ground truth. "
            f"Use the Mac LAN IP on physical devices: {snapshot.suggested_lan_ip}."
        )
        self.debug_server_info.setText(
            f"Server host: {snapshot.host}    Port: {snapshot.port}    Connection: {snapshot.connection_status}"
        )
        self.debug_ip_label.setText(
            f"Use this IP on iOS Logger: {snapshot.suggested_lan_ip if snapshot.suggested_lan_ip != 'unavailable' else 'unavailable'}"
        )
        self.debug_status_box.setPlainText(json.dumps(diagnostics, indent=2, sort_keys=True))
        self._update_debug_ips(snapshot)
        self._update_pin_rhythm_panel(snapshot)
        self._update_pressure_fingerprint(snapshot)
        self._update_groove_stability(snapshot)
        self._update_human_likeness(snapshot)

    def _update_control_message(self, snapshot: TelemetrySnapshot) -> None:
        message = snapshot.control_message
        if message and "reset" in message.lower():
            self.logger_canvas_plot.clear()
            self.canvas_status_label.setText("bounds: reset")
        if message:
            self.control_message_label.setText(message)
            self.control_message_label.setVisible(True)
        else:
            self.control_message_label.clear()
            self.control_message_label.setVisible(False)

    def _update_debug_ips(self, snapshot: TelemetrySnapshot) -> None:
        if snapshot.suggested_lan_ip and snapshot.suggested_lan_ip != "unavailable":
            self.debug_summary.setText(
                f"Server bound to {snapshot.host}:{snapshot.port}. "
                f"Physical devices must use {snapshot.suggested_lan_ip}, not 127.0.0.1."
            )

    def _update_plot_surfaces(self, snapshot: TelemetrySnapshot, active_session: dict[str, Any] | None) -> None:
        if not active_session:
            self._clear_plots()
            return

        events = [event for event in active_session.get("events", []) if event.get("messageType") == "touch_event"]
        if not events:
            self._clear_plots()
            return

        xs = np.asarray([float(event.get("x", 0.0)) for event in events], dtype=np.float64)
        ys = np.asarray([float(event.get("y", 0.0)) for event in events], dtype=np.float64)
        times = np.asarray([float(event.get("timestamp", 0.0)) for event in events], dtype=np.float64)
        forces = np.asarray([float(event["force"]) if event.get("force") is not None else np.nan for event in events], dtype=np.float64)
        radii = np.asarray([float(event.get("majorRadius", 0.0)) for event in events], dtype=np.float64)
        phases = np.asarray([_phase_to_numeric(str(event.get("phase", "unknown"))) for event in events], dtype=np.float64)

        self._render_trajectory(xs, ys)
        self._render_force_radius(times, forces, radii)
        self._render_signature_layer(forces, radii, phases)
        self._render_groove_view(xs, ys, forces, radii, times, phases)
        self._render_phase_timeline(times, phases, events)
        self._update_groove3d(events)
        self._render_logger_canvas_mirror(events)

    def _clear_plots(self) -> None:
        for plot in [self.trajectory_plot, self.force_plot, self.signature_plot, self.groove_plot, self.phase_plot, self.pressure_hist_plot, self.logger_canvas_plot]:
            plot.clear()
        self._update_groove3d([])
        self._render_logger_canvas_mirror([])

    def _render_trajectory(self, xs: np.ndarray, ys: np.ndarray) -> None:
        plot = self.trajectory_plot
        plot.clear()
        plot.setAspectLocked(True, ratio=1.0)
        plot.addItem(pg.PlotDataItem(xs, ys, pen=pg.mkPen("#2f8cff", width=2)))
        plot.addItem(pg.ScatterPlotItem([xs[-1]], [ys[-1]], size=10, brush=pg.mkBrush("#ff453a"), pen=pg.mkPen(None)))
        plot.setLabel("left", "Y")
        plot.setLabel("bottom", "X")

    def _render_force_radius(self, times: np.ndarray, forces: np.ndarray, radii: np.ndarray) -> None:
        plot = self.force_plot
        plot.clear()
        plot.addItem(pg.PlotDataItem(times, forces, pen=pg.mkPen("#34c759", width=2), name="Force"))
        plot.addItem(pg.PlotDataItem(times, radii, pen=pg.mkPen("#ff9f0a", width=2), name="Radius"))
        plot.setLabel("left", "Value")
        plot.setLabel("bottom", "Timestamp")

    def _render_signature_layer(self, forces: np.ndarray, radii: np.ndarray, phases: np.ndarray) -> None:
        plot = self.signature_plot
        plot.clear()
        if len(forces) == 0:
            return
        x_values = np.arange(len(forces), dtype=np.float64)
        normalized_forces = self._normalize_series(forces)
        sizes = np.clip(np.nan_to_num(radii, nan=0.0), 4.0, 22.0)
        spots = []
        for index, (x_value, force_value, radius_value, phase_value) in enumerate(zip(x_values, normalized_forces, sizes, phases, strict=False)):
            spots.append(
                {
                    "pos": (x_value, force_value),
                    "size": float(radius_value),
                    "brush": pg.mkBrush(self._phase_color(float(phase_value))),
                    "pen": pg.mkPen(None),
                }
            )
        plot.addItem(pg.ScatterPlotItem(spots=spots))
        plot.addItem(pg.PlotDataItem(x_values, normalized_forces, pen=pg.mkPen("#8e8e93", width=1)))
        plot.setLabel("left", "Normalized Force")
        plot.setLabel("bottom", "Event Index")

    def _render_groove_view(
        self,
        xs: np.ndarray,
        ys: np.ndarray,
        forces: np.ndarray,
        radii: np.ndarray,
        times: np.ndarray,
        phases: np.ndarray,
    ) -> None:
        plot = self.groove_plot
        plot.clear()
        if len(xs) == 0:
            return

        centroid_x = float(np.nanmean(xs)) if len(xs) else 0.0
        centroid_y = float(np.nanmean(ys)) if len(ys) else 0.0
        radial_distance = np.sqrt((xs - centroid_x) ** 2 + (ys - centroid_y) ** 2)
        normalized_radius = self._normalize_series(radial_distance)
        normalized_time = self._normalize_series(times)
        angle = normalized_time * (math.tau * 10.0)
        groove_r = 0.35 + 1.65 * normalized_radius
        groove_x = groove_r * np.cos(angle)
        groove_y = groove_r * np.sin(angle)

        spots = []
        for groove_x_value, groove_y_value, phase_value, force_value, radius_value in zip(groove_x, groove_y, phases, forces, radii, strict=False):
            spots.append(
                {
                    "pos": (float(groove_x_value), float(groove_y_value)),
                    "size": float(np.clip(radius_value if not np.isnan(radius_value) else 6.0, 4.0, 18.0)),
                    "brush": pg.mkBrush(self._phase_color(float(phase_value), alpha=180)),
                    "pen": pg.mkPen(None),
                }
            )

        plot.addItem(pg.ScatterPlotItem(spots=spots))
        plot.setAspectLocked(True, ratio=1.0)
        plot.setLabel("left", "Groove Y")
        plot.setLabel("bottom", "Groove X")

    def _render_phase_timeline(self, times: np.ndarray, phases: np.ndarray, events: list[dict[str, Any]] | None = None) -> None:
        plot = self.phase_plot
        plot.clear()
        times, phases = self._guard_series_pair(times, phases)
        if len(times) == 0 or len(phases) == 0:
            return
        plot.addItem(
            pg.PlotDataItem(
                times,
                phases,
                pen=pg.mkPen("#5ac8fa", width=2),
                symbol="o",
                symbolSize=4,
                symbolBrush=pg.mkBrush("#5ac8fa"),
                symbolPen=pg.mkPen(None),
            )
        )
        plot.setLabel("left", "")
        plot.setLabel("bottom", "Timestamp")
        plot.hideAxis("left")
        plot.getAxis("bottom").setStyle(tickTextOffset=4)

    def _clear_logger_canvas_mirror(self) -> None:
        self._canvas_manual_clear_generation += 1
        self.logger_canvas_plot.clear()
        self.canvas_status_label.setText("bounds: cleared")

    def _fit_logger_canvas_mirror(self) -> None:
        self.logger_canvas_plot.enableAutoRange(x=True, y=True)

    def _render_logger_canvas_mirror(self, events: list[dict[str, Any]]) -> None:
        self.logger_canvas_plot.clear()
        frame = build_canvas_mirror_frame(
            events,
            use_force_thickness=self.canvas_force_toggle.isChecked(),
            default_width=2.1,
        )
        if not frame.strokes:
            self.canvas_status_label.setText("bounds: inferred")
            return
        self.canvas_status_label.setText("bounds: inferred" if frame.inferred_bounds else "bounds: telemetry surface")
        show_trails = self.canvas_trails_toggle.isChecked()
        for stroke in frame.strokes:
            if stroke.xs.size == 1:
                self.logger_canvas_plot.addItem(
                    pg.ScatterPlotItem(
                        [float(stroke.xs[0])],
                        [float(stroke.ys[0])],
                        size=max(5.0, stroke.width * 2.1),
                        brush=pg.mkBrush(self._phase_color(_phase_to_numeric(stroke.phase), alpha=220)),
                        pen=pg.mkPen(None),
                    )
                )
                continue
            color = self._phase_color(_phase_to_numeric(stroke.phase), alpha=220 if show_trails else 120)
            self.logger_canvas_plot.addItem(
                pg.PlotDataItem(
                    stroke.xs,
                    stroke.ys,
                    pen=pg.mkPen(color, width=stroke.width),
                )
            )
            if stroke.digit is not None:
                label = pg.TextItem(text=stroke.digit, color="#f5f5f7", anchor=(0.5, 0.5))
                label.setPos(float(stroke.xs[-1]), float(stroke.ys[-1]))
                self.logger_canvas_plot.addItem(label)
        if frame.latest_point is not None:
            lx, ly = frame.latest_point
            self.logger_canvas_plot.addItem(
                pg.ScatterPlotItem(
                    [lx],
                    [ly],
                    size=11,
                    brush=pg.mkBrush("#ff453a"),
                    pen=pg.mkPen(None),
                )
            )

    def _update_groove3d(self, events: list[dict[str, Any]]) -> None:
        if self.groove3d_renderer is None:
            return

        if not events:
            self.groove3d_renderer.clear()
            self.groove3d_status_label.setText("Z mode: —")
            return

        now = time.monotonic()
        if (now - self._groove3d_last_update_monotonic) < self._groove3d_update_interval_s:
            return
        self._groove3d_last_update_monotonic = now

        trace = build_groove3d_trace(
            events,
            z_mode=self._selected_groove3d_mode(),
            max_points=self._groove3d_max_points,
        )
        if trace.source_count == 0:
            self.groove3d_renderer.clear()
            self.groove3d_status_label.setText("Z mode: —")
            return

        self.groove3d_renderer.render_trace(trace)
        renderer_name = getattr(self.groove3d_renderer, "name", "—")
        self.groove3d_status_label.setText(
            f"Z mode: {trace.z_mode_used.title()} • Renderer: {renderer_name} • points: {trace.source_count}"
        )

    def _update_pin_rhythm_panel(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = (active_session or {}).get("events", [])
        metrics = compute_pin_rhythm_metrics(events)

        if metrics.collecting:
            self.pin_sequence_label.setText(EMPTY_PIN_LABEL)
            self.pin_rhythm_score_label.setText("Consistency: collecting…")
            self.pin_rhythm_bar_label.setText(metrics.bar_text)
            self.pin_detail_label.setText("Waiting for PIN input")
            self.pin_feedback_label.setText("Action: —")
            self.pin_feedback_label.setStyleSheet("color: #c7c7cc; font-size: 11px;")
            self._apply_pin_highlight(None)
            return

        sequence_display = metrics.digit_text.replace("PIN: ", "")
        self.pin_sequence_label.setText(metrics.digit_text)
        self.pin_rhythm_score_label.setText(f"Consistency: {metrics.consistency_score:.0f}%")
        self.pin_rhythm_bar_label.setText(metrics.bar_text)
        if metrics.average_interval_ms is not None:
            detail_text = (
                f"Avg {metrics.average_interval_ms:.0f}ms • Var {metrics.interval_variance_ms:.1f} • Seq {self._short_session_id(metrics.sequence_id)}"
            )
        else:
            detail_text = f"Seq {self._short_session_id(metrics.sequence_id)}"

        latest = None
        for event in reversed([event for event in events if event.get("messageType") == "touch_event"]):
            if event.get("pinSequenceId") == metrics.sequence_id or str(event.get("pinSequenceId") or "__unknown__") == metrics.sequence_id:
                latest = event
                break
        latest_digit = latest.get("digit") if latest else None
        latest_index = latest.get("digitIndex") if latest else None
        self.pin_detail_label.setText(
            f"Digit {latest_digit if latest_digit is not None else '—'} • Index {latest_index if latest_index is not None else '—'} • {detail_text}"
        )
        self.pin_feedback_label.setText(f"Action: rhythm • {sequence_display}")
        self.pin_feedback_label.setStyleSheet("color: #5ac8fa; font-size: 11px;")
        if latest and isinstance(latest.get("digit"), str) and latest.get("digit") in self.pin_cells:
            self._pin_highlight_token += 1
            token = self._pin_highlight_token
            self._apply_pin_highlight(str(latest.get("digit")))
            QTimer.singleShot(320, lambda token=token: self._clear_pin_highlight(token))
        else:
            self._apply_pin_highlight(None)

    def _update_pressure_fingerprint(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = (active_session or {}).get("events", [])
        metrics = compute_pressure_fingerprint_metrics(events)
        plot = self.pressure_hist_plot
        plot.clear()

        if metrics.collecting:
            self.pressure_summary_label.setText("Collecting...")
            self.pressure_detail_label.setText("Force: —  Median: —  Std Dev: —  Radius Stability: —")
            return

        counts = metrics.histogram_counts
        edges = metrics.histogram_edges
        if counts.size > 0 and edges.size > 0:
            x_positions = edges[:-1]
            widths = np.diff(edges)
            plot.addItem(
                pg.BarGraphItem(
                    x=x_positions,
                    height=counts,
                    width=widths,
                    brush=pg.mkBrush(90, 200, 250, 180),
                    pen=pg.mkPen(None),
                )
            )
        plot.setLabel("left", "Count")
        plot.setLabel("bottom", "Force bins")

        summary = (
            f"Mean {metrics.mean_force:.3f} • Median {metrics.median_force:.3f} • Std {metrics.std_force:.3f}"
        )
        self.pressure_summary_label.setText(summary)
        if metrics.radius_stability is not None:
            self.pressure_detail_label.setText(
                f"Force Var {metrics.force_variance:.3f} • Radius Var {metrics.radius_variance:.3f} • Radius Stability {metrics.radius_stability:.0f}%"
            )
        else:
            self.pressure_detail_label.setText("Radius Stability: collecting…")

    def _update_groove_stability(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = (active_session or {}).get("events", [])
        metrics = compute_groove_stability_metrics(events)

        if metrics.collecting or metrics.overall_score is None:
            self.groove_stability_score_label.setText("Collecting...")
            self.groove_stability_bar.setValue(0)
            self.groove_stability_detail_label.setText("Trajectory: —  Force: —  Timing: —  Layers: —")
            self.groove_stability_status_label.setText("Waiting for enough live events")
            return

        score = int(round(metrics.overall_score))
        self.groove_stability_score_label.setText(f"{score}%")
        self.groove_stability_bar.setValue(max(0, min(100, score)))
        self.groove_stability_detail_label.setText(
            f"Trajectory: {metrics.trajectory_score:.0f}%  Force: {metrics.force_score:.0f}%  Timing: {metrics.timing_score:.0f}%  Layers: {metrics.layer_score:.0f}%"
        )
        if score >= 80:
            status_text = "Stable"
            color = "#34c759"
        elif score >= 50:
            status_text = "Moderate"
            color = "#ff9f0a"
        else:
            status_text = "Unstable"
            color = "#ff453a"
        self.groove_stability_score_label.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color};")
        self.groove_stability_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                height: 18px;
                color: #f5f5f7;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 8px;
            }}
            """
        )
        self.groove_stability_status_label.setText(f"{status_text}: {score}%")

    def _update_human_likeness(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = (active_session or {}).get("events", [])
        metrics = compute_human_likeness_metrics(events)
        self._latest_human_likeness_metrics = metrics
        if self._human_likeness_dialog is not None and self._human_likeness_dialog.isVisible():
            self._human_likeness_dialog.sync_live_context(
                session_id=snapshot.active_session_id,
                events=[dict(event) for event in events if event.get("messageType") == "touch_event"],
                last_timestamp=snapshot.last_event_timestamp,
            )

        if metrics.human_likeness_score is None:
            self.human_likeness_score_label.setText("Collecting...")
            self.human_likeness_score_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #8e8e93;")
            self.human_likeness_meta_label.setText("Suspicion: collecting…  |  Confidence: Low")
            flags = metrics.explanation_flags[:3] if metrics.explanation_flags else ["collecting live signal"]
            self.human_likeness_flags_label.setText("\n".join(f"• {flag}" for flag in flags))
            return

        score = float(np.clip(metrics.human_likeness_score, 0.0, 100.0))
        suspicion_level = self._suspicion_level(metrics.automation_suspicion_score)
        color = "#34c759" if score >= 70.0 else "#ff9f0a" if score >= 45.0 else "#ff453a"
        self.human_likeness_score_label.setText(f"{score:.0f}")
        self.human_likeness_score_label.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color};")
        self.human_likeness_meta_label.setText(
            f"Suspicion: {suspicion_level}  |  Confidence: {metrics.confidence.title()}  |  Automation: {metrics.automation_suspicion_score:.0f}"
        )
        flags = metrics.explanation_flags[:3] if metrics.explanation_flags else ["collecting live signal"]
        self.human_likeness_flags_label.setText("\n".join(f"• {flag}" for flag in flags))

    def _suspicion_level(self, value: float | None) -> str:
        if value is None:
            return "Collecting"
        if value >= 67.0:
            return "High"
        if value >= 34.0:
            return "Medium"
        return "Low"

    def _open_human_likeness_details(self) -> None:
        metrics = self._latest_human_likeness_metrics
        if metrics is None:
            return
        self._human_likeness_dialog = HumanLikenessDetailsDialog(metrics, self)
        snapshot = self.live_server.snapshot()
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        self._human_likeness_dialog.sync_live_context(
            session_id=snapshot.active_session_id,
            events=[dict(event) for event in (active_session or {}).get("events", []) if event.get("messageType") == "touch_event"],
            last_timestamp=snapshot.last_event_timestamp,
        )
        self._human_likeness_dialog.show()

    def _update_stability_panel(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = [event for event in (active_session or {}).get("events", []) if event.get("messageType") == "touch_event"]
        if len(events) < 2:
            self.drift_label.setText("drift: —")
            self.jitter_label.setText("jitter: collecting…")
            self.stability_label.setText("force/radius stability: collecting…")
            self.sample_health_label.setText("sample-rate health: collecting…")
            return

        sample = events[-60:]
        xs = np.asarray([float(event.get("x", 0.0)) for event in sample], dtype=np.float64)
        ys = np.asarray([float(event.get("y", 0.0)) for event in sample], dtype=np.float64)
        forces = np.asarray([float(event["force"]) if event.get("force") is not None else np.nan for event in sample], dtype=np.float64)
        radii = np.asarray([float(event.get("majorRadius", 0.0)) for event in sample], dtype=np.float64)
        times = np.asarray([float(event.get("timestamp", 0.0)) for event in sample], dtype=np.float64)

        drift_distance = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0])) if len(xs) > 1 else 0.0
        jitter_level = safe_nanstd(np.diff(xs)) if len(xs) > 2 else 0.0
        force_stability = float(max(0.0, 1.0 - safe_nanstd(forces))) if len(forces) else 0.0
        radius_stability = float(max(0.0, 1.0 - safe_nanstd(radii))) if len(radii) else 0.0
        sample_rate_health = self._sample_rate_health(times, snapshot.sample_rate_hz)

        self.drift_label.setText(f"drift: {drift_distance:.2f}px")
        self.jitter_label.setText(f"jitter: {jitter_level:.3f}")
        self.stability_label.setText(f"force/radius stability: {((force_stability + radius_stability) / 2.0):.3f}")
        self.sample_health_label.setText(f"sample-rate health: {sample_rate_health:.2f}")


    def _formatted_pin_sequence(self, entered_pin: str, length: int = 4) -> str:
        cleaned = [char for char in entered_pin if char.isdigit()]
        display: list[str] = cleaned[:length]
        while len(display) < length:
            display.append("_")
        return " ".join(display)

    def _sample_rate_health(self, times: np.ndarray, reported_sample_rate: float) -> float:
        if len(times) < 2:
            return 0.0
        elapsed = float(times[-1] - times[0])
        if elapsed <= 0.0:
            return 0.0
        observed = float(len(times) / elapsed)
        if reported_sample_rate <= 0.0:
            return 0.0
        return float(max(0.0, min(1.0, observed / reported_sample_rate)))

    def _toggle_debug_panel(self) -> None:
        self.debug_panel.setVisible(not self.debug_panel.isVisible())
        self.debug_toggle.setText("Debug" if not self.debug_panel.isVisible() else "Hide Debug")
        self.debug_close_button.setText("Close")
        self.view_restack()

    def toggle_debug_panel(self) -> None:
        self._toggle_debug_panel()

    def is_debug_panel_visible(self) -> bool:
        return self.debug_panel.isVisible()

    def view_restack(self) -> None:
        self.status_bar.raise_()
        self.debug_panel.raise_()

    def _copy_ip_to_clipboard(self) -> None:
        ip_address = self.live_server.snapshot().suggested_lan_ip
        if not ip_address or ip_address == "unavailable":
            return
        QApplication.clipboard().setText(ip_address)

    def _short_session_id(self, session_id: str | None) -> str:
        if not session_id or session_id == "—":
            return "—"
        if len(session_id) <= 10:
            return session_id
        return f"{session_id[:4]}…{session_id[-4:]}"

    def _pretty_input_mode(self, raw_input_type: str | None) -> str:
        normalized = str(raw_input_type or "unknown").strip().lower()
        if normalized == "finger":
            return "Finger"
        if normalized == "pencil":
            return "Pencil"
        if normalized in {"mixed", "indirect", "indirectpointer"}:
            return "Mixed"
        return "Unknown"

    def _normalize_series(self, values: np.ndarray) -> np.ndarray:
        if len(values) == 0:
            return values
        clean = np.nan_to_num(values.astype(np.float64), nan=0.0)
        minimum = float(np.min(clean))
        maximum = float(np.max(clean))
        if abs(maximum - minimum) < 1e-12:
            return np.zeros_like(clean)
        return (clean - minimum) / (maximum - minimum)

    def _phase_color(self, phase_value: float, alpha: int = 220) -> tuple[int, int, int, int]:
        palette = {
            -1.0: (140, 140, 145, alpha),
            0.0: (90, 200, 250, alpha),
            1.0: (52, 199, 89, alpha),
            2.0: (255, 149, 0, alpha),
            3.0: (255, 69, 58, alpha),
        }
        key = phase_value if phase_value in palette else -1.0
        return palette[key]

    def _guard_series_pair(self, times: np.ndarray, phases: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        times = np.asarray(times, dtype=np.float64)
        phases = np.asarray(phases, dtype=np.float64)
        if len(times) == 0 or len(phases) == 0:
            return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
        limit = min(len(times), len(phases))
        if limit <= 0:
            return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
        if len(times) != len(phases):
            times = times[:limit]
            phases = phases[:limit]
        return times, phases


def _phase_to_numeric(phase: str) -> float:
    mapping = {
        "began": 0.0,
        "moved": 1.0,
        "ended": 2.0,
        "cancelled": 3.0,
    }
    return mapping.get(phase, -1.0)
    QMenu,
