from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

GROOVE3D_UNAVAILABLE_BASE_MESSAGE = "3D Groove View unavailable on this system."


@dataclass(slots=True)
class Groove3DTrace:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    z_mode_used: str
    source_count: int


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not np.isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _normalize_01(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return np.asarray([], dtype=np.float32)
    finite = np.isfinite(values)
    if not finite.any():
        return np.zeros(values.shape, dtype=np.float32)
    clean = np.where(finite, values, np.nan)
    minimum = float(np.nanmin(clean))
    maximum = float(np.nanmax(clean))
    span = maximum - minimum
    if span <= 1e-12:
        return np.zeros(values.shape, dtype=np.float32)
    normalized = (clean - minimum) / span
    return np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


def _normalize_axis(values: np.ndarray, explicit_size: float | None) -> np.ndarray:
    if values.size == 0:
        return np.asarray([], dtype=np.float32)
    if explicit_size is not None and explicit_size > 1e-9:
        normalized = values / explicit_size
        return np.clip(np.nan_to_num(normalized, nan=0.0), 0.0, 1.0).astype(np.float32)
    return _normalize_01(values)


def _resolve_axis_size(events: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    for event in reversed(events):
        for key in keys:
            value = _as_float(event.get(key))
            if value is not None and value > 0.0:
                return value
    return None


def build_groove3d_trace(
    events: list[dict[str, Any]],
    *,
    z_mode: str = "force",
    max_points: int = 500,
) -> Groove3DTrace:
    touch_events = [event for event in events if event.get("messageType") == "touch_event"]
    if max_points > 0 and len(touch_events) > max_points:
        touch_events = touch_events[-max_points:]
    if not touch_events:
        return Groove3DTrace(
            x=np.asarray([], dtype=np.float32),
            y=np.asarray([], dtype=np.float32),
            z=np.asarray([], dtype=np.float32),
            z_mode_used=z_mode,
            source_count=0,
        )

    xs = np.asarray([_as_float(event.get("x")) or 0.0 for event in touch_events], dtype=np.float64)
    ys = np.asarray([_as_float(event.get("y")) or 0.0 for event in touch_events], dtype=np.float64)
    force = np.asarray([_as_float(event.get("force")) if _as_float(event.get("force")) is not None else np.nan for event in touch_events], dtype=np.float64)
    max_force = np.asarray(
        [
            _as_float(event.get("maximumPossibleForce")) if _as_float(event.get("maximumPossibleForce")) is not None else np.nan
            for event in touch_events
        ],
        dtype=np.float64,
    )
    radii = np.asarray([_as_float(event.get("majorRadius")) if _as_float(event.get("majorRadius")) is not None else np.nan for event in touch_events], dtype=np.float64)
    phase = np.asarray(
        [
            0.0 if str(event.get("phase", "")).lower() == "began" else 0.5 if str(event.get("phase", "")).lower() == "moved" else 1.0
            if str(event.get("phase", "")).lower() == "ended"
            else 0.25
            for event in touch_events
        ],
        dtype=np.float64,
    )

    width = _resolve_axis_size(touch_events, ("captureWidth", "viewWidth", "screenWidth", "displayWidth"))
    height = _resolve_axis_size(touch_events, ("captureHeight", "viewHeight", "screenHeight", "displayHeight"))
    x_norm = _normalize_axis(xs, width)
    y_norm = _normalize_axis(ys, height)

    safe_max_force = np.where(np.isfinite(max_force) & (max_force > 1e-9), max_force, np.nan)
    force_norm = np.where(np.isfinite(force), force / safe_max_force, np.nan)
    force_norm = np.clip(np.nan_to_num(force_norm, nan=np.nan), 0.0, 1.0)
    radius_norm = _normalize_01(np.nan_to_num(radii, nan=np.nan))

    z_mode_normalized = str(z_mode or "force").strip().lower()
    if z_mode_normalized not in {"force", "radius", "layer"}:
        z_mode_normalized = "force"

    if z_mode_normalized == "force":
        if np.isfinite(force_norm).any() and float(np.nanmax(force_norm)) > 0.0:
            z = np.nan_to_num(force_norm, nan=0.0).astype(np.float32)
            z_mode_used = "force"
        elif np.isfinite(radii).any():
            z = radius_norm.astype(np.float32)
            z_mode_used = "radius"
        else:
            z = np.zeros_like(x_norm, dtype=np.float32)
            z_mode_used = "force"
    elif z_mode_normalized == "radius":
        if np.isfinite(radii).any():
            z = radius_norm.astype(np.float32)
            z_mode_used = "radius"
        elif np.isfinite(force_norm).any():
            z = np.nan_to_num(force_norm, nan=0.0).astype(np.float32)
            z_mode_used = "force"
        else:
            z = np.zeros_like(x_norm, dtype=np.float32)
            z_mode_used = "radius"
    else:
        force_component = np.nan_to_num(force_norm, nan=0.0)
        radius_component = np.nan_to_num(radius_norm, nan=0.0)
        z = np.clip((0.45 * force_component) + (0.45 * radius_component) + (0.10 * phase), 0.0, 1.0).astype(np.float32)
        z_mode_used = "layer"

    return Groove3DTrace(
        x=x_norm.astype(np.float32),
        y=y_norm.astype(np.float32),
        z=z,
        z_mode_used=z_mode_used,
        source_count=len(touch_events),
    )


def groove3d_unavailable_message(details: str | None = None) -> str:
    if details and str(details).strip():
        return f"{GROOVE3D_UNAVAILABLE_BASE_MESSAGE}\n{details}"
    return GROOVE3D_UNAVAILABLE_BASE_MESSAGE
