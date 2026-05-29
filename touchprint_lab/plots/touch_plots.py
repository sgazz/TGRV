from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget

from touchprint_lab.analyzer.analysis import inter_touch_timing, touch_density_grid
from touchprint_lab.analyzer.models import TouchSessionRecord


class TouchPlotWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.session: TouchSessionRecord | None = None
        self.current_index = 0

        self.trajectory_plot = pg.PlotWidget(title="Touch Trajectory")
        self.trajectory_plot.setBackground("w")
        self.trajectory_plot.showGrid(x=True, y=True, alpha=0.2)
        self.trajectory_plot.setAspectLocked(False)
        self.trajectory_curve = self.trajectory_plot.plot([], [], pen=pg.mkPen("#00a3ff", width=2))
        self.trajectory_density = pg.ImageItem()
        self.trajectory_plot.addItem(self.trajectory_density)
        self.current_point = pg.ScatterPlotItem(size=12, brush=pg.mkBrush("#ff2d55"), pen=pg.mkPen(None))
        self.trajectory_plot.addItem(self.current_point)

        self.force_plot = pg.PlotWidget(title="Force / Radius over Time")
        self.force_plot.setBackground("w")
        self.force_plot.showGrid(x=True, y=True, alpha=0.2)
        self.force_curve = self.force_plot.plot([], [], pen=pg.mkPen("#34c759", width=2), name="Force")
        self.radius_curve = self.force_plot.plot([], [], pen=pg.mkPen("#ff9500", width=2), name="Radius")

        self.timing_plot = pg.PlotWidget(title="Inter-touch Timing")
        self.timing_plot.setBackground("w")
        self.timing_plot.showGrid(x=True, y=True, alpha=0.2)
        self.timing_curve = self.timing_plot.plot([], [], pen=pg.mkPen("#5856d6", width=2), stepMode=False)

        self.replay_slider = QSlider(Qt.Orientation.Horizontal)
        self.replay_slider.setMinimum(0)
        self.replay_slider.valueChanged.connect(self._handle_slider_change)
        self.play_button = QPushButton("Play Replay")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._toggle_play)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.replay_slider, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.trajectory_plot, 3)
        layout.addWidget(self.force_plot, 2)
        layout.addWidget(self.timing_plot, 1)
        layout.addLayout(controls)

        self.timer = QTimer(self)
        self.timer.setInterval(35)
        self.timer.timeout.connect(self._advance_replay)

    def set_session(self, session: TouchSessionRecord | None) -> None:
        self.session = session
        self.current_index = 0
        self.play_button.setChecked(False)
        self.timer.stop()

        if session is None or not session.events:
            self._clear_plots()
            return

        events = sorted(session.events, key=lambda item: item.timestamp)
        x = np.asarray([event.x for event in events], dtype=np.float64)
        y = np.asarray([event.y for event in events], dtype=np.float64)
        force = np.asarray([event.force if event.force is not None else np.nan for event in events], dtype=np.float64)
        radius = np.asarray([event.major_radius for event in events], dtype=np.float64)
        times = np.asarray([event.timestamp for event in events], dtype=np.float64)

        self.trajectory_curve.setData(x, y)
        self._update_density(x, y)

        self.force_curve.setData(times, force)
        self.radius_curve.setData(times, radius)

        timing = inter_touch_timing(session)
        if timing:
            xs = np.arange(1, len(timing) + 1, dtype=np.float64)
            self.timing_curve.setData(xs, np.asarray(timing, dtype=np.float64))
        else:
            self.timing_curve.setData([], [])

        self.replay_slider.blockSignals(True)
        self.replay_slider.setMaximum(len(events) - 1)
        self.replay_slider.setValue(0)
        self.replay_slider.blockSignals(False)
        self._set_current_point(0)

    def _clear_plots(self) -> None:
        self.trajectory_curve.setData([], [])
        self.force_curve.setData([], [])
        self.radius_curve.setData([], [])
        self.timing_curve.setData([], [])
        self.trajectory_density.clear()
        self.current_point.setData([], [])
        self.replay_slider.blockSignals(True)
        self.replay_slider.setMaximum(0)
        self.replay_slider.setValue(0)
        self.replay_slider.blockSignals(False)

    def _update_density(self, x: np.ndarray, y: np.ndarray) -> None:
        if len(x) == 0:
            self.trajectory_density.clear()
            return
        density, x_edges, y_edges = touch_density_grid(self.session)  # type: ignore[arg-type]
        self.trajectory_density.setImage(density, autoLevels=True)
        self.trajectory_density.setRect(
            QRectF(
                float(x_edges[0]),
                float(y_edges[0]),
                float(x_edges[-1] - x_edges[0]),
                float(y_edges[-1] - y_edges[0]),
            )
        )
        self.trajectory_density.setOpacity(0.35)

    def _handle_slider_change(self, value: int) -> None:
        self.current_index = value
        self._set_current_point(value)

    def _set_current_point(self, index: int) -> None:
        if self.session is None or not self.session.events:
            self.current_point.setData([], [])
            return
        events = sorted(self.session.events, key=lambda item: item.timestamp)
        index = max(0, min(index, len(events) - 1))
        event = events[index]
        self.current_point.setData([event.x], [event.y])

    def _toggle_play(self, checked: bool) -> None:
        if checked:
            self.timer.start()
        else:
            self.timer.stop()

    def _advance_replay(self) -> None:
        if self.session is None or not self.session.events:
            self.timer.stop()
            self.play_button.setChecked(False)
            return
        next_index = self.replay_slider.value() + 1
        if next_index > self.replay_slider.maximum():
            self.timer.stop()
            self.play_button.setChecked(False)
            return
        self.replay_slider.setValue(next_index)
