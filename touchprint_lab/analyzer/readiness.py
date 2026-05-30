from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from touchprint_lab.live.telemetry_server import TelemetrySnapshot
from touchprint_lab.utils.paths import TouchprintPaths


@dataclass(slots=True)
class ReadinessCheckResult:
    key: str
    label: str
    passed: bool
    detail: str


@dataclass(slots=True)
class ReadinessReport:
    generated_at: str
    active_session_id: str | None
    checks: list[ReadinessCheckResult]
    overall_passed: bool
    report_json_path: Path
    report_md_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "generatedAt": self.generated_at,
            "activeSessionId": self.active_session_id,
            "overallPassed": self.overall_passed,
            "checks": [
                {
                    "key": row.key,
                    "label": row.label,
                    "passed": row.passed,
                    "detail": row.detail,
                }
                for row in self.checks
            ],
            "files": {
                "json": str(self.report_json_path),
                "markdown": str(self.report_md_path),
            },
        }


def run_system_readiness_check(paths: TouchprintPaths, snapshot: TelemetrySnapshot) -> ReadinessReport:
    active_session_id = snapshot.active_session_id
    active_session = next((row for row in snapshot.sessions if row.get("sessionId") == active_session_id), None)
    events = list((active_session or {}).get("events", []))

    checks: list[ReadinessCheckResult] = []
    checks.append(
        ReadinessCheckResult(
            key="telemetry_server_running",
            label="Live telemetry server running",
            passed=snapshot.server_state == "running",
            detail=f"server_state={snapshot.server_state}, host={snapshot.host}, port={snapshot.port}",
        )
    )
    checks.append(
        ReadinessCheckResult(
            key="ios_device_connected",
            label="iOS device connected",
            passed=snapshot.connection_status == "connected",
            detail=f"connection_status={snapshot.connection_status}",
        )
    )
    checks.append(
        ReadinessCheckResult(
            key="events_received",
            label="Events received",
            passed=snapshot.event_count > 0,
            detail=f"event_count={snapshot.event_count}",
        )
    )
    pin_events = [
        event for event in events if event.get("digit") is not None or event.get("pinSequenceId") is not None or event.get("experimentMode") == "pin_entry"
    ]
    checks.append(
        ReadinessCheckResult(
            key="pin_metadata_received",
            label="PIN metadata received",
            passed=len(pin_events) > 0,
            detail=f"pin_event_count={len(pin_events)}",
        )
    )
    reset_seen = bool(snapshot.control_message and "reset" in snapshot.control_message.lower()) or any(
        str(session.get("status", "")).startswith("reset") for session in snapshot.sessions
    )
    checks.append(
        ReadinessCheckResult(
            key="reset_command_works",
            label="Reset command works",
            passed=reset_seen,
            detail=snapshot.control_message or "No recent reset control message detected.",
        )
    )

    export_path = _session_raw_json_path(paths, active_session_id)
    checks.append(
        ReadinessCheckResult(
            key="export_json_received",
            label="Export JSON received",
            passed=export_path is not None and export_path.exists(),
            detail=str(export_path) if export_path is not None else "No exported raw.json for active session.",
        )
    )

    export_status = str(snapshot.export_summary.get("exportStatus") or snapshot.export_status)
    export_matched = export_status in {"export_verified", "live_only", "export_expected"}
    if export_path is not None and export_path.exists():
        export_matched = export_status != "export_mismatch"
    checks.append(
        ReadinessCheckResult(
            key="export_matches_live_session",
            label="Exported session matches live sessionId",
            passed=export_matched and active_session_id is not None,
            detail=f"export_status={export_status}, session_id={active_session_id or '—'}",
        )
    )

    feature_path = paths.features / f"{active_session_id}.json" if active_session_id else None
    checks.append(
        ReadinessCheckResult(
            key="feature_vector_generated",
            label="Feature vector generated",
            passed=feature_path is not None and feature_path.exists(),
            detail=str(feature_path) if feature_path is not None else "No active session to check features for.",
        )
    )

    report_dir = paths.reports / "system_readiness"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_probe_path = report_dir / "readiness_probe.txt"
    try:
        report_probe_path.write_text("ok\n", encoding="utf-8")
        report_export_ok = True
        report_export_detail = str(report_probe_path)
    except Exception as error:  # pragma: no cover
        report_export_ok = False
        report_export_detail = str(error)
    checks.append(
        ReadinessCheckResult(
            key="report_export_works",
            label="Report export works",
            passed=report_export_ok,
            detail=report_export_detail,
        )
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    overall = all(row.passed for row in checks)
    report_json_path = report_dir / "readiness_report.json"
    report_md_path = report_dir / "readiness_report.md"
    report = ReadinessReport(
        generated_at=generated_at,
        active_session_id=active_session_id,
        checks=checks,
        overall_passed=overall,
        report_json_path=report_json_path,
        report_md_path=report_md_path,
    )
    _write_report_files(report)
    return report


def _session_raw_json_path(paths: TouchprintPaths, session_id: str | None) -> Path | None:
    if not session_id:
        return None
    for path in paths.dataset.glob(f"*/session_{session_id}/raw.json"):
        return path
    return None


def _write_report_files(report: ReadinessReport) -> None:
    payload = report.to_dict()
    report.report_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# System Readiness Report",
        "",
        f"- Generated At: `{report.generated_at}`",
        f"- Active Session: `{report.active_session_id or '—'}`",
        f"- Overall: `{'PASS' if report.overall_passed else 'FAIL'}`",
        "",
        "## Checklist",
    ]
    for row in report.checks:
        badge = "PASS" if row.passed else "FAIL"
        lines.append(f"- [{badge}] **{row.label}** — {row.detail}")
    lines.append("")
    report.report_md_path.write_text("\n".join(lines), encoding="utf-8")

