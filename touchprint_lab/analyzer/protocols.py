from __future__ import annotations

import csv
import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:  # pragma: no cover - optional rendering dependency
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - keep module importable
    Image = ImageDraw = ImageFont = None  # type: ignore

from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.similarity import cosine_similarity, normalized_distance_score
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)

EXPERIMENT_TYPES: tuple[str, ...] = (
    "random_tap",
    "intentional_tap",
    "signature_tap",
    "pin_entry",
    "line_drawing",
    "pressure_stabilization",
    "hold_and_release",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _time_of_day_label(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _default_instructions(experiment_type: str) -> str:
    return {
        "random_tap": "Tap the highlighted target naturally, without trying to be consistent.",
        "intentional_tap": "Tap the target intentionally and repeat the same motor strategy.",
        "signature_tap": "Produce a signature-like touch pattern with your preferred style.",
        "pin_entry": "Enter the requested PIN sequence using the keypad.",
        "line_drawing": "Draw a straight line from the start target to the end target.",
        "pressure_stabilization": "Hold contact steady and keep pressure stable.",
        "hold_and_release": "Hold contact in place, then release cleanly.",
    }.get(experiment_type, "Follow the on-screen protocol instructions.")


@dataclass(slots=True)
class ExperimentTrial:
    trial_id: str
    trial_index: int
    experiment_id: str
    participant_id: str
    experiment_type: str
    instructions: str
    expected_duration_seconds: int
    repeat_index: int
    scheduled_delay_seconds: int = 0
    labels: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trialId": self.trial_id,
            "trialIndex": self.trial_index,
            "experimentId": self.experiment_id,
            "participantId": self.participant_id,
            "experimentType": self.experiment_type,
            "instructions": self.instructions,
            "expectedDurationSeconds": self.expected_duration_seconds,
            "repeatIndex": self.repeat_index,
            "scheduledDelaySeconds": self.scheduled_delay_seconds,
            "labels": self.labels,
        }


@dataclass(slots=True)
class ExperimentRun:
    protocol_session_id: str
    experiment_id: str
    participant_id: str
    protocol_type: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    trials: list[ExperimentTrial]
    current_trial_index: int = 0
    participant_metadata: dict[str, Any] = field(default_factory=dict)
    environment_labels: dict[str, Any] = field(default_factory=dict)
    protocol_metadata: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    status: str = "created"

    def current_trial(self) -> ExperimentTrial | None:
        if 0 <= self.current_trial_index < len(self.trials):
            return self.trials[self.current_trial_index]
        return None

    def progress(self) -> float:
        if not self.trials:
            return 1.0
        return min(max(self.current_trial_index / len(self.trials), 0.0), 1.0)

    def completion_fraction(self) -> float:
        if not self.trials:
            return 1.0
        completed = sum(1 for item in self.history if item.get("status") == "completed")
        return completed / len(self.trials)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocolSessionId": self.protocol_session_id,
            "experimentId": self.experiment_id,
            "participantId": self.participant_id,
            "protocolType": self.protocol_type,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "currentTrialIndex": self.current_trial_index,
            "status": self.status,
            "participantMetadata": self.participant_metadata,
            "environmentLabels": self.environment_labels,
            "protocolMetadata": self.protocol_metadata,
            "trials": [trial.to_dict() for trial in self.trials],
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExperimentRun":
        trials = [
            ExperimentTrial(
                trial_id=str(item["trialId"]),
                trial_index=int(item.get("trialIndex", 0)),
                experiment_id=str(item.get("experimentId", payload.get("experimentId", "experiment_01"))),
                participant_id=str(item.get("participantId", payload.get("participantId", "participant_01"))),
                experiment_type=str(item.get("experimentType", "random_tap")),
                instructions=str(item.get("instructions", "")),
                expected_duration_seconds=int(item.get("expectedDurationSeconds", 10)),
                repeat_index=int(item.get("repeatIndex", 0)),
                scheduled_delay_seconds=int(item.get("scheduledDelaySeconds", 0)),
                labels=dict(item.get("labels") or {}),
            )
            for item in payload.get("trials", [])
        ]
        return cls(
            protocol_session_id=str(payload.get("protocolSessionId", uuid.uuid4().hex)),
            experiment_id=str(payload.get("experimentId", "experiment_01")),
            participant_id=str(payload.get("participantId", "participant_01")),
            protocol_type=str(payload.get("protocolType", "controlled_protocol")),
            created_at=str(payload.get("createdAt", _utc_now())),
            started_at=payload.get("startedAt"),
            completed_at=payload.get("completedAt"),
            trials=trials,
            current_trial_index=int(payload.get("currentTrialIndex", 0)),
            participant_metadata=dict(payload.get("participantMetadata") or {}),
            environment_labels=dict(payload.get("environmentLabels") or {}),
            protocol_metadata=dict(payload.get("protocolMetadata") or {}),
            history=list(payload.get("history") or []),
            status=str(payload.get("status", "created")),
        )


class ExperimentManager:
    def __init__(self, paths: TouchprintPaths):
        self.paths = paths
        self.study_manager: Any | None = None
        self.protocol_root = self.paths.protocols
        self.report_root = self.paths.protocol_reports
        self.active_path = self.protocol_root / "active_protocol.json"
        self.history_path = self.protocol_root / "history.json"
        self.runs_dir = self.protocol_root / "runs"
        self.protocol_root.mkdir(parents=True, exist_ok=True)
        self.report_root.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.active_run: ExperimentRun | None = self._load_active_run()
        self.history: list[dict[str, Any]] = self._load_history()

    def _load_active_run(self) -> ExperimentRun | None:
        if not self.active_path.exists():
            return None
        try:
            return ExperimentRun.from_dict(json.loads(self.active_path.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Active protocol state is invalid; resetting.")
            return None

    def _load_history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
            return list(payload) if isinstance(payload, list) else []
        except Exception:
            logger.warning("Protocol history is invalid; starting fresh.")
            return []

    def _save_active_run(self) -> None:
        if self.active_run is None:
            if self.active_path.exists():
                self.active_path.unlink()
            return
        self.active_path.write_text(json.dumps(self.active_run.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _save_history(self) -> None:
        self.history_path.write_text(json.dumps(self.history, indent=2, sort_keys=True), encoding="utf-8")

    def create_protocol(
        self,
        participant_id: str,
        experiment_id: str | None = None,
        experiment_types: Iterable[str] | None = None,
        participant_metadata: dict[str, Any] | None = None,
        environment_labels: dict[str, Any] | None = None,
        protocol_metadata: dict[str, Any] | None = None,
        repetitions: int = 1,
        same_day_repetitions: int = 1,
        multi_day_repetitions: int = 1,
        delayed_retest_hours: int = 24,
        device_type: str = "other",
        input_modality: str = "finger",
        dominant_hand: str = "unknown",
        seed: int = 42,
    ) -> ExperimentRun:
        experiment_id = experiment_id or f"exp_{uuid.uuid4().hex[:8]}"
        experiment_types = list(experiment_types or EXPERIMENT_TYPES)
        rng = random.Random(seed)
        ordered_types = list(experiment_types)
        if protocol_metadata and protocol_metadata.get("shuffleTrials"):
            rng.shuffle(ordered_types)

        participant_metadata = dict(participant_metadata or {})
        environment_labels = dict(environment_labels or {})
        protocol_metadata = dict(protocol_metadata or {})
        environment_labels.setdefault("deviceType", device_type)
        environment_labels.setdefault("inputModality", input_modality)
        environment_labels.setdefault("dominantHand", dominant_hand)
        if environment_labels.get("timeOfDay") in {None, "", "auto"}:
            environment_labels["timeOfDay"] = _time_of_day_label()

        trials: list[ExperimentTrial] = []
        trial_index = 0
        for repeat_index in range(max(1, repetitions)):
            for experiment_type in ordered_types:
                for _sub_repeat in range(max(1, same_day_repetitions)):
                    trial_id = f"trial_{uuid.uuid4().hex[:10]}"
                    labels = {
                        "repeatIndex": repeat_index,
                        "sameDayRepeatIndex": _sub_repeat,
                        "multiDayRepeatIndex": 0,
                        "delayedRetestHours": delayed_retest_hours,
                        "protocolSessionId": None,
                    }
                    trials.append(
                        ExperimentTrial(
                            trial_id=trial_id,
                            trial_index=trial_index,
                            experiment_id=experiment_id,
                            participant_id=participant_id,
                            experiment_type=experiment_type,
                            instructions=_default_instructions(experiment_type),
                            expected_duration_seconds=self._expected_duration(experiment_type),
                            repeat_index=repeat_index,
                            scheduled_delay_seconds=0,
                            labels=labels,
                        )
                    )
                    trial_index += 1
        if multi_day_repetitions > 1:
            base_trials = list(trials)
            for day_index in range(1, multi_day_repetitions):
                for trial in base_trials:
                    duplicate = ExperimentTrial(
                        trial_id=f"trial_{uuid.uuid4().hex[:10]}",
                        trial_index=trial_index,
                        experiment_id=experiment_id,
                        participant_id=participant_id,
                        experiment_type=trial.experiment_type,
                        instructions=trial.instructions,
                        expected_duration_seconds=trial.expected_duration_seconds,
                        repeat_index=trial.repeat_index,
                        scheduled_delay_seconds=delayed_retest_hours * day_index * 3600,
                        labels={**trial.labels, "multiDayRepeatIndex": day_index},
                    )
                    trials.append(duplicate)
                    trial_index += 1

        run = ExperimentRun(
            protocol_session_id=f"protocol_{uuid.uuid4().hex[:12]}",
            experiment_id=experiment_id,
            participant_id=participant_id,
            protocol_type="controlled_protocol",
            created_at=_utc_now(),
            started_at=None,
            completed_at=None,
            trials=trials,
            participant_metadata=participant_metadata,
            environment_labels=environment_labels,
            protocol_metadata={
                **protocol_metadata,
                "seed": seed,
                "repetitions": repetitions,
                "sameDayRepetitions": same_day_repetitions,
                "multiDayRepetitions": multi_day_repetitions,
                "delayedRetestHours": delayed_retest_hours,
                "experimentTypes": ordered_types,
            },
            status="created",
        )
        self.active_run = run
        self._save_active_run()
        logger.info("Created protocol %s for participant %s", run.protocol_session_id, participant_id)
        return run

    @staticmethod
    def _expected_duration(experiment_type: str) -> int:
        return {
            "random_tap": 4,
            "intentional_tap": 5,
            "signature_tap": 8,
            "pin_entry": 10,
            "line_drawing": 7,
            "pressure_stabilization": 12,
            "hold_and_release": 6,
        }.get(experiment_type, 6)

    def start_protocol(self) -> ExperimentRun | None:
        if self.active_run is None:
            return None
        if self.active_run.started_at is None:
            self.active_run.started_at = _utc_now()
        self.active_run.status = "running"
        self._save_active_run()
        return self.active_run

    def finish_protocol(self, completion_note: str | None = None) -> ExperimentRun | None:
        if self.active_run is None:
            return None
        self.active_run.completed_at = _utc_now()
        self.active_run.status = "completed"
        if completion_note:
            self.active_run.protocol_metadata["completionNote"] = completion_note
        self.history.append(self.active_run.to_dict())
        self._save_history()
        finished = self.active_run
        self.active_run = None
        self._save_active_run()
        logger.info("Finished protocol %s", finished.protocol_session_id)
        return finished

    def current_trial(self) -> ExperimentTrial | None:
        if self.active_run is None:
            return None
        return self.active_run.current_trial()

    def progress_snapshot(self) -> dict[str, Any]:
        run = self.active_run
        if run is None:
            return {
                "status": "idle",
                "progress": 0.0,
                "currentTrialIndex": None,
                "totalTrials": 0,
            }
        current = run.current_trial()
        return {
            "status": run.status,
            "progress": run.progress(),
            "completionFraction": run.completion_fraction(),
            "currentTrialIndex": run.current_trial_index,
            "totalTrials": len(run.trials),
            "participantId": run.participant_id,
            "experimentId": run.experiment_id,
            "protocolSessionId": run.protocol_session_id,
            "currentTrial": current.to_dict() if current else None,
            "nextTrialInSeconds": current.scheduled_delay_seconds if current else None,
        }

    def advance_trial(self) -> ExperimentTrial | None:
        if self.active_run is None:
            return None
        if self.active_run.current_trial_index < len(self.active_run.trials) - 1:
            self.active_run.current_trial_index += 1
            self.active_run.status = "running"
            self._save_active_run()
            return self.active_run.current_trial()
        self.finish_protocol()
        return None

    def label_session(self, session: TouchSessionRecord) -> TouchSessionRecord:
        study_manager = getattr(self, "study_manager", None)
        active_study = getattr(study_manager, "active_study", None) if study_manager is not None else None
        active_study_spec = active_study.next_pending() if active_study is not None else None

        if self.active_run is None:
            session.protocol_session_id = session.protocol_session_id or "unknown"
        else:
            trial = self.active_run.current_trial()
            if trial is not None:
                session.protocol_session_id = self.active_run.protocol_session_id
                session.protocol_type = self.active_run.protocol_type
                session.participant_id = self.active_run.participant_id
                session.experiment_id = self.active_run.experiment_id
                session.trial_id = trial.trial_id
                session.trial_index = trial.trial_index
                session.session_type = trial.experiment_type
                session.participant_metadata = dict(self.active_run.participant_metadata)
                session.environment_labels = {
                    **self.active_run.environment_labels,
                    **trial.labels,
                    "experimentType": trial.experiment_type,
                }
                session.timing_metadata = {
                    "capturedAt": _utc_now(),
                    "startedAt": session.started_at,
                    "exportedAt": session.exported_at,
                    "trialExpectedDurationSeconds": trial.expected_duration_seconds,
                    "trialScheduledDelaySeconds": trial.scheduled_delay_seconds,
                }
                session.protocol_metadata = {
                    **self.active_run.protocol_metadata,
                    "instructions": trial.instructions,
                    "trial": trial.to_dict(),
                }
                session.user_id = self.active_run.participant_id

        if active_study is not None:
            session.study_id = active_study.study_id
            session.study_template_id = active_study.template_id
            session.study_template_version = active_study.template_version
            session.study_session_id = active_study.study_id
            if active_study_spec is not None:
                session.study_step_id = active_study_spec.step_id
                session.study_step_index = active_study_spec.step_index
                session.study_labels = dict(active_study_spec.labels)
                session.study_labels.setdefault("studyId", active_study.study_id)
                session.study_labels.setdefault("studyTemplateId", active_study.template_id)
                session.study_labels.setdefault("studyTemplateVersion", active_study.template_version)
                session.study_labels.setdefault("pacingMode", active_study_spec.pacing_mode)
                session.study_labels.setdefault("plannedStartAt", active_study_spec.planned_start_at)
            session.protocol_metadata = {
                **session.protocol_metadata,
                "study": {
                    "studyId": active_study.study_id,
                    "templateId": active_study.template_id,
                    "templateVersion": active_study.template_version,
                    "templateName": active_study.template_name,
                    "templateDescription": active_study.template_description,
                    "currentStep": active_study_spec.to_dict() if active_study_spec is not None else None,
                },
            }

        return session

    def record_completed_session(self, session: TouchSessionRecord) -> dict[str, Any]:
        trial = self.current_trial()
        record = {
            "protocolSessionId": session.protocol_session_id,
            "participantId": session.participant_id,
            "experimentId": session.experiment_id,
            "trialId": session.trial_id,
            "trialIndex": session.trial_index,
            "sessionId": session.session_id,
            "sessionType": session.session_type,
            "deviceType": session.device_type,
            "startedAt": session.started_at,
            "exportedAt": session.exported_at,
            "status": "completed",
            "environmentLabels": session.environment_labels,
            "participantMetadata": session.participant_metadata,
            "timingMetadata": session.timing_metadata,
            "protocolMetadata": session.protocol_metadata,
        }
        if self.active_run is not None and trial is not None and trial.trial_id == session.trial_id:
            self.active_run.history.append(record)
            self.active_run.current_trial_index = min(self.active_run.current_trial_index + 1, len(self.active_run.trials))
            if self.active_run.current_trial_index >= len(self.active_run.trials):
                self.finish_protocol()
            else:
                self._save_active_run()
        study_manager = getattr(self, "study_manager", None)
        if study_manager is not None:
            try:
                study_manager.mark_session_completed(session)
            except Exception:
                logger.exception("Failed to update study manager for session %s", session.session_id)
        return record

    def protocol_history(self) -> list[dict[str, Any]]:
        return list(self.history)

    def experiment_dashboard(self, sessions: list[TouchSessionRecord]) -> list[dict[str, Any]]:
        by_participant: dict[str, list[TouchSessionRecord]] = {}
        for session in sessions:
            by_participant.setdefault(session.participant_id, []).append(session)

        dashboard: list[dict[str, Any]] = []
        for participant_id, participant_sessions in sorted(by_participant.items()):
            ordered = sorted(participant_sessions, key=lambda item: (item.experiment_id, item.trial_index, item.started_at))
            feature_vectors = [TouchFeatureVector.from_dict(item.feature_vector) for item in ordered if item.feature_vector]
            repeatability = self._repeatability_score(feature_vectors)
            drift = self._drift_score(ordered)
            dashboard.append(
                {
                    "participantId": participant_id,
                    "sessionCount": len(participant_sessions),
                    "experimentCount": len({session.experiment_id for session in participant_sessions}),
                    "repeatabilityScore": repeatability,
                    "driftScore": drift,
                    "deviceTypes": sorted({session.device_type for session in participant_sessions}),
                    "sessionTypes": sorted({session.session_type for session in participant_sessions}),
                }
            )
        return dashboard

    def export_protocol_report(self, sessions: list[TouchSessionRecord], output_dir: Path | None = None) -> dict[str, Any]:
        output_dir = output_dir or self.report_root
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = output_dir / f"protocol_report_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        report = self._build_report_payload(sessions)
        summary_path = run_dir / "summary.json"
        history_path = run_dir / "protocol_history.json"
        completion_path = run_dir / "protocol_completion.csv"
        repeatability_path = run_dir / "repeatability.csv"
        drift_path = run_dir / "temporal_drift.csv"
        environment_path = run_dir / "environment_sensitivity.csv"
        markdown_path = run_dir / "report.md"

        summary_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        history_path.write_text(json.dumps(self.protocol_history(), indent=2, sort_keys=True), encoding="utf-8")
        self._write_csv(completion_path, report["completionRows"])
        self._write_csv(repeatability_path, report["repeatabilityRows"])
        self._write_csv(drift_path, report["driftRows"])
        self._write_csv(environment_path, report["environmentRows"])
        markdown_path.write_text(self._markdown_report(report), encoding="utf-8")

        plot_files = self._render_report_plots(run_dir, report)
        files = {
            "summaryJson": str(summary_path),
            "protocolHistoryJson": str(history_path),
            "protocolCompletionCsv": str(completion_path),
            "repeatabilityCsv": str(repeatability_path),
            "temporalDriftCsv": str(drift_path),
            "environmentSensitivityCsv": str(environment_path),
            "markdownReport": str(markdown_path),
            **plot_files,
        }
        report["files"] = files
        summary_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _build_report_payload(self, sessions: list[TouchSessionRecord]) -> dict[str, Any]:
        completion_rows: list[dict[str, Any]] = []
        repeatability_rows: list[dict[str, Any]] = []
        drift_rows: list[dict[str, Any]] = []
        environment_rows: list[dict[str, Any]] = []

        by_trial: dict[tuple[str, str, str], list[TouchSessionRecord]] = {}
        by_participant_experiment: dict[tuple[str, str], list[TouchSessionRecord]] = {}
        for session in sessions:
            key = (session.participant_id, session.experiment_id, session.trial_id)
            by_trial.setdefault(key, []).append(session)
            by_participant_experiment.setdefault((session.participant_id, session.experiment_id), []).append(session)

        planned_trials = len(self.active_run.trials) if self.active_run is not None else len(by_trial)
        completed_trials = sum(1 for items in by_trial.values() if items)
        for (participant_id, experiment_id, trial_id), grouped in sorted(by_trial.items()):
            first = min(grouped, key=lambda item: item.started_at)
            last = max(grouped, key=lambda item: item.exported_at)
            completion_rows.append(
                {
                    "participantId": participant_id,
                    "experimentId": experiment_id,
                    "trialId": trial_id,
                    "sessionCount": len(grouped),
                    "deviceTypes": ";".join(sorted({item.device_type for item in grouped})),
                    "sessionTypes": ";".join(sorted({item.session_type for item in grouped})),
                    "startedAt": first.started_at,
                    "exportedAt": last.exported_at,
                    "durationSeconds": max(last.exported_at - first.started_at, 0.0),
                }
            )

        for (participant_id, experiment_id), grouped in sorted(by_participant_experiment.items()):
            ordered = sorted(grouped, key=lambda item: (item.trial_index, item.started_at))
            vectors = [TouchFeatureVector.from_dict(item.feature_vector) for item in ordered if item.feature_vector]
            similarity_scores = self._pairwise_repeatability(vectors)
            repeatability_rows.append(
                {
                    "participantId": participant_id,
                    "experimentId": experiment_id,
                    "sessionCount": len(ordered),
                    "meanRepeatability": float(np.mean(similarity_scores)) if similarity_scores else 0.0,
                    "stdRepeatability": float(np.std(similarity_scores)) if len(similarity_scores) > 1 else 0.0,
                    "adaptationDelta": self._adaptation_delta(ordered),
                    "driftScore": self._drift_score(ordered),
                }
            )
            drift_rows.extend(self._drift_rows_for_participant(participant_id, experiment_id, ordered))

        environment_rows = self._environment_rows(sessions)
        participant_dashboard = self.experiment_dashboard(sessions)

        summary = {
            "generatedAt": _utc_now(),
            "protocolHistoryCount": len(self.history),
            "completedTrials": completed_trials,
            "totalTrials": planned_trials,
            "completionRate": (completed_trials / planned_trials) if planned_trials else 0.0,
            "participantDashboard": participant_dashboard,
            "experimentTypes": list(EXPERIMENT_TYPES),
            "files": {},
        }
        return {
            **summary,
            "completionRows": completion_rows,
            "repeatabilityRows": repeatability_rows,
            "driftRows": drift_rows,
            "environmentRows": environment_rows,
        }

    def _environment_rows(self, sessions: list[TouchSessionRecord]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not sessions:
            return rows
        by_label: dict[str, list[TouchSessionRecord]] = {}
        for session in sessions:
            for key, value in session.environment_labels.items():
                label_key = f"{key}={value}"
                by_label.setdefault(label_key, []).append(session)
        for label_key, grouped in sorted(by_label.items()):
            feature_vectors = [TouchFeatureVector.from_dict(session.feature_vector) for session in grouped if session.feature_vector]
            rows.append(
                {
                    "label": label_key,
                    "sessionCount": len(grouped),
                    "meanRepeatability": self._repeatability_score(feature_vectors),
                    "meanDrift": self._drift_score(grouped),
                }
            )
        return rows

    def _drift_rows_for_participant(self, participant_id: str, experiment_id: str, sessions: list[TouchSessionRecord]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        ordered = sorted(sessions, key=lambda item: (item.trial_index, item.started_at))
        if len(ordered) < 2:
            return rows
        base = ordered[0]
        base_vector = TouchFeatureVector.from_dict(base.feature_vector) if base.feature_vector else None
        for index, session in enumerate(ordered[1:], start=1):
            if base_vector is None or not session.feature_vector:
                continue
            current_vector = TouchFeatureVector.from_dict(session.feature_vector)
            rows.append(
                {
                    "participantId": participant_id,
                    "experimentId": experiment_id,
                    "trialIndex": session.trial_index,
                    "sessionId": session.session_id,
                    "timeDeltaSeconds": max(session.started_at - base.started_at, 0.0),
                    "similarityToFirst": normalized_distance_score(base_vector, current_vector),
                    "cosineSimilarityToFirst": cosine_similarity(base_vector, current_vector),
                    "driftFromFirst": abs(current_vector.drift_distance - base_vector.drift_distance),
                    "adaptationIndex": index,
                }
            )
        return rows

    def _repeatability_score(self, vectors: list[TouchFeatureVector]) -> float:
        if len(vectors) < 2:
            return 1.0 if vectors else 0.0
        scores: list[float] = []
        for left_index, left in enumerate(vectors):
            for right in vectors[left_index + 1 :]:
                scores.append(normalized_distance_score(left, right))
        return float(np.mean(scores)) if scores else 0.0

    def _pairwise_repeatability(self, vectors: list[TouchFeatureVector]) -> list[float]:
        scores: list[float] = []
        for left_index, left in enumerate(vectors):
            for right in vectors[left_index + 1 :]:
                scores.append(normalized_distance_score(left, right))
        return scores

    def _drift_score(self, sessions: list[TouchSessionRecord]) -> float:
        if len(sessions) < 2:
            return 0.0
        vectors = [TouchFeatureVector.from_dict(session.feature_vector) for session in sessions if session.feature_vector]
        if len(vectors) < 2:
            return 0.0
        base = vectors[0]
        drift_values = [abs(vector.drift_distance - base.drift_distance) for vector in vectors[1:]]
        return float(np.mean(drift_values)) if drift_values else 0.0

    def _adaptation_delta(self, sessions: list[TouchSessionRecord]) -> float:
        if len(sessions) < 3:
            return 0.0
        vectors = [TouchFeatureVector.from_dict(session.feature_vector) for session in sessions if session.feature_vector]
        if len(vectors) < 3:
            return 0.0
        first_half = vectors[: max(1, len(vectors) // 2)]
        second_half = vectors[max(1, len(vectors) // 2) :]
        return float(self._repeatability_score(second_half) - self._repeatability_score(first_half))

    def _markdown_report(self, report: dict[str, Any]) -> str:
        lines = [
            "# Protocol Repeatability Report",
            "",
            f"- Generated at: `{report['generatedAt']}`",
            f"- Completion rate: `{report['completionRate']:.4f}`",
            f"- Completed trials: `{report['completedTrials']}` / `{report['totalTrials']}`",
            "",
            "## Participant Dashboard",
        ]
        for row in report["participantDashboard"][:20]:
            lines.append(
                f"- {row['participantId']}: sessions={row['sessionCount']}, repeatability={row['repeatabilityScore']:.4f}, drift={row['driftScore']:.4f}"
            )
        lines.extend(["", "## Environment Sensitivity"])
        for row in report["environmentRows"][:20]:
            lines.append(f"- {row['label']}: repeatability={row['meanRepeatability']:.4f}, drift={row['meanDrift']:.4f}")
        return "\n".join(lines) + "\n"

    def _render_report_plots(self, output_dir: Path, report: dict[str, Any]) -> dict[str, str]:
        if Image is None:
            return {}
        files: dict[str, str] = {}
        repeatability_path = output_dir / "repeatability_over_time.png"
        drift_path = output_dir / "temporal_drift.png"
        environment_path = output_dir / "environment_sensitivity.png"
        participant_path = output_dir / "participant_consistency.png"
        self._draw_bar_plot(repeatability_path, report["repeatabilityRows"], "repeatability", "Repeatability by Participant / Experiment")
        self._draw_bar_plot(drift_path, report["driftRows"], "similarityToFirst", "Temporal Drift")
        self._draw_bar_plot(environment_path, report["environmentRows"], "meanRepeatability", "Environment Sensitivity")
        self._draw_bar_plot(participant_path, report["participantDashboard"], "repeatabilityScore", "Participant Consistency")
        files.update(
            {
                "repeatabilityPng": str(repeatability_path),
                "temporalDriftPng": str(drift_path),
                "environmentSensitivityPng": str(environment_path),
                "participantConsistencyPng": str(participant_path),
            }
        )
        return files

    def _draw_bar_plot(self, output_path: Path, rows: list[dict[str, Any]], value_key: str, title: str) -> None:
        canvas = Image.new("RGB", (1200, 800), "white")
        draw = ImageDraw.Draw(canvas)
        font = self._font(14)
        title_font = self._font(20)
        draw.text((24, 20), title, fill=(28, 28, 30), font=title_font)
        if not rows:
            canvas.save(str(output_path))
            return
        labels = [self._row_label(row) for row in rows[:18]]
        values = [float(row.get(value_key, 0.0)) for row in rows[:18]]
        max_value = max(values) if values else 1.0
        left, top, right, bottom = 160, 80, 80, 80
        width = 1200 - left - right
        height = 800 - top - bottom
        bar_height = height / len(values)
        for index, (label, value) in enumerate(zip(labels, values)):
            y = top + index * bar_height
            bar_width = (value / (max_value or 1.0)) * width
            draw.rectangle([left, y, left + bar_width, y + bar_height * 0.7], fill=(52, 199, 89))
            draw.text((24, y + bar_height * 0.2), label[:28], fill=(28, 28, 30), font=font)
            draw.text((left + bar_width + 8, y + bar_height * 0.2), f"{value:.4f}", fill=(28, 28, 30), font=font)
        canvas.save(str(output_path))

    def _row_label(self, row: dict[str, Any]) -> str:
        if "participantId" in row and "experimentId" in row:
            return f"{row['participantId']} / {row['experimentId']}"
        if "label" in row:
            return str(row["label"])
        return str(row.get("participantId", row.get("sessionId", "item")))

    def _font(self, size: int):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
