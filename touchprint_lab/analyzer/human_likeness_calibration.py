from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from touchprint_lab.analyzer.human_likeness import HumanLikenessMetrics, compute_human_likeness_metrics
from touchprint_lab.utils.paths import TouchprintPaths

try:  # pragma: no cover - optional plotting dependency
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None  # type: ignore
    PdfPages = None  # type: ignore
else:  # pragma: no cover - optional plotting dependency
    from matplotlib.backends.backend_pdf import PdfPages

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CalibrationScenario:
    scenario_id: str
    label: str
    expected_type: str
    events: list[dict[str, Any]]


@dataclass(slots=True)
class CalibrationScenarioResult:
    scenario_id: str
    label: str
    expected_type: str
    human_likeness_score: float | None
    automation_suspicion_score: float | None
    confidence: str
    timing_naturalness: float | None
    jitter_naturalness: float | None
    pressure_naturalness: float | None
    release_dynamics: float | None
    repetition_diversity: float | None
    signal_quality: float | None
    suspicious_flags: list[str]
    explanation_flags: list[str]

    def to_row(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenario_id,
            "label": self.label,
            "expectedType": self.expected_type,
            "humanLikenessScore": self.human_likeness_score,
            "automationSuspicionScore": self.automation_suspicion_score,
            "confidence": self.confidence,
            "timingNaturalness": self.timing_naturalness,
            "jitterNaturalness": self.jitter_naturalness,
            "pressureNaturalness": self.pressure_naturalness,
            "releaseDynamics": self.release_dynamics,
            "repetitionDiversity": self.repetition_diversity,
            "signalQuality": self.signal_quality,
            "suspiciousFlags": "; ".join(self.suspicious_flags),
            "explanationFlags": "; ".join(self.explanation_flags),
        }


@dataclass(slots=True)
class CalibrationReport:
    scenarios: list[CalibrationScenarioResult]
    summary: dict[str, Any]
    output_dir: Path
    files: dict[str, str] = field(default_factory=dict)


