from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from touchprint_lab.analyzer.batch import BatchAnalyzer
from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.tests.synthetic import SyntheticTouchGenerator, canonical_sha256, make_paths, normalize_batch_summary


class BatchStabilityTests(unittest.TestCase):
    def test_batch_analysis_is_stable_across_multiple_reruns(self) -> None:
        generator = SyntheticTouchGenerator()

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = make_paths(root)
            dataset_manager = DatasetManager(paths)

            sessions = generator.generate_sessions(100, seed=707, participant_count=10)
            for session in sessions:
                generator.write_session(session, paths.incoming / f"{session.session_id}.json")
                imported = dataset_manager.import_session_file(paths.incoming / f"{session.session_id}.json")
                self.assertIsNotNone(imported)

            loaded_sessions = dataset_manager.load_all_sessions()
            self.assertEqual(len(loaded_sessions), 100)

            analyzer = BatchAnalyzer()
            runs = [analyzer.analyze(loaded_sessions) for _ in range(3)]
            summaries = [normalize_batch_summary(run.summary_dict()) for run in runs]
            matrices = [run.similarity_matrix for run in runs]
            distances = [run.distance_matrix for run in runs]

            summary_hashes = [canonical_sha256(summary) for summary in summaries]
            self.assertEqual(len(set(summary_hashes)), 1)

            for left, right in zip(matrices, matrices[1:]):
                self.assertTrue(np.allclose(left, right, atol=1e-12, rtol=1e-12))
            for left, right in zip(distances, distances[1:]):
                self.assertTrue(np.allclose(left, right, atol=1e-12, rtol=1e-12))

            report = analyzer.export_report(runs[0], paths.reports)
            self.assertTrue(Path(report.files["summaryJson"]).exists())
            self.assertTrue(Path(report.files["pairwiseComparisonsCsv"]).exists())
            self.assertTrue(Path(report.files["featureImportanceCsv"]).exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
