from __future__ import annotations

import unittest

from touchprint_lab.ui.help_registry import LIVE_PANEL_HELP_KEY_MAP, PANEL_HELP, REQUIRED_HELP_FIELDS, panel_help_for_live_panel


class HelpRegistryTests(unittest.TestCase):
    def test_live_panel_help_entries_have_required_fields(self) -> None:
        for panel_id in LIVE_PANEL_HELP_KEY_MAP:
            payload = panel_help_for_live_panel(panel_id)
            for field_name in REQUIRED_HELP_FIELDS:
                self.assertIn(field_name, payload)
                self.assertTrue(str(payload[field_name]).strip())

    def test_named_help_payloads_cover_required_live_panels(self) -> None:
        expected = {
            "touch_trajectory",
            "force_radius_timeline",
            "signature_layer",
            "groove_view",
            "phase_timeline",
            "pin_keyboard_mirror",
            "pin_rhythm_strip",
            "pressure_fingerprint",
            "groove_stability",
            "human_likeness",
        }
        self.assertTrue(expected.issubset(set(PANEL_HELP.keys())))

    def test_fallback_payload_is_safe(self) -> None:
        payload = panel_help_for_live_panel("unknown_panel_key")
        for field_name in REQUIRED_HELP_FIELDS:
            self.assertIn(field_name, payload)
            self.assertTrue(str(payload[field_name]).strip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
