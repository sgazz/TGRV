from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import uuid


@dataclass(slots=True)
class TouchEventRecord:
    id: str
    session_id: str
    touch_id: str
    phase: str
    sample_kind: str
    sample_index: int
    sample_count: int
    timestamp: float
    x: float
    y: float
    force: float | None
    maximum_possible_force: float
    major_radius: float
    altitude_angle: float | None
    azimuth_angle: float | None
    touch_type: str
    device_type: str
    coalesced_touches_count: int
    predicted_touches_count: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TouchEventRecord":
        return cls(
            id=str(payload.get("id") or uuid.uuid4()),
            session_id=str(payload["sessionId"]),
            touch_id=str(payload["touchId"]),
            phase=str(payload["phase"]),
            sample_kind=str(payload.get("sampleKind", "live")),
            sample_index=int(payload.get("sampleIndex", 0)),
            sample_count=int(payload.get("sampleCount", 1)),
            timestamp=float(payload["timestamp"]),
            x=float(payload["x"]),
            y=float(payload["y"]),
            force=_optional_float(payload.get("force")),
            maximum_possible_force=float(payload.get("maximumPossibleForce", 0.0)),
            major_radius=float(payload.get("majorRadius", 0.0)),
            altitude_angle=_optional_float(payload.get("altitudeAngle")),
            azimuth_angle=_optional_float(payload.get("azimuthAngle")),
            touch_type=str(payload.get("touchType", "unknown")),
            device_type=str(payload.get("deviceType", "other")),
            coalesced_touches_count=int(payload.get("coalescedTouchesCount", 0)),
            predicted_touches_count=int(payload.get("predictedTouchesCount", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "touchId": self.touch_id,
            "phase": self.phase,
            "sampleKind": self.sample_kind,
            "sampleIndex": self.sample_index,
            "sampleCount": self.sample_count,
            "timestamp": self.timestamp,
            "x": self.x,
            "y": self.y,
            "force": self.force,
            "maximumPossibleForce": self.maximum_possible_force,
            "majorRadius": self.major_radius,
            "altitudeAngle": self.altitude_angle,
            "azimuthAngle": self.azimuth_angle,
            "touchType": self.touch_type,
            "deviceType": self.device_type,
            "coalescedTouchesCount": self.coalesced_touches_count,
            "predictedTouchesCount": self.predicted_touches_count,
        }


@dataclass(slots=True)
class TouchSessionRecord:
    session_id: str
    started_at: float
    exported_at: float
    device_type: str
    touch_event_count: int
    session_type: str = "unknown"
    participant_id: str = "participant_01"
    experiment_id: str = "experiment_01"
    trial_id: str = "trial_01"
    trial_index: int = 0
    protocol_session_id: str = "unknown"
    protocol_type: str = "unknown"
    study_id: str = "study_01"
    study_template_id: str = "study_template_01"
    study_template_version: str = "v1"
    study_session_id: str = "unknown"
    study_step_id: str = "unknown"
    study_step_index: int = 0
    study_labels: dict[str, Any] = field(default_factory=dict)
    protocol_metadata: dict[str, Any] = field(default_factory=dict)
    participant_metadata: dict[str, Any] = field(default_factory=dict)
    environment_labels: dict[str, Any] = field(default_factory=dict)
    timing_metadata: dict[str, Any] = field(default_factory=dict)
    events: list[TouchEventRecord] = field(default_factory=list)
    source_path: Path | None = None
    source_hash: str | None = None
    user_id: str = "user_01"
    session_dir: Path | None = None
    feature_vector: dict[str, Any] | None = None

    @classmethod
    def from_json(cls, payload: dict[str, Any], source_path: Path | None = None) -> "TouchSessionRecord":
        events = [TouchEventRecord.from_dict(event) for event in payload.get("events", [])]
        metadata = payload.get("protocolMetadata") or payload.get("metadata") or {}
        participant_metadata = payload.get("participantMetadata") or {}
        environment_labels = payload.get("environmentLabels") or {}
        timing_metadata = payload.get("timingMetadata") or {}
        study_metadata = payload.get("studyMetadata") or {}
        session_type = str(
            payload.get("sessionType")
            or payload.get("session_type")
            or metadata.get("sessionType")
            or metadata.get("session_type")
            or "unknown"
        )
        return cls(
            session_id=str(payload["sessionId"]),
            started_at=float(payload.get("startedAt", 0.0)),
            exported_at=float(payload.get("exportedAt", 0.0)),
            device_type=str(payload.get("deviceType", "other")),
            session_type=session_type,
            touch_event_count=int(payload.get("touchEventCount", len(events))),
            participant_id=str(payload.get("participantId", metadata.get("participantId", "participant_01"))),
            experiment_id=str(payload.get("experimentId", metadata.get("experimentId", "experiment_01"))),
            trial_id=str(payload.get("trialId", metadata.get("trialId", "trial_01"))),
            trial_index=int(payload.get("trialIndex", metadata.get("trialIndex", 0))),
            protocol_session_id=str(payload.get("protocolSessionId", metadata.get("protocolSessionId", "unknown"))),
            protocol_type=str(payload.get("protocolType", metadata.get("protocolType", "unknown"))),
            study_id=str(payload.get("studyId", study_metadata.get("studyId", "study_01"))),
            study_template_id=str(payload.get("studyTemplateId", study_metadata.get("studyTemplateId", "study_template_01"))),
            study_template_version=str(payload.get("studyTemplateVersion", study_metadata.get("studyTemplateVersion", "v1"))),
            study_session_id=str(payload.get("studySessionId", study_metadata.get("studySessionId", "unknown"))),
            study_step_id=str(payload.get("studyStepId", study_metadata.get("studyStepId", "unknown"))),
            study_step_index=int(payload.get("studyStepIndex", study_metadata.get("studyStepIndex", 0))),
            study_labels=dict(payload.get("studyLabels") or study_metadata.get("studyLabels") or {}),
            protocol_metadata=dict(metadata) if isinstance(metadata, dict) else {},
            participant_metadata=dict(participant_metadata) if isinstance(participant_metadata, dict) else {},
            environment_labels=dict(environment_labels) if isinstance(environment_labels, dict) else {},
            timing_metadata=dict(timing_metadata) if isinstance(timing_metadata, dict) else {},
            events=events,
            source_path=source_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "startedAt": self.started_at,
            "exportedAt": self.exported_at,
            "deviceType": self.device_type,
            "sessionType": self.session_type,
            "participantId": self.participant_id,
            "experimentId": self.experiment_id,
            "trialId": self.trial_id,
            "trialIndex": self.trial_index,
            "protocolSessionId": self.protocol_session_id,
            "protocolType": self.protocol_type,
            "studyId": self.study_id,
            "studyTemplateId": self.study_template_id,
            "studyTemplateVersion": self.study_template_version,
            "studySessionId": self.study_session_id,
            "studyStepId": self.study_step_id,
            "studyStepIndex": self.study_step_index,
            "studyLabels": self.study_labels,
            "protocolMetadata": self.protocol_metadata,
            "participantMetadata": self.participant_metadata,
            "environmentLabels": self.environment_labels,
            "timingMetadata": self.timing_metadata,
            "touchEventCount": self.touch_event_count,
            "events": [event.to_dict() for event in self.events],
        }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
