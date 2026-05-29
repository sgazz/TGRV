from __future__ import annotations

import argparse
import json
import logging
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.utils.paths import TouchprintPaths

logger = logging.getLogger(__name__)


class TelemetryMessageValidationError(ValueError):
    pass


class TelemetryMessageType:
    PING = "ping"
    TOUCH_EVENT = "touch_event"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    RESET = "reset"
    HEARTBEAT = "heartbeat"


@dataclass(slots=True)
class TelemetryMessage:
    message_type: str
    session_id: str
    new_session_id: str | None
    reason: str | None
    timestamp: float
    device_type: str
    export_expected: bool
    touch_id: str | None = None
    phase: str | None = None
    x: float | None = None
    y: float | None = None
    force: float | None = None
    maximum_possible_force: float | None = None
    major_radius: float | None = None
    altitude_angle: float | None = None
    azimuth_angle: float | None = None
    coalesced_count: int | None = None
    predicted_count: int | None = None
    input_type: str = "unknown"
    sample_kind: str | None = None
    sample_index: int | None = None
    sample_count: int | None = None
    experiment_mode: str | None = None
    pin_sequence_id: str | None = None
    pin_sequence: str | None = None
    digit: str | None = None
    digit_index: int | None = None
    keypad_button_id: str | None = None
    keypad_action: str | None = None
    expected_pin: str | None = None
    entered_pin_so_far: str | None = None
    is_pin_submit: bool | None = None
    is_pin_clear: bool | None = None
    button_frame_x: float | None = None
    button_frame_y: float | None = None
    button_frame_width: float | None = None
    button_frame_height: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TelemetryMessage":
        message_type = str(payload.get("messageType", "")).strip()
        if message_type == TelemetryMessageType.PING:
            session_id = str(payload.get("sessionId", "")).strip() or "ping"
            return cls(
                message_type=message_type,
                session_id=session_id,
                new_session_id=None,
                reason=None,
                timestamp=time.time(),
                device_type=str(payload.get("deviceType", "unknown")).strip() or "unknown",
                export_expected=bool(payload.get("exportExpected", False)),
                payload=dict(payload),
            )
        if message_type == TelemetryMessageType.RESET:
            session_id = str(payload.get("sessionId", "")).strip()
            if not session_id:
                raise TelemetryMessageValidationError("sessionId is required")
            timestamp = _optional_float(payload.get("timestamp")) or time.time()
            device_type = str(payload.get("deviceType", "unknown")).strip() or "unknown"
            export_expected = _optional_bool(payload.get("exportExpected")) or False
            return cls(
                message_type=message_type,
                session_id=session_id,
                new_session_id=_optional_string(payload.get("newSessionId")),
                reason=_optional_string(payload.get("reason")) or "user_reset",
                timestamp=timestamp,
                device_type=device_type,
                export_expected=export_expected,
                payload=dict(payload),
            )
        if message_type not in {
            TelemetryMessageType.TOUCH_EVENT,
            TelemetryMessageType.SESSION_START,
            TelemetryMessageType.SESSION_END,
            TelemetryMessageType.HEARTBEAT,
        }:
            raise TelemetryMessageValidationError(f"Unsupported messageType: {message_type!r}")

        session_id = str(payload.get("sessionId", "")).strip()
        if not session_id:
            raise TelemetryMessageValidationError("sessionId is required")

        timestamp = _coerce_float(payload.get("timestamp"), "timestamp")
        device_type = str(payload.get("deviceType", "")).strip()
        if not device_type:
            raise TelemetryMessageValidationError("deviceType is required")

        export_expected = bool(payload.get("exportExpected", True))

        touch_id = _optional_string(payload.get("touchId"))
        phase = _optional_string(payload.get("phase"))
        x = _optional_float(payload.get("x"))
        y = _optional_float(payload.get("y"))
        force = _optional_float(payload.get("force"))
        maximum_possible_force = _optional_float(payload.get("maximumPossibleForce"))
        major_radius = _optional_float(payload.get("majorRadius"))
        altitude_angle = _optional_float(payload.get("altitudeAngle"))
        azimuth_angle = _optional_float(payload.get("azimuthAngle"))
        coalesced_count = _optional_int(payload.get("coalescedCount"))
        predicted_count = _optional_int(payload.get("predictedCount"))
        input_type = str(payload.get("inputType", "unknown")).strip() or "unknown"
        sample_kind = _optional_string(payload.get("sampleKind"))
        sample_index = _optional_int(payload.get("sampleIndex"))
        sample_count = _optional_int(payload.get("sampleCount"))
        experiment_mode = _optional_string(payload.get("experimentMode"))
        pin_sequence_id = _optional_string(payload.get("pinSequenceId"))
        pin_sequence = _optional_string(payload.get("pinSequence"))
        digit = _optional_string(payload.get("digit"))
        digit_index = _optional_int(payload.get("digitIndex"))
        keypad_button_id = _optional_string(payload.get("keypadButtonId"))
        keypad_action = _optional_string(payload.get("keypadAction"))
        expected_pin = _optional_string(payload.get("expectedPin"))
        entered_pin_so_far = _optional_string(payload.get("enteredPinSoFar"))
        is_pin_submit = _optional_bool(payload.get("isPinSubmit"))
        is_pin_clear = _optional_bool(payload.get("isPinClear"))
        button_frame_x = _optional_float(payload.get("buttonFrameX"))
        button_frame_y = _optional_float(payload.get("buttonFrameY"))
        button_frame_width = _optional_float(payload.get("buttonFrameWidth"))
        button_frame_height = _optional_float(payload.get("buttonFrameHeight"))

        if message_type == TelemetryMessageType.TOUCH_EVENT:
            missing = [name for name, value in {
                "touchId": touch_id,
                "phase": phase,
                "x": x,
                "y": y,
                "maximumPossibleForce": maximum_possible_force,
                "majorRadius": major_radius,
            }.items() if value is None]
            if missing:
                raise TelemetryMessageValidationError(f"Missing touch_event fields: {', '.join(missing)}")

        return cls(
            message_type=message_type,
            session_id=session_id,
            new_session_id=_optional_string(payload.get("newSessionId")),
            reason=_optional_string(payload.get("reason")),
            timestamp=timestamp,
            device_type=device_type,
            export_expected=export_expected,
            touch_id=touch_id,
            phase=phase,
            x=x,
            y=y,
            force=force,
            maximum_possible_force=maximum_possible_force,
            major_radius=major_radius,
            altitude_angle=altitude_angle,
            azimuth_angle=azimuth_angle,
            coalesced_count=coalesced_count,
            predicted_count=predicted_count,
            input_type=input_type,
            sample_kind=sample_kind,
            sample_index=sample_index,
            sample_count=sample_count,
            experiment_mode=experiment_mode,
            pin_sequence_id=pin_sequence_id,
            pin_sequence=pin_sequence,
            digit=digit,
            digit_index=digit_index,
            keypad_button_id=keypad_button_id,
            keypad_action=keypad_action,
            expected_pin=expected_pin,
            entered_pin_so_far=entered_pin_so_far,
            is_pin_submit=is_pin_submit,
            is_pin_clear=is_pin_clear,
            button_frame_x=button_frame_x,
            button_frame_y=button_frame_y,
            button_frame_width=button_frame_width,
            button_frame_height=button_frame_height,
            payload=dict(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.payload)
        payload.update(
            {
                "messageType": self.message_type,
                "sessionId": self.session_id,
                "newSessionId": self.new_session_id,
                "reason": self.reason,
                "timestamp": self.timestamp,
                "deviceType": self.device_type,
                "exportExpected": self.export_expected,
                "touchId": self.touch_id,
                "phase": self.phase,
                "x": self.x,
                "y": self.y,
                "force": self.force,
                "maximumPossibleForce": self.maximum_possible_force,
                "majorRadius": self.major_radius,
                "altitudeAngle": self.altitude_angle,
                "azimuthAngle": self.azimuth_angle,
                "coalescedCount": self.coalesced_count,
                "predictedCount": self.predicted_count,
                "inputType": self.input_type,
                "sampleKind": self.sample_kind,
                "sampleIndex": self.sample_index,
                "sampleCount": self.sample_count,
                "experimentMode": self.experiment_mode,
                "pinSequenceId": self.pin_sequence_id,
                "pinSequence": self.pin_sequence,
                "digit": self.digit,
                "digitIndex": self.digit_index,
                "keypadButtonId": self.keypad_button_id,
                "keypadAction": self.keypad_action,
                "expectedPin": self.expected_pin,
                "enteredPinSoFar": self.entered_pin_so_far,
                "isPinSubmit": self.is_pin_submit,
                "isPinClear": self.is_pin_clear,
                "buttonFrameX": self.button_frame_x,
                "buttonFrameY": self.button_frame_y,
                "buttonFrameWidth": self.button_frame_width,
                "buttonFrameHeight": self.button_frame_height,
            }
        )
        return payload


@dataclass(slots=True)
class TelemetrySessionState:
    session_id: str
    device_type: str = "unknown"
    input_type: str = "unknown"
    export_expected: bool = False
    status: str = "live_only"
    started_at: float | None = None
    ended_at: float | None = None
    last_event_timestamp: float | None = None
    last_received_at: float | None = None
    event_count: int = 0
    touch_count: int = 0
    tap_count: int = 0
    marker_count: int = 0
    out_of_order_count: int = 0
    possible_drop_count: int = 0
    warnings: list[str] = field(default_factory=list)
    export_mismatch_reasons: list[str] = field(default_factory=list)
    export_summary: dict[str, Any] = field(default_factory=dict)
    events: list[TelemetryMessage] = field(default_factory=list)

    def append(self, message: TelemetryMessage, received_at: float) -> None:
        if self.started_at is None:
            self.started_at = message.timestamp
        self.last_received_at = received_at
        self.device_type = message.device_type or self.device_type
        self.input_type = message.input_type or self.input_type
        self.export_expected = self.export_expected or message.export_expected
        if message.message_type == TelemetryMessageType.SESSION_END:
            self.ended_at = message.timestamp
            self.export_expected = message.export_expected
            self.status = "export_expected" if message.export_expected else "live_only"
        elif message.message_type == TelemetryMessageType.SESSION_START:
            self.status = "live_only"

        if message.message_type == TelemetryMessageType.TOUCH_EVENT:
            self.event_count += 1
            self.touch_count = len({event.touch_id for event in self.events if event.touch_id})
            if message.phase == "began":
                self.tap_count += 1
            if message.experiment_mode == "pin_entry" and message.keypad_action == "submit":
                self.marker_count += 1
            if self.last_event_timestamp is not None:
                delta = message.timestamp - self.last_event_timestamp
                if delta < -1e-9:
                    self.out_of_order_count += 1
                    self.warnings.append(
                        f"Out-of-order timestamp detected: {message.timestamp:.6f} < {self.last_event_timestamp:.6f}"
                    )
                elif delta > 0.5:
                    self.possible_drop_count += 1
                    self.warnings.append(
                        f"Timestamp gap detected: {delta:.6f}s for session {self.session_id}"
                    )
            self.last_event_timestamp = message.timestamp

        self.events.append(message)

    @property
    def unique_touch_count(self) -> int:
        return len({event.touch_id for event in self.events if event.touch_id})

    @property
    def duration_seconds(self) -> float:
        timestamps = [event.timestamp for event in self.events if event.message_type == TelemetryMessageType.TOUCH_EVENT]
        if len(timestamps) < 2:
            return 0.0
        return max(timestamps) - min(timestamps)

    @property
    def sample_rate_hz(self) -> float:
        duration = self.duration_seconds
        if duration <= 0.0:
            return float(self.event_count)
        return self.event_count / duration

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "deviceType": self.device_type,
            "inputType": self.input_type,
            "exportExpected": self.export_expected,
            "status": self.status,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "lastEventTimestamp": self.last_event_timestamp,
            "eventCount": self.event_count,
            "touchCount": self.unique_touch_count,
            "tapCount": self.tap_count,
            "markerCount": self.marker_count,
            "sampleRateHz": self.sample_rate_hz,
            "outOfOrderCount": self.out_of_order_count,
            "possibleDropCount": self.possible_drop_count,
            "warnings": list(self.warnings[-10:]),
            "exportMismatchReasons": list(self.export_mismatch_reasons),
            "exportSummary": dict(self.export_summary),
            "events": [event.to_dict() for event in self.events[-200:]],
        }


