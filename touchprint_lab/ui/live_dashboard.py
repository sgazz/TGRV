from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.live.telemetry_server import LiveTelemetryServer, TelemetrySnapshot
from touchprint_lab.live.research_metrics import (
    compute_groove_stability_metrics,
    compute_pin_rhythm_metrics,
    compute_pressure_fingerprint_metrics,
)
from touchprint_lab.utils.numeric import safe_nanstd

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveLayoutState:
    mode: str = "default"
    panel_id: str | None = None


class LivePanelCard(QFrame):
    def __init__(
        self,
        dashboard: "LiveDashboardWidget",
        panel_id: str,
        title: str,
        content_widget: QWidget,
        *,
        compact_min_height: int = 180,
    ) -> None:
        super().__init__()
        self.dashboard = dashboard
        self.panel_id = panel_id
        self.title = title
        self.content_widget = content_widget
        self.compact_min_height = compact_min_height
        self._focused = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)

        self.zoom_quarter_button = QToolButton()
        self.zoom_quarter_button.setText("1/4")
        self.zoom_quarter_button.setToolTip(f"Focus {title} to about one quarter of the live area")
        self.zoom_quarter_button.clicked.connect(lambda: self.dashboard.focus_panel(self.panel_id, "quarter"))
        self.zoom_quarter_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.zoom_half_button = QToolButton()
        self.zoom_half_button.setText("1/2")
        self.zoom_half_button.setToolTip(f"Focus {title} to about one half of the live area")
        self.zoom_half_button.clicked.connect(lambda: self.dashboard.focus_panel(self.panel_id, "half"))
        self.zoom_half_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.restore_button = QToolButton()
        self.restore_button.setText("Restore")
        self.restore_button.setToolTip("Restore the default live cockpit layout")
        self.restore_button.clicked.connect(self.dashboard.restore_live_layout)
        self.restore_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_button.setVisible(False)

        header_buttons = [self.zoom_quarter_button, self.zoom_half_button, self.restore_button]
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
        self._apply_state(False, "default")

    def set_compact_mode(self, enabled: bool) -> None:
        minimum_height = max(120, self.compact_min_height - 30) if enabled else self.compact_min_height
        self.content_widget.setMinimumHeight(minimum_height)

    def _apply_state(self, focused: bool, mode: str) -> None:
        self._focused = focused
        if focused:
            self.title_label.setText(f"Focused: {self.title}")
            self.title_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #5ac8fa;")
            self.zoom_quarter_button.setVisible(False)
            self.zoom_half_button.setVisible(False)
            self.restore_button.setVisible(True)
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
            self.zoom_quarter_button.setVisible(True)
            self.zoom_half_button.setVisible(True)
            self.restore_button.setVisible(False)
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

