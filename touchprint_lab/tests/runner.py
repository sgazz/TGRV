from __future__ import annotations

import csv
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional PNG rendering
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - keep CLI usable
    Image = ImageDraw = ImageFont = None  # type: ignore

from touchprint_lab.analyzer.batch import BatchAnalyzer
from touchprint_lab.analyzer.dataset import DatasetManager
from touchprint_lab.analyzer.features import FeatureExtractor
from touchprint_lab.tests.synthetic import (
    SyntheticTouchGenerator,
    canonical_json_text,
    canonical_sha256,
    compare_feature_payloads,
    make_paths,
    normalize_batch_summary,
    validate_feature_payload,
    validate_session_payload,
)


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[2]
    report_root = project_root / "touchprint_lab" / "processed" / "tests" / "reports"
    report_root.mkdir(parents=True, exist_ok=True)

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(Path(__file__).resolve().parent),
        pattern="test_*.py",
        top_level_dir=str(project_root),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    diagnostics = build_pipeline_diagnostics(project_root)
    write_reports(report_root, result, diagnostics)

    return 0 if result.wasSuccessful() else 1


def build_pipeline_diagnostics(project_root: Path) -> dict[str, Any]:
    generator = SyntheticTouchGenerator()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        paths = make_paths(root)
        dataset_manager = DatasetManager(paths)
        feature_extractor = FeatureExtractor()

        sessions = generator.generate_sessions(100, seed=909, participant_count=10)
        roundtrip_diffs: list[dict[str, Any]] = []
        for session in sessions:
            source_path = paths.incoming / f"{session.session_id}.json"
            generator.write_session(session, source_path)
            imported = dataset_manager.import_session_file(source_path)
            if imported is None or imported.session_dir is None:
                roundtrip_diffs.append({"sessionId": session.session_id, "error": "import_failed"})
                continue

            raw_path = imported.session_dir / "raw.json"
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
            validate_session_payload(raw_payload)
            if canonical_sha256(session.to_dict()) != canonical_sha256(raw_payload):
                roundtrip_diffs.append({"sessionId": session.session_id, "check": "raw_hash"})

            imported_feature = imported.feature_vector
            direct_feature = feature_extractor.extract_session(imported).to_dict()
            if imported_feature is None:
                roundtrip_diffs.append({"sessionId": session.session_id, "check": "feature_missing"})
            else:
                validate_feature_payload(imported_feature)
                roundtrip_diffs.extend(
                    {
                        "sessionId": session.session_id,
                        "field": diff["field"],
                        "left": diff["left"],
                        "right": diff["right"],
                    }
                    for diff in compare_feature_payloads(imported_feature, direct_feature)
                )

        loaded_sessions = dataset_manager.load_all_sessions()
        batch_analyzer = BatchAnalyzer()
        batch_runs = [batch_analyzer.analyze(loaded_sessions) for _ in range(3)]
        batch_hashes = [canonical_sha256(normalize_batch_summary(run.summary_dict())) for run in batch_runs]
        similarity_deltas = _matrix_deltas([run.similarity_matrix for run in batch_runs])
        distance_deltas = _matrix_deltas([run.distance_matrix for run in batch_runs])
        feature_deltas = _feature_deltas(loaded_sessions, feature_extractor)

        metrics_rows = [
            {"metric": "loaded_sessions", "value": len(loaded_sessions)},
            {"metric": "roundtrip_diffs", "value": len(roundtrip_diffs)},
            {"metric": "unique_batch_hashes", "value": len(set(batch_hashes))},
            {"metric": "max_feature_delta", "value": feature_deltas["max_feature_delta"]},
            {"metric": "max_similarity_delta", "value": similarity_deltas},
            {"metric": "max_distance_delta", "value": distance_deltas},
        ]

        return {
            "sessions": len(loaded_sessions),
            "roundtripDiffs": roundtrip_diffs,
            "batchHashes": batch_hashes,
            "featureDeltas": feature_deltas,
            "similarityDelta": similarity_deltas,
            "distanceDelta": distance_deltas,
            "metricsRows": metrics_rows,
            "batchSummary": normalize_batch_summary(batch_runs[0].summary_dict()),
            "projectRoot": str(project_root),
        }


def write_reports(report_root: Path, result: unittest.result.TestResult, diagnostics: dict[str, Any]) -> None:
    summary = {
        "testsRun": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "wasSuccessful": result.wasSuccessful(),
        "diagnostics": diagnostics,
    }

    summary_path = report_root / "test_summary.json"
    integrity_path = report_root / "integrity_report.md"
    stability_path = report_root / "stability_metrics.csv"
    diffs_path = report_root / "roundtrip_diffs.json"
    png_path = report_root / "pipeline_diagnostics.png"

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    diffs_path.write_text(json.dumps(diagnostics["roundtripDiffs"], indent=2, sort_keys=True), encoding="utf-8")
    _write_stability_csv(stability_path, diagnostics["metricsRows"])
    integrity_path.write_text(_integrity_markdown(summary), encoding="utf-8")
    _write_diagnostics_png(png_path, summary, diagnostics)


