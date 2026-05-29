from __future__ import annotations

import csv
from math import hypot
from io import StringIO
from statistics import mean, pstdev
from typing import Any

import numpy as np

from touchprint_lab.analyzer.models import TouchEventRecord, TouchSessionRecord
from touchprint_lab.utils.numeric import safe_nanvar


def session_rows(session: TouchSessionRecord) -> list[dict[str, Any]]:
    rows = [event.to_dict() for event in session.events]
    return sorted(rows, key=lambda item: item["timestamp"])


def session_csv(session: TouchSessionRecord) -> str:
    rows = session_rows(session)
    if not rows:
        return ""
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def touch_duration_statistics(session: TouchSessionRecord) -> dict[str, float]:
    grouped = _group_by_touch(session.events)
    durations = [
        touch_events[-1].timestamp - touch_events[0].timestamp
        for touch_events in grouped.values()
        if len(touch_events) > 1
    ]
    if not durations:
        return {"mean_duration": 0.0, "std_duration": 0.0, "max_duration": 0.0, "touch_count": 0.0}
    return {
        "mean_duration": float(mean(durations)),
        "std_duration": float(pstdev(durations)) if len(durations) > 1 else 0.0,
        "max_duration": float(max(durations)),
        "touch_count": float(len(durations)),
    }


def average_force(session: TouchSessionRecord) -> float:
    values = [event.force for event in session.events if event.force is not None]
    return float(mean(values)) if values else 0.0


def force_variance(session: TouchSessionRecord) -> float:
    values = [event.force for event in session.events if event.force is not None]
    return safe_nanvar(values)


def radius_variance(session: TouchSessionRecord) -> float:
    values = [event.major_radius for event in session.events]
    return safe_nanvar(values)


def drift_distance(session: TouchSessionRecord) -> float:
    if not session.events:
        return 0.0
    first = session.events[0]
    last = session.events[-1]
    return float(hypot(last.x - first.x, last.y - first.y))


def velocity_estimation(session: TouchSessionRecord) -> dict[str, float]:
    if len(session.events) < 2:
        return {"mean_velocity": 0.0, "peak_velocity": 0.0}
    velocities: list[float] = []
    ordered = sorted(session.events, key=lambda item: item.timestamp)
    for previous, current in zip(ordered, ordered[1:]):
        dt = current.timestamp - previous.timestamp
        if dt <= 0:
            continue
        distance = hypot(current.x - previous.x, current.y - previous.y)
        velocities.append(distance / dt)
    if not velocities:
        return {"mean_velocity": 0.0, "peak_velocity": 0.0}
    return {"mean_velocity": float(mean(velocities)), "peak_velocity": float(max(velocities))}


def inter_touch_timing(session: TouchSessionRecord) -> list[float]:
    begins = sorted(
        [event.timestamp for event in session.events if event.phase == "began"]
    )
    return [current - previous for previous, current in zip(begins, begins[1:])]


def session_summary_metrics(session: TouchSessionRecord) -> dict[str, Any]:
    rows = session_rows(session)
    timing = inter_touch_timing(session)
    velocity = velocity_estimation(session)
    timestamps = [row["timestamp"] for row in rows]
    metrics = {
        "session_id": session.session_id,
        "device_type": session.device_type,
        "input_type": session.resolved_input_type(),
        "event_count": len(rows),
        "touch_count": len({row["touchId"] for row in rows}),
        "duration_seconds": float(max(timestamps) - min(timestamps)) if timestamps else 0.0,
        "average_force": average_force(session),
        "force_variance": force_variance(session),
        "radius_variance": radius_variance(session),
        "drift_distance": drift_distance(session),
        "mean_touch_duration": touch_duration_statistics(session)["mean_duration"],
        "mean_velocity": velocity["mean_velocity"],
        "peak_velocity": velocity["peak_velocity"],
        "inter_touch_interval_mean": float(mean(timing)) if timing else 0.0,
        "inter_touch_interval_std": float(pstdev(timing)) if len(timing) > 1 else 0.0,
    }
    return metrics


def touch_density_grid(session: TouchSessionRecord, bins: int = 64) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not session.events:
        return np.zeros((bins, bins)), np.array([]), np.array([])
    x = np.asarray([event.x for event in session.events], dtype=np.float64)
    y = np.asarray([event.y for event in session.events], dtype=np.float64)
    grid, x_edges, y_edges = np.histogram2d(x, y, bins=bins)
    return grid.T, x_edges, y_edges


def _group_by_touch(events: list[TouchEventRecord]) -> dict[str, list[TouchEventRecord]]:
    grouped: dict[str, list[TouchEventRecord]] = {}
    for event in sorted(events, key=lambda item: item.timestamp):
        grouped.setdefault(event.touch_id, []).append(event)
    return grouped
