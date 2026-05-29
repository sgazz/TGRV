from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from touchprint_lab.analyzer.human_vs_synthetic_validation import ValidationFilters, run_human_vs_synthetic_validation
from touchprint_lab.utils.paths import TouchprintPaths


def _make_paths(root: Path) -> TouchprintPaths:
    return TouchprintPaths(
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


def _write_real_pin_session(paths: TouchprintPaths, session_id: str = "real-pin-1") -> None:
    user_dir = paths.dataset / "user_01" / f"session_{session_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    raw_path = user_dir / "raw.json"

    payload = {
        "sessionId": session_id,
        "startedAt": 1717000000.0,
        "exportedAt": 1717000010.0,
        "deviceType": "iPad",
        "inputType": "finger",
        "sessionType": "pin_entry",
        "participantId": "participant_01",
        "touchEventCount": 12,
        "events": [],
    }
    timestamp = 1717000000.0
    digits = ["1", "2", "3", "4"]
    for index, digit in enumerate(digits, start=1):
        timestamp += [0.0, 0.21, 0.24, 0.18][index - 1]
        for sample_index, (phase, force) in enumerate([("began", 0.18), ("moved", 0.31), ("ended", 0.17)]):
            payload["events"].append(
                {
                    "sessionId": session_id,
                    "touchId": f"touch-{index}",
                    "phase": phase,
                    "sampleKind": "live",
                    "sampleIndex": sample_index,
                    "sampleCount": 3,
                    "timestamp": timestamp + sample_index * 0.015,
                    "x": 100.0 + index * 10.0 + sample_index * 0.4,
                    "y": 300.0 + index * 5.0 + sample_index * 0.25,
                    "force": force + index * 0.01,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 15.0 + sample_index * 0.4,
                    "touchType": "direct",
                    "deviceType": "iPad",
                    "coalescedTouchesCount": 1,
                    "predictedTouchesCount": 0,
                    "inputType": "finger",
                    "experimentMode": "pin_entry",
                    "pinSequenceId": "seq-1",
                    "digit": digit,
                    "digitIndex": index,
                }
            )

    raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paths.processed.mkdir(parents=True, exist_ok=True)
    index_payload = {
        "by_hash": {},
        "sessions": [
            {
                "sessionId": session_id,
                "sessionDir": str(user_dir),
                "sourceHash": "test-hash",
                "deviceType": "iPad",
                "sessionType": "pin_entry",
                "participantId": "participant_01",
                "startedAt": 1717000000.0,
                "exportedAt": 1717000010.0,
                "eventCount": 12,
                "userId": "user_01",
            }
        ],
    }
    (paths.processed / "import_index.json").write_text(
        json.dumps(index_payload, indent=2),
        encoding="utf-8",
    )


class HumanVsSyntheticValidationTests(unittest.TestCase):
    def test_no_real_sessions_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            paths.ensure_directories()
            report = run_human_vs_synthetic_validation(paths=paths, synthetic_seed=123)
            self.assertTrue(report.summary["noRealSessions"])
            self.assertIn("No real PIN sessions found", report.summary["message"])
            self.assertGreater(report.summary["syntheticSessionCount"], 0)

    def test_human_like_simulated_scores_above_synthetic_regular(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            paths.ensure_directories()
            report = run_human_vs_synthetic_validation(paths=paths, synthetic_seed=123)
            self.assertGreater(
                report.summary["syntheticHumanLikeAverageScore"],
                report.summary["syntheticAverageScore"],
            )

    def test_validation_summary_exports_with_real_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            paths.ensure_directories()
            _write_real_pin_session(paths)
            filters = ValidationFilters.from_values(participant_id="participant_01")
            report = run_human_vs_synthetic_validation(paths=paths, filters=filters, synthetic_seed=321)

            self.assertFalse(report.summary["noRealSessions"])
            self.assertGreaterEqual(report.summary["realSessionCount"], 1)
            self.assertIn("scientificLabeling", report.summary)

            required = [
                "validation_summary.json",
                "validation_results.csv",
                "validation_report.md",
                "human_vs_synthetic_scores.png",
                "suspicion_comparison.png",
            ]
            for file_name in required:
                self.assertTrue((report.output_dir / file_name).exists(), file_name)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