@dataclass(slots=True)
class TelemetrySnapshot:
    connection_status: str
    server_state: str
    host: str
    port: int
    suggested_lan_ip: str
    active_session_id: str | None
    event_count: int
    touch_count: int
    tap_count: int
    marker_count: int
    sample_rate_hz: float
    last_event_timestamp: float | None
    last_error: str | None
    dropped_messages: int
    malformed_messages: int
    export_status: str
    export_summary: dict[str, Any]
    warnings: list[str]
    control_message: str | None
    sessions: list[dict[str, Any]]


class _TelemetryTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_class: type[socketserver.StreamRequestHandler], manager: "LiveTelemetryServer"):
        super().__init__(server_address, handler_class)
        self.manager = manager


class _TelemetryRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.server.manager._connection_opened(self.client_address)  # type: ignore[attr-defined]
        try:
            for raw_line in self.rfile:
                if not raw_line:
                    continue
                response = self.server.manager.ingest_raw_line(raw_line.decode("utf-8", errors="ignore"), self.client_address)  # type: ignore[attr-defined]
                if response is not None:
                    self.wfile.write(response.encode("utf-8") + b"\n")
                    self.wfile.flush()
        finally:
            self.server.manager._connection_closed(self.client_address)  # type: ignore[attr-defined]


