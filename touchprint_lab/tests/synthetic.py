from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from touchprint_lab.analyzer.models import TouchEventRecord, TouchSessionRecord

PROFILE_MAP: dict[str, str] = {
    "deterministic": "intentional_tap",
    "randomized": "random_tap",
    "signature": "signature_tap",
    "pin": "pin_entry",
}

SUPPORTED_PROFILES: tuple[str, ...] = tuple(PROFILE_MAP.keys())

SESSION_REQUIRED_KEYS: tuple[str, ...] = (
    "sessionId",
    "startedAt",
    "exportedAt",
    "deviceType",
    "inputType",
    "sessionType",
    "participantId",
    "experimentId",
    "trialId",
    "trialIndex",
    "protocolSessionId",
    "protocolType",
    "studyId",
    "studyTemplateId",
    "studyTemplateVersion",
    "studySessionId",
    "studyStepId",
    "studyStepIndex",
    "studyLabels",
    "protocolMetadata",
    "participantMetadata",
    "environmentLabels",
    "timingMetadata",
    "touchEventCount",
    "events",
)

EVENT_REQUIRED_KEYS: tuple[str, ...] = (
    "sessionId",
    "touchId",
    "phase",
    "sampleKind",
    "sampleIndex",
    "sampleCount",
    "timestamp",
    "x",
    "y",
    "force",
    "maximumPossibleForce",
    "majorRadius",
    "altitudeAngle",
    "azimuthAngle",
    "touchType",
    "deviceType",
    "inputType",
    "coalescedTouchesCount",
    "predictedTouchesCount",
)

FEATURE_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "featureVersion",
    "sessionId",
    "userId",
    "deviceType",
    "inputType",
    "metadata",
)

