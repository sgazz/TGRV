from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from touchprint_lab.utils.numeric import safe_nanstd, safe_nanvar


@dataclass(slots=True)
class HumanLikenessMetrics:
    human_likeness_score: float | None
    automation_suspicion_score: float | None
    confidence: str
    explanation_flags: list[str]
    suspicious_flags: list[str]
    timing_naturalness: float | None
    jitter_naturalness: float | None
    pressure_naturalness: float | None
    release_dynamics: float | None
    repetition_diversity: float | None
    signal_quality: float | None
    recent_intervals_ms: list[float]
    force_variance: float | None
    radius_variance: float | None
    collecting: bool


def compute_human_likeness_metrics(events: Sequence[Any]) -> HumanLikenessMetrics:
    payloads = [_event_payload(event) for event in events]
    touch_events = [event for event in payloads if event.get("messageType") == "touch_event" or event.get("phase") is not None]
    touch_events.sort(key=lambda event: _safe_float(event.get("timestamp")))

    timing_score, intervals_ms, timing_flags, sequence_intervals = _timing_naturalness(payloads)
    jitter_score, jitter_flags = _jitter_naturalness(touch_events)
    pressure_score, force_variance, radius_variance, pressure_flags = _pressure_naturalness(touch_events)
    release_score, release_flags = _release_dynamics(touch_events)
    repetition_score, repetition_flags = _repetition_diversity(sequence_intervals)
    signal_quality = _signal_quality(touch_events, payloads)

    scored_components = {
        "timing_naturalness": (timing_score, 1.25),
        "jitter_naturalness": (jitter_score, 1.0),
        "pressure_naturalness": (pressure_score, 1.0),
        "release_dynamics": (release_score, 0.9),
        "repetition_diversity": (repetition_score, 1.1),
        "signal_quality": (signal_quality, 0.85),
    }
    weighted_sum = 0.0
    weight_total = 0.0
    available_count = 0
    for score, weight in scored_components.values():
        if score is None:
            continue
        weighted_sum += float(score) * float(weight)
        weight_total += float(weight)
        available_count += 1

    if available_count == 0 or weight_total <= 0.0:
        return HumanLikenessMetrics(
            human_likeness_score=None,
            automation_suspicion_score=None,
            confidence="low",
            explanation_flags=["collecting live signal"],
            suspicious_flags=[],
            timing_naturalness=timing_score,
            jitter_naturalness=jitter_score,
            pressure_naturalness=pressure_score,
            release_dynamics=release_score,
            repetition_diversity=repetition_score,
            signal_quality=signal_quality,
            recent_intervals_ms=[float(value) for value in intervals_ms[-6:]],
            force_variance=force_variance,
            radius_variance=radius_variance,
            collecting=True,
        )

    human_score = float(np.clip(weighted_sum / weight_total, 0.0, 100.0))
    suspicious_flags = timing_flags + jitter_flags + pressure_flags + release_flags + repetition_flags
    automation_score = float(np.clip(100.0 - human_score + min(18.0, len(suspicious_flags) * 6.0), 0.0, 100.0))

    confidence = _confidence_level(
        available_count=available_count,
        touch_event_count=len(touch_events),
        interval_count=len(intervals_ms),
    )

    explanation_flags = _build_explanation_flags(
        timing_score=timing_score,
        jitter_score=jitter_score,
        pressure_score=pressure_score,
        repetition_score=repetition_score,
        signal_quality=signal_quality,
        suspicious_flags=suspicious_flags,
        confidence=confidence,
    )

    collecting = available_count < 3
    return HumanLikenessMetrics(
        human_likeness_score=human_score,
        automation_suspicion_score=automation_score,
        confidence=confidence,
        explanation_flags=explanation_flags,
        suspicious_flags=suspicious_flags,
        timing_naturalness=timing_score,
        jitter_naturalness=jitter_score,
        pressure_naturalness=pressure_score,
        release_dynamics=release_score,
        repetition_diversity=repetition_score,
        signal_quality=signal_quality,
        recent_intervals_ms=[float(value) for value in intervals_ms[-6:]],
        force_variance=force_variance,
        radius_variance=radius_variance,
        collecting=collecting,
    )


