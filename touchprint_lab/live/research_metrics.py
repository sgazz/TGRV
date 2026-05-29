from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from touchprint_lab.utils.numeric import safe_nanstd, safe_nanvar


def _event_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        return dict(event.to_dict())
    return dict(event)


def _finite_array(values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 0:
        array = array.reshape(1)
    return array[np.isfinite(array)]


def _safe_mean(values: Sequence[float] | np.ndarray, default: float = 0.0) -> float:
    array = _finite_array(values)
    if array.size == 0:
        return float(default)
    return float(np.mean(array))


def _safe_median(values: Sequence[float] | np.ndarray, default: float = 0.0) -> float:
    array = _finite_array(values)
    if array.size == 0:
        return float(default)
    return float(np.median(array))


def _safe_cosine_similarity(left: Sequence[float] | np.ndarray, right: Sequence[float] | np.ndarray) -> float:
    left_array = _finite_array(left)
    right_array = _finite_array(right)
    if left_array.size == 0 or right_array.size == 0:
        return 0.0
    limit = min(left_array.size, right_array.size)
    if limit <= 0:
        return 0.0
    left_array = left_array[:limit]
    right_array = right_array[:limit]
    left_norm = float(np.linalg.norm(left_array))
    right_norm = float(np.linalg.norm(right_array))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    similarity = float(np.dot(left_array, right_array) / (left_norm * right_norm))
    return float(np.clip(similarity, -1.0, 1.0))


def _resample_series(values: Sequence[float] | np.ndarray, target_length: int = 16) -> np.ndarray:
    array = _finite_array(values)
    if array.size == 0:
        return np.zeros(target_length, dtype=np.float64)
    if array.size == 1:
        return np.repeat(array[0], target_length)
    source = np.linspace(0.0, 1.0, array.size)
    target = np.linspace(0.0, 1.0, target_length)
    return np.interp(target, source, array).astype(np.float64)


def _normalize_series(values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = _finite_array(values)
    if array.size == 0:
        return np.asarray([], dtype=np.float64)
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    if abs(maximum - minimum) <= 1e-12:
        return np.zeros_like(array)
    return ((array - minimum) / (maximum - minimum)).astype(np.float64)


def _phase_histogram(events: list[dict[str, Any]]) -> np.ndarray:
    mapping = {"began": 0, "moved": 1, "ended": 2, "cancelled": 3}
    counts = np.zeros(4, dtype=np.float64)
    for event in events:
        phase = str(event.get("phase", "")).lower()
        index = mapping.get(phase)
        if index is not None:
            counts[index] += 1.0
    total = float(counts.sum())
    if total <= 0.0:
        return counts
    return counts / total


@dataclass(slots=True)
class PinRhythmMetrics:
    sequence_id: str | None
    intervals_ms: list[float]
    average_interval_ms: float | None
    interval_variance_ms: float | None
    consistency_score: float | None
    digit_text: str
    bar_text: str
    collecting: bool


@dataclass(slots=True)
class PressureFingerprintMetrics:
    forces: np.ndarray
    radii: np.ndarray
    histogram_counts: np.ndarray
    histogram_edges: np.ndarray
    mean_force: float | None
    median_force: float | None
    std_force: float | None
    force_variance: float | None
    radius_variance: float | None
    radius_stability: float | None
    collecting: bool


@dataclass(slots=True)
class GrooveStabilityMetrics:
    overall_score: float | None
    trajectory_score: float | None
    force_score: float | None
    timing_score: float | None
    layer_score: float | None
    collecting: bool


def compute_pin_rhythm_metrics(events: Sequence[Any]) -> PinRhythmMetrics:
    pin_events = []
    for event in events:
        payload = _event_dict(event)
        if (
            payload.get("experimentMode") == "pin_entry"
            or payload.get("digit") is not None
            or payload.get("digitIndex") is not None
            or payload.get("pinSequenceId") is not None
        ):
            pin_events.append(payload)

    if not pin_events:
        return PinRhythmMetrics(None, [], None, None, None, "PIN: —", "| collecting... |", True)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in pin_events:
        sequence_id = str(event.get("pinSequenceId") or "__unknown__")
        grouped.setdefault(sequence_id, []).append(event)

    sequence_id = max(
        grouped,
        key=lambda item: max(float(event.get("timestamp", 0.0)) for event in grouped[item]),
    )
    sequence_events = grouped[sequence_id]
    sequence_events = [event for event in sequence_events if event.get("digit") is not None]
    if len(sequence_events) < 2:
        digit_text = "PIN: " + " ".join(str(event.get("digit", "_")) for event in sequence_events) if sequence_events else "PIN: —"
        return PinRhythmMetrics(sequence_id, [], None, None, None, digit_text, "| collecting... |", True)

    sequence_events.sort(key=lambda event: (int(event.get("digitIndex", 10**6) or 10**6), float(event.get("timestamp", 0.0))))
    timestamps = np.asarray([float(event.get("timestamp", 0.0)) for event in sequence_events], dtype=np.float64)
    intervals_ms = np.diff(timestamps) * 1000.0
    average_interval = _safe_mean(intervals_ms)
    interval_variance = safe_nanvar(intervals_ms)
    interval_std = safe_nanstd(intervals_ms)
    if average_interval <= 0.0:
        consistency_score = 0.0
    else:
        coefficient_of_variation = float(interval_std / max(average_interval, 1e-6))
        consistency_score = float(np.clip(100.0 * (1.0 - coefficient_of_variation), 0.0, 100.0))

    bar_text = _build_rhythm_bar(intervals_ms)
    digit_text = "PIN: " + " ".join(str(event.get("digit", "_")) for event in sequence_events)
    return PinRhythmMetrics(
        sequence_id=sequence_id,
        intervals_ms=[float(value) for value in intervals_ms.tolist()],
        average_interval_ms=average_interval,
        interval_variance_ms=interval_variance,
        consistency_score=consistency_score,
        digit_text=digit_text,
        bar_text=bar_text,
        collecting=False,
    )


def compute_pressure_fingerprint_metrics(events: Sequence[Any], bins: int = 12) -> PressureFingerprintMetrics:
    touch_events = []
    for event in events:
        payload = _event_dict(event)
        if payload.get("messageType") == "touch_event" or payload.get("phase") is not None:
            touch_events.append(payload)

    forces = _finite_array([float(event["force"]) for event in touch_events if event.get("force") is not None])
    radii = _finite_array([float(event.get("majorRadius", 0.0)) for event in touch_events])
    if forces.size < 2:
        return PressureFingerprintMetrics(
            forces=forces,
            radii=radii,
            histogram_counts=np.asarray([], dtype=np.float64),
            histogram_edges=np.asarray([], dtype=np.float64),
            mean_force=None,
            median_force=None,
            std_force=None,
            force_variance=None,
            radius_variance=None,
            radius_stability=None,
            collecting=True,
        )

    histogram_counts, histogram_edges = np.histogram(forces, bins=max(4, bins))
    mean_force = _safe_mean(forces)
    median_force = _safe_median(forces)
    std_force = safe_nanstd(forces)
    force_variance = safe_nanvar(forces)
    radius_variance = safe_nanvar(radii) if radii.size >= 2 else None
    radius_stability = None
    if radius_variance is not None:
        radius_stability = float(np.clip(100.0 * (1.0 - safe_nanstd(radii) / max(_safe_mean(radii), 1e-6)), 0.0, 100.0))

    return PressureFingerprintMetrics(
        forces=forces,
        radii=radii,
        histogram_counts=histogram_counts.astype(np.float64),
        histogram_edges=histogram_edges.astype(np.float64),
        mean_force=mean_force,
        median_force=median_force,
        std_force=std_force,
        force_variance=force_variance,
        radius_variance=radius_variance,
        radius_stability=radius_stability,
        collecting=False,
    )


def compute_groove_stability_metrics(
    events: Sequence[Any],
    *,
    recent_window: int = 50,
    baseline_window: int = 200,
) -> GrooveStabilityMetrics:
    touch_events = []
    for event in events:
        payload = _event_dict(event)
        if payload.get("messageType") == "touch_event" or payload.get("phase") is not None:
            touch_events.append(payload)

    if len(touch_events) < max(8, recent_window // 2):
        return GrooveStabilityMetrics(None, None, None, None, None, True)

    recent_events = touch_events[-recent_window:]
    baseline_start = max(0, len(touch_events) - recent_window - baseline_window)
    baseline_events = touch_events[baseline_start:-recent_window] if len(touch_events) > recent_window else touch_events[:-recent_window]

    if len(recent_events) < 5 or len(baseline_events) < 5:
        return GrooveStabilityMetrics(None, None, None, None, None, True)

    trajectory_score = _paired_similarity(
        _trajectory_vector(recent_events),
        _trajectory_vector(baseline_events),
    )
    force_score = _paired_similarity(
        _force_vector(recent_events),
        _force_vector(baseline_events),
    )
    timing_score = _paired_similarity(
        _timing_vector(recent_events),
        _timing_vector(baseline_events),
    )
    layer_score = _paired_similarity(
        _phase_histogram(recent_events),
        _phase_histogram(baseline_events),
    )

    overall = 0.35 * trajectory_score + 0.25 * force_score + 0.20 * timing_score + 0.20 * layer_score
    return GrooveStabilityMetrics(
        overall_score=float(np.clip(overall, 0.0, 100.0)),
        trajectory_score=float(np.clip(trajectory_score, 0.0, 100.0)),
        force_score=float(np.clip(force_score, 0.0, 100.0)),
        timing_score=float(np.clip(timing_score, 0.0, 100.0)),
        layer_score=float(np.clip(layer_score, 0.0, 100.0)),
        collecting=False,
    )


def _trajectory_vector(events: Sequence[dict[str, Any]]) -> np.ndarray:
    xs = [float(event.get("x", 0.0)) for event in events]
    ys = [float(event.get("y", 0.0)) for event in events]
    normalized_x = _resample_series(_normalize_series(xs))
    normalized_y = _resample_series(_normalize_series(ys))
    return np.concatenate([normalized_x, normalized_y]).astype(np.float64)


def _force_vector(events: Sequence[dict[str, Any]]) -> np.ndarray:
    forces = [float(event["force"]) for event in events if event.get("force") is not None]
    radii = [float(event.get("majorRadius", 0.0)) for event in events]
    force_series = _resample_series(_normalize_series(forces))
    radius_series = _resample_series(_normalize_series(radii))
    return np.concatenate([force_series, radius_series]).astype(np.float64)


def _timing_vector(events: Sequence[dict[str, Any]]) -> np.ndarray:
    timestamps = np.asarray([float(event.get("timestamp", 0.0)) for event in events], dtype=np.float64)
    if timestamps.size < 2:
        return np.zeros(16, dtype=np.float64)
    deltas = np.diff(timestamps)
    normalized_deltas = _normalize_series(deltas)
    return _resample_series(normalized_deltas)


def _paired_similarity(left: Sequence[float] | np.ndarray, right: Sequence[float] | np.ndarray) -> float:
    similarity = _safe_cosine_similarity(left, right)
    return 100.0 * ((similarity + 1.0) / 2.0)


def _build_rhythm_bar(intervals_ms: Sequence[float]) -> str:
    interval_list = [float(value) for value in intervals_ms if np.isfinite(value)]
    if not interval_list:
        return "| collecting... |"
    maximum = max(interval_list)
    if maximum <= 0.0:
        return "|" + "-" * max(3, len(interval_list)) + "|"
    segments = []
    for interval in interval_list:
        segment_length = max(3, int(round(10.0 * interval / maximum)))
        segments.append("-" * segment_length)
    return "|" + "|".join(segments) + "|"