FEATURE_METRIC_KEYS: tuple[str, ...] = (
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


def canonical_json_text(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(payload: Any) -> str:
    return sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()


def float_close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)


def make_paths(root: Path):
    from touchprint_lab.utils.paths import TouchprintPaths

    paths = TouchprintPaths(
        root=root,
        incoming=root / "incoming",
        dataset=root / "dataset",
        processed=root / "processed",
        reports=root / "processed" / "reports",
        protocols=root / "processed" / "protocols",
        protocol_reports=root / "processed" / "protocols" / "reports",
        studies=root / "processed" / "studies",
        study_reports=root / "processed" / "studies" / "reports",
        features=root / "processed" / "features",
        analyzer=root / "analyzer",
        ui=root / "ui",
        plots=root / "plots",
        utils=root / "utils",
    )
    paths.ensure_directories()
    return paths


@dataclass(slots=True)
class SyntheticTouchGenerator:
    base_timestamp: float = 1_700_000_000.0

    def generate_session(
        self,
        profile: str,
        *,
        seed: int,
        participant_index: int,
        session_index: int,
        user_id: str | None = None,
        participant_id: str | None = None,
        experiment_id: str | None = None,
        trial_id: str | None = None,
        device_type: str | None = None,
        input_modality: str | None = None,
        study_id: str = "study_01",
        study_template_id: str = "synthetic_study",
        study_template_version: str = "v1",
        dominant_hand: str = "right",
    ) -> TouchSessionRecord:
        if profile not in PROFILE_MAP:
            raise ValueError(f"Unsupported synthetic profile: {profile}")

        rng = random.Random(self._stable_seed(profile, seed, participant_index, session_index))
        device_type = device_type or ("iPad" if participant_index % 2 else "iPhone")
        input_modality = input_modality or ("pencil" if profile == "signature" and participant_index % 3 == 0 else "finger")
        user_id = user_id or f"user_{participant_index:02d}"
        participant_id = participant_id or f"participant_{participant_index:02d}"
        experiment_id = experiment_id or f"experiment_{profile}"
        trial_id = trial_id or f"trial_{session_index:03d}"
        session_id = f"{profile}_{seed:04d}_{participant_index:02d}_{session_index:03d}"
        started_at = self.base_timestamp + participant_index * 1000.0 + session_index * 17.0 + seed * 0.1

        events = self._build_events(
            profile=profile,
            rng=rng,
            session_id=session_id,
            started_at=started_at,
            device_type=device_type,
            input_modality=input_modality,
        )
        exported_at = events[-1].timestamp + 0.25 if events else started_at + 0.25
        session_type = PROFILE_MAP[profile]
        session = TouchSessionRecord(
            session_id=session_id,
            started_at=started_at,
            exported_at=exported_at,
            device_type=device_type,
            input_type=input_modality if input_modality in {"finger", "pencil"} else "mixed",
            session_type=session_type,
            touch_event_count=len(events),
            participant_id=participant_id,
            experiment_id=experiment_id,
            trial_id=trial_id,
            trial_index=session_index,
            protocol_session_id=f"protocol_{participant_index:02d}",
            protocol_type="synthetic_protocol",
            study_id=study_id,
            study_template_id=study_template_id,
            study_template_version=study_template_version,
            study_session_id=f"{study_id}_{session_index:03d}",
            study_step_id=f"{profile}_step",
            study_step_index=session_index,
            study_labels={
                "profile": profile,
                "seed": seed,
                "studyId": study_id,
                "studyTemplateId": study_template_id,
                "studyTemplateVersion": study_template_version,
                "inputModality": input_modality,
            },
            protocol_metadata={
                "profile": profile,
                "seed": seed,
                "experimentType": session_type,
                "instructions": f"Synthetic {profile} validation sequence.",
            },
            participant_metadata={
                "dominantHand": dominant_hand,
                "participantIndex": participant_index,
            },
            environment_labels={
                "deviceType": device_type,
                "inputModality": input_modality,
                "timeOfDay": self._time_of_day(session_index),
            },
            timing_metadata={
                "plannedDurationSeconds": round(events[-1].timestamp - started_at, 6) if events else 0.0,
                "generatedBy": "SyntheticTouchGenerator",
            },
            events=events,
            user_id=user_id,
        )
        return session

    def generate_sessions(
        self,
        count: int,
        *,
        seed: int = 7,
        participant_count: int = 10,
        profile_cycle: Iterable[str] | None = None,
    ) -> list[TouchSessionRecord]:
        cycle = list(profile_cycle or SUPPORTED_PROFILES)
        sessions: list[TouchSessionRecord] = []
        for index in range(count):
            participant_index = index % max(participant_count, 1)
            profile = cycle[index % len(cycle)]
            sessions.append(
                self.generate_session(
                    profile,
                    seed=seed + index,
                    participant_index=participant_index,
                    session_index=index,
                )
            )
        return sessions

    def write_session(self, session: TouchSessionRecord, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical_json_text(session.to_dict()), encoding="utf-8")
        return path

    def _build_events(
        self,
        *,
        profile: str,
        rng: random.Random,
        session_id: str,
        started_at: float,
        device_type: str,
        input_modality: str,
    ) -> list[TouchEventRecord]:
        if profile in {"deterministic", "randomized"}:
            return self._build_tap_events(
                rng=rng,
                session_id=session_id,
                started_at=started_at,
                device_type=device_type,
                input_modality=input_modality,
                randomize=(profile == "randomized"),
            )
        if profile == "signature":
            return self._build_signature_events(rng, session_id, started_at, device_type, input_modality)
        if profile == "pin":
            return self._build_pin_events(rng, session_id, started_at, device_type, input_modality)
        raise ValueError(profile)

    def _build_tap_events(
        self,
        *,
        rng: random.Random,
        session_id: str,
        started_at: float,
        device_type: str,
        input_modality: str,
        randomize: bool,
    ) -> list[TouchEventRecord]:
        events: list[TouchEventRecord] = []
        touch_count = 8
        event_index = 0
        for touch_index in range(touch_count):
            touch_id = f"{session_id}_touch_{touch_index:02d}"
            base_x = 140.0 + (touch_index % 4) * 120.0
            base_y = 220.0 + (touch_index // 4) * 140.0
            if randomize:
                base_x += rng.uniform(-24.0, 24.0)
                base_y += rng.uniform(-24.0, 24.0)
            timestamps = self._timestamps(started_at + touch_index * 0.14, 4, 0.015 if randomize else 0.012)
            xs = [base_x + rng.uniform(-6.0, 6.0) * (1.0 if randomize else 0.25) for _ in range(4)]
            ys = [base_y + rng.uniform(-6.0, 6.0) * (1.0 if randomize else 0.25) for _ in range(4)]
            force_base = 0.35 + touch_index * 0.03
            forces = [force_base + step * 0.05 + (rng.uniform(-0.02, 0.02) if randomize else 0.0) for step in range(4)]
            radii = [6.0 + touch_index * 0.08 + (rng.uniform(-0.15, 0.15) if randomize else 0.0) for _ in range(4)]
            phases = ["began", "moved", "moved", "ended"]
            for sample_index, (timestamp, x, y, force, radius, phase) in enumerate(zip(timestamps, xs, ys, forces, radii, phases)):
                events.append(
                    self._event(
                        session_id=session_id,
                        touch_id=touch_id,
                        phase=phase,
                        sample_kind="live",
                        sample_index=sample_index,
                        sample_count=4,
                        timestamp=timestamp,
                        x=x,
                        y=y,
                        force=force,
                        maximum_possible_force=1.0,
                        major_radius=radius,
                        altitude_angle=0.92,
                        azimuth_angle=0.3,
                        touch_type=input_modality,
                        device_type=device_type,
                        coalesced_touches_count=1 + (touch_index % 2),
                        predicted_touches_count=touch_index % 3,
                    )
                )
                event_index += 1
        return events

    def _build_signature_events(
        self,
        rng: random.Random,
        session_id: str,
        started_at: float,
        device_type: str,
        input_modality: str,
    ) -> list[TouchEventRecord]:
        events: list[TouchEventRecord] = []
        strokes = 3
        for stroke_index in range(strokes):
            touch_id = f"{session_id}_stroke_{stroke_index:02d}"
            sample_count = 16
            base_x = 120.0 + stroke_index * 65.0
            base_y = 300.0 + stroke_index * 20.0
            timestamps = self._timestamps(started_at + stroke_index * 0.9, sample_count, 0.028)
            phases = ["began"] + ["moved"] * (sample_count - 2) + ["ended"]
            for sample_index, timestamp in enumerate(timestamps):
                t = sample_index / max(sample_count - 1, 1)
                curve = math.sin(t * math.pi * 2.3 + stroke_index * 0.6)
                micro = math.sin(t * math.pi * 20.0 + stroke_index) * 1.4
                x = base_x + t * 180.0 + curve * 24.0 + micro
                y = base_y + math.sin(t * math.pi * 1.2) * 36.0 + math.cos(t * math.pi * 3.0) * 7.0
                force = 0.28 + t * 0.32 + math.sin(t * math.pi * 4.0) * 0.03
                radius = 5.4 + stroke_index * 0.12 + math.cos(t * math.pi * 2.0) * 0.12
                events.append(
                    self._event(
                        session_id=session_id,
                        touch_id=touch_id,
                        phase=phases[sample_index],
                        sample_kind="live" if sample_index % 2 == 0 else "coalesced",
                        sample_index=sample_index,
                        sample_count=sample_count,
                        timestamp=timestamp,
                        x=x,
                        y=y,
                        force=force,
                        maximum_possible_force=1.0,
                        major_radius=radius,
                        altitude_angle=1.15,
                        azimuth_angle=0.9,
                        touch_type=input_modality,
                        device_type=device_type,
                        coalesced_touches_count=2 + stroke_index,
                        predicted_touches_count=1 + (stroke_index % 2),
                    )
                )
        return events

    def _build_pin_events(
        self,
        rng: random.Random,
        session_id: str,
        started_at: float,
        device_type: str,
        input_modality: str,
    ) -> list[TouchEventRecord]:
        events: list[TouchEventRecord] = []
        keypad_positions = [
            (80.0, 220.0),
            (190.0, 220.0),
            (300.0, 220.0),
            (80.0, 320.0),
            (190.0, 320.0),
            (300.0, 320.0),
            (80.0, 420.0),
            (190.0, 420.0),
            (300.0, 420.0),
            (190.0, 520.0),
        ]
        pin_digits = [1, 3, 5, 7]
        for touch_index, digit in enumerate(pin_digits):
            touch_id = f"{session_id}_pin_{touch_index:02d}"
            base_x, base_y = keypad_positions[digit]
            timestamps = self._timestamps(started_at + touch_index * 0.42, 4, 0.02)
            xs = [base_x + rng.uniform(-3.0, 3.0) for _ in range(4)]
            ys = [base_y + rng.uniform(-3.0, 3.0) for _ in range(4)]
            forces = [0.3 + touch_index * 0.04 + step * 0.04 for step in range(4)]
            phases = ["began", "moved", "moved", "ended"]
            for sample_index, (timestamp, x, y, force, phase) in enumerate(zip(timestamps, xs, ys, forces, phases)):
                events.append(
                    self._event(
                        session_id=session_id,
                        touch_id=touch_id,
                        phase=phase,
                        sample_kind="live",
                        sample_index=sample_index,
                        sample_count=4,
                        timestamp=timestamp,
                        x=x,
                        y=y,
                        force=force,
                        maximum_possible_force=1.0,
                        major_radius=5.9 + touch_index * 0.07,
                        altitude_angle=1.0,
                        azimuth_angle=0.4,
                        touch_type=input_modality,
                        device_type=device_type,
                        coalesced_touches_count=1 + (digit % 2),
                        predicted_touches_count=digit % 3,
                    )
                )
        return events

    @staticmethod
    def _event(
        *,
        session_id: str,
        touch_id: str,
        phase: str,
        sample_kind: str,
        sample_index: int,
        sample_count: int,
        timestamp: float,
        x: float,
        y: float,
        force: float,
        maximum_possible_force: float,
        major_radius: float,
        altitude_angle: float,
        azimuth_angle: float,
        touch_type: str,
        device_type: str,
        coalesced_touches_count: int,
        predicted_touches_count: int,
    ) -> TouchEventRecord:
        return TouchEventRecord(
            id=f"{session_id}_{touch_id}_{sample_index:02d}",
            session_id=session_id,
            touch_id=touch_id,
            phase=phase,
            sample_kind=sample_kind,
            sample_index=sample_index,
            sample_count=sample_count,
            timestamp=timestamp,
            x=x,
            y=y,
            force=force,
            maximum_possible_force=maximum_possible_force,
            major_radius=major_radius,
            altitude_angle=altitude_angle,
            azimuth_angle=azimuth_angle,
            touch_type=touch_type,
            device_type=device_type,
            input_type=touch_type if touch_type in {"finger", "pencil", "indirect"} else "unknown",
            coalesced_touches_count=coalesced_touches_count,
            predicted_touches_count=predicted_touches_count,
        )

    @staticmethod
    def _timestamps(start: float, count: int, step: float) -> list[float]:
        return [start + index * step for index in range(count)]

    @staticmethod
    def _time_of_day(session_index: int) -> str:
        return ["morning", "afternoon", "evening", "night"][session_index % 4]

    @staticmethod
    def _stable_seed(*parts: Any) -> int:
        value = 0
        for part in parts:
            for character in str(part):
                value = (value * 131 + ord(character)) % (2**32)
        return value


def validate_session_payload(payload: dict[str, Any]) -> None:
    missing = [key for key in SESSION_REQUIRED_KEYS if key not in payload]
    if missing:
        raise AssertionError(f"Session payload missing keys: {missing}")
    if not isinstance(payload["events"], list) or not payload["events"]:
        raise AssertionError("Session payload must contain a non-empty events array")
    validate_timestamp_monotonicity(payload)
    for event in payload["events"]:
        validate_event_payload(event)


def validate_event_payload(payload: dict[str, Any]) -> None:
    missing = [key for key in EVENT_REQUIRED_KEYS if key not in payload]
    if missing:
        raise AssertionError(f"Event payload missing keys: {missing}")
    for key in ("timestamp", "x", "y", "maximumPossibleForce", "majorRadius"):
        if not isinstance(payload[key], (int, float)):
            raise AssertionError(f"Event field {key} must be numeric")
        if not math.isfinite(float(payload[key])):
            raise AssertionError(f"Event field {key} must be finite")
    if payload["force"] is not None and not isinstance(payload["force"], (int, float)):
        raise AssertionError("Event force must be numeric or null")


def validate_feature_payload(payload: dict[str, Any]) -> None:
    missing = [key for key in FEATURE_TOP_LEVEL_KEYS if key not in payload]
    if missing:
        raise AssertionError(f"Feature payload missing keys: {missing}")
    for key in FEATURE_METRIC_KEYS:
        if not isinstance(payload[key], (int, float)):
            raise AssertionError(f"Feature field {key} must be numeric")
        if not math.isfinite(float(payload[key])):
            raise AssertionError(f"Feature field {key} must be finite")
    if payload.get("metadata") is not None and not isinstance(payload["metadata"], dict):
        raise AssertionError("Feature metadata must be an object or null")


def validate_timestamp_monotonicity(payload: dict[str, Any]) -> None:
    timestamps = [float(event["timestamp"]) for event in payload["events"]]
    if timestamps != sorted(timestamps):
        raise AssertionError("Session timestamps must be monotonically non-decreasing")

    grouped: dict[str, list[float]] = {}
    for event in payload["events"]:
        grouped.setdefault(str(event["touchId"]), []).append(float(event["timestamp"]))
    for touch_id, touch_timestamps in grouped.items():
        if touch_timestamps != sorted(touch_timestamps):
            raise AssertionError(f"Timestamps must be monotonic within touch {touch_id}")


def compare_feature_payloads(left: dict[str, Any], right: dict[str, Any], tolerance: float = 1e-9) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for key in ("featureVersion", "sessionId", "userId", "deviceType", "metadata"):
        if key == "metadata":
            if left.get(key) != right.get(key):
                diffs.append({"field": key, "left": left.get(key), "right": right.get(key)})
            continue
        if left.get(key) != right.get(key):
            diffs.append({"field": key, "left": left.get(key), "right": right.get(key)})
    for key in FEATURE_METRIC_KEYS:
        if not float_close(float(left[key]), float(right[key]), tolerance=tolerance):
            diffs.append({"field": key, "left": left[key], "right": right[key]})
    return diffs


def normalize_batch_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in summary.items()
        if key not in {"runId", "generatedAt", "files"}
    }

def session_summary(session: TouchSessionRecord) -> dict[str, Any]:
    return {
        "sessionId": session.session_id,
        "sessionType": session.session_type,
        "touchEventCount": session.touch_event_count,
        "eventHash": canonical_sha256(session.to_dict()),
        "touchIds": sorted({event.touch_id for event in session.events}),
    }