def _timing_naturalness(events: list[dict[str, Any]]) -> tuple[float | None, list[float], list[str], dict[str, np.ndarray]]:
    pin_events = [event for event in events if event.get("digit") is not None and event.get("timestamp") is not None]
    if len(pin_events) < 2:
        return None, [], [], {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in pin_events:
        sequence_id = str(event.get("pinSequenceId") or "__unknown__")
        grouped.setdefault(sequence_id, []).append(event)

    intervals_ms: list[float] = []
    sequence_intervals: dict[str, np.ndarray] = {}
    for sequence_id, group in grouped.items():
        ordered = sorted(group, key=lambda item: (_digit_index(item), _safe_float(item.get("timestamp"))))
        timestamps = np.asarray([_safe_float(item.get("timestamp")) for item in ordered], dtype=np.float64)
        if timestamps.size < 2:
            continue
        sequence_interval = np.diff(timestamps) * 1000.0
        sequence_interval = _finite(sequence_interval)
        if sequence_interval.size == 0:
            continue
        sequence_intervals[sequence_id] = sequence_interval
        intervals_ms.extend(float(value) for value in sequence_interval.tolist())

    finite_intervals = _finite(intervals_ms)
    if finite_intervals.size < 2:
        return None, [], [], sequence_intervals

    std_ms = safe_nanstd(finite_intervals)
    mean_ms = float(np.mean(finite_intervals))
    cv = std_ms / max(mean_ms, 1e-6)

    flags: list[str] = []
    score = 100.0
    if std_ms < 6.0:
        score -= 55.0
        flags.append("interval variance extremely low")
    elif std_ms < 12.0:
        score -= 32.0
    elif std_ms < 18.0:
        score -= 14.0

    if cv < 0.03:
        score -= 24.0
    elif cv < 0.06:
        score -= 12.0
    elif cv > 1.2:
        score -= 20.0

    rounded = np.round(finite_intervals, 1)
    if rounded.size >= 3 and np.unique(rounded).size <= max(1, rounded.size // 3):
        score -= 18.0
        flags.append("repeated near-identical PIN intervals")

    return float(np.clip(score, 0.0, 100.0)), [float(value) for value in finite_intervals.tolist()], flags, sequence_intervals


def _jitter_naturalness(touch_events: list[dict[str, Any]]) -> tuple[float | None, list[str]]:
    if len(touch_events) < 3:
        return None, []
    xs = _finite([_safe_float(event.get("x")) for event in touch_events])
    ys = _finite([_safe_float(event.get("y")) for event in touch_events])
    if xs.size < 3 or ys.size < 3:
        return None, []

    limit = min(xs.size, ys.size)
    xs = xs[:limit]
    ys = ys[:limit]
    steps = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    steps = _finite(steps)
    if steps.size < 2:
        return None, []

    range_x = float(np.max(xs) - np.min(xs))
    range_y = float(np.max(ys) - np.min(ys))
    path_length = float(np.sum(steps))
    direct = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]))
    linearity = path_length / max(direct, 1e-6)
    step_std = safe_nanstd(steps)

    score = 100.0
    flags: list[str] = []
    if range_x < 0.05 and range_y < 0.05:
        score -= 58.0
        flags.append("coordinates are nearly static")
    if step_std < 0.015:
        score -= 34.0
    elif step_std < 0.04:
        score -= 14.0
    if path_length > 8.0 and linearity < 1.01:
        score -= 16.0
        flags.append("movement appears unnaturally linear")
    if step_std > 24.0:
        score -= 20.0
    return float(np.clip(score, 0.0, 100.0)), flags


