# TGRV / Touchprint Research Platform

Touchprint research platform for controlled behavioral biometric experiments.

This repository contains two coordinated parts:

- **iOS UIKit touch logger** — captures raw touch events and exports structured JSON sessions.
- **Python Touchprint Analyzer** — ingests sessions, extracts features, runs similarity/statistical analysis, and manages experimental studies.

## What it is

This is a scientific R&D environment for studying whether touch interactions contain stable, user-specific micro-dynamics.

It is **not** authentication software.

## Repository layout

- `TGRV/` — iOS UIKit instrumentation app for touch acquisition
- `touchprint_lab/` — Python 3.12+ analysis and study orchestration tool
- `Touchprint Analyzer.command` — macOS launcher for the Python app
- `requirements.txt` — Python dependencies for the analyzer
- `docs/` — detailed project documentation

## iOS logger

The iOS app captures:

- touch location, timestamp, and phase
- force, max force, major radius
- altitude and azimuth angle when available
- coalesced and predicted touch counts
- session, trial, protocol, and study metadata

Exports are written as JSON for later analysis.

## Python analyzer

The Python platform provides:

- automatic ingestion from `incoming/`
- dataset organization and deduplication
- feature extraction and similarity metrics
- batch statistics and statistical validation
- controlled experiment orchestration
- study templates and longitudinal study support
- report export in JSON, CSV, Markdown, and PNG

## Requirements

- Xcode 15+ for the iOS app
- Python 3.12+ for the analyzer
- PyQt6, pyqtgraph, numpy, pandas, scipy, matplotlib, scikit-learn

## Running the analyzer

```bash
cd /Volumes/TGRV
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m touchprint_lab.main
```

Or double-click:

- `Touchprint Analyzer.command`

## Study workflow

1. Export touch sessions from the iOS logger.
2. Drop JSON files into `touchprint_lab/incoming/`.
3. The analyzer imports and labels sessions automatically.
4. Feature vectors, statistics, and reports are generated in `touchprint_lab/processed/`.
5. Study templates and protocol metadata remain versioned for reproducibility.

## Output directories

- `touchprint_lab/dataset/` — organized session dataset
- `touchprint_lab/processed/features/` — per-session feature vectors
- `touchprint_lab/processed/protocols/` — protocol state and reports
- `touchprint_lab/processed/studies/` — study templates, schedules, and study reports
- `touchprint_lab/processed/reports/` — batch-analysis reports

## Notes

- No networking.
- No authentication logic.
- No neural networks or deep learning.
- The design prioritizes reproducibility and inspectable experimental flow.

## Documentation

Full documentation lives in `docs/`:

- `docs/README.md`
- `docs/overview.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/study-templates.md`
- `docs/longitudinal-wizard.md`
- `docs/workflows.md`
- `docs/testing.md`
- `docs/setup.md`

## Testing

Run the end-to-end validation suite from the project root:

```bash
python -m touchprint_lab.tests.runner
```

The runner also writes reports to `touchprint_lab/processed/tests/reports/`.
