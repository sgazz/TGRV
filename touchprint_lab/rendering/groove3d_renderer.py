from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from touchprint_lab.live.groove3d import Groove3DTrace
from touchprint_lab.rendering.metal_groove_renderer import detect_metal_availability

try:
    import pyqtgraph as pg
except Exception as error:  # pragma: no cover - environment dependent
    pg = None  # type: ignore[assignment]
    _PG_ERROR = str(error)
else:
    _PG_ERROR = ""

try:
    from pyqtgraph.opengl import GLGridItem, GLLinePlotItem, GLScatterPlotItem, GLViewWidget

    _OPENGL_AVAILABLE = True
    _OPENGL_REASON = "OpenGL available"
except Exception as error:  # pragma: no cover - environment dependent
    GLGridItem = GLLinePlotItem = GLScatterPlotItem = GLViewWidget = None  # type: ignore[assignment]
    _OPENGL_AVAILABLE = False
    _OPENGL_REASON = f"OpenGL unavailable: {error}"


class Groove3DRendererBase(Protocol):
    name: str
    available: bool
    reason: str

    def widget(self) -> QWidget: ...
    def clear(self) -> None: ...
    def render_trace(self, trace: Groove3DTrace) -> None: ...
    def reset_camera(self) -> None: ...
    def set_auto_rotate(self, enabled: bool) -> None: ...


class Fallback2DGrooveRenderer:
    name = "2D fallback"

    def __init__(self) -> None:
        self.available = True
        self.reason = "Always available"
        self._plot = None
        if pg is None:
            self.reason = f"pyqtgraph unavailable: {_PG_ERROR}"
            self._label = QLabel("2D fallback visualization unavailable: pyqtgraph is missing.")
            self._label.setWordWrap(True)
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return
        self._plot = pg.PlotWidget()
        self._plot.setBackground("#0f1014")
        self._plot.showGrid(x=True, y=True, alpha=0.18)
        self._plot.setLabel("left", "Y + Z")
        self._plot.setLabel("bottom", "X")

    def widget(self) -> QWidget:
        if self._plot is not None:
            return self._plot
        return self._label

    def clear(self) -> None:
        if self._plot is not None:
            self._plot.clear()

    def render_trace(self, trace: Groove3DTrace) -> None:
        if self._plot is None:
            return
        self._plot.clear()
        if trace.source_count == 0:
            return
        x = trace.x
        y = trace.y + (0.35 * trace.z)
        self._plot.addItem(pg.PlotDataItem(x, y, pen=pg.mkPen("#5ac8fa", width=2)))
        self._plot.addItem(pg.ScatterPlotItem([x[-1]], [y[-1]], size=8, brush=pg.mkBrush("#ff453a"), pen=pg.mkPen(None)))

    def reset_camera(self) -> None:
        self._plot.enableAutoRange()

    def set_auto_rotate(self, enabled: bool) -> None:
        _ = enabled


