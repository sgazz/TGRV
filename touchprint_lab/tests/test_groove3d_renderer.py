from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from touchprint_lab.live.groove3d import Groove3DTrace

try:
    from touchprint_lab.rendering.groove3d_renderer import RendererSelection, select_renderer
except Exception:  # pragma: no cover - optional GUI deps may be missing in CI
    RendererSelection = None  # type: ignore[assignment]
    select_renderer = None  # type: ignore[assignment]


class Groove3DRendererSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        if select_renderer is None:
            self.skipTest("Renderer selection tests require optional GUI dependencies.")

    def test_non_macos_auto_prefers_opengl_or_fallback(self) -> None:
        with patch("touchprint_lab.rendering.groove3d_renderer.platform.system", return_value="Linux"):
            selection = select_renderer("auto")
        self.assertIsInstance(selection, RendererSelection)
        self.assertIn(selection.status, {"OpenGL", "2D fallback"})

    def test_macos_missing_metal_dependency_fallback_safe(self) -> None:
        with patch("touchprint_lab.rendering.groove3d_renderer.platform.system", return_value="Darwin"), patch(
            "touchprint_lab.rendering.groove3d_renderer.detect_metal_availability"
        ) as mocked_detect:
            mocked_detect.return_value.available = False
            mocked_detect.return_value.reason = "PyObjC missing"
            selection = select_renderer("metal")
        self.assertIn(selection.status, {"OpenGL", "2D fallback"})
        self.assertIn("Metal unavailable", selection.reason)

    def test_macos_no_metal_device_fallback_safe(self) -> None:
        with patch("touchprint_lab.rendering.groove3d_renderer.platform.system", return_value="Darwin"), patch(
            "touchprint_lab.rendering.groove3d_renderer.detect_metal_availability"
        ) as mocked_detect:
            mocked_detect.return_value.available = False
            mocked_detect.return_value.reason = "MTLCreateSystemDefaultDevice() returned None."
            selection = select_renderer("auto")
        self.assertIn(selection.status, {"OpenGL", "2D fallback"})
        self.assertIn("Metal unavailable", selection.reason)

    def test_renderer_interface_accepts_empty_trace(self) -> None:
        selection = select_renderer("2d")
        empty = Groove3DTrace(
            x=np.asarray([], dtype=np.float32),
            y=np.asarray([], dtype=np.float32),
            z=np.asarray([], dtype=np.float32),
            z_mode_used="force",
            source_count=0,
        )
        selection.renderer.clear()
        selection.renderer.render_trace(empty)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