def _pressure_naturalness(touch_events: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None, list[str]]:
    if len(touch_events) < 3:
        return None, None, None, []

    forces = _finite([_safe_float(event.get("force")) for event in touch_events if event.get("force") is not None])
    radii = _finite([_safe_float(event.get("majorRadius")) for event in touch_events if event.get("majorRadius") is not None])

    if forces.size < 2 and radii.size < 2:
        return None, None, None, []

    force_var = safe_nanvar(forces) if forces.size >= 2 else None
    radius_var = safe_nanvar(radii) if radii.size >= 2 else None
    force_std = safe_nanstd(forces) if forces.size >= 2 else 0.0
    radius_std = safe_nanstd(radii) if radii.size >= 2 else 0.0
    force_range = float(np.max(forces) - np.min(forces)) if forces.size else 0.0

    score = 100.0
    flags: list[str] = []
    if forces.size >= 2:
        if force_std < 0.005:
            score -= 46.0
            flags.append("force signal is almost flat")
        elif force_std < 0.015:
            score -= 26.0
        if force_range < 0.02:
            score -= 22.0
    if radii.size >= 2:
        if radius_std < 0.02:
            score -= 30.0
        elif radius_std < 0.08:
            score -= 14.0
    if forces.size < 2 or radii.size < 2:
        score -= 8.0
    return float(np.clip(score, 0.0, 100.0)), force_var, radius_var, flags