class OpenGLGroove3DRenderer:
    name = "OpenGL"

    def __init__(self) -> None:
        self.available = bool(_OPENGL_AVAILABLE and pg is not None)
        self.reason = _OPENGL_REASON if pg is not None else f"pyqtgraph unavailable: {_PG_ERROR}"
        if not self.available or GLViewWidget is None:
            self._fallback_label = QLabel(self.reason)
            self._fallback_label.setWordWrap(True)
            return
        self._view = GLViewWidget()
        self._view.setMinimumHeight(180)
        self._grid = GLGridItem()
        self._grid.setSize(1.2, 1.2)
        self._grid.setSpacing(0.1, 0.1)
        self._view.addItem(self._grid)
        self._line = GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(0.35, 0.78, 0.98, 0.95),
            width=2.0,
            antialias=True,
            mode="line_strip",
        )
        self._points = GLScatterPlotItem(pos=np.zeros((1, 3), dtype=np.float32), color=(0.20, 0.70, 0.99, 0.60), size=5.0)
        self._last = GLScatterPlotItem(pos=np.zeros((1, 3), dtype=np.float32), color=(1.0, 0.27, 0.23, 0.95), size=10.0)
        self._view.addItem(self._line)
        self._view.addItem(self._points)
        self._view.addItem(self._last)
        self._auto_rotate = False
        self.reset_camera()

    def widget(self) -> QWidget:
        if self.available and hasattr(self, "_view"):
            return self._view
        return self._fallback_label

    def clear(self) -> None:
        if not self.available or not hasattr(self, "_line"):
            return
        empty = np.zeros((1, 3), dtype=np.float32)
        self._line.setData(pos=empty, color=(0.35, 0.78, 0.98, 0.0), width=1.0, mode="line_strip")
        self._points.setData(pos=empty, color=(0.20, 0.70, 0.99, 0.0), size=1.0)
        self._last.setData(pos=empty, color=(1.0, 0.27, 0.23, 0.0), size=1.0)

    def render_trace(self, trace: Groove3DTrace) -> None:
        if not self.available or not hasattr(self, "_line"):
            return
        if trace.source_count == 0:
            self.clear()
            return
        points = np.column_stack((trace.x, trace.y, trace.z)).astype(np.float32)
        self._line.setData(pos=points, color=(0.35, 0.78, 0.98, 0.95), width=2.0, mode="line_strip")
        self._points.setData(pos=points[-90:], color=(0.20, 0.70, 0.99, 0.65), size=5.0)
        self._last.setData(pos=points[-1:].astype(np.float32), color=(1.0, 0.27, 0.23, 0.98), size=10.0)
        if self._auto_rotate:
            self._view.orbit(0.55, 0.0)

    def reset_camera(self) -> None:
        if not self.available or not hasattr(self, "_view"):
            return
        self._view.opts["center"] = pg.Vector(0.5, 0.5, 0.4)
        self._view.opts["distance"] = 2.5
        self._view.opts["elevation"] = 24
        self._view.opts["azimuth"] = -38
        self._view.update()

    def set_auto_rotate(self, enabled: bool) -> None:
        self._auto_rotate = bool(enabled)


class MetalGroove3DRenderer:
    name = "Metal"

    def __init__(self) -> None:
        availability = detect_metal_availability() if platform.system() == "Darwin" else None
        self.available = bool(availability and availability.available)
        self.reason = "Metal available (experimental)."
        if availability and not availability.available:
            self.reason = availability.reason
        if platform.system() != "Darwin":
            self.reason = "Metal backend is macOS-only."
            self.available = False
        self._label = QLabel(
            "Metal renderer is experimental.\n"
            "Live 3D rendering currently falls back automatically to OpenGL/2D."
        )
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def widget(self) -> QWidget:
        return self._label

    def clear(self) -> None:
        return

    def render_trace(self, trace: Groove3DTrace) -> None:
        _ = trace

    def reset_camera(self) -> None:
        return

    def set_auto_rotate(self, enabled: bool) -> None:
        _ = enabled


@dataclass(slots=True)
class RendererSelection:
    renderer: Groove3DRendererBase
    status: str
    reason: str


def select_renderer(mode: str) -> RendererSelection:
    normalized = str(mode or "auto").strip().lower()
    is_macos = platform.system() == "Darwin"

    metal = MetalGroove3DRenderer()
    ogl = OpenGLGroove3DRenderer()
    fallback = Fallback2DGrooveRenderer()

    if normalized == "metal":
        if metal.available:
            return RendererSelection(ogl, "OpenGL", f"Metal selected but experimental path uses OpenGL fallback: {metal.reason}")
        if ogl.available:
            return RendererSelection(ogl, "OpenGL", f"Metal unavailable: {metal.reason}")
        return RendererSelection(fallback, "2D fallback", f"Metal unavailable: {metal.reason}; OpenGL unavailable: {ogl.reason}")

    if normalized == "opengl":
        if ogl.available:
            return RendererSelection(ogl, "OpenGL", ogl.reason)
        return RendererSelection(fallback, "2D fallback", f"OpenGL unavailable: {ogl.reason}")

    if normalized in {"2d", "2d fallback", "fallback"}:
        return RendererSelection(fallback, "2D fallback", fallback.reason)

    if is_macos:
        if metal.available:
            if ogl.available:
                return RendererSelection(ogl, "OpenGL", f"Metal detected ({metal.reason}), using OpenGL until Metal draw path is enabled.")
            return RendererSelection(fallback, "2D fallback", f"Metal detected but OpenGL unavailable: {ogl.reason}")
        if ogl.available:
            return RendererSelection(ogl, "OpenGL", f"Metal unavailable: {metal.reason}")
        return RendererSelection(fallback, "2D fallback", f"Metal unavailable: {metal.reason}; OpenGL unavailable: {ogl.reason}")

    if ogl.available:
        return RendererSelection(ogl, "OpenGL", ogl.reason)
    return RendererSelection(fallback, "2D fallback", f"OpenGL unavailable: {ogl.reason}")