def _integrity_markdown(summary: dict[str, Any]) -> str:
    diagnostics = summary["diagnostics"]
    lines = [
        "# Touchprint End-to-End Test Report",
        "",
        f"- Tests run: `{summary['testsRun']}`",
        f"- Failures: `{summary['failures']}`",
        f"- Errors: `{summary['errors']}`",
        f"- Successful: `{summary['wasSuccessful']}`",
        f"- Sessions: `{diagnostics['sessions']}`",
        f"- Round-trip diffs: `{len(diagnostics['roundtripDiffs'])}`",
        f"- Batch hash variants: `{len(set(diagnostics['batchHashes']))}`",
        "",
        "## Stability Summary",
        f"- Max feature delta: `{diagnostics['featureDeltas']['max_feature_delta']:.12f}`",
        f"- Max similarity delta: `{diagnostics['similarityDelta']:.12f}`",
        f"- Max distance delta: `{diagnostics['distanceDelta']:.12f}`",
        "",
        "## Validation Notes",
        "- Raw session JSON is canonicalized before hash comparison.",
        "- Feature vectors are re-extracted to verify deterministic output.",
        "- Batch analysis is rerun multiple times to confirm matrix stability.",
        "- No UI or network dependencies are required for the test suite.",
    ]
    return "\n".join(lines) + "\n"


def _write_stability_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_diagnostics_png(path: Path, summary: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    if Image is None:
        path.write_text(json.dumps({"summary": summary, "diagnostics": diagnostics}, indent=2, sort_keys=True), encoding="utf-8")
        return

    canvas = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default() if ImageFont is not None else None

    draw.text((40, 30), "Touchprint End-to-End Diagnostics", fill="black", font=font)
    stats = [
        ("Tests run", summary["testsRun"]),
        ("Failures", summary["failures"]),
        ("Errors", summary["errors"]),
        ("Sessions", diagnostics["sessions"]),
        ("Round-trip diffs", len(diagnostics["roundtripDiffs"])),
        ("Batch hash variants", len(set(diagnostics["batchHashes"]))),
        ("Max feature delta", f"{diagnostics['featureDeltas']['max_feature_delta']:.6f}"),
        ("Max similarity delta", f"{diagnostics['similarityDelta']:.6f}"),
        ("Max distance delta", f"{diagnostics['distanceDelta']:.6f}"),
    ]

    y = 90
    for label, value in stats:
        draw.text((40, y), f"{label}: {value}", fill="black", font=font)
        y += 42

    bars = [
        ("Feature delta", float(diagnostics["featureDeltas"]["max_feature_delta"])),
        ("Similarity delta", float(diagnostics["similarityDelta"])),
        ("Distance delta", float(diagnostics["distanceDelta"])),
        ("Round-trip diffs", float(len(diagnostics["roundtripDiffs"]))),
    ]
    max_value = max((value for _, value in bars), default=1.0) or 1.0
    base_x = 560
    base_y = 770
    bar_width = 180
    gap = 35
    for index, (label, value) in enumerate(bars):
        height = int(400 * (value / max_value if max_value else 0.0))
        x0 = base_x + index * (bar_width + gap)
        x1 = x0 + bar_width
        y0 = base_y - height
        draw.rectangle([x0, y0, x1, base_y], fill="#4c78a8")
        draw.text((x0, base_y + 10), label, fill="black", font=font)
        draw.text((x0, y0 - 18), f"{value:.6f}" if value < 10 else f"{value:.0f}", fill="black", font=font)

    canvas.save(str(path))


def _matrix_deltas(matrices: list[Any]) -> float:
    import numpy as np

    if len(matrices) < 2:
        return 0.0
    base = np.asarray(matrices[0], dtype=float)
    deltas = [float(np.max(np.abs(base - np.asarray(matrix, dtype=float)))) for matrix in matrices[1:]]
    return max(deltas) if deltas else 0.0


def _feature_deltas(sessions, feature_extractor: FeatureExtractor) -> dict[str, float]:
    import numpy as np

    feature_arrays = [feature_extractor.extract_session(session).feature_array() for session in sessions]
    if not feature_arrays:
        return {"max_feature_delta": 0.0}
    base = feature_arrays[0]
    deltas = [float(np.max(np.abs(base - vector))) for vector in feature_arrays[1:]]
    return {"max_feature_delta": max(deltas) if deltas else 0.0}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
