from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from touchprint_lab.analyzer.batch import BatchAnalyzer
from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.features import FeatureExtractor
from touchprint_lab.tests.synthetic import (
    SyntheticTouchGenerator,
    canonical_sha256,
    compare_feature_payloads,
    make_paths,
    validate_feature_payload,
    validate_session_payload,
)


class PipelineRoundtripTests(unittest.TestCase):
    def test_full_pipeline_roundtrip_is_lossless_and_deterministic(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("pin", seed=505, participant_index=4, session_index=6)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = make_paths(root)
            dataset_manager = DatasetManager(paths)

            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)

            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None

            loaded_sessions = dataset_manager.load_all_sessions()
            self.assertEqual(len(loaded_sessions), 1)
            loaded_session = loaded_sessions[0]

            original_payload = session.to_dict()
            raw_payload = json.loads((loaded_session.session_dir / "raw.json").read_text(encoding="utf-8"))
            validate_session_payload(raw_payload)
            self.assertEqual(canonical_sha256(original_payload), canonical_sha256(raw_payload))

            feature_extractor = FeatureExtractor()
            direct_feature = feature_extractor.extract_session(loaded_session)
            stored_feature = loaded_session.feature_vector
            self.assertIsNotNone(stored_feature)
            assert stored_feature is not None

            validate_feature_payload(stored_feature)
            direct_payload = direct_feature.to_dict()
            self.assertEqual(canonical_sha256(stored_feature), canonical_sha256(direct_payload))
            self.assertEqual(compare_feature_payloads(stored_feature, direct_payload), [])

            exported_feature = feature_extractor.export_session(loaded_session, paths.features / "roundtrip")
            self.assertEqual(canonical_sha256(exported_feature.to_dict()), canonical_sha256(direct_payload))

            batch_report = BatchAnalyzer().analyze(loaded_sessions)
            batch_report = BatchAnalyzer().export_report(batch_report, paths.reports)
            self.assertTrue((Path(batch_report.files["summaryJson"])).exists())
            self.assertTrue((Path(batch_report.files["markdownReport"])).exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

