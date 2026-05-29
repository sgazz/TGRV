# Testing Guide

This document describes the end-to-end validation suite for the Touchprint research platform.

## Purpose

The tests validate signal fidelity and determinism across the full pipeline:

- iOS touch capture
- JSON export
- Python ingestion
- feature extraction
- batch analysis

These tests are designed for scientific validation, not for authentication logic.

## Test modules

The suite lives in `touchprint_lab/tests/`:

- `test_signal_sanity.py`
- `test_export_import_integrity.py`
- `test_feature_determinism.py`
- `test_pipeline_roundtrip.py`
- `test_batch_stability.py`

## Synthetic generator

The suite uses a deterministic synthetic touch generator that can emit:

- deterministic tap sequences
- randomized sequences
- signature-like sequences
- PIN-like sequences

The generator supports fixed seeds so repeated runs stay reproducible.

## CLI runner

Run the full suite and generate reports with:

```bash
python -m touchprint_lab.tests.runner
```

You can also run the package directly:

```bash
python -m touchprint_lab.tests
```

## Generated reports

The runner writes artifacts to:

- `touchprint_lab/processed/tests/reports/`

Generated files include:

- `test_summary.json`
- `integrity_report.md`
- `stability_metrics.csv`
- `roundtrip_diffs.json`
- `pipeline_diagnostics.png`

## Validation methodology

The suite checks:

- schema integrity for raw session JSON
- timestamp monotonicity
- canonical hash stability for JSON round-trips
- feature vector determinism
- similarity and batch analysis stability across reruns
- report generation on the local filesystem

