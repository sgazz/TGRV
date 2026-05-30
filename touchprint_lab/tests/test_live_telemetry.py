from __future__ import annotations

import io
import json
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - optional UI dependency in some test environments
    from PyQt6.QtWidgets import QApplication
    from touchprint_lab.ui.live_dashboard import LiveDashboardWidget
    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - keep telemetry tests runnable without PyQt6
    QApplication = None  # type: ignore[assignment]
    LiveDashboardWidget = None  # type: ignore[assignment]
    PYQT_AVAILABLE = False

from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.live.diagnostics import print_diagnostics
from touchprint_lab.live.telemetry_server import (
    LiveTelemetryServer,
    TelemetryMessage,
    TelemetryMessageType,
    TelemetryMessageValidationError,
)
from touchprint_lab.tests.synthetic import SyntheticTouchGenerator, make_paths
from touchprint_lab.tests.qt_test_utils import get_or_create_qapplication


class LiveTelemetryTests(unittest.TestCase):
    def _start_or_skip(self, server: LiveTelemetryServer) -> None:
        if server.start():
            return
        snapshot = server.snapshot()
        message = str(snapshot.last_error or "unknown")
        if "Operation not permitted" in message or "PermissionError" in message:
            self.skipTest(f"Socket bind is not permitted in this environment: {message}")
        self.fail(f"Failed to start live telemetry server: {message}")

    def test_message_validation_accepts_valid_payload(self) -> None:
        payload = {
            "messageType": "touch_event",
            "sessionId": "session-123",
            "touchId": "touch-456",
            "timestamp": 123.456,
            "phase": "moved",
            "x": 12.5,
            "y": 34.5,
            "force": 0.42,
            "maximumPossibleForce": 1.0,
            "majorRadius": 18.2,
            "altitudeAngle": 0.8,
            "azimuthAngle": 1.4,
            "coalescedCount": 4,
            "predictedCount": 2,
            "deviceType": "iPad",
            "inputType": "pencil",
            "exportExpected": True,
        }
        message = TelemetryMessage.from_payload(payload)
        self.assertEqual(message.message_type, TelemetryMessageType.TOUCH_EVENT)
        self.assertEqual(message.session_id, "session-123")
        self.assertEqual(message.device_type, "iPad")

    def test_message_validation_accepts_pin_payload(self) -> None:
        payload = {
            "messageType": "touch_event",
            "sessionId": "session-pin-001",
            "touchId": "touch-pin-001",
            "timestamp": 123.456,
            "phase": "ended",
            "x": 12.5,
            "y": 34.5,
            "force": 0.42,
            "maximumPossibleForce": 1.0,
            "majorRadius": 18.2,
            "deviceType": "iPhone",
            "inputType": "finger",
            "exportExpected": True,
            "experimentMode": "pin_entry",
            "pinSequenceId": "pin-seq-123",
            "digit": "2",
            "digitIndex": 2,
            "keypadButtonId": "digit_2",
            "enteredPinSoFar": "12",
            "isPinSubmit": False,
            "isPinClear": False,
            "buttonFrameX": 100.0,
            "buttonFrameY": 220.0,
            "buttonFrameWidth": 80.0,
            "buttonFrameHeight": 60.0,
        }
        message = TelemetryMessage.from_payload(payload)
        self.assertEqual(message.experiment_mode, "pin_entry")
        self.assertEqual(message.digit, "2")
        self.assertEqual(message.digit_index, 2)
        self.assertEqual(message.entered_pin_so_far, "12")
        self.assertFalse(message.is_pin_submit or False)
        self.assertFalse(message.is_pin_clear or False)

    def test_message_validation_rejects_malformed_payload(self) -> None:
        with self.assertRaises(TelemetryMessageValidationError):
            TelemetryMessage.from_payload({"messageType": "touch_event", "sessionId": "abc"})

    def test_live_server_receives_and_buffers_messages(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("signature", seed=301, participant_index=1, session_index=1)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            try:
                self._start_or_skip(server)
                self._send_session(server, session)
                self._wait_for(
                    lambda: server.snapshot().event_count == len(session.events)
                    and server.snapshot().export_status == "export_expected"
                )
                snapshot = server.snapshot()
                self.assertEqual(snapshot.active_session_id, session.session_id)
                self.assertEqual(snapshot.event_count, len(session.events))
                self.assertGreaterEqual(snapshot.touch_count, 1)
                self.assertEqual(snapshot.export_status, "export_expected")
            finally:
                server.stop()

    def test_server_binds_to_any_address_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            server = LiveTelemetryServer(paths, port=0)
            try:
                self._start_or_skip(server)
                snapshot = server.snapshot()
                self.assertEqual(server.host, "0.0.0.0")
                self.assertEqual(snapshot.host, "0.0.0.0")
                self.assertEqual(snapshot.server_state, "running")
                self.assertIn(snapshot.connection_status, {"listening", "connected"})
                self.assertNotEqual(snapshot.suggested_lan_ip, "unavailable")
            finally:
                server.stop()

    def test_export_matching_by_session_id(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("pin", seed=404, participant_index=2, session_index=3)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            dataset_manager = DatasetManager(paths)
            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)
            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None

            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            try:
                self._start_or_skip(server)
                self._send_session(server, session)
                self._wait_for(
                    lambda: server.snapshot().event_count == len(session.events)
                    and server.snapshot().export_status == "export_expected"
                )
                result = server.observe_export(imported)
                self.assertEqual(result["exportStatus"], "export_verified")
                self.assertEqual(result["reasons"], [])
            finally:
                server.stop()

    def test_export_mismatch_detection(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("deterministic", seed=505, participant_index=3, session_index=4)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            dataset_manager = DatasetManager(paths)
            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)
            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None

            imported.device_type = "iPad" if imported.device_type != "iPad" else "iPhone"

            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            try:
                self._start_or_skip(server)
                self._send_session(server, session)
                self._wait_for(
                    lambda: server.snapshot().event_count == len(session.events)
                    and server.snapshot().export_status == "export_expected"
                )
                result = server.observe_export(imported)
                self.assertEqual(result["exportStatus"], "export_mismatch")
                self.assertGreater(len(result["reasons"]), 0)
            finally:
                server.stop()

    def test_malformed_json_does_not_crash_server(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("randomized", seed=606, participant_index=1, session_index=2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            try:
                self._start_or_skip(server)
                with socket.create_connection((server.host, server.port), timeout=2.0) as sock:
                    sock.sendall(b"{not-json}\n")
                    for line in self._telemetry_lines(session):
                        sock.sendall(line.encode("utf-8") + b"\n")
                self._wait_for(
                    lambda: server.snapshot().malformed_messages >= 1
                    and server.snapshot().event_count == len(session.events)
                    and server.snapshot().export_status == "export_expected"
                )
                snapshot = server.snapshot()
                self.assertGreaterEqual(snapshot.malformed_messages, 1)
                self.assertEqual(snapshot.event_count, len(session.events))
            finally:
                server.stop()

    def test_export_pipeline_stays_available_without_telemetry(self) -> None:
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("deterministic", seed=707, participant_index=4, session_index=1)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            dataset_manager = DatasetManager(paths)
            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)

            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None
            self.assertTrue(imported.session_dir is not None)
            self.assertTrue((imported.session_dir / "raw.json").exists())
            self.assertTrue((imported.session_dir / "protocol.json").exists())
            self.assertTrue((imported.session_dir / "manifest.json").exists())
            self.assertTrue((imported.session_dir / "summary.json").exists())

    def test_ping_handler_returns_pong(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            try:
                self._start_or_skip(server)
                with socket.create_connection((server.host, server.port), timeout=2.0) as sock:
                    sock.sendall(b'{"messageType":"ping"}\n')
                    response = sock.makefile("r", encoding="utf-8").readline().strip()
                payload = json.loads(response)
                self.assertEqual(payload["messageType"], "pong")
                self.assertIn("serverTime", payload)
            finally:
                server.stop()

    def test_reset_message_clears_live_state_and_pin_mirror(self) -> None:
        if not PYQT_AVAILABLE:
            self.skipTest("PyQt6 is not available in this test environment.")
        generator = SyntheticTouchGenerator()
        session = generator.generate_session("pin", seed=808, participant_index=5, session_index=2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            dataset_manager = DatasetManager(paths)
            incoming_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, incoming_path)
            imported = dataset_manager.import_session_file(incoming_path)
            self.assertIsNotNone(imported)
            assert imported is not None
            imported_files = {
                "raw": imported.session_dir / "raw.json",
                "protocol": imported.session_dir / "protocol.json",
                "manifest": imported.session_dir / "manifest.json",
            }
            server = LiveTelemetryServer(paths, host="127.0.0.1", port=0)
            app = get_or_create_qapplication()
            widget = LiveDashboardWidget(server, paths)
            try:
                self._start_or_skip(server)
                self._send_session(server, session)
                self._wait_for(
                    lambda: server.snapshot().event_count == len(session.events)
                    and server.snapshot().export_status == "export_expected"
                )
                reset_payload = {
                    "messageType": "reset",
                    "sessionId": session.session_id,
                    "newSessionId": "reset-session-001",
                    "timestamp": time.time(),
                    "deviceType": session.device_type,
                    "exportExpected": False,
                    "reason": "user_reset",
                }
                server.ingest_raw_line(json.dumps(reset_payload))
                snapshot = server.snapshot()
                self.assertEqual(snapshot.active_session_id, "reset-session-001")
                self.assertEqual(snapshot.event_count, 0)
                self.assertEqual(snapshot.export_status, "live_only")
                self.assertIsNotNone(snapshot.control_message)
                for file_path in imported_files.values():
                    self.assertTrue(file_path.exists())
                widget.refresh()
                self.assertEqual(widget.pin_sequence_label.text(), "PIN: _ _ _ _")
                self.assertEqual(widget.pin_detail_label.text(), "Waiting for PIN input")
            finally:
                widget.deleteLater()
                server.stop()
                if app is not None:
                    app.processEvents()

    def test_cli_diagnostics_prints_host_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = make_paths(Path(tmp_dir))
            server = LiveTelemetryServer(paths, host="0.0.0.0", port=0)
            try:
                self._start_or_skip(server)
                buffer = io.StringIO()
                from contextlib import redirect_stdout

                with redirect_stdout(buffer):
                    print_diagnostics(server.host, server.port)
                output = buffer.getvalue()
                self.assertIn("Touchprint Live Telemetry Diagnostics", output)
                self.assertIn("Suggested iOS host", output)
                self.assertIn("nc -vz", output)
            finally:
                server.stop()

    def _send_session(self, server: LiveTelemetryServer, session: TouchSessionRecord) -> None:
        with socket.create_connection((server.host, server.port), timeout=2.0) as sock:
            for line in self._telemetry_lines(session):
                sock.sendall(line.encode("utf-8") + b"\n")

    def _telemetry_lines(self, session: TouchSessionRecord) -> list[str]:
        payload = session.to_dict()
        lines: list[str] = [
            json.dumps(
                {
                    "messageType": "session_start",
                    "sessionId": payload["sessionId"],
                    "timestamp": payload["startedAt"],
                    "deviceType": payload["deviceType"],
                    "inputType": "finger",
                    "exportExpected": True,
                }
            )
        ]
        for event in payload["events"]:
            event_payload = dict(event)
            event_payload.update(
                {
                    "messageType": "touch_event",
                    "inputType": "pencil" if event_payload.get("touchType") == "pencil" else "finger",
                    "exportExpected": True,
                }
            )
            lines.append(json.dumps(event_payload))
        lines.append(
            json.dumps(
                {
                    "messageType": "session_end",
                    "sessionId": payload["sessionId"],
                    "timestamp": payload["exportedAt"],
                    "deviceType": payload["deviceType"],
                    "inputType": "finger",
                    "exportExpected": True,
                }
            )
        )
        return lines

    def _wait_for(self, predicate, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("Timed out waiting for live telemetry state to update.")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