class LiveTelemetryServer:
    def __init__(self, paths: TouchprintPaths, host: str = "0.0.0.0", port: int = 8765, max_sessions: int = 50):
        self.paths = paths
        self.host = host
        self.port = port
        self.max_sessions = max_sessions
        self._lock = threading.RLock()
        self._server: _TelemetryTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._connection_count = 0
        self._active_connections = 0
        self._malformed_messages = 0
        self._dropped_messages = 0
        self._last_error: str | None = None
        self._last_control_message: str | None = None
        self._last_control_message_at: float | None = None
        self._sessions: dict[str, TelemetrySessionState] = {}
        self._session_order: list[str] = []
        self.paths.processed.mkdir(parents=True, exist_ok=True)

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return True
            try:
                self._server = _TelemetryTCPServer((self.host, self.port), _TelemetryRequestHandler, self)
            except OSError as exc:
                self._last_error = str(exc)
                logger.exception("Failed to start live telemetry server")
                return False
            self.host, self.port = self._server.server_address
            self._running = True
            self._thread = threading.Thread(target=self._server.serve_forever, name="LiveTelemetryServer", daemon=True)
            self._thread.start()
            logger.info("Live telemetry server listening on %s:%s", self.host, self.port)
            return True

    def stop(self) -> None:
        with self._lock:
            if self._server is None:
                self._running = False
                return
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def ingest_raw_line(self, raw_line: str, remote_address: tuple[str, int] | None = None) -> str | None:
        try:
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise TelemetryMessageValidationError("Telemetry payload must be a JSON object")
            message = TelemetryMessage.from_payload(payload)
        except Exception as exc:
            with self._lock:
                self._malformed_messages += 1
                self._last_error = str(exc)
            logger.warning("Rejected telemetry payload from %s: %s", remote_address, exc)
            return None

        if message.message_type == TelemetryMessageType.PING:
            response = {
                "messageType": "pong",
                "serverTime": time.time(),
                "serverState": "running" if self._running else "stopped",
                "host": self.host,
                "port": self.port,
            }
            return json.dumps(response, sort_keys=True)

        self.ingest_message(message)
        return None

    def ingest_message(self, message: TelemetryMessage) -> None:
        received_at = time.time()
        with self._lock:
            if message.message_type == TelemetryMessageType.RESET:
                self._handle_reset(message, received_at)
                self._last_error = None
                return

            state = self._sessions.get(message.session_id)
            if state is None:
                state = TelemetrySessionState(session_id=message.session_id)
                self._sessions[message.session_id] = state
                self._session_order.append(message.session_id)
                while len(self._session_order) > self.max_sessions:
                    removed_session_id = self._session_order.pop(0)
                    self._sessions.pop(removed_session_id, None)

            state.append(message, received_at)
            self._last_error = None
            if message.message_type == TelemetryMessageType.SESSION_END and message.export_expected:
                state.status = "export_expected"

    def _handle_reset(self, message: TelemetryMessage, received_at: float) -> None:
        old_session_id = message.session_id
        new_session_id = message.new_session_id or message.session_id
        old_state = self._sessions.get(old_session_id)
        if old_state is not None:
            old_state.status = "reset_pending"
            old_state.export_expected = False
            old_state.ended_at = message.timestamp
            old_state.last_received_at = received_at

        if new_session_id == old_session_id and old_state is not None:
            new_state = old_state
            new_state.events.clear()
            new_state.event_count = 0
            new_state.touch_count = 0
            new_state.tap_count = 0
            new_state.marker_count = 0
            new_state.out_of_order_count = 0
            new_state.possible_drop_count = 0
            new_state.warnings.clear()
            new_state.export_mismatch_reasons.clear()
            new_state.export_summary = {}
            new_state.last_event_timestamp = None
            new_state.started_at = message.timestamp
            new_state.ended_at = None
            new_state.status = "live_only"
            new_state.export_expected = False
            new_state.device_type = message.device_type or new_state.device_type
            new_state.input_type = message.input_type or new_state.input_type
            new_state.last_received_at = received_at
        else:
            new_state = TelemetrySessionState(
                session_id=new_session_id,
                device_type=message.device_type or "unknown",
                input_type=message.input_type or "unknown",
                export_expected=False,
                status="live_only",
                started_at=message.timestamp,
                last_received_at=received_at,
            )
            self._sessions[new_session_id] = new_state
            self._session_order.append(new_session_id)
            while len(self._session_order) > self.max_sessions:
                removed_session_id = self._session_order.pop(0)
                self._sessions.pop(removed_session_id, None)

        self._last_control_message = f"Live session reset → {self._short_session_id(new_session_id)}"
        self._last_control_message_at = received_at

    def observe_export(self, session: TouchSessionRecord) -> dict[str, Any]:
        with self._lock:
            state = self._sessions.get(session.session_id)
            if state is None:
                result = {
                    "sessionId": session.session_id,
                    "status": "export_only",
                    "reasons": ["No matching live session was found."],
                }
                return result

            export_payload = session.to_dict()
            live_event_count = state.event_count
            export_event_count = len(export_payload.get("events", []))
            live_touch_count = state.unique_touch_count
            export_touch_count = len({str(event.get("touchId")) for event in export_payload.get("events", []) if event.get("touchId")})
            live_timestamps = [float(event.timestamp) for event in state.events if event.message_type == TelemetryMessageType.TOUCH_EVENT]
            export_timestamps = [float(event.get("timestamp", 0.0)) for event in export_payload.get("events", [])]
            live_start = min(live_timestamps) if live_timestamps else None
            live_end = max(live_timestamps) if live_timestamps else None
            export_start = min(export_timestamps) if export_timestamps else None
            export_end = max(export_timestamps) if export_timestamps else None

            reasons: list[str] = []
            if live_event_count != export_event_count:
                reasons.append(f"event count mismatch: live={live_event_count} export={export_event_count}")
            if live_touch_count != export_touch_count:
                reasons.append(f"touch count mismatch: live={live_touch_count} export={export_touch_count}")
            if (live_start is not None and export_start is not None) and abs(live_start - export_start) > 1e-6:
                reasons.append(f"timestamp range start mismatch: live={live_start:.6f} export={export_start:.6f}")
            if (live_end is not None and export_end is not None) and abs(live_end - export_end) > 1e-6:
                reasons.append(f"timestamp range end mismatch: live={live_end:.6f} export={export_end:.6f}")
            if state.device_type != str(export_payload.get("deviceType", state.device_type)):
                reasons.append(f"device type mismatch: live={state.device_type} export={export_payload.get('deviceType')}")

            if reasons:
                state.status = "export_mismatch"
                state.export_mismatch_reasons = reasons
            else:
                state.status = "export_verified"
                state.export_mismatch_reasons = []

            state.export_summary = {
                "exportStatus": state.status,
                "liveEventCount": live_event_count,
                "exportEventCount": export_event_count,
                "liveTouchCount": live_touch_count,
                "exportTouchCount": export_touch_count,
                "liveTimestampRange": [live_start, live_end],
                "exportTimestampRange": [export_start, export_end],
                "deviceType": state.device_type,
                "reasons": list(state.export_mismatch_reasons),
            }
            return dict(state.export_summary)

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            active_state = self._active_state()
            control_message = None
            if self._last_control_message_at is not None and time.time() - self._last_control_message_at <= 3.0:
                control_message = self._last_control_message
            return TelemetrySnapshot(
                connection_status=self.connection_status,
                server_state="running" if self._running else "stopped",
                host=self.host,
                port=self.port,
                suggested_lan_ip=_suggested_lan_ip(),
                active_session_id=active_state.session_id if active_state else None,
                event_count=active_state.event_count if active_state else 0,
                touch_count=active_state.unique_touch_count if active_state else 0,
                tap_count=active_state.tap_count if active_state else 0,
                marker_count=active_state.marker_count if active_state else 0,
                sample_rate_hz=active_state.sample_rate_hz if active_state else 0.0,
                last_event_timestamp=active_state.last_event_timestamp if active_state else None,
                last_error=self._last_error,
                dropped_messages=self._dropped_messages,
                malformed_messages=self._malformed_messages,
                export_status=active_state.status if active_state else "live_only",
                export_summary=dict(active_state.export_summary) if active_state else {},
                warnings=list(active_state.warnings[-10:]) if active_state else [],
                control_message=control_message,
                sessions=[self._sessions[session_id].to_snapshot() for session_id in self._session_order if session_id in self._sessions],
            )

    @property
    def connection_status(self) -> str:
        if not self._running:
            return "disconnected"
        if self._active_connections > 0:
            return "connected"
        return "listening"

    def _active_state(self) -> TelemetrySessionState | None:
        if not self._session_order:
            return None
        return self._sessions.get(self._session_order[-1])

    def _connection_opened(self, remote_address: tuple[str, int]) -> None:
        with self._lock:
            self._connection_count += 1
            self._active_connections += 1
        logger.info("Live telemetry client connected: %s", remote_address)

    def _connection_closed(self, remote_address: tuple[str, int]) -> None:
        with self._lock:
            self._active_connections = max(0, self._active_connections - 1)
        logger.info("Live telemetry client disconnected: %s", remote_address)

    @staticmethod
    def _short_session_id(session_id: str | None) -> str:
        if not session_id:
            return "—"
        if len(session_id) <= 8:
            return session_id
        return f"{session_id[:4]}…{session_id[-4:]}"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryMessageValidationError(f"Invalid float value: {value!r}") from exc


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryMessageValidationError(f"Invalid integer value: {value!r}") from exc


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise TelemetryMessageValidationError(f"Invalid boolean value: {value!r}")


def _coerce_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryMessageValidationError(f"Invalid {field_name}: {value!r}") from exc


def _suggested_lan_ip() -> str:
    for endpoint in [("8.8.8.8", 80), ("1.1.1.1", 80)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                udp_socket.connect(endpoint)
                local_ip = udp_socket.getsockname()[0]
                if local_ip and not local_ip.startswith("127."):
                    return local_ip
        except OSError:
            continue

    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip and not local_ip.startswith("127."):
            return local_ip
    except OSError:
        pass

    return "unavailable"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Touchprint live telemetry server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    paths = TouchprintPaths.create_default()
    paths.ensure_directories()
    server = LiveTelemetryServer(paths, host=args.host, port=args.port)
    if not server.start():
        raise SystemExit(1)

    logger.info("Press Ctrl+C to stop the live telemetry server.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
