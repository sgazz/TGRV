from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional UI dependency
    QApplication = None  # type: ignore

from touchprint_lab.analyzer.human_likeness import HumanLikenessMetrics
try:
    from touchprint_lab.ui.live_dashboard import HumanLikenessDetailsDialog
except Exception:  # pragma: no cover - optional UI dependency
    HumanLikenessDetailsDialog = None  # type: ignore


class _FakeCalibrationReport:
    def __init__(self, *, pdf_path: str | None = None, pdf_warning: str | None = None) -> None:
        self.summary = {
            "averageHumanLikeScore": 77.4,
            "averageSyntheticRegularScore": 42.1,
            "separationMargin": 35.3,
            "suspiciousPatternDetectionRate": 0.88,
        }
        self.output_dir = "/tmp/synthetic_calibration"
        self.files = {}
        if pdf_path is not None:
            self.files["pdfReport"] = pdf_path
        if pdf_warning is not None:
            self.files["pdfWarning"] = pdf_warning


@unittest.skipUnless(QApplication is not None and HumanLikenessDetailsDialog is not None, "PyQt6 is not available")
class HumanLikenessDetailsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_metrics(self) -> HumanLikenessMetrics:
        return HumanLikenessMetrics(
            human_likeness_score=None,
            automation_suspicion_score=None,
            confidence="low",
            explanation_flags=["collecting live signal"],
            suspicious_flags=[],
            timing_naturalness=None,
            jitter_naturalness=None,
            pressure_naturalness=None,
            release_dynamics=None,
            repetition_diversity=None,
            signal_quality=None,
            recent_intervals_ms=[],
            force_variance=None,
            radius_variance=None,
            collecting=True,
        )

    def test_current_session_evaluation_refuses_empty_input(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        dialog.sync_live_context(session_id="session-a", events=[], last_timestamp=None)
        dialog.evaluate_current_session_now()
        self.assertIn("collecting", dialog.current_header_label.text().lower())
        self.assertIn("Not enough live input", dialog.current_body_label.text())

    def test_current_session_evaluation_uses_live_events(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        events = []
        base_timestamp = 1000.0
        for index in range(10):
            events.append(
                {
                    "messageType": "touch_event",
                    "sessionId": "session-b",
                    "touchId": f"touch-{index}",
                    "timestamp": base_timestamp + index * 0.03,
                    "phase": "moved",
                    "x": 50.0 + index * 0.7,
                    "y": 80.0 + index * 0.5,
                    "force": 0.22 + (index % 4) * 0.03,
                    "majorRadius": 14.0 + (index % 3) * 0.2,
                    "digit": str((index % 4) + 1),
                    "digitIndex": (index % 4) + 1,
                    "pinSequenceId": "seq-1",
                }
            )
        dialog.sync_live_context(session_id="session-b", events=events, last_timestamp=base_timestamp + 0.27)
        dialog.evaluate_current_session_now()
        self.assertIn("completed", dialog.current_header_label.text().lower())
        self.assertIn("Current session evaluation complete", dialog.current_body_label.text())
        self.assertIn("Events analyzed: 10", dialog.current_body_label.text())

    def test_synthetic_calibration_label_is_not_misleading(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "calibration_report.pdf"
            pdf_path.write_text("fake", encoding="utf-8")
            with patch(
                "touchprint_lab.ui.live_dashboard.run_human_likeness_calibration",
                return_value=_FakeCalibrationReport(pdf_path=str(pdf_path)),
            ):
                dialog._run_calibration()
        text = dialog.synthetic_body_label.text()
        self.assertIn("Synthetic calibration complete", text)
        self.assertIn("Uses generated synthetic scenarios", text)
        self.assertIn("Simulated human-like avg", text)
        self.assertNotIn("Human avg", text)

    def test_stale_result_clears_on_session_change(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        dialog._set_section("synthetic", "completed", "old synthetic result", "#34c759")
        self.assertIn("completed", dialog.synthetic_header_label.text().lower())
        dialog.sync_live_context(session_id="session-1", events=[], last_timestamp=None)
        dialog.sync_live_context(session_id="session-2", events=[], last_timestamp=None)
        self.assertIn("not run", dialog.synthetic_header_label.text().lower())

    def test_preview_enables_when_pdf_exists(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "calibration_report.pdf"
            pdf_path.write_text("fake", encoding="utf-8")
            with patch(
                "touchprint_lab.ui.live_dashboard.run_human_likeness_calibration",
                return_value=_FakeCalibrationReport(pdf_path=str(pdf_path)),
            ):
                dialog._run_calibration()
        self.assertTrue(dialog.preview_pdf_button.isEnabled())
        self.assertEqual(dialog._calibration_pdf_path, pdf_path)

    def test_missing_pdf_disables_preview_safely(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        with patch(
            "touchprint_lab.ui.live_dashboard.run_human_likeness_calibration",
            return_value=_FakeCalibrationReport(pdf_path="/tmp/does-not-exist.pdf", pdf_warning="Calibration completed, but PDF export failed."),
        ):
            dialog._run_calibration()
        self.assertFalse(dialog.preview_pdf_button.isEnabled())
        self.assertIn("Calibration completed, but PDF export failed.", dialog.synthetic_body_label.text())

    def test_preview_failure_shows_manual_path(self) -> None:
        dialog = HumanLikenessDetailsDialog(self._make_metrics())
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "calibration_report.pdf"
            pdf_path.write_text("fake", encoding="utf-8")
            dialog._calibration_pdf_path = pdf_path
            dialog.preview_pdf_button.setEnabled(True)
            with patch("touchprint_lab.ui.live_dashboard.QDesktopServices.openUrl", return_value=False):
                dialog._preview_calibration_pdf()
        self.assertIn("Open manually", dialog.synthetic_body_label.text())
        self.assertIn("calibration_report.pdf", dialog.synthetic_body_label.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
