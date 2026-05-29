from __future__ import annotations

import json
import csv
from dataclasses import dataclass, field
from math import hypot, pi
from pathlib import Path
from statistics import mean
from typing import Any, ClassVar

import numpy as np

try:
    from scipy.signal import find_peaks, welch  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    def find_peaks(data: np.ndarray, prominence: float | None = None):  # type: ignore
        peaks: list[int] = []
        if len(data) < 3:
            return np.asarray(peaks, dtype=np.int64), {}
        threshold = float(prominence) if prominence is not None and prominence > 0 else 0.0
        for index in range(1, len(data) - 1):
            if data[index] > data[index - 1] and data[index] >= data[index + 1]:
                if threshold <= 0 or (data[index] - min(data[index - 1], data[index + 1])) >= threshold:
                    peaks.append(index)
        return np.asarray(peaks, dtype=np.int64), {}

    def welch(data: np.ndarray, fs: float = 1.0, nperseg: int | None = None):  # type: ignore
        if len(data) == 0:
            return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
        centered = np.asarray(data, dtype=np.float64) - float(np.mean(data))
        spectrum = np.fft.rfft(centered)
        power = (np.abs(spectrum) ** 2) / max(len(centered), 1)
        frequencies = np.fft.rfftfreq(len(centered), d=1.0 / fs)
        return frequencies, power

from touchprint_lab.analyzer.models import TouchEventRecord, TouchSessionRecord
from touchprint_lab.utils.numeric import safe_nanstd, safe_nanvar

FEATURE_VERSION = "v1"
EPSILON = 1e-9


