from __future__ import annotations

import unittest

from touchprint_lab.ui.help_registry import (
    LIVE_PANEL_HELP_KEY_MAP,
    LIVE_TELEMETRY_TOOLTIPS,
    PANEL_HELP,
    PANEL_TOOLTIPS,
    REQUIRED_HELP_FIELDS,
    human_likeness_research_guide,
    live_telemetry_tooltip,
    panel_help_for_live_panel,
    panel_tooltip_for_live_panel,
)


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
            "groove_view_3d",
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

    def test_human_likeness_research_guide_contains_required_sections(self) -> None:
        payload = human_likeness_research_guide("en")
        self.assertEqual(payload["title"], "Human-Likeness Research Guide")
        headings = {str(section.get("heading", "")) for section in payload.get("sections", [])}
        required = {
            "What is Human-Likeness?",
            "Why does it matter?",
            "Timing Naturalness",
            "Jitter Naturalness",
            "Pressure Naturalness",
            "Release Dynamics",
            "Repetition Diversity",
            "Signal Quality",
            "Automation Suspicion",
            "Confidence",
            "Interpretation Guide",
            "Research Warning",
        }
        self.assertTrue(required.issubset(headings))

    def test_human_likeness_research_guide_fallbacks_to_english(self) -> None:
        fallback_payload = human_likeness_research_guide("sr")
        self.assertEqual(fallback_payload["title"], "Human-Likeness Research Guide")

    def test_panel_tooltips_exist_for_live_panel_map(self) -> None:
        for panel_id in LIVE_PANEL_HELP_KEY_MAP:
            tooltip = panel_tooltip_for_live_panel(panel_id)
            self.assertTrue(tooltip.strip())
            self.assertLessEqual(len(tooltip), 180)

    def test_human_likeness_tooltip_matches_required_text(self) -> None:
        value = PANEL_TOOLTIPS["human_likeness"]
        self.assertIn("Research score estimating how natural", value)
        self.assertIn("Not authentication", value)

    def test_live_telemetry_tooltip_registry_entries(self) -> None:
        required_keys = {
            "debug_toggle",
            "panel_help",
            "panel_double_click_focus",
            "run_calibration",
            "preview_calibration_pdf",
            "run_human_vs_synthetic_validation",
            "debug_copy_ip",
        }
        self.assertTrue(required_keys.issubset(set(LIVE_TELEMETRY_TOOLTIPS.keys())))
        self.assertEqual(live_telemetry_tooltip("unknown_key", "fallback"), "fallback")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
