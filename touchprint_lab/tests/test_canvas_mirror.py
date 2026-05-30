from __future__ import annotations

import unittest

from touchprint_lab.live.canvas_mirror import build_canvas_mirror_frame, normalize_canvas_points


def _event(
    *,
    x: float,
    y: float,
    phase: str = "moved",
    touch_id: str = "t1",
    force: float | None = None,
    max_force: float | None = 1.0,
    radius: float | None = None,
    width: float | None = None,
    height: float | None = None,
    digit: str | None = None,
) -> dict:
    payload = {
        "messageType": "touch_event",
        "x": x,
        "y": y,
        "phase": phase,
        "touchId": touch_id,
    }
    if force is not None:
        payload["force"] = force
    if max_force is not None:
        payload["maximumPossibleForce"] = max_force
    if radius is not None:
        payload["majorRadius"] = radius
    if width is not None:
        payload["captureWidth"] = width
    if height is not None:
        payload["captureHeight"] = height
    if digit is not None:
        payload["digit"] = digit
    return payload


class CanvasMirrorTests(unittest.TestCase):
    def test_coordinate_normalization_with_surface_size(self) -> None:
        events = [
            _event(x=50, y=25, width=100, height=50),
            _event(x=100, y=50, width=100, height=50),
        ]
        xs, ys, inferred = normalize_canvas_points(events)
        self.assertFalse(inferred)
        self.assertAlmostEqual(float(xs[0]), 0.5)
        self.assertAlmostEqual(float(ys[0]), 0.5)
        self.assertAlmostEqual(float(xs[1]), 1.0)
        self.assertAlmostEqual(float(ys[1]), 1.0)

    def test_missing_surface_size_fallback_infers_bounds(self) -> None:
        events = [_event(x=10, y=10), _event(x=30, y=40)]
        xs, ys, inferred = normalize_canvas_points(events)
        self.assertTrue(inferred)
        self.assertAlmostEqual(float(xs[0]), 0.0)
        self.assertAlmostEqual(float(ys[0]), 0.0)
        self.assertAlmostEqual(float(xs[-1]), 1.0)
        self.assertAlmostEqual(float(ys[-1]), 1.0)

    def test_empty_event_buffer(self) -> None:
        frame = build_canvas_mirror_frame([])
        self.assertEqual(frame.strokes, [])
        self.assertIsNone(frame.latest_point)

    def test_single_tap_rendering_data(self) -> None:
        frame = build_canvas_mirror_frame([_event(x=10, y=10, phase="began", touch_id="tap-1")])
        self.assertEqual(len(frame.strokes), 1)
        self.assertEqual(frame.strokes[0].touch_id, "tap-1")
        self.assertEqual(frame.strokes[0].xs.size, 1)

    def test_line_path_reconstruction(self) -> None:
        events = [
            _event(x=0, y=0, touch_id="line"),
            _event(x=50, y=50, touch_id="line"),
            _event(x=100, y=100, touch_id="line", phase="ended"),
        ]
        frame = build_canvas_mirror_frame(events)
        self.assertEqual(len(frame.strokes), 1)
        self.assertEqual(frame.strokes[0].xs.size, 3)
        self.assertEqual(frame.strokes[0].phase, "ended")

    def test_reset_clears_mirror_state_by_empty_input(self) -> None:
        frame = build_canvas_mirror_frame([])
        self.assertEqual(len(frame.strokes), 0)
        self.assertIsNone(frame.latest_point)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