class LiveDashboardWidget(QWidget):
    def __init__(self, live_server: LiveTelemetryServer, parent: QWidget | None = None):
        super().__init__(parent)
        self.live_server = live_server
        self._plot_error_keys: set[str] = set()
        self._pin_highlight_token = 0
        self._live_layout_state = LiveLayoutState()
        self._panel_cards: dict[str, LivePanelCard] = {}
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
        self.device_chip = self._make_chip("device: —")
        self.input_chip = self._make_chip("input: —")
        self.sample_rate_chip = self._make_chip("sample rate: 0.00 Hz")
        self.session_chip = self._make_chip("session: —")
        self.export_chip = self._make_chip("export: live_only")
        self.debug_toggle = QToolButton()
        self.debug_toggle.setText("Debug")
        self.debug_toggle.setToolTip("Show or hide developer diagnostics")
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
        self.pin_mirror_frame.setMinimumHeight(260)
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
        self.pin_sequence_label = QLabel("PIN: —")
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
                    spacer.setFixedSize(28, 24)
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
        self.phase_plot = self._make_plot("Phase Timeline", minimum_height=110)

        self.pressure_frame = QFrame()
        self.pressure_frame.setMinimumHeight(260)
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
        self.groove_stability_frame.setMinimumHeight(260)
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

        self.panel_cards = {
            "trajectory": LivePanelCard(self, "trajectory", "Touch Trajectory", self.trajectory_plot, compact_min_height=220),
            "force_radius": LivePanelCard(self, "force_radius", "Force / Radius Timeline", self.force_plot, compact_min_height=220),
            "signature_layer": LivePanelCard(self, "signature_layer", "Signature Layer", self.signature_plot, compact_min_height=220),
            "groove_view": LivePanelCard(self, "groove_view", "Groove View", self.groove_plot, compact_min_height=220),
            "phase_timeline": LivePanelCard(self, "phase_timeline", "Phase Timeline", self.phase_plot, compact_min_height=130),
            "pin_keyboard_mirror": LivePanelCard(self, "pin_keyboard_mirror", "PIN Keyboard Mirror", self.pin_mirror_frame, compact_min_height=220),
            "pressure_fingerprint": LivePanelCard(self, "pressure_fingerprint", "Pressure Fingerprint", self.pressure_frame, compact_min_height=220),
            "groove_stability": LivePanelCard(self, "groove_stability", "Groove Stability", self.groove_stability_frame, compact_min_height=220),
        }

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
        root_layout.addWidget(self.panel_root, 1)

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
        self.debug_copy_ip_button.clicked.connect(self._copy_ip_to_clipboard)
        debug_ip_layout.addWidget(self.debug_ip_label, 1)
        debug_ip_layout.addWidget(self.debug_copy_ip_button)
        debug_layout.addWidget(self.debug_ip_row)

        self.debug_status_box = QPlainTextEdit()
        self.debug_status_box.setReadOnly(True)
        self.debug_status_box.setMinimumHeight(160)
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
        cell.setFixedSize(36, 32)
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

        register("Escape", self.restore_live_layout)
        for sequence, panel_id in [
            ("Ctrl+1", "trajectory"),
            ("Meta+1", "trajectory"),
            ("Ctrl+2", "force_radius"),
            ("Meta+2", "force_radius"),
            ("Ctrl+3", "groove_view"),
            ("Meta+3", "groove_view"),
            ("Ctrl+4", "groove_stability"),
            ("Meta+4", "groove_stability"),
        ]:
            register(sequence, lambda panel_id=panel_id: self.focus_panel(panel_id, "half"))

    def focus_panel(self, panel_id: str, fraction: str) -> None:
        if panel_id not in self.panel_cards:
            return
        mode = "quarter" if fraction == "quarter" else "half"
        self._live_layout_state = LiveLayoutState(mode=mode, panel_id=panel_id)
        self._apply_live_layout()

    def restore_live_layout(self) -> None:
        self._live_layout_state = LiveLayoutState()
        self._apply_live_layout()

    def _clear_layout(self, layout: QGridLayout | QHBoxLayout | QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _apply_live_layout(self) -> None:
        state = self._live_layout_state
        focused_panel = self.panel_cards.get(state.panel_id) if state.panel_id else None

        for card in self.panel_cards.values():
            card.set_compact_mode(state.mode != "default")
            card._apply_state(card is focused_panel, state.mode)

        self._clear_layout(self.focus_area_layout)
        self._clear_layout(self.overview_grid)

        default_positions = {
            "trajectory": (0, 0),
            "force_radius": (0, 1),
            "signature_layer": (0, 2),
            "groove_view": (0, 3),
            "phase_timeline": (1, 0),
            "pin_keyboard_mirror": (1, 1),
            "pressure_fingerprint": (1, 2),
            "groove_stability": (1, 3),
        }

        if focused_panel is None or state.mode == "default":
            self.focus_area.setVisible(False)
            self.panel_root_layout.setStretch(0, 0)
            self.panel_root_layout.setStretch(1, 1)
            for panel_id, card in self.panel_cards.items():
                row, column = default_positions[panel_id]
                self.overview_grid.addWidget(card, row, column)
            for column in range(4):
                self.overview_grid.setColumnStretch(column, 1)
            for row in range(2):
                self.overview_grid.setRowStretch(row, 1)
            return

        self.focus_area.setVisible(True)
        self.focus_area_layout.addWidget(focused_panel)
        focus_stretch = 1 if state.mode == "quarter" else 2
        overview_stretch = 3 if state.mode == "quarter" else 2
        self.panel_root_layout.setStretch(0, focus_stretch)
        self.panel_root_layout.setStretch(1, overview_stretch)

        for panel_id, card in self.panel_cards.items():
            if card is focused_panel:
                continue
            row, column = default_positions[panel_id]
            self.overview_grid.addWidget(card, row, column)
        for column in range(4):
            self.overview_grid.setColumnStretch(column, 1)
        for row in range(2):
            self.overview_grid.setRowStretch(row, 1)

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

    def _update_control_message(self, snapshot: TelemetrySnapshot) -> None:
        message = snapshot.control_message
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

    def _clear_plots(self) -> None:
        for plot in [self.trajectory_plot, self.force_plot, self.signature_plot, self.groove_plot, self.phase_plot, self.pressure_hist_plot]:
            plot.clear()

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

    def _update_pin_rhythm_panel(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        events = (active_session or {}).get("events", [])
        metrics = compute_pin_rhythm_metrics(events)

        if metrics.collecting:
            self.pin_sequence_label.setText("PIN: —")
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
