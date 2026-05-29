from __future__ import annotations

import unittest

from touchprint_lab.tests.synthetic import (
    SUPPORTED_PROFILES,
    SyntheticTouchGenerator,
    canonical_sha256,
    validate_event_payload,
    validate_session_payload,
    validate_timestamp_monotonicity,
)


class SignalSanityTests(unittest.TestCase):
    def test_synthetic_profiles_are_schema_valid(self) -> None:
        generator = SyntheticTouchGenerator()

        for index, profile in enumerate(SUPPORTED_PROFILES):
            session = generator.generate_session(
                profile,
                seed=101,
                participant_index=index,
                session_index=index,
            )
            payload = session.to_dict()

            validate_session_payload(payload)
            validate_timestamp_monotonicity(payload)
            for event in payload["events"]:
                validate_event_payload(event)

            self.assertGreater(len(payload["events"]), 0)
            self.assertEqual(payload["touchEventCount"], len(payload["events"]))
            self.assertEqual(payload["sessionId"], session.session_id)
            self.assertTrue(canonical_sha256(payload))
            self.assertGreater(len({event["touchId"] for event in payload["events"]}), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

