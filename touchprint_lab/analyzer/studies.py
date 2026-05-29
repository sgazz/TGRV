from __future__ import annotations

import csv
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # pragma: no cover - optional YAML support
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback to JSON-compatible YAML
    yaml = None  # type: ignore

try:  # pragma: no cover - optional plotting dependency
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - keep module importable
    Image = ImageDraw = ImageFont = None  # type: ignore

import numpy as np

from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.similarity import normalized_distance_score
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)

STUDY_VERSION = "v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _stable_seed(*parts: str) -> int:
    seed = 0
    for part in parts:
        for character in part:
            seed = (seed * 33 + ord(character)) % (2**32)
    return seed


def _yaml_dump(payload: dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return json.dumps(payload, indent=2, sort_keys=True)


def _yaml_load(text: str) -> dict[str, Any]:
    if yaml is not None:
        loaded = yaml.safe_load(text)
        return dict(loaded) if isinstance(loaded, dict) else {}
    loaded = json.loads(text)
    return dict(loaded) if isinstance(loaded, dict) else {}


def _default_labels(*items: tuple[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in items if value is not None}


@dataclass(slots=True)
class StudyStep:
    step_id: str
    experiment_type: str
    repetitions: int
    pause_seconds: int
    pacing_mode: str
    interval_seconds: int
    labels: dict[str, Any] = field(default_factory=dict)
    required_metadata: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    adaptive_factor: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "experimentType": self.experiment_type,
            "repetitions": self.repetitions,
            "pauseSeconds": self.pause_seconds,
            "pacingMode": self.pacing_mode,
            "intervalSeconds": self.interval_seconds,
            "labels": self.labels,
            "requiredMetadata": self.required_metadata,
            "notes": self.notes,
            "adaptiveFactor": self.adaptive_factor,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudyStep":
        return cls(
            step_id=str(payload["stepId"]),
            experiment_type=str(payload["experimentType"]),
            repetitions=int(payload.get("repetitions", 1)),
            pause_seconds=int(payload.get("pauseSeconds", 0)),
            pacing_mode=str(payload.get("pacingMode", "fixed")),
            interval_seconds=int(payload.get("intervalSeconds", 0)),
            labels=dict(payload.get("labels") or {}),
            required_metadata=dict(payload.get("requiredMetadata") or {}),
            notes=str(payload.get("notes", "")),
            adaptive_factor=float(payload.get("adaptiveFactor", 1.0)),
        )


@dataclass(slots=True)
class StudySessionSpec:
    study_id: str
    study_template_id: str
    study_template_version: str
    session_id: str
    participant_id: str
    step_id: str
    step_index: int
    experiment_type: str
    planned_start_at: str
    pause_before_seconds: int
    interval_seconds: int
    pacing_mode: str
    repetition_index: int
    day_index: int
    labels: dict[str, Any] = field(default_factory=dict)
    required_metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "studyId": self.study_id,
            "studyTemplateId": self.study_template_id,
            "studyTemplateVersion": self.study_template_version,
            "sessionId": self.session_id,
            "participantId": self.participant_id,
            "stepId": self.step_id,
            "stepIndex": self.step_index,
            "experimentType": self.experiment_type,
            "plannedStartAt": self.planned_start_at,
            "pauseBeforeSeconds": self.pause_before_seconds,
            "intervalSeconds": self.interval_seconds,
            "pacingMode": self.pacing_mode,
            "repetitionIndex": self.repetition_index,
            "dayIndex": self.day_index,
            "labels": self.labels,
            "requiredMetadata": self.required_metadata,
            "status": self.status,
            "completedAt": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudySessionSpec":
        return cls(
            study_id=str(payload["studyId"]),
            study_template_id=str(payload["studyTemplateId"]),
            study_template_version=str(payload.get("studyTemplateVersion", STUDY_VERSION)),
            session_id=str(payload["sessionId"]),
            participant_id=str(payload["participantId"]),
            step_id=str(payload["stepId"]),
            step_index=int(payload.get("stepIndex", 0)),
            experiment_type=str(payload["experimentType"]),
            planned_start_at=str(payload.get("plannedStartAt", _utc_now())),
            pause_before_seconds=int(payload.get("pauseBeforeSeconds", 0)),
            interval_seconds=int(payload.get("intervalSeconds", 0)),
            pacing_mode=str(payload.get("pacingMode", "fixed")),
            repetition_index=int(payload.get("repetitionIndex", 0)),
            day_index=int(payload.get("dayIndex", 0)),
            labels=dict(payload.get("labels") or {}),
            required_metadata=dict(payload.get("requiredMetadata") or {}),
            status=str(payload.get("status", "pending")),
            completed_at=payload.get("completedAt"),
        )


@dataclass(slots=True)
class StudyTemplate:
    template_id: str
    version: str
    name: str
    description: str
    steps: list[StudyStep]
    session_schedule: dict[str, Any] = field(default_factory=dict)
    pacing_rules: dict[str, Any] = field(default_factory=dict)
    required_metadata: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    deterministic_seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "templateId": self.template_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "sessionSchedule": self.session_schedule,
            "pacingRules": self.pacing_rules,
            "requiredMetadata": self.required_metadata,
            "labels": self.labels,
            "deterministicSeed": self.deterministic_seed,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudyTemplate":
        return cls(
            template_id=str(payload["templateId"]),
            version=str(payload.get("version", STUDY_VERSION)),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            steps=[StudyStep.from_dict(item) for item in payload.get("steps", [])],
            session_schedule=dict(payload.get("sessionSchedule") or {}),
            pacing_rules=dict(payload.get("pacingRules") or {}),
            required_metadata=dict(payload.get("requiredMetadata") or {}),
            labels=dict(payload.get("labels") or {}),
            deterministic_seed=int(payload.get("deterministicSeed", 42)),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_yaml(self) -> str:
        return _yaml_dump(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "StudyTemplate":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_yaml(cls, text: str) -> "StudyTemplate":
        return cls.from_dict(_yaml_load(text))

    def clone(self, *, template_id: str | None = None, version: str | None = None, name: str | None = None) -> "StudyTemplate":
        return StudyTemplate.from_dict(
            {
                **self.to_dict(),
                "templateId": template_id or self.template_id,
                "version": version or self.version,
                "name": name or self.name,
            }
        )


@dataclass(slots=True)
class StudyPlan:
    study_id: str
    template_id: str
    template_version: str
    participant_id: str
    created_at: str
    start_at: str
    status: str
    template_name: str
    template_description: str
    schedule: list[StudySessionSpec]
    history: list[dict[str, Any]] = field(default_factory=list)
    paused_at: str | None = None
    completed_at: str | None = None
    cloned_from: str | None = None

    def current(self) -> StudySessionSpec | None:
        for spec in self.schedule:
            if spec.status == "pending":
                return spec
        return None

    def next_pending(self) -> StudySessionSpec | None:
        return self.current()

    def progress(self) -> float:
        if not self.schedule:
            return 1.0
        done = sum(1 for spec in self.schedule if spec.status == "completed")
        return done / len(self.schedule)

    def queue(self) -> list[StudySessionSpec]:
        return [spec for spec in self.schedule if spec.status == "pending"]

    def timeline(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in self.schedule]

    def to_dict(self) -> dict[str, Any]:
        return {
            "studyId": self.study_id,
            "templateId": self.template_id,
            "templateVersion": self.template_version,
            "participantId": self.participant_id,
            "createdAt": self.created_at,
            "startAt": self.start_at,
            "status": self.status,
            "templateName": self.template_name,
            "templateDescription": self.template_description,
            "schedule": [spec.to_dict() for spec in self.schedule],
            "history": self.history,
            "pausedAt": self.paused_at,
            "completedAt": self.completed_at,
            "clonedFrom": self.cloned_from,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudyPlan":
        return cls(
            study_id=str(payload["studyId"]),
            template_id=str(payload["templateId"]),
            template_version=str(payload.get("templateVersion", STUDY_VERSION)),
            participant_id=str(payload["participantId"]),
            created_at=str(payload.get("createdAt", _utc_now())),
            start_at=str(payload.get("startAt", _utc_now())),
            status=str(payload.get("status", "created")),
            template_name=str(payload.get("templateName", "")),
            template_description=str(payload.get("templateDescription", "")),
            schedule=[StudySessionSpec.from_dict(item) for item in payload.get("schedule", [])],
            history=list(payload.get("history") or []),
            paused_at=payload.get("pausedAt"),
            completed_at=payload.get("completedAt"),
            cloned_from=payload.get("clonedFrom"),
        )


class StudyTemplateEngine:
    def __init__(self):
        self.templates: dict[str, StudyTemplate] = {}
        self._register_builtin_templates()

    def _register_builtin_templates(self) -> None:
        self.register_template(
            StudyTemplate(
                template_id="baseline_identity_study",
                version=STUDY_VERSION,
                name="Baseline Identity Study",
                description="Baseline stable identity protocol with tap, intentional, and signature segments.",
                steps=[
                    StudyStep("baseline_tap", "random_tap", 8, 2, "fixed", 4, labels={"studyMode": "baseline_identity"}),
                    StudyStep("intentional_identity", "intentional_tap", 6, 3, "fixed", 5, labels={"studyMode": "baseline_identity"}),
                    StudyStep("signature_identity", "signature_tap", 4, 4, "fixed", 8, labels={"studyMode": "baseline_identity"}),
                ],
                session_schedule={"sameDaySessions": 2, "multiDaySessions": 2, "delayedRetestHours": 24},
                pacing_rules={"mode": "fixed", "intervalSeconds": 30, "mandatoryPauseSeconds": 10},
                required_metadata={"deviceType": True, "inputModality": True, "dominantHand": True, "timeOfDay": True},
                labels={"studyMode": "baseline_identity"},
                deterministic_seed=101,
            )
        )
        self.register_template(
            StudyTemplate(
                template_id="pin_behavior_study",
                version=STUDY_VERSION,
                name="PIN Behavior Study",
                description="Deterministic PIN-entry protocol with paced repetition and pause control.",
                steps=[
                    StudyStep(
                        "pin_sequence_a",
                        "pin_entry",
                        12,
                        4,
                        "fixed",
                        6,
                        labels={"pinLength": 4, "pinPattern": "A"},
                        required_metadata={"deviceType": True, "inputModality": True},
                    ),
                    StudyStep(
                        "pin_sequence_b",
                        "pin_entry",
                        12,
                        5,
                        "randomized",
                        7,
                        labels={"pinLength": 4, "pinPattern": "B"},
                        required_metadata={"deviceType": True, "inputModality": True},
                    ),
                ],
                session_schedule={"sameDaySessions": 1, "multiDaySessions": 3, "delayedRetestHours": 12},
                pacing_rules={"mode": "fixed", "intervalSeconds": 20, "mandatoryPauseSeconds": 8},
                required_metadata={"deviceType": True, "attentionMode": True},
                labels={"studyMode": "pin_behavior"},
                deterministic_seed=202,
            )
        )
        self.register_template(
            StudyTemplate(
                template_id="motor_fatigue_study",
                version=STUDY_VERSION,
                name="Motor Fatigue Study",
                description="Progressive pacing protocol to examine drift and fatigue adaptation.",
                steps=[
                    StudyStep("fatigue_warmup", "line_drawing", 8, 2, "adaptive", 5, labels={"fatigueBlock": "warmup"}, adaptive_factor=1.0),
                    StudyStep("fatigue_mid", "pressure_stabilization", 8, 4, "fatigue", 7, labels={"fatigueBlock": "mid"}, adaptive_factor=0.75),
                    StudyStep("fatigue_peak", "hold_and_release", 8, 6, "adaptive", 8, labels={"fatigueBlock": "peak"}, adaptive_factor=0.5),
                ],
                session_schedule={"sameDaySessions": 2, "multiDaySessions": 2, "delayedRetestHours": 24},
                pacing_rules={"mode": "fatigue", "intervalSeconds": 15, "mandatoryPauseSeconds": 12},
                required_metadata={"fatigueState": True, "stressLevel": True, "posture": True},
                labels={"studyMode": "motor_fatigue"},
                deterministic_seed=303,
            )
        )
        self.register_template(
            StudyTemplate(
                template_id="pencil_precision_study",
                version=STUDY_VERSION,
                name="Pencil Precision Study",
                description="High-fidelity pencil protocol focused on geometric precision and repeated control.",
                steps=[
                    StudyStep("pencil_line_a", "line_drawing", 10, 3, "fixed", 6, labels={"inputModality": "pencil", "precisionBlock": "line"}),
                    StudyStep("pencil_signature_a", "signature_tap", 8, 3, "fixed", 8, labels={"inputModality": "pencil", "precisionBlock": "signature"}),
                ],
                session_schedule={"sameDaySessions": 1, "multiDaySessions": 3, "delayedRetestHours": 24},
                pacing_rules={"mode": "fixed", "intervalSeconds": 25, "mandatoryPauseSeconds": 9},
                required_metadata={"deviceType": True, "inputModality": True, "dominantHand": True},
                labels={"studyMode": "pencil_precision", "inputModality": "pencil"},
                deterministic_seed=404,
            )
        )
        self.register_template(
            StudyTemplate(
                template_id="replayability_study",
                version=STUDY_VERSION,
                name="Replayability Study",
                description="Repeated protocol used to probe within-subject replayability over time.",
                steps=[
                    StudyStep("replay_block_a", "random_tap", 10, 2, "fixed", 4, labels={"replayBlock": "a"}),
                    StudyStep("replay_block_b", "intentional_tap", 10, 3, "fixed", 5, labels={"replayBlock": "b"}),
                    StudyStep("replay_block_c", "signature_tap", 10, 4, "adaptive", 6, labels={"replayBlock": "c"}),
                ],
                session_schedule={"sameDaySessions": 2, "multiDaySessions": 4, "delayedRetestHours": 48},
                pacing_rules={"mode": "fixed", "intervalSeconds": 18, "mandatoryPauseSeconds": 10},
                required_metadata={"deviceType": True, "timeOfDay": True},
                labels={"studyMode": "replayability"},
                deterministic_seed=505,
            )
        )

    def register_template(self, template: StudyTemplate) -> None:
        self.templates[template.template_id] = template

    def list_templates(self) -> list[StudyTemplate]:
        return [self.templates[key] for key in sorted(self.templates)]

    def get_template(self, template_id: str) -> StudyTemplate:
        if template_id not in self.templates:
            raise KeyError(f"Unknown study template: {template_id}")
        return self.templates[template_id]

    def export_template(self, template_id: str, output_path: Path) -> None:
        template = self.get_template(template_id)
        output_path.write_text(template.to_json(), encoding="utf-8")

    def export_template_yaml(self, template_id: str, output_path: Path) -> None:
        template = self.get_template(template_id)
        output_path.write_text(template.to_yaml(), encoding="utf-8")

    def import_template(self, path: Path) -> StudyTemplate:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            return StudyTemplate.from_yaml(text)
        return StudyTemplate.from_json(text)

    def create_study(
        self,
        template_id: str,
        participant_id: str,
        start_at: str | None = None,
        study_id: str | None = None,
        custom_labels: dict[str, Any] | None = None,
        custom_required_metadata: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> StudyPlan:
        template = self.get_template(template_id)
        study_id = study_id or f"study_{uuid.uuid4().hex[:10]}"
        seed_value = seed if seed is not None else template.deterministic_seed
        rng = random.Random(_stable_seed(study_id, participant_id, template.template_id, str(seed_value)))
        start_dt = _parse_datetime(start_at)
        current_dt = start_dt
        schedule: list[StudySessionSpec] = []
        step_order = self._deterministic_step_order(template.steps, rng)
        session_index = 0
        day_index = 0
        same_day_sessions = int(template.session_schedule.get("sameDaySessions", 1))
        multi_day_sessions = int(template.session_schedule.get("multiDaySessions", 1))
        delayed_retest_hours = int(template.session_schedule.get("delayedRetestHours", 24))
        day_spacing = timedelta(days=1)

        for day in range(max(1, multi_day_sessions)):
            day_index = day
            if day > 0:
                current_dt = start_dt + day * day_spacing
            for same_day_index in range(max(1, same_day_sessions)):
                for step_index, step in enumerate(step_order):
                    for repetition_index in range(max(1, step.repetitions)):
                        step_pause = self._pacing_pause(step, repetition_index, rng)
                        current_dt += timedelta(seconds=step_pause)
                        spec = StudySessionSpec(
                            study_id=study_id,
                            study_template_id=template.template_id,
                            study_template_version=template.version,
                            session_id=f"study_session_{uuid.uuid4().hex[:10]}",
                            participant_id=participant_id,
                            step_id=step.step_id,
                            step_index=step_index,
                            experiment_type=step.experiment_type,
                            planned_start_at=current_dt.isoformat(),
                            pause_before_seconds=step_pause,
                            interval_seconds=self._interval_seconds(step, repetition_index, rng),
                            pacing_mode=step.pacing_mode,
                            repetition_index=repetition_index,
                            day_index=day_index,
                            labels={
                                **template.labels,
                                **step.labels,
                                **(custom_labels or {}),
                                "studyId": study_id,
                                "studyTemplateId": template.template_id,
                                "studyTemplateVersion": template.version,
                                "sameDaySessionIndex": same_day_index,
                                "multiDaySessionIndex": day_index,
                                "repetitionIndex": repetition_index,
                                "delayedRetestHours": delayed_retest_hours,
                            },
                            required_metadata={
                                **template.required_metadata,
                                **step.required_metadata,
                                **(custom_required_metadata or {}),
                            },
                        )
                        schedule.append(spec)
                        session_index += 1
                        current_dt += timedelta(seconds=spec.interval_seconds)

        plan = StudyPlan(
            study_id=study_id,
            template_id=template.template_id,
            template_version=template.version,
            participant_id=participant_id,
            created_at=_utc_now(),
            start_at=start_dt.isoformat(),
            status="created",
            template_name=template.name,
            template_description=template.description,
            schedule=schedule,
        )
        return plan

    def _deterministic_step_order(self, steps: list[StudyStep], rng: random.Random) -> list[StudyStep]:
        ordered = list(steps)
        if any(step.pacing_mode == "randomized" for step in ordered):
            rng.shuffle(ordered)
        return ordered

    def _pacing_pause(self, step: StudyStep, repetition_index: int, rng: random.Random) -> int:
        if step.pacing_mode == "randomized":
            return max(0, step.pause_seconds + rng.randint(-1, 2))
        if step.pacing_mode == "fatigue":
            return max(0, int(round(step.pause_seconds * max(step.adaptive_factor, 0.25))))
        if step.pacing_mode == "adaptive":
            return max(0, int(round(step.pause_seconds + repetition_index * step.adaptive_factor)))
        return max(0, step.pause_seconds)

    def _interval_seconds(self, step: StudyStep, repetition_index: int, rng: random.Random) -> int:
        if step.pacing_mode == "randomized":
            return max(1, step.interval_seconds + rng.randint(-2, 2))
        if step.pacing_mode == "fatigue":
            return max(1, int(round(step.interval_seconds * max(step.adaptive_factor, 0.25))))
        if step.pacing_mode == "adaptive":
            return max(1, int(round(step.interval_seconds + repetition_index * max(step.adaptive_factor, 0.25))))
        return max(1, step.interval_seconds)


class StudyManager:
    def __init__(self, paths: TouchprintPaths, experiment_manager: Any | None = None):
        self.paths = paths
        self.engine = StudyTemplateEngine()
        self.experiment_manager = experiment_manager
        self.active_path = self.paths.studies / "active_study.json"
        self.history_path = self.paths.studies / "history.json"
        self.templates_dir = self.paths.studies / "templates"
        self.runs_dir = self.paths.studies / "runs"
        self.report_root = self.paths.study_reports
        self.paths.studies.mkdir(parents=True, exist_ok=True)
        self.paths.study_reports.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.active_study: StudyPlan | None = self._load_active()
        self.last_completed_study: StudyPlan | None = None
        self.history: list[dict[str, Any]] = self._load_history()
        self._write_builtin_templates()

    def _load_active(self) -> StudyPlan | None:
        if not self.active_path.exists():
            return None
        try:
            return StudyPlan.from_dict(json.loads(self.active_path.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Invalid active study state; resetting.")
            return None

    def _load_history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
            return list(payload) if isinstance(payload, list) else []
        except Exception:
            logger.warning("Invalid study history; starting fresh.")
            return []

    def _save_active(self) -> None:
        if self.active_study is None:
            if self.active_path.exists():
                self.active_path.unlink()
            return
        self.active_path.write_text(json.dumps(self.active_study.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _save_history(self) -> None:
        self.history_path.write_text(json.dumps(self.history, indent=2, sort_keys=True), encoding="utf-8")

    def _write_builtin_templates(self) -> None:
        for template in self.engine.list_templates():
            path = self.templates_dir / f"{template.template_id}.json"
            yaml_path = self.templates_dir / f"{template.template_id}.yaml"
            if not path.exists():
                path.write_text(template.to_json(), encoding="utf-8")
            if not yaml_path.exists():
                yaml_path.write_text(template.to_yaml(), encoding="utf-8")

    def list_templates(self) -> list[StudyTemplate]:
        return self.engine.list_templates()

    def get_template(self, template_id: str) -> StudyTemplate:
        return self.engine.get_template(template_id)

    def register_template(self, template: StudyTemplate) -> None:
        self.engine.register_template(template)
        self._write_builtin_templates()

    def save_active_study(self) -> None:
        self._save_active()

    def import_template(self, path: Path) -> StudyTemplate:
        template = self.engine.import_template(path)
        self.register_template(template)
        return template

    def create_study(
        self,
        template_id: str,
        participant_id: str,
        start_at: str | None = None,
        study_id: str | None = None,
        custom_labels: dict[str, Any] | None = None,
        custom_required_metadata: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> StudyPlan:
        study = self.engine.create_study(
            template_id=template_id,
            participant_id=participant_id,
            start_at=start_at,
            study_id=study_id,
            custom_labels=custom_labels,
            custom_required_metadata=custom_required_metadata,
            seed=seed,
        )
        self.active_study = study
        self._save_active()
        return study

    def export_study_bundle(
        self,
        study: StudyPlan | None = None,
        *,
        participant_metadata: dict[str, Any] | None = None,
        protocol_manifest: dict[str, Any] | None = None,
        environment_labels: dict[str, Any] | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, str]:
        study = study or self.active_study or self.last_completed_study
        if study is None:
            raise ValueError("No study available to export.")

        study_dir = output_dir or (self.paths.studies / study.study_id)
        study_dir.mkdir(parents=True, exist_ok=True)

        study_plan_path = study_dir / "study_plan.json"
        study_schedule_path = study_dir / "study_schedule.json"
        participant_metadata_path = study_dir / "participant_metadata.json"
        protocol_manifest_path = study_dir / "protocol_manifest.json"
        study_draft_path = study_dir / "study_draft.json"

        study_plan_path.write_text(json.dumps(study.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        study_schedule_path.write_text(json.dumps([spec.to_dict() for spec in study.schedule], indent=2, sort_keys=True), encoding="utf-8")
        study_draft_path.write_text(json.dumps(study.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

        participant_payload = {
            "studyId": study.study_id,
            "templateId": study.template_id,
            "templateVersion": study.template_version,
            "participantId": study.participant_id,
            "createdAt": study.created_at,
            "startAt": study.start_at,
            "participantMetadata": participant_metadata or {},
            "environmentLabels": environment_labels or {},
        }
        participant_metadata_path.write_text(json.dumps(participant_payload, indent=2, sort_keys=True), encoding="utf-8")

        protocol_payload = protocol_manifest or {
            "studyId": study.study_id,
            "templateId": study.template_id,
            "templateVersion": study.template_version,
            "templateName": study.template_name,
            "templateDescription": study.template_description,
            "sessionCount": len(study.schedule),
            "queue": [spec.to_dict() for spec in study.queue()],
        }
        protocol_manifest_path.write_text(json.dumps(protocol_payload, indent=2, sort_keys=True), encoding="utf-8")

        return {
            "studyPlanJson": str(study_plan_path),
            "studyScheduleJson": str(study_schedule_path),
            "participantMetadataJson": str(participant_metadata_path),
            "protocolManifestJson": str(protocol_manifest_path),
            "studyDraftJson": str(study_draft_path),
        }

    def start_study(self) -> StudyPlan | None:
        if self.active_study is None:
            return None
        self.active_study.status = "running"
        self._save_active()
        return self.active_study

    def pause_study(self) -> StudyPlan | None:
        if self.active_study is None:
            return None
        self.active_study.status = "paused"
        self.active_study.paused_at = _utc_now()
        self._save_active()
        return self.active_study

    def resume_study(self) -> StudyPlan | None:
        if self.active_study is None:
            return None
        self.active_study.status = "running"
        self.active_study.paused_at = None
        self._save_active()
        return self.active_study

    def clone_study(self, template_id: str | None = None, participant_id: str | None = None) -> StudyPlan | None:
        if self.active_study is None:
            return None
        original_study_id = self.active_study.study_id
        cloned_template = self.get_template(template_id or self.active_study.template_id)
        cloned = self.create_study(
            cloned_template.template_id,
            participant_id or self.active_study.participant_id,
            seed=cloned_template.deterministic_seed,
        )
        cloned.cloned_from = original_study_id
        self.active_study = cloned
        self._save_active()
        return cloned

    def finish_study(self) -> StudyPlan | None:
        if self.active_study is None:
            return None
        self.active_study.status = "completed"
        self.active_study.completed_at = _utc_now()
        finished = self.active_study
        self.history.append(finished.to_dict())
        self._save_history()
        self.last_completed_study = finished
        self.active_study = None
        self._save_active()
        return finished

    def mark_session_completed(self, session: TouchSessionRecord) -> StudySessionSpec | None:
        study = self.active_study
        if study is None:
            return None
        for spec in study.schedule:
            if spec.status == "completed":
                continue
            matches_step = session.study_step_id != "unknown" and spec.step_id == session.study_step_id
            matches_type = spec.experiment_type == session.session_type
            if spec.participant_id == session.participant_id and (matches_step or matches_type):
                spec.status = "completed"
                spec.completed_at = _utc_now()
                study.history.append(
                    {
                        "sessionId": session.session_id,
                        "studyId": study.study_id,
                        "stepId": spec.step_id,
                        "stepIndex": spec.step_index,
                        "participantId": session.participant_id,
                        "completedAt": spec.completed_at,
                    }
                )
                self._save_active()
                if all(item.status == "completed" for item in study.schedule):
                    self.finish_study()
                return spec
        return None

    def session_timeline(self) -> list[dict[str, Any]]:
        if self.active_study is None:
            return []
        return self.active_study.timeline()

    def pending_sessions(self) -> list[StudySessionSpec]:
        if self.active_study is None:
            return []
        return self.active_study.queue()

    def progress_dashboard(self, sessions: list[TouchSessionRecord]) -> list[dict[str, Any]]:
        study = self.active_study or self.last_completed_study
        if study is None:
            return []
        by_participant: dict[str, list[TouchSessionRecord]] = {}
        for session in sessions:
            by_participant.setdefault(session.participant_id, []).append(session)
        rows: list[dict[str, Any]] = []
        schedule = [spec for spec in study.schedule if spec.participant_id == study.participant_id]
        participant_sessions = by_participant.get(study.participant_id, [])
        ordered = sorted(participant_sessions, key=lambda item: (item.started_at, item.session_id))
        vectors = [TouchFeatureVector.from_dict(item.feature_vector) for item in ordered if item.feature_vector]
        consistency_evolution = self._consistency_evolution(vectors)
        rows.append(
            {
                "participantId": study.participant_id,
                "sessionCount": len(schedule),
                "completionCount": sum(1 for spec in schedule if spec.status == "completed"),
                "consistencyEvolution": consistency_evolution,
                "driftScore": self._longitudinal_drift(vectors),
                "templateId": study.template_id,
            }
        )
        for participant_id, participant_sessions in sorted(by_participant.items()):
            if participant_id == study.participant_id:
                continue
            ordered = sorted(participant_sessions, key=lambda item: (item.started_at, item.session_id))
            vectors = [TouchFeatureVector.from_dict(item.feature_vector) for item in ordered if item.feature_vector]
            consistency_evolution = self._consistency_evolution(vectors)
            rows.append(
                {
                    "participantId": participant_id,
                    "sessionCount": len(ordered),
                    "completionCount": sum(1 for session in ordered if session.study_id == self.active_study.study_id),
                    "consistencyEvolution": consistency_evolution,
                    "driftScore": self._longitudinal_drift(vectors),
                    "templateId": self.active_study.template_id,
                }
            )
        return rows

    def export_study(self, sessions: list[TouchSessionRecord] | None = None, output_dir: Path | None = None) -> dict[str, Any]:
        output_dir = output_dir or self.report_root
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = output_dir / f"study_report_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        report = self._build_report(sessions or [])
        summary_path = run_dir / "summary.json"
        timeline_path = run_dir / "study_timeline.csv"
        queue_path = run_dir / "upcoming_queue.csv"
        dashboard_path = run_dir / "participant_dashboard.csv"
        completeness_path = run_dir / "protocol_adherence.csv"
        drift_path = run_dir / "longitudinal_drift.csv"
        markdown_path = run_dir / "report.md"

        summary_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        self._write_csv(timeline_path, report["timelineRows"])
        self._write_csv(queue_path, report["queueRows"])
        self._write_csv(dashboard_path, report["dashboardRows"])
        self._write_csv(completeness_path, report["adherenceRows"])
        self._write_csv(drift_path, report["driftRows"])
        markdown_path.write_text(self._markdown_report(report), encoding="utf-8")

        plot_files = self._render_plots(run_dir, report)
        files = {
            "summaryJson": str(summary_path),
            "studyTimelineCsv": str(timeline_path),
            "upcomingQueueCsv": str(queue_path),
            "participantDashboardCsv": str(dashboard_path),
            "protocolAdherenceCsv": str(completeness_path),
            "longitudinalDriftCsv": str(drift_path),
            "markdownReport": str(markdown_path),
            **plot_files,
        }
        report["files"] = files
        summary_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _build_report(self, sessions: list[TouchSessionRecord]) -> dict[str, Any]:
        study = self.active_study or self.last_completed_study
        if study is None:
            return {
                "generatedAt": _utc_now(),
                "study": None,
                "timelineRows": [],
                "queueRows": [],
                "dashboardRows": [],
                "adherenceRows": [],
                "driftRows": [],
            }

        timeline_rows = [spec.to_dict() for spec in study.schedule]
        queue_rows = [spec.to_dict() for spec in study.queue()]
        dashboard_rows = self.progress_dashboard(sessions)
        adherence_rows = self._protocol_adherence_rows(study.schedule)
        drift_rows = self._drift_rows(study.schedule)
        return {
            "generatedAt": _utc_now(),
            "study": study.to_dict(),
            "timelineRows": timeline_rows,
            "queueRows": queue_rows,
            "dashboardRows": dashboard_rows,
            "adherenceRows": adherence_rows,
            "driftRows": drift_rows,
            "templates": [template.to_dict() for template in self.list_templates()],
        }

    def _protocol_adherence_rows(self, schedule: list[StudySessionSpec]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in schedule:
            planned = _parse_datetime(spec.planned_start_at)
            completed = _parse_datetime(spec.completed_at) if spec.completed_at else None
            delay = (completed - planned).total_seconds() if completed is not None else None
            rows.append(
                {
                    "participantId": spec.participant_id,
                    "stepId": spec.step_id,
                    "stepIndex": spec.step_index,
                    "plannedStartAt": spec.planned_start_at,
                    "completedAt": spec.completed_at,
                    "status": spec.status,
                    "pauseBeforeSeconds": spec.pause_before_seconds,
                    "intervalSeconds": spec.interval_seconds,
                    "delaySeconds": delay,
                    "adherenceScore": 1.0 if spec.status == "completed" else 0.0,
                }
            )
        return rows

    def _drift_rows(self, schedule: list[StudySessionSpec]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        by_participant: dict[str, list[StudySessionSpec]] = {}
        for spec in schedule:
            by_participant.setdefault(spec.participant_id, []).append(spec)
        for participant_id, specs in sorted(by_participant.items()):
            for index, spec in enumerate(specs[1:], start=1):
                rows.append(
                    {
                        "participantId": participant_id,
                        "stepId": spec.step_id,
                        "stepIndex": spec.step_index,
                        "dayIndex": spec.day_index,
                        "repetitionIndex": spec.repetition_index,
                        "plannedStartAt": spec.planned_start_at,
                        "driftSeconds": index * spec.interval_seconds,
                        "adaptationIndex": index,
                    }
                )
        return rows

    def _consistency_evolution(self, vectors: list[TouchFeatureVector]) -> list[float]:
        if len(vectors) < 2:
            return [1.0] if vectors else []
        base = vectors[0]
        return [float(normalized_distance_score(base, vector)) for vector in vectors]

    def _longitudinal_drift(self, vectors: list[TouchFeatureVector]) -> float:
        if len(vectors) < 2:
            return 0.0
        base = vectors[0]
        drift_values = [abs(vector.drift_distance - base.drift_distance) for vector in vectors[1:]]
        return float(np.mean(drift_values)) if drift_values else 0.0

    def _markdown_report(self, report: dict[str, Any]) -> str:
        lines = [
            "# Study Report",
            "",
            f"- Generated at: `{report['generatedAt']}`",
        ]
        if report.get("study"):
            study = report["study"]
            lines.extend(
                [
                    f"- Study ID: `{study['studyId']}`",
                    f"- Template: `{study['templateId']}@{study['templateVersion']}`",
                    f"- Participant: `{study['participantId']}`",
                    f"- Status: `{study['status']}`",
                ]
            )
        lines.extend(["", "## Templates"])
        for template in report.get("templates", [])[:10]:
            lines.append(f"- {template['templateId']} — {template['name']}")
        lines.extend(["", "## Timeline"])
        for row in report.get("timelineRows", [])[:20]:
            lines.append(
                f"- {row['stepId']} ({row['experimentType']}): planned {row['plannedStartAt']} / status {row['status']}"
            )
        lines.extend(["", "## Participant Consistency"])
        for row in report.get("dashboardRows", [])[:20]:
            lines.append(
                f"- {row['participantId']}: sessionCount={row['sessionCount']}, drift={row['driftScore']:.4f}"
            )
        return "\n".join(lines) + "\n"

    def _render_plots(self, output_dir: Path, report: dict[str, Any]) -> dict[str, str]:
        if Image is None:
            return {}
        files: dict[str, str] = {}
        timeline_png = output_dir / "study_timeline.png"
        adherence_png = output_dir / "protocol_adherence.png"
        drift_png = output_dir / "longitudinal_drift.png"
        queue_png = output_dir / "upcoming_queue.png"
        self._draw_timeline(timeline_png, report.get("timelineRows", []))
        self._draw_bar_png(adherence_png, report.get("adherenceRows", []), "adherenceScore", "Protocol Adherence")
        self._draw_bar_png(drift_png, report.get("driftRows", []), "driftSeconds", "Longitudinal Drift")
        self._draw_queue_png(queue_png, report.get("queueRows", []))
        files.update(
            {
                "studyTimelinePng": str(timeline_png),
                "protocolAdherencePng": str(adherence_png),
                "longitudinalDriftPng": str(drift_png),
                "upcomingQueuePng": str(queue_png),
            }
        )
        return files

    def _draw_timeline(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = Image.new("RGB", (1400, 800), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 20), "Study Timeline", fill=(28, 28, 30), font=self._font(20))
        if not rows:
            canvas.save(str(output_path))
            return
        left, top, right, bottom = 180, 80, 80, 80
        width = 1400 - left - right
        height = 800 - top - bottom
        start_times = [_parse_datetime(row["plannedStartAt"]) for row in rows]
        start_min = min(start_times)
        start_max = max(start_times)
        span = max((start_max - start_min).total_seconds(), 1.0)
        for index, row in enumerate(rows[:60]):
            planned = _parse_datetime(row["plannedStartAt"])
            x = left + ((planned - start_min).total_seconds() / span) * width
            y = top + (index % 20) * 30
            draw.rectangle([x, y, x + 8, y + 18], fill=(52, 199, 89))
            draw.text((24, y), f"{row['stepId'][:24]} / {row['experimentType'][:18]}", fill=(28, 28, 30), font=self._font(11))
        canvas.save(str(output_path))

    def _draw_bar_png(self, output_path: Path, rows: list[dict[str, Any]], value_key: str, title: str) -> None:
        canvas = Image.new("RGB", (1200, 800), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 20), title, fill=(28, 28, 30), font=self._font(20))
        if not rows:
            canvas.save(str(output_path))
            return
        labels = [self._row_label(row) for row in rows[:20]]
        values = [float(row.get(value_key, 0.0)) for row in rows[:20]]
        max_value = max(values) if values else 1.0
        left, top, right, bottom = 180, 80, 80, 80
        width = 1200 - left - right
        height = 800 - top - bottom
        bar_height = height / len(values)
        for index, (label, value) in enumerate(zip(labels, values)):
            y = top + index * bar_height
            bar_width = (value / (max_value or 1.0)) * width
            draw.rectangle([left, y, left + bar_width, y + bar_height * 0.7], fill=(0, 122, 255))
            draw.text((24, y + 4), label[:26], fill=(28, 28, 30), font=self._font(11))
            draw.text((left + bar_width + 8, y + 4), f"{value:.4f}", fill=(28, 28, 30), font=self._font(11))
        canvas.save(str(output_path))

    def _draw_queue_png(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = Image.new("RGB", (1200, 800), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 20), "Upcoming Session Queue", fill=(28, 28, 30), font=self._font(20))
        if not rows:
            canvas.save(str(output_path))
            return
        for index, row in enumerate(rows[:20]):
            y = 80 + index * 30
            draw.text((24, y), f"{row['stepId']} / {row['plannedStartAt']} / {row['status']}", fill=(28, 28, 30), font=self._font(11))
        canvas.save(str(output_path))

    def _font(self, size: int):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

    def _row_label(self, row: dict[str, Any]) -> str:
        if "participantId" in row and "stepId" in row:
            return f"{row['participantId']} / {row['stepId']}"
        return str(row.get("label", row.get("stepId", "item")))

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
