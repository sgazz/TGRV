from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from touchprint_lab.analyzer.readiness import run_system_readiness_check
from touchprint_lab.live.telemetry_server import TelemetrySnapshot
from touchprint_lab.utils.paths import TouchprintPaths


class ReadinessCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.paths = TouchprintPaths(
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
        self.paths.ensure_directories()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _snapshot(self) -> TelemetrySnapshot:
        session_id = "session-ready-01"
        session_dir = self.paths.dataset / "user_01" / f"session_{session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "raw.json").write_text("{}", encoding="utf-8")
        (self.paths.features / f"{session_id}.json").write_text("{}", encoding="utf-8")
        return TelemetrySnapshot(
            connection_status="connected",
            server_state="running",
            host="0.0.0.0",
            port=8765,
            suggested_lan_ip="192.168.1.10",
            active_session_id=session_id,
            event_count=24,
            touch_count=3,
            tap_count=4,
            marker_count=1,
            sample_rate_hz=60.0,
            last_event_timestamp=12345.0,
            last_error=None,
            dropped_messages=0,
            malformed_messages=0,
            export_status="export_verified",
            export_summary={"exportStatus": "export_verified"},
            warnings=[],
            control_message="Live session reset → ready",
            sessions=[
                {
                    "sessionId": session_id,
                    "status": "export_verified",
                    "events": [
                        {"messageType": "touch_event", "timestamp": 1.0, "digit": "1", "pinSequenceId": "pin-1"},
                    ],
                }
            ],
        )

    def test_readiness_generates_reports(self) -> None:
        report = run_system_readiness_check(self.paths, self._snapshot())
        self.assertTrue(report.report_json_path.exists())
        self.assertTrue(report.report_md_path.exists())
        self.assertTrue(any(row.key == "report_export_works" and row.passed for row in report.checks))

    def test_readiness_detects_missing_events(self) -> None:
        snapshot = self._snapshot()
        snapshot.event_count = 0
        snapshot.sessions = []
        report = run_system_readiness_check(self.paths, snapshot)
        by_key = {row.key: row for row in report.checks}
        self.assertFalse(by_key["events_received"].passed)
        self.assertFalse(by_key["pin_metadata_received"].passed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