def _release_dynamics(touch_events: list[dict[str, Any]]) -> tuple[float | None, list[str]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in touch_events:
        touch_id = event.get("touchId")
        if touch_id is None:
            continue
        grouped.setdefault(str(touch_id), []).append(event)

    shape_scores: list[float] = []
    flags: list[str] = []
    for events in grouped.values():
        ordered = sorted(events, key=lambda item: _safe_float(item.get("timestamp")))
        forces = _finite([_safe_float(event.get("force")) for event in ordered if event.get("force") is not None])
        if forces.size < 3:
            continue
        peak = int(np.argmax(forces))
        pre = np.diff(forces[: peak + 1]) if peak >= 1 else np.asarray([], dtype=np.float64)
        post = np.diff(forces[peak:]) if peak < forces.size - 1 else np.asarray([], dtype=np.float64)
        has_ramp = bool(pre.size and np.any(pre > 0.001))
        has_decay = bool(post.size and np.any(post < -0.001))
        if has_ramp and has_decay:
            shape_scores.append(100.0)
        elif has_ramp or has_decay:
            shape_scores.append(55.0)
        else:
            shape_scores.append(18.0)

    if not shape_scores:
        return None, []

    score = float(np.clip(np.mean(shape_scores), 0.0, 100.0))
    if score < 45.0:
        flags.append("press/release dynamics are weak")
    return score, flags


def _repetition_diversity(sequence_intervals: dict[str, np.ndarray]) -> tuple[float | None, list[str]]:
    vectors = []
    for intervals in sequence_intervals.values():
        if intervals.size < 2:
            continue
        normalized = intervals / max(float(np.mean(intervals)), 1e-6)
        vectors.append(_resample(normalized, target=8))
    if len(vectors) < 2:
        return None, []

    pairwise: list[float] = []
    for left_index in range(len(vectors)):
        for right_index in range(left_index + 1, len(vectors)):
            pairwise.append(_cosine(vectors[left_index], vectors[right_index]))
    if not pairwise:
        return None, []

    mean_similarity = float(np.mean(pairwise))
    flags: list[str] = []
    if mean_similarity > 0.999:
        score = 4.0
        flags.append("PIN attempts look almost identical")
    elif mean_similarity > 0.995:
        score = 18.0
        flags.append("PIN attempts have near-identical rhythm")
    elif mean_similarity > 0.98:
        score = 58.0
    elif mean_similarity > 0.85:
        score = 90.0
    elif mean_similarity > 0.65:
        score = 78.0
    elif mean_similarity > 0.4:
        score = 62.0
    else:
        score = 36.0

    return float(np.clip(score, 0.0, 100.0)), flags


def _signal_quality(touch_events: list[dict[str, Any]], all_events: list[dict[str, Any]]) -> float | None:
    if not all_events:
        return None

    timestamps = _finite([_safe_float(event.get("timestamp")) for event in touch_events if event.get("timestamp") is not None])
    monotonic_ratio = 1.0
    if timestamps.size >= 2:
        deltas = np.diff(timestamps)
        monotonic_ratio = float(np.mean(deltas >= -1e-9))

    finite_ratio_numerator = 0
    finite_ratio_denominator = 0
    for event in touch_events:
        for key in ("x", "y", "timestamp"):
            value = event.get(key)
            if value is None:
                continue
            finite_ratio_denominator += 1
            if np.isfinite(_safe_float(value)):
                finite_ratio_numerator += 1
    finite_ratio = (finite_ratio_numerator / finite_ratio_denominator) if finite_ratio_denominator else 0.0

    digit_events = [event for event in all_events if event.get("digit") is not None]
    score = (
        min(60.0, len(touch_events) / 120.0 * 60.0)
        + min(20.0, len(digit_events) / 12.0 * 20.0)
        + 20.0 * monotonic_ratio * finite_ratio
    )
    return float(np.clip(score, 0.0, 100.0))


def _build_explanation_flags(
    *,
    timing_score: float | None,
    jitter_score: float | None,
    pressure_score: float | None,
    repetition_score: float | None,
    signal_quality: float | None,
    suspicious_flags: list[str],
    confidence: str,
) -> list[str]:
    flags: list[str] = []
    if timing_score is not None:
        flags.append("natural rhythm variation" if timing_score >= 70.0 else "timing regularity is suspicious")
    if pressure_score is not None:
        flags.append("pressure variation present" if pressure_score >= 65.0 else "flat pressure profile detected")
    if jitter_score is not None:
        flags.append("micro-jitter present" if jitter_score >= 65.0 else "movement jitter is too limited")
    if repetition_score is None:
        flags.append("not enough repeated PIN attempts")
    elif repetition_score >= 70.0:
        flags.append("repetition is similar but non-identical")
    else:
        flags.append("repetition diversity is unusually low")
    if signal_quality is not None and signal_quality < 45.0:
        flags.append("signal quality still sparse")
    if confidence == "low":
        flags.append("collecting more samples improves confidence")

    if suspicious_flags:
        for suspicious in suspicious_flags:
            if suspicious not in flags:
                flags.append(suspicious)
            if len(flags) >= 6:
                break

    deduplicated: list[str] = []
    for flag in flags:
        if flag not in deduplicated:
            deduplicated.append(flag)
        if len(deduplicated) >= 6:
            break
    return deduplicated


def _confidence_level(*, available_count: int, touch_event_count: int, interval_count: int) -> str:
    if available_count >= 5 and touch_event_count >= 90 and interval_count >= 8:
        return "high"
    if available_count >= 3 and touch_event_count >= 30:
        return "medium"
    return "low"


def _event_payload(event: Any) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        return dict(event.to_dict())
    return dict(event)


def _digit_index(event: dict[str, Any]) -> int:
    raw = event.get("digitIndex")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 10**9


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _finite(values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 0:
        array = array.reshape(1)
    return array[np.isfinite(array)]


def _resample(values: np.ndarray, target: int = 8) -> np.ndarray:
    array = _finite(values)
    if array.size == 0:
        return np.zeros(target, dtype=np.float64)
    if array.size == 1:
        return np.repeat(array[0], target)
    source_x = np.linspace(0.0, 1.0, array.size)
    target_x = np.linspace(0.0, 1.0, target)
    return np.interp(target_x, source_x, array).astype(np.float64)


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    left = _finite(left)
    right = _finite(right)
    if left.size == 0 or right.size == 0:
        return 0.0
    limit = min(left.size, right.size)
    left = left[:limit]
    right = right[:limit]
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return float(np.clip(np.dot(left, right) / (left_norm * right_norm), -1.0, 1.0))
