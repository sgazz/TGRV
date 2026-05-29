from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from touchprint_lab.analyzer.features import FeatureExtractor, TouchFeatureVector
from touchprint_lab.tests.synthetic import (
    SyntheticTouchGenerator,
    canonical_sha256,
    compare_feature_payloads,
    validate_feature_payload,
)


class FeatureDeterminismTests(unittest.TestCase):
    def test_repeated_extraction_is_deterministic(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("randomized", seed=303, participant_index=1, session_index=9)
        extractor = FeatureExtractor()

        first = extractor.extract_session(session)
        second = extractor.extract_session(session)

        first_payload = first.to_dict()
        second_payload = second.to_dict()

        validate_feature_payload(first_payload)
        validate_feature_payload(second_payload)

        self.assertEqual(canonical_sha256(first_payload), canonical_sha256(second_payload))
        self.assertEqual(compare_feature_payloads(first_payload, second_payload), [])
        self.assertTrue(np.allclose(first.feature_array(), second.feature_array(), atol=1e-9, rtol=1e-9))

    def test_exported_feature_files_are_stable_across_runs(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("deterministic", seed=404, participant_index=3, session_index=5)
        extractor = FeatureExtractor()

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir)
            first_dir = base_path / "first"
            second_dir = base_path / "second"

            first_vector = extractor.export_session(session, first_dir)
            second_vector = extractor.export_session(session, second_dir)

            self.assertEqual(canonical_sha256(first_vector.to_dict()), canonical_sha256(second_vector.to_dict()))
            self.assertEqual((first_dir / f"{session.session_id}.json").read_text(encoding="utf-8"),
                             (second_dir / f"{session.session_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(TouchFeatureVector.from_dict(first_vector.to_dict()).to_dict(), first_vector.to_dict())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