def generate_calibration_scenarios(seed: int = 42) -> list[CalibrationScenario]:
    rng = np.random.default_rng(seed)
    scenarios: list[CalibrationScenario] = [
        CalibrationScenario(
            scenario_id="synthetic_regular_perfect",
            label="Synthetic perfect regular timing",
            expected_type="synthetic_regular",
            events=_build_pin_attempts(
                scenario_id="synthetic_regular_perfect",
                attempts=4,
                base_intervals=[0.200, 0.200, 0.200],
                interval_jitter_std=0.0,
                position_jitter_std=0.0,
                force_mode="flat",
                radius_mode="flat",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="synthetic_regular_tiny_noise",
            label="Synthetic near-regular tiny noise timing",
            expected_type="synthetic_noisy",
            events=_build_pin_attempts(
                scenario_id="synthetic_regular_tiny_noise",
                attempts=4,
                base_intervals=[0.200, 0.200, 0.200],
                interval_jitter_std=0.004,
                position_jitter_std=0.08,
                force_mode="flat",
                radius_mode="flat",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="human_like_variable_timing",
            label="Human-like variable timing",
            expected_type="human_like_simulated",
            events=_build_pin_attempts(
                scenario_id="human_like_variable_timing",
                attempts=5,
                base_intervals=[0.180, 0.240, 0.165],
                interval_jitter_std=0.028,
                position_jitter_std=1.35,
                force_mode="variable",
                radius_mode="variable",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="synthetic_flat_pressure",
            label="Synthetic flat pressure",
            expected_type="synthetic_regular",
            events=_build_pin_attempts(
                scenario_id="synthetic_flat_pressure",
                attempts=4,
                base_intervals=[0.205, 0.205, 0.205],
                interval_jitter_std=0.003,
                position_jitter_std=0.2,
                force_mode="flat",
                radius_mode="variable",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="human_variable_pressure",
            label="Human-like variable pressure",
            expected_type="human_like_simulated",
            events=_build_pin_attempts(
                scenario_id="human_variable_pressure",
                attempts=5,
                base_intervals=[0.190, 0.250, 0.170],
                interval_jitter_std=0.020,
                position_jitter_std=1.1,
                force_mode="variable",
                radius_mode="variable",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="synthetic_repeated_identical_attempts",
            label="Synthetic repeated identical attempts",
            expected_type="synthetic_regular",
            events=_build_pin_attempts(
                scenario_id="synthetic_repeated_identical_attempts",
                attempts=5,
                base_intervals=[0.210, 0.210, 0.210],
                interval_jitter_std=0.0,
                position_jitter_std=0.0,
                force_mode="flat",
                radius_mode="flat",
                rng=rng,
            ),
        ),
        CalibrationScenario(
            scenario_id="human_similar_not_identical_attempts",
            label="Human-like similar but non-identical attempts",
            expected_type="human_like_simulated",
            events=_build_pin_attempts(
                scenario_id="human_similar_not_identical_attempts",
                attempts=5,
                base_intervals=[0.185, 0.230, 0.175],
                interval_jitter_std=0.018,
                position_jitter_std=0.9,
                force_mode="variable",
                radius_mode="variable",
                rng=rng,
            ),
        ),
    ]
    return scenarios


def run_human_likeness_calibration(
    *,
    output_dir: Path | None = None,
    seed: int = 42,
) -> CalibrationReport:
    scenarios = generate_calibration_scenarios(seed=seed)
    scenario_results: list[CalibrationScenarioResult] = []
    for scenario in scenarios:
        metrics = compute_human_likeness_metrics(scenario.events)
        scenario_results.append(_result_from_metrics(scenario, metrics))

    summary = _summarize_calibration(scenario_results)

    if output_dir is None:
        paths = TouchprintPaths.create_default()
        paths.ensure_directories()
        output_dir = paths.reports / "human_likeness_calibration"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = CalibrationReport(
        scenarios=scenario_results,
        summary=summary,
        output_dir=output_dir,
    )
    _export_report(report)
    return report


def _result_from_metrics(scenario: CalibrationScenario, metrics: HumanLikenessMetrics) -> CalibrationScenarioResult:
    return CalibrationScenarioResult(
        scenario_id=scenario.scenario_id,
        label=scenario.label,
        expected_type=scenario.expected_type,
        human_likeness_score=metrics.human_likeness_score,
        automation_suspicion_score=metrics.automation_suspicion_score,
        confidence=metrics.confidence,
        timing_naturalness=metrics.timing_naturalness,
        jitter_naturalness=metrics.jitter_naturalness,
        pressure_naturalness=metrics.pressure_naturalness,
        release_dynamics=metrics.release_dynamics,
        repetition_diversity=metrics.repetition_diversity,
        signal_quality=metrics.signal_quality,
        suspicious_flags=list(metrics.suspicious_flags),
        explanation_flags=list(metrics.explanation_flags),
    )


def _summarize_calibration(results: list[CalibrationScenarioResult]) -> dict[str, Any]:
    grouped_scores: dict[str, list[float]] = {}
    for row in results:
        if row.human_likeness_score is not None:
            grouped_scores.setdefault(row.expected_type, []).append(float(row.human_likeness_score))

    def average(kind: str) -> float:
        values = grouped_scores.get(kind, [])
        return float(np.mean(values)) if values else 0.0

    human_average = average("human_like_simulated")
    synthetic_regular_average = average("synthetic_regular")
    synthetic_noisy_average = average("synthetic_noisy")

    suspicious_expected = [row for row in results if row.expected_type in {"synthetic_regular", "synthetic_noisy"}]
    suspicious_detected = [
        row
        for row in suspicious_expected
        if (row.automation_suspicion_score or 0.0) >= 60.0 or len(row.suspicious_flags) > 0
    ]
    suspicious_detection_rate = (
        float(len(suspicious_detected) / len(suspicious_expected)) if suspicious_expected else 0.0
    )

    return {
        "scenarioCount": len(results),
        "averageHumanLikeScore": human_average,
        "averageSyntheticRegularScore": synthetic_regular_average,
        "averageSyntheticNoisyScore": synthetic_noisy_average,
        "separationMargin": human_average - synthetic_regular_average,
        "suspiciousPatternDetectionRate": suspicious_detection_rate,
    }


def _export_report(report: CalibrationReport) -> None:
    summary_path = report.output_dir / "calibration_summary.json"
    csv_path = report.output_dir / "calibration_results.csv"
    markdown_path = report.output_dir / "calibration_report.md"
    score_distribution_path = report.output_dir / "score_distribution.png"
    suspicion_distribution_path = report.output_dir / "suspicion_distribution.png"
    pdf_path = report.output_dir / "calibration_report.pdf"

    summary_payload = {
        "summary": report.summary,
        "scenarios": [result.to_row() for result in report.scenarios],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")

    rows = [result.to_row() for result in report.scenarios]
    _write_csv(csv_path, rows)
    markdown_path.write_text(_build_markdown(report), encoding="utf-8")
    _render_distribution_plot(report, score_distribution_path, value_key="human_likeness_score", title="Human-Likeness Score Distribution")
    _render_distribution_plot(report, suspicion_distribution_path, value_key="automation_suspicion_score", title="Automation Suspicion Distribution")

    report.files = {
        "summaryJson": str(summary_path),
        "resultsCsv": str(csv_path),
        "markdownReport": str(markdown_path),
        "scoreDistributionPng": str(score_distribution_path),
        "suspicionDistributionPng": str(suspicion_distribution_path),
    }
    try:
        _export_pdf_report(
            report=report,
            output_path=pdf_path,
            score_plot_path=score_distribution_path,
            suspicion_plot_path=suspicion_distribution_path,
        )
        report.files["pdfReport"] = str(pdf_path)
    except Exception as error:  # defensive fallback: keep calibration run valid
        logger.warning("Rich PDF export failed; using text-only fallback: %s", error)
        try:
            _write_minimal_text_pdf(report=report, output_path=pdf_path)
            report.files["pdfReport"] = str(pdf_path)
            report.files["pdfWarning"] = "Calibration completed with text-only PDF fallback."
        except Exception as fallback_error:
            logger.warning("Calibration completed, but PDF export failed: %s", fallback_error)
            report.files["pdfWarning"] = "Calibration completed, but PDF export failed."


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "scenarioId",
        "label",
        "expectedType",
        "humanLikenessScore",
        "automationSuspicionScore",
        "confidence",
        "timingNaturalness",
        "jitterNaturalness",
        "pressureNaturalness",
        "releaseDynamics",
        "repetitionDiversity",
        "signalQuality",
        "suspiciousFlags",
        "explanationFlags",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_markdown(report: CalibrationReport) -> str:
    lines = [
        "# Human-Likeness Calibration Report",
        "",
        "Research metric — not definitive bot detection.",
        "",
        "## Summary",
        f"- Scenario Count: `{report.summary['scenarioCount']}`",
        f"- Avg Human-Like Score: `{report.summary['averageHumanLikeScore']:.2f}`",
        f"- Avg Synthetic Regular Score: `{report.summary['averageSyntheticRegularScore']:.2f}`",
        f"- Avg Synthetic Noisy Score: `{report.summary['averageSyntheticNoisyScore']:.2f}`",
        f"- Separation Margin: `{report.summary['separationMargin']:.2f}`",
        f"- Suspicious Detection Rate: `{report.summary['suspiciousPatternDetectionRate']:.2%}`",
        "",
        "## Scenario Results",
    ]
    for row in report.scenarios:
        lines.append(
            f"- `{row.scenario_id}` ({row.expected_type}): "
            f"human={_fmt(row.human_likeness_score)} "
            f"suspicion={_fmt(row.automation_suspicion_score)} "
            f"confidence={row.confidence} "
            f"flags={', '.join(row.suspicious_flags[:3]) if row.suspicious_flags else 'none'}"
        )
    lines.append("")
    return "\n".join(lines)


def _export_pdf_report(
    *,
    report: CalibrationReport,
    output_path: Path,
    score_plot_path: Path,
    suspicion_plot_path: Path,
) -> None:
    if PdfPages is None or plt is None:
        raise RuntimeError("matplotlib PDF backend is unavailable")

    with PdfPages(output_path) as pdf:
        _write_pdf_summary_page(pdf, report)
        try:
            _write_pdf_images_page(pdf, score_plot_path, suspicion_plot_path)
        except Exception:
            _write_pdf_text_fallback_page(pdf)


def _write_pdf_summary_page(pdf: "PdfPages", report: CalibrationReport) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    figure, axis = plt.subplots(figsize=(8.27, 11.69))
    axis.axis("off")

    summary = report.summary
    header_lines = [
        "Human-Likeness Calibration Report",
        f"Generated at: {generated_at}",
        "",
        f"Scenario Count: {summary['scenarioCount']}",
        f"Avg Human-Like Score: {summary['averageHumanLikeScore']:.2f}",
        f"Avg Synthetic Regular Score: {summary['averageSyntheticRegularScore']:.2f}",
        f"Avg Synthetic Noisy Score: {summary['averageSyntheticNoisyScore']:.2f}",
        f"Separation Margin: {summary['separationMargin']:.2f}",
        f"Suspicious Detection Rate: {summary['suspiciousPatternDetectionRate']:.2%}",
        "",
        "Research metric — not definitive human/bot detection.",
    ]
    axis.text(0.02, 0.98, "\n".join(header_lines), va="top", ha="left", fontsize=10)

    table_rows = [
        [
            row.scenario_id,
            row.expected_type,
            _fmt(row.human_likeness_score),
            _fmt(row.automation_suspicion_score),
            row.confidence,
        ]
        for row in report.scenarios
    ]
    table = axis.table(
        cellText=table_rows,
        colLabels=["Scenario", "Type", "Human Score", "Suspicion", "Confidence"],
        loc="lower center",
        cellLoc="left",
        colLoc="left",
        bbox=[0.02, 0.03, 0.96, 0.52],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    pdf.savefig(figure)
    plt.close(figure)


def _write_pdf_images_page(pdf: "PdfPages", score_plot_path: Path, suspicion_plot_path: Path) -> None:
    if not score_plot_path.exists() or not suspicion_plot_path.exists():
        raise RuntimeError("Distribution PNG files are missing")
    score_image = plt.imread(score_plot_path)
    suspicion_image = plt.imread(suspicion_plot_path)
    figure, axes = plt.subplots(2, 1, figsize=(8.27, 11.69))
    axes[0].imshow(score_image)
    axes[0].set_title("Human-Likeness Score Distribution")
    axes[0].axis("off")
    axes[1].imshow(suspicion_image)
    axes[1].set_title("Automation Suspicion Distribution")
    axes[1].axis("off")
    figure.tight_layout()
    pdf.savefig(figure)
    plt.close(figure)


def _write_pdf_text_fallback_page(pdf: "PdfPages") -> None:
    figure, axis = plt.subplots(figsize=(8.27, 11.69))
    axis.axis("off")
    axis.text(
        0.02,
        0.98,
        "Chart embedding fallback:\n"
        "Distribution images could not be embedded on this system.\n"
        "Use score_distribution.png and suspicion_distribution.png files.",
        va="top",
        ha="left",
        fontsize=10,
    )
    pdf.savefig(figure)
    plt.close(figure)


def _write_minimal_text_pdf(*, report: CalibrationReport, output_path: Path) -> None:
    summary = report.summary
    lines = [
        "Human-Likeness Calibration Report",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Scenario Count: {summary['scenarioCount']}",
        f"Avg Human-Like Score: {summary['averageHumanLikeScore']:.2f}",
        f"Avg Synthetic Regular Score: {summary['averageSyntheticRegularScore']:.2f}",
        f"Avg Synthetic Noisy Score: {summary['averageSyntheticNoisyScore']:.2f}",
        f"Separation Margin: {summary['separationMargin']:.2f}",
        f"Suspicious Detection Rate: {summary['suspiciousPatternDetectionRate']:.2%}",
        "",
        "Research metric — not definitive human/bot detection.",
        "",
        "Scenario Comparison:",
    ]
    for row in report.scenarios:
        lines.append(
            f"- {row.scenario_id} | {row.expected_type} | "
            f"human={_fmt(row.human_likeness_score)} | suspicion={_fmt(row.automation_suspicion_score)}"
        )
    lines.append("")
    lines.append("Charts are available in score_distribution.png and suspicion_distribution.png.")
    _write_simple_pdf(output_path, lines)


def _write_simple_pdf(path: Path, lines: list[str]) -> None:
    escaped_lines = [_pdf_escape(line) for line in lines]
    y = 820
    stream_lines = ["BT", "/F1 11 Tf"]
    for line in escaped_lines:
        stream_lines.append(f"1 0 0 1 50 {y} Tm")
        stream_lines.append(f"({line}) Tj")
        y -= 14
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
    objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    buffer = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer.extend(f"{index} 0 obj\n".encode("latin-1"))
        buffer.extend(obj)
        buffer.extend(b"\nendobj\n")

    xref_position = len(buffer)
    buffer.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(buffer))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_distribution_plot(report: CalibrationReport, output_path: Path, *, value_key: str, title: str) -> None:
    if plt is None:  # pragma: no cover
        output_path.write_bytes(b"")
        return

    groups: dict[str, list[float]] = {}
    for row in report.scenarios:
        value = getattr(row, value_key)
        if value is None:
            continue
        groups.setdefault(row.expected_type, []).append(float(value))

    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.set_title(title)
    axis.set_xlabel("Score")
    axis.set_ylabel("Count")
    bins = np.linspace(0.0, 100.0, 21)
    colors = {
        "synthetic_regular": "#ff453a",
        "synthetic_noisy": "#ff9f0a",
        "human_like_simulated": "#34c759",
    }

    for expected_type in ["synthetic_regular", "synthetic_noisy", "human_like_simulated"]:
        values = groups.get(expected_type, [])
        if not values:
            continue
        axis.hist(
            values,
            bins=bins,
            alpha=0.55,
            label=expected_type,
            color=colors.get(expected_type, "#8e8e93"),
            edgecolor="#101014",
        )

    axis.legend()
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _build_pin_attempts(
    *,
    scenario_id: str,
    attempts: int,
    base_intervals: list[float],
    interval_jitter_std: float,
    position_jitter_std: float,
    force_mode: str,
    radius_mode: str,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    keypad_positions: dict[str, tuple[float, float]] = {
        "1": (90.0, 420.0),
        "2": (150.0, 420.0),
        "3": (210.0, 420.0),
        "4": (90.0, 480.0),
    }
    digits = ["1", "2", "3", "4"]
    events: list[dict[str, Any]] = []
    base_time = 1000.0

    for attempt_index in range(attempts):
        sequence_id = f"{scenario_id}-seq-{attempt_index + 1}"
        start_time = base_time + attempt_index * 3.0
        timestamp = start_time
        for digit_index, digit in enumerate(digits):
            if digit_index > 0:
                interval = base_intervals[digit_index - 1] + float(rng.normal(0.0, interval_jitter_std))
                timestamp += max(0.06, interval)
            touch_id = f"{sequence_id}-touch-{digit_index + 1}"
            events.extend(
                _digit_touch_samples(
                    scenario_id=scenario_id,
                    timestamp=timestamp,
                    touch_id=touch_id,
                    sequence_id=sequence_id,
                    digit=digit,
                    digit_index=digit_index + 1,
                    position=keypad_positions[digit],
                    position_jitter_std=position_jitter_std,
                    force_mode=force_mode,
                    radius_mode=radius_mode,
                    rng=rng,
                )
            )
    return events


def _digit_touch_samples(
    *,
    scenario_id: str,
    timestamp: float,
    touch_id: str,
    sequence_id: str,
    digit: str,
    digit_index: int,
    position: tuple[float, float],
    position_jitter_std: float,
    force_mode: str,
    radius_mode: str,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    x_center = position[0]
    y_center = position[1]
    jx = float(rng.normal(0.0, position_jitter_std))
    jy = float(rng.normal(0.0, position_jitter_std))
    path = [
        (x_center + jx * 0.4, y_center + jy * 0.4, "began"),
        (x_center + jx, y_center + jy, "moved"),
        (x_center + jx * 0.65, y_center + jy * 0.65, "ended"),
    ]
    if force_mode == "flat":
        force_values = [0.26, 0.26, 0.26]
    else:
        peak = 0.38 + float(rng.normal(0.0, 0.045))
        force_values = [
            max(0.05, peak * 0.55 + float(rng.normal(0.0, 0.01))),
            max(0.05, peak),
            max(0.05, peak * 0.42 + float(rng.normal(0.0, 0.01))),
        ]
    if radius_mode == "flat":
        radius_values = [16.0, 16.0, 16.0]
    else:
        base_radius = 15.0 + float(rng.normal(0.0, 0.7))
        radius_values = [
            max(8.0, base_radius + float(rng.normal(0.0, 0.25))),
            max(8.0, base_radius + float(rng.normal(0.0, 0.35))),
            max(8.0, base_radius + float(rng.normal(0.0, 0.28))),
        ]

    samples: list[dict[str, Any]] = []
    for sample_index, ((x, y, phase), force, radius) in enumerate(zip(path, force_values, radius_values, strict=False)):
        samples.append(
            {
                "messageType": "touch_event",
                "sessionId": scenario_id,
                "touchId": touch_id,
                "timestamp": float(timestamp + sample_index * 0.018),
                "phase": phase,
                "x": float(x),
                "y": float(y),
                "force": float(force),
                "maximumPossibleForce": 1.0,
                "majorRadius": float(radius),
                "coalescedCount": 1,
                "predictedCount": 0,
                "deviceType": "iPad",
                "inputType": "finger",
                "experimentMode": "pin_entry",
                "pinSequenceId": sequence_id,
                "digit": digit,
                "digitIndex": digit_index,
            }
        )
    return samples


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
