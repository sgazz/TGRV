from __future__ import annotations

import json
import logging
import math
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.live.telemetry_server import LiveTelemetryServer, TelemetrySnapshot
from touchprint_lab.utils.numeric import safe_nanstd

logger = logging.getLogger(__name__)


class LiveDashboardWidget(QWidget):
    def __init__(self, live_server: LiveTelemetryServer, parent: QWidget | None = None):
        super().__init__(parent)
        self.live_server = live_server
        self._plot_error_keys: set[str] = set()
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
        status_layout.addWidget(self.sample_rate_chip)
        status_layout.addWidget(self.session_chip)
        status_layout.addWidget(self.export_chip)
        status_layout.addStretch(1)
        status_layout.addWidget(self.debug_toggle)

        root_layout.addWidget(self.status_bar)

        self.stability_frame = QFrame()
        self.stability_frame.setStyleSheet(
            """
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f7;
            }
            """
        )
        stability_layout = QHBoxLayout(self.stability_frame)
        stability_layout.setContentsMargins(12, 8, 12, 8)
        stability_layout.setSpacing(12)

        self.drift_label = self._make_metric_chip("drift: —")
        self.jitter_label = self._make_metric_chip("jitter: —")
        self.stability_label = self._make_metric_chip("force/radius stability: —")
        self.sample_health_label = self._make_metric_chip("sample-rate health: —")
        stability_layout.addWidget(self.drift_label)
        stability_layout.addWidget(self.jitter_label)
        stability_layout.addWidget(self.stability_label)
        stability_layout.addWidget(self.sample_health_label)
        stability_layout.addStretch(1)

        root_layout.addWidget(self.stability_frame)

        plots_frame = QFrame()
        plots_layout = QGridLayout(plots_frame)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.setSpacing(8)

        self.trajectory_plot = self._make_plot("Touch Trajectory")
        self.force_plot = self._make_plot("Force / Radius Timeline")
        self.signature_plot = self._make_plot("Signature Layer")
        self.groove_plot = self._make_plot("Groove View")
        self.phase_plot = self._make_plot("Phase Timeline", minimum_height=140)

        plots_layout.addWidget(self.trajectory_plot, 0, 0)
        plots_layout.addWidget(self.force_plot, 0, 1)
        plots_layout.addWidget(self.signature_plot, 1, 0)
        plots_layout.addWidget(self.groove_plot, 1, 1)
        plots_layout.addWidget(self.phase_plot, 2, 0, 1, 2)

        root_layout.addWidget(plots_frame, 1)

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

    def _make_plot(self, title: str, minimum_height: int = 240) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setMinimumHeight(minimum_height)
        plot.setBackground("#0f1014")
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.getPlotItem().titleLabel.setText(title, size="12pt")
        plot.getPlotItem().titleLabel.setText(
            f'<span style="color:#f5f5f7;">{title}</span>',
            size="12pt",
        )
        plot.getPlotItem().getAxis("left").setPen(pg.mkPen("#8e8e93"))
        plot.getPlotItem().getAxis("bottom").setPen(pg.mkPen("#8e8e93"))
        return plot

    def _install_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self) -> None:
        snapshot = self.live_server.snapshot()
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        try:
            active_session = next((session for session in snapshot.sessions if session.get("sessionId") == snapshot.active_session_id), None)
            self.connection_chip.setText(snapshot.connection_status)
            self.device_chip.setText(f"device: {(active_session or {}).get('deviceType', snapshot.export_summary.get('deviceType', '—')) or '—'}")
            self.sample_rate_chip.setText(f"sample rate: {snapshot.sample_rate_hz:.2f} Hz")
            self.session_chip.setText(f"session: {self._short_session_id(snapshot.active_session_id)}")
            self.export_chip.setText(f"export: {snapshot.export_status}")

            self._update_plot_surfaces(snapshot, active_session)
            self._update_debug_panel(snapshot)
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
        self._update_stability_panel(snapshot)

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
        self._render_phase_timeline(times, phases)

    def _clear_plots(self) -> None:
        for plot in [self.trajectory_plot, self.force_plot, self.signature_plot, self.groove_plot, self.phase_plot]:
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

    def _render_phase_timeline(self, times: np.ndarray, phases: np.ndarray) -> None:
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
        plot.setLabel("left", "Phase", units="began/moved/ended/cancelled")
        plot.setLabel("bottom", "Timestamp")
        plot.getAxis("left").setTicks([
            [(0, "began"), (1, "moved"), (2, "ended"), (-1, "cancelled")]
        ])

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
