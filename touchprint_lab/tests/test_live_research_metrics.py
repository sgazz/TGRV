from __future__ import annotations

import unittest

from touchprint_lab.live.research_metrics import (
    compute_groove_stability_metrics,
    compute_pin_rhythm_metrics,
    compute_pressure_fingerprint_metrics,
)


class LiveResearchMetricsTests(unittest.TestCase):
    def test_pin_rhythm_metrics_produce_consistency_score(self) -> None:
        events = [
            {
                "messageType": "touch_event",
                "experimentMode": "pin_entry",
                "pinSequenceId": "pin-seq-1",
                "digit": "1",
                "digitIndex": 1,
                "timestamp": 100.0,
                "phase": "ended",
            },
            {
                "messageType": "touch_event",
                "experimentMode": "pin_entry",
                "pinSequenceId": "pin-seq-1",
                "digit": "2",
                "digitIndex": 2,
                "timestamp": 100.18,
                "phase": "ended",
            },
            {
                "messageType": "touch_event",
                "experimentMode": "pin_entry",
                "pinSequenceId": "pin-seq-1",
                "digit": "3",
                "digitIndex": 3,
                "timestamp": 100.40,
                "phase": "ended",
            },
            {
                "messageType": "touch_event",
                "experimentMode": "pin_entry",
                "pinSequenceId": "pin-seq-1",
                "digit": "4",
                "digitIndex": 4,
                "timestamp": 100.54,
                "phase": "ended",
            },
        ]
        metrics = compute_pin_rhythm_metrics(events)
        self.assertFalse(metrics.collecting)
        self.assertEqual(metrics.sequence_id, "pin-seq-1")
        self.assertEqual(len(metrics.intervals_ms), 3)
        self.assertIsNotNone(metrics.consistency_score)
        self.assertGreaterEqual(metrics.consistency_score or 0.0, 0.0)
        self.assertLessEqual(metrics.consistency_score or 0.0, 100.0)
        self.assertIn("|", metrics.bar_text)

    def test_pressure_fingerprint_metrics_produce_histogram(self) -> None:
        events = []
        for index in range(32):
            events.append(
                {
                    "messageType": "touch_event",
                    "timestamp": 200.0 + index * 0.05,
                    "phase": "moved",
                    "x": 120.0 + index * 0.8,
                    "y": 220.0 + index * 0.4,
                    "force": 0.15 + (index % 7) * 0.08,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 16.0 + (index % 5) * 0.7,
                }
            )

        metrics = compute_pressure_fingerprint_metrics(events)
        self.assertFalse(metrics.collecting)
        self.assertIsNotNone(metrics.mean_force)
        self.assertIsNotNone(metrics.median_force)
        self.assertIsNotNone(metrics.std_force)
        self.assertGreater(metrics.histogram_counts.size, 0)
        self.assertGreater(metrics.histogram_edges.size, 0)

    def test_groove_stability_metrics_score_live_window(self) -> None:
        events = []
        phases = ["began", "moved", "moved", "ended"]
        for index in range(260):
            phase = phases[index % len(phases)]
            events.append(
                {
                    "messageType": "touch_event",
                    "timestamp": 300.0 + index * 0.04,
                    "phase": phase,
                    "x": 50.0 + index * 0.6 + (index % 3) * 0.2,
                    "y": 90.0 + index * 0.3 + (index % 4) * 0.15,
                    "force": 0.10 + (index % 8) * 0.05,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 14.0 + (index % 6) * 0.5,
                }
            )

        metrics = compute_groove_stability_metrics(events)
        self.assertFalse(metrics.collecting)
        self.assertIsNotNone(metrics.overall_score)
        self.assertGreaterEqual(metrics.overall_score or 0.0, 0.0)
        self.assertLessEqual(metrics.overall_score or 0.0, 100.0)
        self.assertIsNotNone(metrics.trajectory_score)
        self.assertIsNotNone(metrics.force_score)
        self.assertIsNotNone(metrics.timing_score)
        self.assertIsNotNone(metrics.layer_score)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
