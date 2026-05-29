from __future__ import annotations

import json
import logging
import shutil
import csv
from pathlib import Path
from typing import Any

from touchprint_lab.analyzer.analysis import session_csv, session_summary_metrics
from touchprint_lab.analyzer.features import FeatureExtractor, TouchFeatureVector
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.protocols import ExperimentManager
from touchprint_lab.utils.hash import file_sha256
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class DatasetManager:
    def __init__(self, paths: TouchprintPaths, experiment_manager: ExperimentManager | None = None):
        self.paths = paths
        self.experiment_manager = experiment_manager
        self.index_path = self.paths.processed / "import_index.json"
        self.feature_index_path = self.paths.processed / "feature_index.json"
        self.feature_csv_path = self.paths.processed / "feature_vectors.csv"
        self.feature_json_path = self.paths.processed / "feature_vectors.json"
        self.feature_extractor = FeatureExtractor()
        self.index = self._load_index()
        self.feature_index = self._load_feature_index()

    def _load_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Import index is invalid; starting fresh.")
        return {"by_hash": {}, "sessions": []}

    def _save_index(self) -> None:
        self.index_path.write_text(json.dumps(self.index, indent=2, sort_keys=True), encoding="utf-8")

    def _load_feature_index(self) -> dict[str, Any]:
        if self.feature_index_path.exists():
            try:
                return json.loads(self.feature_index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Feature index is invalid; starting fresh.")
        return {"sessions": []}

    def _save_feature_index(self) -> None:
        self.feature_index_path.write_text(json.dumps(self.feature_index, indent=2, sort_keys=True), encoding="utf-8")

    def scan_incoming(self) -> list[TouchSessionRecord]:
        imported: list[TouchSessionRecord] = []
        for json_path in sorted(self.paths.incoming.glob("*.json")):
            session = self.import_session_file(json_path)
            if session is not None:
                imported.append(session)
        return imported

    def import_session_file(self, source_path: Path) -> TouchSessionRecord | None:
        source_hash = file_sha256(source_path)
        if source_hash in self.index["by_hash"]:
            logger.info("Skipping duplicate import: %s", source_path.name)
            return None

        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Skipping incomplete or invalid JSON file: %s", source_path.name)
            return None

        session = TouchSessionRecord.from_json(payload, source_path=source_path)
        session.source_hash = source_hash
        if self.experiment_manager is not None:
            self.experiment_manager.label_session(session)

        session_dir = self._allocate_session_dir(session)
        session.session_dir = session_dir

        (session_dir / "raw.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        (session_dir / "protocol.json").write_text(
            json.dumps(self._protocol_payload(session), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (session_dir / "summary.json").write_text(
            json.dumps(session_summary_metrics(session), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (session_dir / "manifest.json").write_text(
            json.dumps(self._manifest_for(session, source_hash, source_path.name), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (session_dir / "events.csv").write_text(session_csv(session), encoding="utf-8")

        feature_vector = self._extract_and_store_features(session)
        session.feature_vector = feature_vector.to_dict()
        if self.experiment_manager is not None:
            self.experiment_manager.record_completed_session(session)

        moved_path = session_dir / source_path.name
        if source_path.resolve() != moved_path.resolve():
            shutil.move(str(source_path), str(moved_path))

        self.index["by_hash"][source_hash] = {
            "sessionId": session.session_id,
            "sessionDir": str(session_dir),
            "sourceFile": source_path.name,
        }
        self.index["sessions"].append(
            {
                "sessionId": session.session_id,
                "sessionDir": str(session_dir),
                "sourceHash": source_hash,
                "deviceType": session.device_type,
                "sessionType": session.session_type,
                "protocolSessionId": session.protocol_session_id,
                "protocolType": session.protocol_type,
                "studyId": session.study_id,
                "studyTemplateId": session.study_template_id,
                "studyTemplateVersion": session.study_template_version,
                "studySessionId": session.study_session_id,
                "studyStepId": session.study_step_id,
                "studyStepIndex": session.study_step_index,
                "participantId": session.participant_id,
                "experimentId": session.experiment_id,
                "trialId": session.trial_id,
                "trialIndex": session.trial_index,
                "startedAt": session.started_at,
                "exportedAt": session.exported_at,
                "eventCount": len(session.events),
                "userId": session.user_id,
            }
        )
        self._save_index()

        logger.info("Imported session %s -> %s", session.session_id, session_dir)
        return session

    def load_all_sessions(self) -> list[TouchSessionRecord]:
        sessions: list[TouchSessionRecord] = []
        for entry in self.index.get("sessions", []):
            session_dir = Path(entry["sessionDir"])
            raw_path = session_dir / "raw.json"
            if not raw_path.exists():
                continue
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            session = TouchSessionRecord.from_json(payload, source_path=raw_path)
            session.source_hash = entry.get("sourceHash")
            session.user_id = entry.get("userId", "user_01")
            session.session_type = entry.get("sessionType", getattr(session, "session_type", "unknown"))
            session.protocol_session_id = entry.get("protocolSessionId", getattr(session, "protocol_session_id", "unknown"))
            session.protocol_type = entry.get("protocolType", getattr(session, "protocol_type", "unknown"))
            session.study_id = entry.get("studyId", getattr(session, "study_id", "study_01"))
            session.study_template_id = entry.get("studyTemplateId", getattr(session, "study_template_id", "study_template_01"))
            session.study_template_version = entry.get("studyTemplateVersion", getattr(session, "study_template_version", "v1"))
            session.study_session_id = entry.get("studySessionId", getattr(session, "study_session_id", "unknown"))
            session.study_step_id = entry.get("studyStepId", getattr(session, "study_step_id", "unknown"))
            session.study_step_index = int(entry.get("studyStepIndex", getattr(session, "study_step_index", 0)))
            session.participant_id = entry.get("participantId", getattr(session, "participant_id", "participant_01"))
            session.experiment_id = entry.get("experimentId", getattr(session, "experiment_id", "experiment_01"))
            session.trial_id = entry.get("trialId", getattr(session, "trial_id", "trial_01"))
            session.trial_index = int(entry.get("trialIndex", getattr(session, "trial_index", 0)))
            session.session_dir = session_dir
            protocol_path = session_dir / "protocol.json"
            if protocol_path.exists():
                try:
                    protocol_payload = json.loads(protocol_path.read_text(encoding="utf-8"))
                    session.protocol_metadata = dict(protocol_payload.get("protocolMetadata") or {})
                    session.participant_metadata = dict(protocol_payload.get("participantMetadata") or {})
                    session.environment_labels = dict(protocol_payload.get("environmentLabels") or {})
                    session.timing_metadata = dict(protocol_payload.get("timingMetadata") or {})
                except json.JSONDecodeError:
                    logger.warning("Protocol payload is invalid for session %s", session.session_id)
            feature_vector = self.feature_vector_for_session(session.session_id)
            session.feature_vector = feature_vector.to_dict() if feature_vector else None
            sessions.append(session)
        return sessions

    def load_all_feature_vectors(self) -> list[TouchFeatureVector]:
        vectors: list[TouchFeatureVector] = []
        for entry in self.feature_index.get("sessions", []):
            feature_path = Path(entry["featurePath"])
            if not feature_path.exists():
                continue
            payload = json.loads(feature_path.read_text(encoding="utf-8"))
            vectors.append(TouchFeatureVector.from_dict(payload))
        return vectors

    def feature_vector_for_session(self, session_id: str) -> TouchFeatureVector | None:
        for vector in self.load_all_feature_vectors():
            if vector.session_id == session_id:
                return vector
        return None

    def list_users(self) -> list[str]:
        users = sorted({entry.get("userId", "user_01") for entry in self.index.get("sessions", [])})
        return users or ["user_01"]

    def list_session_records(self) -> list[dict[str, Any]]:
        return list(self.index.get("sessions", []))

    def dataset_statistics(self) -> dict[str, Any]:
        records = self.index.get("sessions", [])
        total_events = sum(int(record.get("eventCount", 0)) for record in records)
        return {
            "users": len(self.list_users()),
            "sessions": len(records),
            "events": total_events,
            "featureVectors": len(self.feature_index.get("sessions", [])),
            "sessionTypes": sorted({str(record.get("sessionType", "unknown")) for record in records}),
            "protocolSessions": len({str(record.get("protocolSessionId", "unknown")) for record in records if record.get("protocolSessionId")}),
            "studySessions": len({str(record.get("studySessionId", "unknown")) for record in records if record.get("studySessionId")}),
            "studyTemplates": sorted({str(record.get("studyTemplateId", "unknown")) for record in records if record.get("studyTemplateId")}),
            "participants": sorted({str(record.get("participantId", "participant_01")) for record in records}),
        }

    def _allocate_session_dir(self, session: TouchSessionRecord) -> Path:
        user_dir = self.paths.dataset / session.user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        session_dir = user_dir / f"session_{session.session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _extract_and_store_features(self, session: TouchSessionRecord) -> TouchFeatureVector:
        feature_vector = self.feature_extractor.export_session(session, self.paths.features)
        feature_path = self.paths.features / f"{session.session_id}.json"
        csv_path = self.paths.features / f"{session.session_id}.csv"

        self.feature_index.setdefault("sessions", [])
        self.feature_index["sessions"] = [
            entry for entry in self.feature_index["sessions"] if entry.get("sessionId") != session.session_id
        ]
        self.feature_index["sessions"].append(
            {
                "sessionId": session.session_id,
                "userId": session.user_id,
                "featurePath": str(feature_path),
                "csvPath": str(csv_path),
            }
        )
        self._save_feature_index()
        self._rewrite_global_feature_exports()
        return feature_vector

    def _rewrite_global_feature_exports(self) -> None:
        vectors = self.load_all_feature_vectors()
        if not vectors:
            return
        rows = self.feature_extractor.feature_rows(vectors)
        self.feature_csv_path.write_text(self._rows_to_csv(rows), encoding="utf-8")
        self.feature_json_path.write_text(
            json.dumps([vector.to_dict() for vector in vectors], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _manifest_for(session: TouchSessionRecord, source_hash: str, source_name: str) -> dict[str, Any]:
        return {
            "sessionId": session.session_id,
            "userId": session.user_id,
            "deviceType": session.device_type,
            "sessionType": session.session_type,
            "protocolSessionId": session.protocol_session_id,
            "protocolType": session.protocol_type,
            "studyId": session.study_id,
            "studyTemplateId": session.study_template_id,
            "studyTemplateVersion": session.study_template_version,
            "studySessionId": session.study_session_id,
            "studyStepId": session.study_step_id,
            "studyStepIndex": session.study_step_index,
            "participantId": session.participant_id,
            "experimentId": session.experiment_id,
            "trialId": session.trial_id,
            "trialIndex": session.trial_index,
            "eventCount": len(session.events),
            "sourceHash": source_hash,
            "sourceName": source_name,
            "sourcePath": str(session.source_path) if session.source_path else None,
            "metrics": session_summary_metrics(session),
        }

    @staticmethod
    def _protocol_payload(session: TouchSessionRecord) -> dict[str, Any]:
        return {
            "protocolSessionId": session.protocol_session_id,
            "protocolType": session.protocol_type,
            "studyId": session.study_id,
            "studyTemplateId": session.study_template_id,
            "studyTemplateVersion": session.study_template_version,
            "studySessionId": session.study_session_id,
            "studyStepId": session.study_step_id,
            "studyStepIndex": session.study_step_index,
            "participantId": session.participant_id,
            "experimentId": session.experiment_id,
            "trialId": session.trial_id,
            "trialIndex": session.trial_index,
            "sessionType": session.session_type,
            "participantMetadata": session.participant_metadata,
            "environmentLabels": session.environment_labels,
            "timingMetadata": session.timing_metadata,
            "protocolMetadata": session.protocol_metadata,
        }

    @staticmethod
    def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
