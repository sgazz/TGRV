from __future__ import annotations

import unittest

from touchprint_lab.analyzer.human_likeness import compute_human_likeness_metrics


def _touch_event(
    *,
    timestamp: float,
    x: float,
    y: float,
    force: float,
    radius: float,
    touch_id: str = "t1",
    digit: str | None = None,
    digit_index: int | None = None,
    sequence_id: str | None = None,
) -> dict:
    return {
        "messageType": "touch_event",
        "sessionId": "session-a",
        "timestamp": timestamp,
        "touchId": touch_id,
        "phase": "moved",
        "x": x,
        "y": y,
        "force": force,
        "majorRadius": radius,
        "maximumPossibleForce": 1.0,
        "experimentMode": "pin_entry" if digit is not None else "free_touch",
        "digit": digit,
        "digitIndex": digit_index,
        "pinSequenceId": sequence_id,
    }


class HumanLikenessTests(unittest.TestCase):
    def test_empty_event_stream_collecting(self) -> None:
        metrics = compute_human_likeness_metrics([])
        self.assertTrue(metrics.collecting)
        self.assertIsNone(metrics.human_likeness_score)
        self.assertEqual(metrics.confidence, "low")

    def test_single_event_collecting(self) -> None:
        metrics = compute_human_likeness_metrics(
            [_touch_event(timestamp=100.0, x=10.0, y=20.0, force=0.2, radius=14.0)]
        )
        self.assertTrue(metrics.collecting)
        self.assertIsNotNone(metrics.signal_quality)
        self.assertEqual(metrics.confidence, "low")

    def test_variable_intervals_score_higher_than_identical(self) -> None:
        human_like = []
        machine_like = []
        human_times = [10.00, 10.18, 10.41, 10.57]
        bot_times = [20.00, 20.20, 20.40, 20.60]
        for index, value in enumerate(human_times, start=1):
            human_like.append(
                _touch_event(
                    timestamp=value,
                    x=100.0 + index * 0.6,
                    y=200.0 + index * 0.4,
                    force=0.22 + index * 0.03,
                    radius=16.0 + index * 0.15,
                    digit=str(index),
                    digit_index=index,
                    sequence_id="seq-human",
                )
            )
        for index, value in enumerate(bot_times, start=1):
            machine_like.append(
                _touch_event(
                    timestamp=value,
                    x=90.0 + index * 0.5,
                    y=180.0 + index * 0.3,
                    force=0.30,
                    radius=17.0,
                    digit=str(index),
                    digit_index=index,
                    sequence_id="seq-bot",
                )
            )

        human_metrics = compute_human_likeness_metrics(human_like)
        bot_metrics = compute_human_likeness_metrics(machine_like)
        self.assertIsNotNone(human_metrics.human_likeness_score)
        self.assertIsNotNone(bot_metrics.human_likeness_score)
        self.assertGreater(human_metrics.human_likeness_score or 0.0, bot_metrics.human_likeness_score or 0.0)
        self.assertGreater(human_metrics.timing_naturalness or 0.0, bot_metrics.timing_naturalness or 0.0)

    def test_flat_pressure_pattern_reduces_pressure_naturalness(self) -> None:
        flat = []
        varied = []
        for index in range(12):
            timestamp = 30.0 + index * 0.05
            flat.append(
                _touch_event(
                    timestamp=timestamp,
                    x=60.0 + index * 0.2,
                    y=80.0 + index * 0.15,
                    force=0.25,
                    radius=14.0,
                )
            )
            varied.append(
                _touch_event(
                    timestamp=timestamp,
                    x=60.0 + index * 0.2,
                    y=80.0 + index * 0.15,
                    force=0.15 + (index % 5) * 0.05,
                    radius=13.0 + (index % 4) * 0.2,
                )
            )

        flat_metrics = compute_human_likeness_metrics(flat)
        varied_metrics = compute_human_likeness_metrics(varied)
        self.assertIsNotNone(flat_metrics.pressure_naturalness)
        self.assertIsNotNone(varied_metrics.pressure_naturalness)
        self.assertLess(flat_metrics.pressure_naturalness or 0.0, varied_metrics.pressure_naturalness or 0.0)

    def test_repeated_identical_sequences_lower_repetition_diversity(self) -> None:
        identical = []
        similar_not_identical = []
        for seq_index in range(3):
            identical_times = [100.0 + seq_index * 2.0, 100.2 + seq_index * 2.0, 100.4 + seq_index * 2.0, 100.6 + seq_index * 2.0]
            rhythm_shapes = [
                [0.00, 0.18, 0.42, 0.58],
                [0.00, 0.23, 0.40, 0.66],
                [0.00, 0.16, 0.45, 0.70],
            ]
            varied_times = [200.0 + seq_index * 2.3 + offset for offset in rhythm_shapes[seq_index]]
            for digit_index, ts in enumerate(identical_times, start=1):
                identical.append(
                    _touch_event(
                        timestamp=ts,
                        x=40.0 + digit_index,
                        y=55.0 + digit_index * 0.5,
                        force=0.24 + digit_index * 0.02,
                        radius=15.0 + digit_index * 0.1,
                        digit=str(digit_index),
                        digit_index=digit_index,
                        sequence_id=f"same-{seq_index}",
                    )
                )
            for digit_index, ts in enumerate(varied_times, start=1):
                similar_not_identical.append(
                    _touch_event(
                        timestamp=ts,
                        x=42.0 + digit_index * 0.9 + seq_index * 0.1,
                        y=57.0 + digit_index * 0.55 + seq_index * 0.1,
                        force=0.20 + digit_index * 0.025 + seq_index * 0.002,
                        radius=14.8 + digit_index * 0.12 + seq_index * 0.01,
                        digit=str(digit_index),
                        digit_index=digit_index,
                        sequence_id=f"var-{seq_index}",
                    )
                )

        identical_metrics = compute_human_likeness_metrics(identical)
        varied_metrics = compute_human_likeness_metrics(similar_not_identical)
        self.assertIsNotNone(identical_metrics.repetition_diversity)
        self.assertIsNotNone(varied_metrics.repetition_diversity)
        self.assertLess(identical_metrics.repetition_diversity or 0.0, varied_metrics.repetition_diversity or 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
