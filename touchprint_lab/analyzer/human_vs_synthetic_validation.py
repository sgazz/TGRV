from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.human_likeness import compute_human_likeness_metrics
from touchprint_lab.analyzer.human_likeness_calibration import generate_calibration_scenarios
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.utils.paths import TouchprintPaths

try:  # pragma: no cover - optional plotting dependency
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None  # type: ignore


@dataclass(slots=True)
class ValidationFilters:
    participant_id: str | None = None
    device_type: str | None = None
    input_type: str | None = None
    started_after: float | None = None
    started_before: float | None = None

    @classmethod
    def from_values(
        cls,
        *,
        participant_id: str | None = None,
        device_type: str | None = None,
        input_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> "ValidationFilters":
        return cls(
            participant_id=_optional_str(participant_id),
            device_type=_optional_str(device_type),
            input_type=_normalize_input_type(input_type),
            started_after=_parse_date_floor(date_from),
            started_before=_parse_date_ceil(date_to),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "participantId": self.participant_id,
            "deviceType": self.device_type,
            "inputType": self.input_type,
            "startedAfter": self.started_after,
            "startedBefore": self.started_before,
        }


@dataclass(slots=True)
class ValidationRow:
    source_type: str
    sample_id: str
    label: str
    class_label: str
    human_likeness_score: float | None
    automation_suspicion_score: float | None
    confidence: str
    suspicious_flags: list[str]
    timing_naturalness: float | None
    jitter_naturalness: float | None
    pressure_naturalness: float | None
    release_dynamics: float | None
    repetition_diversity: float | None
    signal_quality: float | None

    def to_row(self) -> dict[str, Any]:
        return {
            "sourceType": self.source_type,
            "sampleId": self.sample_id,
            "label": self.label,
            "classLabel": self.class_label,
            "humanLikenessScore": self.human_likeness_score,
            "automationSuspicionScore": self.automation_suspicion_score,
            "confidence": self.confidence,
            "suspiciousFlags": "; ".join(self.suspicious_flags),
            "timingNaturalness": self.timing_naturalness,
            "jitterNaturalness": self.jitter_naturalness,
            "pressureNaturalness": self.pressure_naturalness,
            "releaseDynamics": self.release_dynamics,
            "repetitionDiversity": self.repetition_diversity,
            "signalQuality": self.signal_quality,
        }


@dataclass(slots=True)
class HumanVsSyntheticValidationReport:
    rows: list[ValidationRow]
    summary: dict[str, Any]
    output_dir: Path
    files: dict[str, str] = field(default_factory=dict)


def run_human_vs_synthetic_validation(
    *,
    paths: TouchprintPaths | None = None,
    filters: ValidationFilters | None = None,
    output_dir: Path | None = None,
    synthetic_seed: int = 42,
    suspicious_threshold: float = 60.0,
) -> HumanVsSyntheticValidationReport:
    paths = paths or TouchprintPaths.create_default()
    paths.ensure_directories()
    filters = filters or ValidationFilters()
    manager = DatasetManager(paths)

    real_sessions = _load_real_pin_sessions(manager, filters)
    synthetic_rows = _build_synthetic_rows(seed=synthetic_seed)
    real_rows = _build_real_rows(real_sessions)

    rows = real_rows + synthetic_rows
    summary = _build_summary(rows, filters=filters, suspicious_threshold=suspicious_threshold)

    if output_dir is None:
        output_dir = paths.reports / "human_vs_synthetic_validation"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = HumanVsSyntheticValidationReport(rows=rows, summary=summary, output_dir=output_dir)
    _export_report(report)
    return report


def _load_real_pin_sessions(manager: DatasetManager, filters: ValidationFilters) -> list[TouchSessionRecord]:
    sessions = manager.load_all_sessions()
    filtered: list[TouchSessionRecord] = []
    for session in sessions:
        if not _is_pin_entry_session(session):
            continue
        if filters.participant_id and session.participant_id != filters.participant_id:
            continue
        if filters.device_type and session.device_type != filters.device_type:
            continue
        if filters.input_type and session.resolved_input_type() != filters.input_type:
            continue
        if filters.started_after is not None and session.started_at < filters.started_after:
            continue
        if filters.started_before is not None and session.started_at > filters.started_before:
            continue
        filtered.append(session)
    return filtered


def _build_real_rows(sessions: list[TouchSessionRecord]) -> list[ValidationRow]:
    rows: list[ValidationRow] = []
    for session in sessions:
        metrics = compute_human_likeness_metrics([event.to_dict() for event in session.events])
        rows.append(
            ValidationRow(
                source_type="real_human",
                sample_id=session.session_id,
                label=f"Real PIN session {session.session_id}",
                class_label="real_human",
                human_likeness_score=metrics.human_likeness_score,
                automation_suspicion_score=metrics.automation_suspicion_score,
                confidence=metrics.confidence,
                suspicious_flags=list(metrics.suspicious_flags),
                timing_naturalness=metrics.timing_naturalness,
                jitter_naturalness=metrics.jitter_naturalness,
                pressure_naturalness=metrics.pressure_naturalness,
                release_dynamics=metrics.release_dynamics,
                repetition_diversity=metrics.repetition_diversity,
                signal_quality=metrics.signal_quality,
            )
        )
    return rows


def _build_synthetic_rows(seed: int) -> list[ValidationRow]:
    rows: list[ValidationRow] = []
    for scenario in generate_calibration_scenarios(seed=seed):
        metrics = compute_human_likeness_metrics(scenario.events)
        class_label = (
            "synthetic_human_like"
            if scenario.expected_type == "human_like_simulated"
            else "synthetic_machine_like"
        )
        rows.append(
            ValidationRow(
                source_type="synthetic",
                sample_id=scenario.scenario_id,
                label=scenario.label,
                class_label=class_label,
                human_likeness_score=metrics.human_likeness_score,
                automation_suspicion_score=metrics.automation_suspicion_score,
                confidence=metrics.confidence,
                suspicious_flags=list(metrics.suspicious_flags),
                timing_naturalness=metrics.timing_naturalness,
                jitter_naturalness=metrics.jitter_naturalness,
                pressure_naturalness=metrics.pressure_naturalness,
                release_dynamics=metrics.release_dynamics,
                repetition_diversity=metrics.repetition_diversity,
                signal_quality=metrics.signal_quality,
            )
        )
    return rows


def _build_summary(rows: list[ValidationRow], *, filters: ValidationFilters, suspicious_threshold: float) -> dict[str, Any]:
    real_rows = [row for row in rows if row.class_label == "real_human"]
    synthetic_machine_rows = [row for row in rows if row.class_label == "synthetic_machine_like"]
    synthetic_human_like_rows = [row for row in rows if row.class_label == "synthetic_human_like"]

    real_scores = _scores(real_rows, "human_likeness_score")
    synthetic_scores = _scores(synthetic_machine_rows, "human_likeness_score")
    synthetic_human_like_scores = _scores(synthetic_human_like_rows, "human_likeness_score")

    false_suspicious_count = sum(1 for row in real_rows if _is_suspicious(row, suspicious_threshold))
    suspicious_detected_count = sum(1 for row in synthetic_machine_rows if _is_suspicious(row, suspicious_threshold))
    false_suspicious_rate = (
        float(false_suspicious_count / len(real_rows)) if real_rows else 0.0
    )
    suspicious_detection_rate = (
        float(suspicious_detected_count / len(synthetic_machine_rows)) if synthetic_machine_rows else 0.0
    )

    no_real_sessions = len(real_rows) == 0
    message = (
        "No real PIN sessions found. Run PIN Keypad study first."
        if no_real_sessions
        else "Validation completed. This is a research validation metric, not identity proof."
    )

    return {
        "filters": filters.to_dict(),
        "realSessionCount": len(real_rows),
        "syntheticSessionCount": len([row for row in rows if row.source_type == "synthetic"]),
        "realHumanAverageScore": _mean_or_zero(real_scores),
        "syntheticAverageScore": _mean_or_zero(synthetic_scores),
        "syntheticHumanLikeAverageScore": _mean_or_zero(synthetic_human_like_scores),
        "separationMargin": _mean_or_zero(real_scores) - _mean_or_zero(synthetic_scores),
        "falseSuspiciousRate": false_suspicious_rate,
        "suspiciousDetectionRate": suspicious_detection_rate,
        "falseSuspiciousCount": false_suspicious_count,
        "suspiciousDetectedCount": suspicious_detected_count,
        "noRealSessions": no_real_sessions,
        "message": message,
        "scientificLabeling": (
            "This is not proof of human identity. "
            "It is a research validation of score behavior and requires larger real datasets."
        ),
    }


def _export_report(report: HumanVsSyntheticValidationReport) -> None:
    summary_path = report.output_dir / "validation_summary.json"
    csv_path = report.output_dir / "validation_results.csv"
    markdown_path = report.output_dir / "validation_report.md"
    score_plot_path = report.output_dir / "human_vs_synthetic_scores.png"
    suspicion_plot_path = report.output_dir / "suspicion_comparison.png"

    summary_payload = {
        "summary": report.summary,
        "rows": [row.to_row() for row in report.rows],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(csv_path, report.rows)
    markdown_path.write_text(_build_markdown(report), encoding="utf-8")
    _render_score_plot(report, score_plot_path)
    _render_suspicion_plot(report, suspicion_plot_path)

    report.files = {
        "summaryJson": str(summary_path),
        "resultsCsv": str(csv_path),
        "markdownReport": str(markdown_path),
        "scoresPlotPng": str(score_plot_path),
        "suspicionPlotPng": str(suspicion_plot_path),
    }


def _write_csv(path: Path, rows: list[ValidationRow]) -> None:
    field_names = [
        "sourceType",
        "sampleId",
        "label",
        "classLabel",
        "humanLikenessScore",
        "automationSuspicionScore",
        "confidence",
        "suspiciousFlags",
        "timingNaturalness",
        "jitterNaturalness",
        "pressureNaturalness",
        "releaseDynamics",
        "repetitionDiversity",
        "signalQuality",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())


def _build_markdown(report: HumanVsSyntheticValidationReport) -> str:
    summary = report.summary
    lines = [
        "# Human vs Synthetic Validation Report",
        "",
        "Research validation only. Not authentication logic and not proof of identity.",
        "",
        "## Summary",
        f"- Real PIN Sessions: `{summary['realSessionCount']}`",
        f"- Synthetic Sessions: `{summary['syntheticSessionCount']}`",
        f"- Real Human Avg Score: `{summary['realHumanAverageScore']:.2f}`",
        f"- Synthetic Avg Score: `{summary['syntheticAverageScore']:.2f}`",
        f"- Separation Margin: `{summary['separationMargin']:.2f}`",
        f"- False Suspicious Rate: `{summary['falseSuspiciousRate']:.2%}`",
        f"- Suspicious Detection Rate: `{summary['suspiciousDetectionRate']:.2%}`",
        "",
        f"> {summary['message']}",
        "",
        f"> {summary['scientificLabeling']}",
        "",
        "## Samples",
    ]
    for row in report.rows:
        lines.append(
            f"- `{row.sample_id}` [{row.class_label}] score={_fmt(row.human_likeness_score)} "
            f"suspicion={_fmt(row.automation_suspicion_score)} "
            f"flags={', '.join(row.suspicious_flags[:3]) if row.suspicious_flags else 'none'}"
        )
    lines.append("")
    return "\n".join(lines)


def _render_score_plot(report: HumanVsSyntheticValidationReport, output_path: Path) -> None:
    if plt is None:  # pragma: no cover
        output_path.write_bytes(b"")
        return

    groups: dict[str, list[float]] = {
        "real_human": _scores([row for row in report.rows if row.class_label == "real_human"], "human_likeness_score"),
        "synthetic_machine_like": _scores([row for row in report.rows if row.class_label == "synthetic_machine_like"], "human_likeness_score"),
        "synthetic_human_like": _scores([row for row in report.rows if row.class_label == "synthetic_human_like"], "human_likeness_score"),
    }
    _render_histogram(
        groups=groups,
        output_path=output_path,
        title="Human vs Synthetic Score Distribution",
        xlabel="Human-Likeness Score",
    )


def _render_suspicion_plot(report: HumanVsSyntheticValidationReport, output_path: Path) -> None:
    if plt is None:  # pragma: no cover
        output_path.write_bytes(b"")
        return

    groups: dict[str, list[float]] = {
        "real_human": _scores([row for row in report.rows if row.class_label == "real_human"], "automation_suspicion_score"),
        "synthetic_machine_like": _scores([row for row in report.rows if row.class_label == "synthetic_machine_like"], "automation_suspicion_score"),
        "synthetic_human_like": _scores([row for row in report.rows if row.class_label == "synthetic_human_like"], "automation_suspicion_score"),
    }
    _render_histogram(
        groups=groups,
        output_path=output_path,
        title="Automation Suspicion Comparison",
        xlabel="Automation Suspicion Score",
    )


def _render_histogram(*, groups: dict[str, list[float]], output_path: Path, title: str, xlabel: str) -> None:
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("Count")
    bins = np.linspace(0.0, 100.0, 21)
    palette = {
        "real_human": "#34c759",
        "synthetic_machine_like": "#ff453a",
        "synthetic_human_like": "#5ac8fa",
    }
    for key in ["real_human", "synthetic_machine_like", "synthetic_human_like"]:
        values = groups.get(key, [])
        if not values:
            continue
        axis.hist(
            values,
            bins=bins,
            alpha=0.55,
            label=key,
            color=palette.get(key, "#8e8e93"),
            edgecolor="#101014",
        )
    axis.grid(True, alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _scores(rows: list[ValidationRow], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = getattr(row, field)
        if value is None:
            continue
        values.append(float(value))
    return values


def _mean_or_zero(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _is_suspicious(row: ValidationRow, threshold: float) -> bool:
    return (row.automation_suspicion_score or 0.0) >= threshold or len(row.suspicious_flags) > 0


def _is_pin_entry_session(session: TouchSessionRecord) -> bool:
    if session.session_type == "pin_entry":
        return True
    for event in session.events:
        if event.experiment_mode == "pin_entry":
            return True
        if event.digit is not None:
            return True
    return False


def _parse_date_floor(value: str | None) -> float | None:
    text = _optional_str(value)
    if text is None:
        return None
    if _looks_like_number(text):
        return float(text)
    try:
        day = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return day.timestamp()


def _parse_date_ceil(value: str | None) -> float | None:
    text = _optional_str(value)
    if text is None:
        return None
    if _looks_like_number(text):
        return float(text)
    try:
        day = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (day.replace(hour=23, minute=59, second=59, microsecond=999999)).timestamp()


def _looks_like_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_input_type(value: str | None) -> str | None:
    raw = _optional_str(value)
    if raw is None:
        return None
    normalized = raw.lower()
    if normalized in {"finger", "pencil", "mixed"}:
        return normalized
    if normalized in {"indirect", "indirectpointer"}:
        return "mixed"
    return normalized


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
