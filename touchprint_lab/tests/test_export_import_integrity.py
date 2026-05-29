from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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


class ExportImportIntegrityTests(unittest.TestCase):
    def test_export_import_roundtrip_preserves_session_payload(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("signature", seed=202, participant_index=2, session_index=4)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            dataset_manager = DatasetManager(paths)

            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)
            original_payload = session.to_dict()

            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None

            raw_path = imported.session_dir / "raw.json"
            self.assertTrue(raw_path.exists())

            raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
            validate_session_payload(raw_payload)
            self.assertEqual(canonical_sha256(original_payload), canonical_sha256(raw_payload))

            self.assertEqual(imported.session_id, session.session_id)
            self.assertEqual(imported.touch_event_count, session.touch_event_count)
            self.assertEqual(imported.participant_id, session.participant_id)
            self.assertEqual(imported.experiment_id, session.experiment_id)
            self.assertEqual(imported.trial_id, session.trial_id)
            self.assertEqual(imported.study_id, session.study_id)
            self.assertEqual(imported.study_template_id, session.study_template_id)
            self.assertEqual(imported.study_template_version, session.study_template_version)
            self.assertEqual(imported.study_step_id, session.study_step_id)
            self.assertEqual(imported.study_step_index, session.study_step_index)

            self.assertIsNotNone(imported.feature_vector)
            assert imported.feature_vector is not None
            validate_feature_payload(imported.feature_vector)

            direct_feature = FeatureExtractor().extract_session(imported).to_dict()
            self.assertEqual(canonical_sha256(imported.feature_vector), canonical_sha256(direct_feature))
            self.assertEqual(compare_feature_payloads(imported.feature_vector, direct_feature), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

