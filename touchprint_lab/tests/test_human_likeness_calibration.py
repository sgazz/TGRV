from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from touchprint_lab.analyzer.human_likeness_calibration import run_human_likeness_calibration


class HumanLikenessCalibrationTests(unittest.TestCase):
    def _run(self, seed: int = 123):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output_dir = Path(tmp.name) / "human_likeness_calibration"
        return run_human_likeness_calibration(output_dir=output_dir, seed=seed)

    def test_synthetic_regular_scores_lower_than_human_like(self) -> None:
        report = self._run(seed=123)
        rows = {row.scenario_id: row for row in report.scenarios}
        self.assertIn("synthetic_regular_perfect", rows)
        self.assertIn("human_like_variable_timing", rows)
        synthetic_score = rows["synthetic_regular_perfect"].human_likeness_score or 0.0
        human_score = rows["human_like_variable_timing"].human_likeness_score or 0.0
        self.assertLess(synthetic_score, human_score)
        self.assertGreater(report.summary["separationMargin"], 0.0)

    def test_flat_pressure_scenario_is_flagged(self) -> None:
        report = self._run(seed=123)
        rows = {row.scenario_id: row for row in report.scenarios}
        flat = rows["synthetic_flat_pressure"]
        joined = " ".join(flat.suspicious_flags).lower()
        self.assertIn("flat", joined)

    def test_repeated_identical_attempts_are_flagged(self) -> None:
        report = self._run(seed=123)
        rows = {row.scenario_id: row for row in report.scenarios}
        repeated = rows["synthetic_repeated_identical_attempts"]
        joined = " ".join(repeated.suspicious_flags).lower()
        self.assertTrue("identical" in joined or "near-identical" in joined)

    def test_calibration_report_exports_all_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "human_likeness_calibration"
            report = run_human_likeness_calibration(output_dir=output_dir, seed=321)

            required = [
                "calibration_summary.json",
                "calibration_results.csv",
                "calibration_report.md",
                "score_distribution.png",
                "suspicion_distribution.png",
                "calibration_report.pdf",
            ]
            for file_name in required:
                self.assertTrue((output_dir / file_name).exists(), file_name)

            self.assertEqual(output_dir, report.output_dir)
            self.assertIn("pdfReport", report.files)
            self.assertGreaterEqual(len(report.files), 6)

    def test_pdf_generation_failure_does_not_break_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "human_likeness_calibration"
            with patch(
                "touchprint_lab.analyzer.human_likeness_calibration._export_pdf_report",
                side_effect=RuntimeError("pdf fail"),
            ):
                report = run_human_likeness_calibration(output_dir=output_dir, seed=321)

            self.assertIn("pdfWarning", report.files)
            self.assertIn("pdfReport", report.files)
            self.assertTrue((output_dir / "calibration_report.pdf").exists())
            self.assertTrue((output_dir / "calibration_summary.json").exists())
            self.assertTrue((output_dir / "calibration_results.csv").exists())
            self.assertTrue((output_dir / "calibration_report.md").exists())
            self.assertTrue((output_dir / "score_distribution.png").exists())
            self.assertTrue((output_dir / "suspicion_distribution.png").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
