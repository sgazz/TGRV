from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class CanvasMirrorStroke:
    touch_id: str
    xs: np.ndarray
    ys: np.ndarray
    phase: str
    width: float
    input_type: str
    digit: str | None


@dataclass(slots=True)
class CanvasMirrorFrame:
    strokes: list[CanvasMirrorStroke]
    latest_point: tuple[float, float] | None
    inferred_bounds: bool
    bounds: tuple[float, float, float, float]


def normalize_canvas_points(events: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, bool]:
    touch_events = [event for event in events if event.get("messageType") == "touch_event"]
    if not touch_events:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64), True
    xs = np.asarray([float(event.get("x", 0.0)) for event in touch_events], dtype=np.float64)
    ys = np.asarray([float(event.get("y", 0.0)) for event in touch_events], dtype=np.float64)

    width = _last_positive(touch_events, ("captureWidth", "surfaceWidth", "viewWidth", "screenWidth", "displayWidth"))
    height = _last_positive(touch_events, ("captureHeight", "surfaceHeight", "viewHeight", "screenHeight", "displayHeight"))
    inferred = width is None or height is None

    if width is not None and width > 0:
        xs = np.clip(xs / width, 0.0, 1.0)
    else:
        xs = _minmax(xs)
    if height is not None and height > 0:
        ys = np.clip(ys / height, 0.0, 1.0)
    else:
        ys = _minmax(ys)
    return xs, ys, inferred


def build_canvas_mirror_frame(
    events: list[dict[str, Any]],
    *,
    use_force_thickness: bool = True,
    default_width: float = 2.2,
) -> CanvasMirrorFrame:
    touch_events = [event for event in events if event.get("messageType") == "touch_event"]
    if not touch_events:
        return CanvasMirrorFrame(strokes=[], latest_point=None, inferred_bounds=True, bounds=(0.0, 0.0, 1.0, 1.0))

    nx, ny, inferred = normalize_canvas_points(touch_events)
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, event in enumerate(touch_events):
        touch_id = str(event.get("touchId", f"touch-{index}"))
        grouped.setdefault(touch_id, []).append((index, event))

    strokes: list[CanvasMirrorStroke] = []
    for touch_id, rows in grouped.items():
        rows.sort(key=lambda row: row[0])
        indices = [index for index, _event in rows]
        xs = nx[indices]
        ys = ny[indices]
        last_event = rows[-1][1]
        phase = str(last_event.get("phase", "moved")).lower()
        input_type = str(last_event.get("inputType", "unknown")).lower()
        digit = str(last_event.get("digit")) if last_event.get("digit") is not None else None
        width = _stroke_width(last_event, use_force_thickness, default_width)
        strokes.append(
            CanvasMirrorStroke(
                touch_id=touch_id,
                xs=xs,
                ys=ys,
                phase=phase,
                width=width,
                input_type=input_type,
                digit=digit,
            )
        )

    latest_point = (float(nx[-1]), float(ny[-1]))
    return CanvasMirrorFrame(
        strokes=strokes,
        latest_point=latest_point,
        inferred_bounds=inferred,
        bounds=(0.0, 0.0, 1.0, 1.0),
    )


def _stroke_width(event: dict[str, Any], use_force: bool, default_width: float) -> float:
    if use_force:
        force = event.get("force")
        max_force = event.get("maximumPossibleForce")
        if force is not None and max_force not in (None, 0, 0.0):
            try:
                normalized = float(force) / float(max_force)
                return float(np.clip(1.6 + (normalized * 5.0), 1.2, 8.0))
            except Exception:
                pass
    radius = event.get("majorRadius")
    if radius is not None:
        try:
            return float(np.clip(float(radius) * 0.24, 1.2, 8.0))
        except Exception:
            pass
    return float(default_width)


def _last_positive(events: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    for event in reversed(events):
        for key in keys:
            value = event.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except Exception:
                continue
            if number > 0:
                return number
    return None


def _minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    minimum = float(np.nanmin(values))
    maximum = float(np.nanmax(values))
    span = maximum - minimum
    if span <= 1e-9:
        return np.zeros_like(values)
    return (values - minimum) / span