@dataclass(slots=True)
class TouchFeatureVector:
    feature_version: str
    session_id: str
    user_id: str
    device_type: str
    input_type: str
    total_touch_count: int
    average_touch_duration: float
    session_duration: float
    pin_rhythm_consistency: float
    touch_duration: float
    inter_touch_interval: float
    hold_stability: float
    stabilization_time: float
    drift_distance: float
    trajectory_length: float
    trajectory_curvature: float
    centroid_variance: float
    directional_entropy: float
    average_force: float
    max_force: float
    force_variance: float
    force_ramp_up_rate: float
    release_decay_rate: float
    average_radius: float
    radius_variance: float
    tremor_frequency_estimate: float
    micro_oscillation_energy: float
    jitter_entropy: float
    acceleration_peak_count: float
    metadata: dict[str, Any] = field(default_factory=dict)

    FEATURE_FIELDS: ClassVar[tuple[str, ...]] = (
        "touch_duration",
        "inter_touch_interval",
        "hold_stability",
        "stabilization_time",
        "drift_distance",
        "trajectory_length",
        "trajectory_curvature",
        "centroid_variance",
        "directional_entropy",
        "average_force",
        "max_force",
        "force_variance",
        "force_ramp_up_rate",
        "release_decay_rate",
        "average_radius",
        "radius_variance",
        "tremor_frequency_estimate",
        "micro_oscillation_energy",
        "jitter_entropy",
        "acceleration_peak_count",
        "total_touch_count",
        "average_touch_duration",
        "session_duration",
        "pin_rhythm_consistency",
    )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TouchFeatureVector":
        def float_value(*keys: str, default: float = 0.0) -> float:
            for key in keys:
                if key in payload and payload[key] is not None and payload[key] != "":
                    return float(payload[key])
            return default

        metadata = payload.get("metadata") or {}

        return cls(
            feature_version=str(payload.get("featureVersion", payload.get("feature_version", FEATURE_VERSION))),
            session_id=str(payload["sessionId"]),
            user_id=str(payload.get("userId", payload.get("user_id", "user_01"))),
            device_type=str(payload.get("deviceType", payload.get("device_type", "other"))),
            input_type=str(payload.get("inputType", payload.get("input_type", "unknown"))),
            total_touch_count=int(payload.get("totalTouchCount", payload.get("total_touch_count", 0))),
            average_touch_duration=float_value("average_touch_duration", "averageTouchDuration"),
            session_duration=float_value("session_duration", "sessionDuration"),
            pin_rhythm_consistency=float_value("pin_rhythm_consistency", "pinRhythmConsistency"),
            touch_duration=float_value("touch_duration", "touchDuration"),
            inter_touch_interval=float_value("inter_touch_interval", "interTouchInterval"),
            hold_stability=float_value("hold_stability", "holdStability"),
            stabilization_time=float_value("stabilization_time", "stabilizationTime"),
            drift_distance=float_value("drift_distance", "driftDistance"),
            trajectory_length=float_value("trajectory_length", "trajectoryLength"),
            trajectory_curvature=float_value("trajectory_curvature", "trajectoryCurvature"),
            centroid_variance=float_value("centroid_variance", "centroidVariance"),
            directional_entropy=float_value("directional_entropy", "directionalEntropy"),
            average_force=float_value("average_force", "averageForce"),
            max_force=float_value("max_force", "maxForce"),
            force_variance=float_value("force_variance", "forceVariance"),
            force_ramp_up_rate=float_value("force_ramp_up_rate", "forceRampUpRate"),
            release_decay_rate=float_value("release_decay_rate", "releaseDecayRate"),
            average_radius=float_value("average_radius", "averageRadius"),
            radius_variance=float_value("radius_variance", "radiusVariance"),
            tremor_frequency_estimate=float_value("tremor_frequency_estimate", "tremorFrequencyEstimate"),
            micro_oscillation_energy=float_value("micro_oscillation_energy", "microOscillationEnergy"),
            jitter_entropy=float_value("jitter_entropy", "jitterEntropy"),
            acceleration_peak_count=float_value("acceleration_peak_count", "accelerationPeakCount"),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def feature_items(self) -> list[tuple[str, float]]:
        return [(name, float(getattr(self, name))) for name in self.FEATURE_FIELDS]

    def feature_array(self) -> np.ndarray:
        return np.asarray([value for _, value in self.feature_items()], dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "featureVersion": self.feature_version,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "deviceType": self.device_type,
            "inputType": self.input_type,
            "metadata": self.metadata,
        }
        for name, value in self.feature_items():
            payload[name] = value
        return payload

    def to_csv_row(self) -> dict[str, Any]:
        payload = {
            "featureVersion": self.feature_version,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "deviceType": self.device_type,
            "inputType": self.input_type,
        }
        for name, value in self.feature_items():
            payload[name] = value
        return payload


class FeatureExtractor:
    def __init__(self, observed_sample_kinds: set[str] | None = None):
        self.observed_sample_kinds = observed_sample_kinds or {"live", "coalesced"}

    def extract_session(self, session: TouchSessionRecord) -> TouchFeatureVector:
        observed_events = self._observed_events(session.events)
        touch_groups = self._group_by_touch(observed_events)
        touch_metrics = [self._extract_touch_metrics(events) for events in touch_groups.values() if events]
        if not touch_metrics and observed_events:
            touch_metrics = [self._extract_touch_metrics(observed_events)]

        began_timestamps = self._began_timestamps(observed_events)
        inter_touch_interval = self._mean(
            [current - previous for previous, current in zip(began_timestamps[:-1], began_timestamps[1:])]
        )

        feature_values = self._aggregate_touch_metrics(touch_metrics)
        return TouchFeatureVector(
            feature_version=FEATURE_VERSION,
            session_id=session.session_id,
            user_id=session.user_id,
            device_type=session.device_type,
            input_type=session.resolved_input_type(),
            total_touch_count=len(touch_groups),
            average_touch_duration=feature_values["average_touch_duration"],
            session_duration=self._session_duration(observed_events),
            pin_rhythm_consistency=self._pin_rhythm_consistency(began_timestamps),
            touch_duration=feature_values["touch_duration"],
            inter_touch_interval=inter_touch_interval,
            hold_stability=feature_values["hold_stability"],
            stabilization_time=feature_values["stabilization_time"],
            drift_distance=feature_values["drift_distance"],
            trajectory_length=feature_values["trajectory_length"],
            trajectory_curvature=feature_values["trajectory_curvature"],
            centroid_variance=feature_values["centroid_variance"],
            directional_entropy=feature_values["directional_entropy"],
            average_force=feature_values["average_force"],
            max_force=feature_values["max_force"],
            force_variance=feature_values["force_variance"],
            force_ramp_up_rate=feature_values["force_ramp_up_rate"],
            release_decay_rate=feature_values["release_decay_rate"],
            average_radius=feature_values["average_radius"],
            radius_variance=feature_values["radius_variance"],
            tremor_frequency_estimate=feature_values["tremor_frequency_estimate"],
            micro_oscillation_energy=feature_values["micro_oscillation_energy"],
            jitter_entropy=feature_values["jitter_entropy"],
            acceleration_peak_count=feature_values["acceleration_peak_count"],
            metadata={
                "observedEventCount": len(observed_events),
                "touchCountWithFeatures": len(touch_metrics),
                "observedSampleKinds": sorted(self.observed_sample_kinds),
                "sessionType": session.session_type,
                "startedAt": session.started_at,
                "exportedAt": session.exported_at,
                "deviceType": session.device_type,
                "inputType": session.resolved_input_type(),
                "userId": session.user_id,
            },
        )

    def export_session(self, session: TouchSessionRecord, processed_dir: Path) -> TouchFeatureVector:
        processed_dir.mkdir(parents=True, exist_ok=True)
        feature_vector = self.extract_session(session)
        json_path = processed_dir / f"{session.session_id}.json"
        csv_path = processed_dir / f"{session.session_id}.csv"
        json_path.write_text(json.dumps(feature_vector.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        csv_path.write_text(self.rows_to_csv([feature_vector.to_csv_row()]), encoding="utf-8")
        return feature_vector

    def feature_rows(self, vectors: list[TouchFeatureVector]) -> list[dict[str, Any]]:
        return [vector.to_csv_row() for vector in vectors]

    def _aggregate_touch_metrics(self, touch_metrics: list[dict[str, float]]) -> dict[str, float]:
        if not touch_metrics:
            return {name: 0.0 for name in TouchFeatureVector.FEATURE_FIELDS}

        aggregated = {name: self._mean([metric.get(name, 0.0) for metric in touch_metrics]) for name in TouchFeatureVector.FEATURE_FIELDS}
        aggregated["max_force"] = max(metric.get("max_force", 0.0) for metric in touch_metrics)
        aggregated["total_touch_count"] = float(len(touch_metrics))
        return aggregated

    def _extract_touch_metrics(self, events: list[TouchEventRecord]) -> dict[str, float]:
        ordered = sorted(events, key=lambda item: item.timestamp)
        timestamps = np.asarray([event.timestamp for event in ordered], dtype=np.float64)
        xs = np.asarray([event.x for event in ordered], dtype=np.float64)
        ys = np.asarray([event.y for event in ordered], dtype=np.float64)
        forces = np.asarray([event.force if event.force is not None else np.nan for event in ordered], dtype=np.float64)
        radii = np.asarray([event.major_radius for event in ordered], dtype=np.float64)

        touch_duration = float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
        trajectory_length = self._trajectory_length(xs, ys)
        drift_distance = float(hypot(xs[-1] - xs[0], ys[-1] - ys[0])) if len(xs) > 1 else 0.0
        centroid_variance = self._centroid_variance(xs, ys)
        trajectory_curvature = self._trajectory_curvature(xs, ys)
        directional_entropy = self._directional_entropy(xs, ys)
        average_force, max_force, force_variance = self._force_stats(forces)
        force_ramp_up_rate = self._force_ramp_up_rate(timestamps, forces)
        release_decay_rate = self._release_decay_rate(timestamps, forces)
        average_radius = float(np.nanmean(radii)) if len(radii) else 0.0
        radius_variance = safe_nanvar(radii)
        hold_stability = self._hold_stability(xs, ys, forces)
        stabilization_time = self._stabilization_time(timestamps, xs, ys)
        tremor_frequency_estimate, micro_oscillation_energy, jitter_entropy = self._micro_dynamics(timestamps, xs, ys)
        acceleration_peak_count = self._acceleration_peak_count(timestamps, xs, ys)

        return {
            "touch_duration": touch_duration,
            "average_touch_duration": touch_duration,
            "hold_stability": hold_stability,
            "stabilization_time": stabilization_time,
            "drift_distance": drift_distance,
            "trajectory_length": trajectory_length,
            "trajectory_curvature": trajectory_curvature,
            "centroid_variance": centroid_variance,
            "directional_entropy": directional_entropy,
            "average_force": average_force,
            "max_force": max_force,
            "force_variance": force_variance,
            "force_ramp_up_rate": force_ramp_up_rate,
            "release_decay_rate": release_decay_rate,
            "average_radius": average_radius,
            "radius_variance": radius_variance,
            "tremor_frequency_estimate": tremor_frequency_estimate,
            "micro_oscillation_energy": micro_oscillation_energy,
            "jitter_entropy": jitter_entropy,
            "acceleration_peak_count": float(acceleration_peak_count),
        }

    def _observed_events(self, events: list[TouchEventRecord]) -> list[TouchEventRecord]:
        filtered = [event for event in events if event.sample_kind in self.observed_sample_kinds]
        return sorted(filtered or events, key=lambda item: item.timestamp)

    @staticmethod
    def _group_by_touch(events: list[TouchEventRecord]) -> dict[str, list[TouchEventRecord]]:
        grouped: dict[str, list[TouchEventRecord]] = {}
        for event in events:
            grouped.setdefault(event.touch_id, []).append(event)
        return grouped

    @staticmethod
    def _mean(values: list[float]) -> float:
        filtered = [value for value in values if np.isfinite(value)]
        return float(mean(filtered)) if filtered else 0.0

    @staticmethod
    def _session_duration(events: list[TouchEventRecord]) -> float:
        if len(events) < 2:
            return 0.0
        timestamps = [event.timestamp for event in events]
        return float(max(timestamps) - min(timestamps))

    def _began_timestamps(self, events: list[TouchEventRecord]) -> list[float]:
        return sorted([event.timestamp for event in events if event.phase == "began"])

    def _pin_rhythm_consistency(self, began_timestamps: list[float]) -> float:
        intervals = [current - previous for previous, current in zip(began_timestamps[:-1], began_timestamps[1:])]
        if len(intervals) < 2:
            return 0.0
        interval_array = np.asarray(intervals, dtype=np.float64)
        mean_interval = float(np.mean(interval_array))
        if mean_interval <= EPSILON:
            return 0.0
        coefficient_of_variation = float(safe_nanstd(interval_array) / (mean_interval + EPSILON))
        return float(1.0 / (1.0 + coefficient_of_variation))

    @staticmethod
    def _trajectory_length(xs: np.ndarray, ys: np.ndarray) -> float:
        if len(xs) < 2:
            return 0.0
        return float(np.sum(np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)))

    def _trajectory_curvature(self, xs: np.ndarray, ys: np.ndarray) -> float:
        if len(xs) < 3:
            return 0.0
        vectors = np.column_stack([np.diff(xs), np.diff(ys)])
        lengths = np.linalg.norm(vectors, axis=1)
        if np.all(lengths <= EPSILON):
            return 0.0
        angles: list[float] = []
        for first, second in zip(vectors, vectors[1:]):
            first_norm = np.linalg.norm(first)
            second_norm = np.linalg.norm(second)
            if first_norm <= EPSILON or second_norm <= EPSILON:
                continue
            cosine = float(np.dot(first, second) / (first_norm * second_norm))
            cosine = float(np.clip(cosine, -1.0, 1.0))
            angles.append(abs(float(np.arccos(cosine))))
        total_length = float(np.sum(lengths)) + EPSILON
        return float(np.sum(angles) / total_length) if angles else 0.0

    @staticmethod
    def _centroid_variance(xs: np.ndarray, ys: np.ndarray) -> float:
        if len(xs) == 0:
            return 0.0
        centroid_x = float(np.mean(xs))
        centroid_y = float(np.mean(ys))
        distances = (xs - centroid_x) ** 2 + (ys - centroid_y) ** 2
        return float(np.mean(distances)) if len(distances) else 0.0

    @staticmethod
    def _directional_entropy(xs: np.ndarray, ys: np.ndarray) -> float:
        if len(xs) < 2:
            return 0.0
        directions = np.arctan2(np.diff(ys), np.diff(xs))
        histogram, _ = np.histogram(directions, bins=16, range=(-pi, pi), density=False)
        probabilities = histogram / max(float(histogram.sum()), EPSILON)
        probabilities = probabilities[probabilities > 0]
        if len(probabilities) == 0:
            return 0.0
        entropy = -np.sum(probabilities * np.log2(probabilities))
        return float(entropy / np.log2(16))

    @staticmethod
    def _force_stats(forces: np.ndarray) -> tuple[float, float, float]:
        valid = forces[np.isfinite(forces)]
        if len(valid) == 0:
            return 0.0, 0.0, 0.0
        return float(np.mean(valid)), float(np.max(valid)), safe_nanvar(valid)

    @staticmethod
    def _force_ramp_up_rate(timestamps: np.ndarray, forces: np.ndarray) -> float:
        valid = np.isfinite(forces)
        if valid.sum() < 2:
            return 0.0
        filtered_timestamps = timestamps[valid]
        filtered_forces = forces[valid]
        peak_index = int(np.argmax(filtered_forces))
        if peak_index <= 0:
            return 0.0
        elapsed = float(filtered_timestamps[peak_index] - filtered_timestamps[0])
        if elapsed <= EPSILON:
            return 0.0
        return float((filtered_forces[peak_index] - filtered_forces[0]) / elapsed)

    @staticmethod
    def _release_decay_rate(timestamps: np.ndarray, forces: np.ndarray) -> float:
        valid = np.isfinite(forces)
        if valid.sum() < 2:
            return 0.0
        filtered_timestamps = timestamps[valid]
        filtered_forces = forces[valid]
        peak_index = int(np.argmax(filtered_forces))
        if peak_index >= len(filtered_forces) - 1:
            return 0.0
        elapsed = float(filtered_timestamps[-1] - filtered_timestamps[peak_index])
        if elapsed <= EPSILON:
            return 0.0
        decay = float(filtered_forces[peak_index] - filtered_forces[-1])
        return float(max(decay / elapsed, 0.0))

    @staticmethod
    def _hold_stability(xs: np.ndarray, ys: np.ndarray, forces: np.ndarray) -> float:
        if len(xs) < 2:
            return 1.0
        centroid_x = float(np.mean(xs))
        centroid_y = float(np.mean(ys))
        distances = np.sqrt((xs - centroid_x) ** 2 + (ys - centroid_y) ** 2)
        mean_distance = float(np.mean(distances))
        force_penalty = float(safe_nanstd(forces)) if np.isfinite(forces).any() else 0.0
        return float(1.0 / (1.0 + mean_distance + force_penalty))

    @staticmethod
    def _stabilization_time(timestamps: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> float:
        if len(timestamps) < 3:
            return 0.0
        dt = np.diff(timestamps)
        distances = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
        valid = dt > EPSILON
        if not np.any(valid):
            return 0.0
        velocities = distances[valid] / dt[valid]
        threshold = float(np.median(velocities) * 0.5)
        stable_index = next((index for index, velocity in enumerate(velocities) if velocity <= threshold), 0)
        return float(max(timestamps[min(stable_index + 1, len(timestamps) - 1)] - timestamps[0], 0.0))

    def _micro_dynamics(self, timestamps: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float]:
        if len(timestamps) < 4:
            return 0.0, 0.0, 0.0
        duration = float(timestamps[-1] - timestamps[0])
        if duration <= EPSILON:
            return 0.0, 0.0, 0.0
        sample_rate = min(120.0, max(20.0, float(len(timestamps) / duration)))
        sample_count = max(int(duration * sample_rate), 8)
        interpolated_time = np.linspace(timestamps[0], timestamps[-1], sample_count)
        interpolated_x = np.interp(interpolated_time, timestamps, xs)
        interpolated_y = np.interp(interpolated_time, timestamps, ys)
        line_x = np.linspace(xs[0], xs[-1], sample_count)
        line_y = np.linspace(ys[0], ys[-1], sample_count)
        residual = np.sqrt((interpolated_x - line_x) ** 2 + (interpolated_y - line_y) ** 2)
        residual = residual - np.mean(residual)
        if np.allclose(residual, 0.0):
            return 0.0, 0.0, 0.0

        frequencies, power = welch(residual, fs=sample_rate, nperseg=min(len(residual), 64))
        dominant_frequency = 0.0
        oscillation_energy = 0.0
        if len(frequencies) and len(power):
            positive = frequencies > 0
            if np.any(positive):
                dominant_frequency = float(frequencies[positive][np.argmax(power[positive])])
            high_band = frequencies >= (sample_rate / 4.0)
            oscillation_energy = float(np.sum(power[high_band]) / (np.sum(power) + EPSILON))

        jitter_histogram, _ = np.histogram(np.abs(residual), bins=12, density=False)
        jitter_probabilities = jitter_histogram / max(float(jitter_histogram.sum()), EPSILON)
        jitter_probabilities = jitter_probabilities[jitter_probabilities > 0]
        jitter_entropy = 0.0
        if len(jitter_probabilities):
            jitter_entropy = float(-np.sum(jitter_probabilities * np.log2(jitter_probabilities)) / np.log2(12))
        return dominant_frequency, oscillation_energy, jitter_entropy

    @staticmethod
    def _acceleration_peak_count(timestamps: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> int:
        if len(timestamps) < 4:
            return 0
        dt = np.diff(timestamps)
        valid = dt > EPSILON
        if valid.sum() < 2:
            return 0
        velocities_x = np.diff(xs)[valid] / dt[valid]
        velocities_y = np.diff(ys)[valid] / dt[valid]
        if len(velocities_x) < 2:
            return 0
        acceleration = np.sqrt(np.diff(velocities_x) ** 2 + np.diff(velocities_y) ** 2)
        if len(acceleration) < 2 or np.allclose(acceleration, 0.0):
            return 0
        prominence = float(safe_nanstd(acceleration)) * 0.5
        peaks, _ = find_peaks(acceleration, prominence=prominence if prominence > 0 else None)
        return int(len(peaks))

    @staticmethod
    def rows_to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
