from __future__ import annotations

import unittest

from touchprint_lab.live.groove3d import build_groove3d_trace, groove3d_unavailable_message


def _touch_event(
    *,
    x: float,
    y: float,
    timestamp: float,
    force: float | None = None,
    maximum_possible_force: float | None = None,
    radius: float | None = None,
    phase: str = "moved",
) -> dict:
    payload = {
        "messageType": "touch_event",
        "x": x,
        "y": y,
        "timestamp": timestamp,
        "phase": phase,
    }
    if force is not None:
        payload["force"] = force
    if maximum_possible_force is not None:
        payload["maximumPossibleForce"] = maximum_possible_force
    if radius is not None:
        payload["majorRadius"] = radius
    return payload


class Groove3DTests(unittest.TestCase):
    def test_empty_event_buffer(self) -> None:
        trace = build_groove3d_trace([], z_mode="force")
        self.assertEqual(trace.source_count, 0)
        self.assertEqual(trace.x.size, 0)
        self.assertEqual(trace.y.size, 0)
        self.assertEqual(trace.z.size, 0)

    def test_z_normalization_with_force(self) -> None:
        events = [
            _touch_event(x=10, y=5, timestamp=1.0, force=0.1, maximum_possible_force=1.0, radius=10),
            _touch_event(x=20, y=15, timestamp=2.0, force=0.6, maximum_possible_force=1.0, radius=12),
            _touch_event(x=30, y=25, timestamp=3.0, force=1.0, maximum_possible_force=1.0, radius=14),
        ]
        trace = build_groove3d_trace(events, z_mode="force")
        self.assertEqual(trace.source_count, 3)
        self.assertEqual(trace.z_mode_used, "force")
        self.assertGreaterEqual(float(trace.z.min()), 0.0)
        self.assertLessEqual(float(trace.z.max()), 1.0)
        self.assertAlmostEqual(float(trace.z[-1]), 1.0, places=4)

    def test_z_fallback_to_radius_when_force_missing(self) -> None:
        events = [
            _touch_event(x=3, y=3, timestamp=1.0, radius=6),
            _touch_event(x=5, y=4, timestamp=2.0, radius=9),
            _touch_event(x=7, y=7, timestamp=3.0, radius=12),
        ]
        trace = build_groove3d_trace(events, z_mode="force")
        self.assertEqual(trace.z_mode_used, "radius")
        self.assertGreater(float(trace.z[-1]), float(trace.z[0]))
        self.assertGreaterEqual(float(trace.z.min()), 0.0)
        self.assertLessEqual(float(trace.z.max()), 1.0)

    def test_open_gl_unavailable_fallback_message_safe(self) -> None:
        text = groove3d_unavailable_message()
        self.assertIn("3D Groove View unavailable on this system.", text)
        self.assertTrue(text.strip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
