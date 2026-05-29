from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.live.telemetry_server import LiveTelemetryServer, TelemetrySnapshot

logger = logging.getLogger(__name__)


class LiveDashboardWidget(QWidget):
    def __init__(self, live_server: LiveTelemetryServer, parent: QWidget | None = None):
        super().__init__(parent)
        self.live_server = live_server
        pg.setConfigOptions(antialias=True)

        self.connection_label = QLabel("Connection: disconnected")
        self.server_state_label = QLabel("Server: stopped")
        self.host_label = QLabel("Listening Host: 0.0.0.0")
        self.port_label = QLabel("Listening Port: 8765")
        self.lan_ip_label = QLabel("Suggested LAN IP: —")
        self.ip_hint_label = QLabel("Use this IP on iOS Logger:")
        self.ip_value = QLineEdit()
        self.ip_value.setReadOnly(True)
        self.ip_value.setPlaceholderText("Waiting for analyzer host IP")
        self.copy_ip_button = QPushButton("Copy IP")
        self.copy_ip_button.clicked.connect(self._copy_ip_to_clipboard)
        self.firewall_label = QLabel("Firewall: allow Python / Touchprint Analyzer on the local network.")
        self.command_hint_label = QLabel("Test command: nc -vz <MacLANIP> 8765")
        self.device_warning_label = QLabel("Physical devices must use the Mac LAN IP, not 127.0.0.1.")
        self.device_label = QLabel("Device: —")
        self.session_label = QLabel("Session: —")
        self.event_count_label = QLabel("Events: 0")
        self.sample_rate_label = QLabel("Sample Rate: 0.00 Hz")
        self.timestamp_label = QLabel("Last Timestamp: —")
        self.export_status_label = QLabel("Export Status: live_only")
        self.warning_label = QLabel("Warnings: none")

        form = QFormLayout()
        form.addRow("Connection", self.connection_label)
        form.addRow("Server", self.server_state_label)
        form.addRow("Host", self.host_label)
        form.addRow("Port", self.port_label)
        form.addRow("Mac LAN IP", self.lan_ip_label)
        ip_row_widget = QWidget()
        ip_row = QHBoxLayout(ip_row_widget)
        ip_row.setContentsMargins(0, 0, 0, 0)
        ip_row.addWidget(self.ip_value, 1)
        ip_row.addWidget(self.copy_ip_button)
        form.addRow(self.ip_hint_label, ip_row_widget)
        form.addRow("Firewall", self.firewall_label)
        form.addRow("Test Hint", self.command_hint_label)
        form.addRow("Device Note", self.device_warning_label)
        form.addRow("Device", self.device_label)
        form.addRow("Session", self.session_label)
        form.addRow("Event Count", self.event_count_label)
        form.addRow("Sample Rate", self.sample_rate_label)
        form.addRow("Last Event", self.timestamp_label)
        form.addRow("Export Status", self.export_status_label)
        form.addRow("Warnings", self.warning_label)

        self.status_box = QPlainTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(140)

        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(status_frame)
        status_layout.addLayout(form)
        status_layout.addWidget(QLabel("Live Diagnostics"))
        status_layout.addWidget(self.status_box)

        self.trajectory_plot = pg.PlotWidget(title="Live Trajectory")
        self.trajectory_plot.setBackground("w")
        self.trajectory_plot.showGrid(x=True, y=True, alpha=0.2)
        self.trajectory_curve = self.trajectory_plot.plot([], [], pen=pg.mkPen("#007aff", width=2))
        self.trajectory_current = pg.ScatterPlotItem(size=10, brush=pg.mkBrush("#ff3b30"), pen=pg.mkPen(None))
        self.trajectory_plot.addItem(self.trajectory_current)

        self.force_plot = pg.PlotWidget(title="Live Force / Radius")
        self.force_plot.setBackground("w")
        self.force_plot.showGrid(x=True, y=True, alpha=0.2)
        self.force_curve = self.force_plot.plot([], [], pen=pg.mkPen("#34c759", width=2))
        self.radius_curve = self.force_plot.plot([], [], pen=pg.mkPen("#ff9500", width=2))

        self.phase_plot = pg.PlotWidget(title="Live Phase Timeline")
        self.phase_plot.setBackground("w")
        self.phase_plot.showGrid(x=True, y=True, alpha=0.2)
        self.phase_curve = self.phase_plot.plot([], [], pen=pg.mkPen("#5856d6", width=2))

        plots_layout = QVBoxLayout()
        plots_layout.addWidget(self.trajectory_plot, 3)
        plots_layout.addWidget(self.force_plot, 2)
        plots_layout.addWidget(self.phase_plot, 1)

        root_layout = QHBoxLayout(self)
        root_layout.addWidget(status_frame, 1)
        root_layout.addLayout(plots_layout, 3)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.live_server.snapshot()
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
        self.connection_label.setText(snapshot.connection_status)
        self.server_state_label.setText(snapshot.server_state)
        self.host_label.setText(snapshot.host)
        self.port_label.setText(str(snapshot.port))
        self.lan_ip_label.setText(snapshot.suggested_lan_ip)
        self.ip_value.setText(snapshot.suggested_lan_ip if snapshot.suggested_lan_ip != "unavailable" else "")
        self.command_hint_label.setText(f"Test command: nc -vz {snapshot.suggested_lan_ip if snapshot.suggested_lan_ip != 'unavailable' else '<MacLANIP>'} {snapshot.port}")
        self.device_label.setText((active_session or {}).get("deviceType", snapshot.export_summary.get("deviceType", "—")) or "—")
        self.session_label.setText(snapshot.active_session_id or "—")
        self.event_count_label.setText(str(snapshot.event_count))
        self.sample_rate_label.setText(f"{snapshot.sample_rate_hz:.2f} Hz")
        self.timestamp_label.setText(
            "—" if snapshot.last_event_timestamp is None else f"{snapshot.last_event_timestamp:.6f}"
        )
        self.export_status_label.setText(snapshot.export_status)
        self.warning_label.setText(str(len(snapshot.warnings)))

        diagnostics = {
            "connectionStatus": snapshot.connection_status,
            "serverState": snapshot.server_state,
            "host": snapshot.host,
            "port": snapshot.port,
            "suggestedLanIp": snapshot.suggested_lan_ip,
            "activeSessionId": snapshot.active_session_id,
            "eventCount": snapshot.event_count,
            "touchCount": snapshot.touch_count,
            "sampleRateHz": snapshot.sample_rate_hz,
            "lastEventTimestamp": snapshot.last_event_timestamp,
            "lastError": snapshot.last_error,
            "droppedMessages": snapshot.dropped_messages,
            "malformedMessages": snapshot.malformed_messages,
            "exportStatus": snapshot.export_status,
            "exportSummary": snapshot.export_summary,
            "warnings": snapshot.warnings,
        }
        self.status_box.setPlainText(json.dumps(diagnostics, indent=2, sort_keys=True))
        self._update_plots(snapshot.sessions)

    def _copy_ip_to_clipboard(self) -> None:
        ip_address = self.ip_value.text().strip()
        if not ip_address:
            return
        QApplication.clipboard().setText(ip_address)

    def _update_plots(self, sessions: list[dict[str, Any]]) -> None:
        active_session_id = self.live_server.snapshot().active_session_id
        if not sessions or active_session_id is None:
            self.trajectory_curve.setData([], [])
            self.trajectory_current.setData([], [])
            self.force_curve.setData([], [])
            self.radius_curve.setData([], [])
            self.phase_curve.setData([], [])
            return

        active_session = next((session for session in sessions if session.get("sessionId") == active_session_id), None)
        if active_session is None:
            self.trajectory_curve.setData([], [])
            self.trajectory_current.setData([], [])
            self.force_curve.setData([], [])
            self.radius_curve.setData([], [])
            self.phase_curve.setData([], [])
            return
        events = [event for event in active_session.get("events", []) if event.get("messageType") == "touch_event"]
        if not events:
            self.trajectory_curve.setData([], [])
            self.trajectory_current.setData([], [])
            self.force_curve.setData([], [])
            self.radius_curve.setData([], [])
            self.phase_curve.setData([], [])
            return

        xs = np.asarray([float(event.get("x", 0.0)) for event in events], dtype=np.float64)
        ys = np.asarray([float(event.get("y", 0.0)) for event in events], dtype=np.float64)
        times = np.asarray([float(event.get("timestamp", 0.0)) for event in events], dtype=np.float64)
        forces = np.asarray([float(event["force"]) if event.get("force") is not None else np.nan for event in events], dtype=np.float64)
        radii = np.asarray([float(event.get("majorRadius", 0.0)) for event in events], dtype=np.float64)

        self.trajectory_curve.setData(xs, ys)
        self.trajectory_current.setData([xs[-1]], [ys[-1]])
        self.force_curve.setData(times, forces)
        self.radius_curve.setData(times, radii)
        phases = np.asarray([_phase_to_numeric(str(event.get("phase", "unknown"))) for event in events], dtype=np.float64)
        self.phase_curve.setData(times, phases)


def _phase_to_numeric(phase: str) -> float:
    mapping = {
        "began": 0.0,
        "moved": 1.0,
        "ended": 2.0,
        "cancelled": 3.0,
    }
    return mapping.get(phase, -1.0)
