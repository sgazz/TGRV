from __future__ import annotations

import unittest

from touchprint_lab.analyzer.features import FeatureExtractor
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.live.telemetry_server import TelemetryMessage, TelemetrySessionState


class InputTypeTests(unittest.TestCase):
    def test_telemetry_message_accepts_input_type(self) -> None:
        message = TelemetryMessage.from_payload(
            {
                "messageType": "touch_event",
                "sessionId": "session-1",
                "touchId": "touch-1",
                "timestamp": 1.0,
                "phase": "began",
                "x": 10.0,
                "y": 20.0,
                "force": 0.4,
                "maximumPossibleForce": 1.0,
                "majorRadius": 12.0,
                "deviceType": "iPad",
                "inputType": "pencil",
            }
        )
        self.assertEqual(message.input_type, "pencil")

    def test_session_input_type_infers_from_events(self) -> None:
        payload = {
            "sessionId": "session-2",
            "startedAt": 1.0,
            "exportedAt": 2.0,
            "deviceType": "iPhone",
            "touchEventCount": 2,
            "events": [
                {
                    "id": "event-1",
                    "sessionId": "session-2",
                    "touchId": "touch-1",
                    "phase": "began",
                    "sampleKind": "live",
                    "sampleIndex": 0,
                    "sampleCount": 1,
                    "timestamp": 1.0,
                    "x": 10.0,
                    "y": 20.0,
                    "force": 0.2,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 10.0,
                    "touchType": "direct",
                    "deviceType": "iPhone",
                    "coalescedTouchesCount": 0,
                    "predictedTouchesCount": 0,
                    "inputType": "finger",
                },
                {
                    "id": "event-2",
                    "sessionId": "session-2",
                    "touchId": "touch-2",
                    "phase": "began",
                    "sampleKind": "live",
                    "sampleIndex": 0,
                    "sampleCount": 1,
                    "timestamp": 1.5,
                    "x": 11.0,
                    "y": 21.0,
                    "force": 0.3,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 11.0,
                    "touchType": "pencil",
                    "deviceType": "iPad",
                    "coalescedTouchesCount": 0,
                    "predictedTouchesCount": 0,
                    "inputType": "pencil",
                },
            ],
        }
        session = TouchSessionRecord.from_json(payload)
        self.assertEqual(session.resolved_input_type(), "mixed")

    def test_feature_vector_contains_input_type(self) -> None:
        payload = {
            "sessionId": "session-3",
            "startedAt": 1.0,
            "exportedAt": 2.0,
            "deviceType": "iPad",
            "inputType": "pencil",
            "touchEventCount": 1,
            "events": [
                {
                    "id": "event-1",
                    "sessionId": "session-3",
                    "touchId": "touch-1",
                    "phase": "began",
                    "sampleKind": "live",
                    "sampleIndex": 0,
                    "sampleCount": 1,
                    "timestamp": 1.0,
                    "x": 10.0,
                    "y": 20.0,
                    "force": 0.2,
                    "maximumPossibleForce": 1.0,
                    "majorRadius": 10.0,
                    "touchType": "pencil",
                    "deviceType": "iPad",
                    "coalescedTouchesCount": 0,
                    "predictedTouchesCount": 0,
                    "inputType": "pencil",
                }
            ],
        }
        session = TouchSessionRecord.from_json(payload)
        vector = FeatureExtractor().extract_session(session)
        self.assertEqual(vector.input_type, "pencil")
        self.assertEqual(vector.to_dict()["inputType"], "pencil")

    def test_live_session_state_tracks_mixed_input_mode(self) -> None:
        state = TelemetrySessionState(session_id="session-4")
        state.observed_input_types = {"finger", "pencil"}
        state.input_type = state.resolved_input_type()
        snapshot = state.to_snapshot()
        self.assertEqual(snapshot["inputType"], "mixed")


if __name__ == "__main__":
    unittest.main()
