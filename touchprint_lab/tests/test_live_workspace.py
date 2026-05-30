from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from touchprint_lab.ui.live_workspace import LiveWorkspaceLayoutManager


class LiveWorkspaceLayoutManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.temp_dir.name) / "live_workspace_layout.json"
        self.panel_ids = [
            "trajectory",
            "force_radius",
            "signature_layer",
            "groove_view",
            "groove_view_3d",
            "phase_timeline",
            "pin_keyboard_mirror",
            "pressure_fingerprint",
            "groove_stability",
            "human_likeness",
        ]
        self.manager = LiveWorkspaceLayoutManager(self.settings_path, self.panel_ids)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_state_has_all_panels(self) -> None:
        self.assertEqual(set(self.manager.state.panel_order), set(self.panel_ids))
        self.assertEqual(self.manager.state.active_preset, "Research Cockpit")

    def test_move_panel_sets_custom_and_reorders(self) -> None:
        before = list(self.manager.state.panel_order)
        self.manager.move_panel("force_radius", "left")
        after = list(self.manager.state.panel_order)
        self.assertNotEqual(before, after)
        self.assertEqual(self.manager.state.active_preset, "Custom")

    def test_save_and_reload_layout(self) -> None:
        self.manager.move_panel("groove_view_3d", "up")
        self.manager.state.collapsed["phase_timeline"] = True
        self.manager.state.panel_heights["human_likeness"] = 260
        self.manager.save()

        reloaded = LiveWorkspaceLayoutManager(self.settings_path, self.panel_ids)
        self.assertEqual(reloaded.state.panel_order, self.manager.state.panel_order)
        self.assertTrue(reloaded.state.collapsed["phase_timeline"])
        self.assertEqual(reloaded.state.panel_heights["human_likeness"], 260)

    def test_reset_default_restores_preset(self) -> None:
        self.manager.move_panel("human_likeness", "left")
        self.manager.reset_default()
        self.assertEqual(self.manager.state.active_preset, "Research Cockpit")
        self.assertEqual(set(self.manager.state.panel_order), set(self.panel_ids))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
