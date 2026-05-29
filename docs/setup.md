# Setup Guide

This guide explains how to run the platform locally.

## Prerequisites

- macOS
- Xcode 15 or later for the iOS app
- Python 3.12 or later for the analyzer

## Python environment

```bash
cd /Volumes/External2TB/Xcode/TGRV
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Launch the analyzer

```bash
python -m touchprint_lab.main
```

Or use the launcher:

- `Touchprint Analyzer.command`

## Ingest data

1. Export touch sessions from the iOS app.
2. Copy the JSON files into `touchprint_lab/incoming/`.
3. Wait for the analyzer to detect and import them.

## Verify output

After import, inspect these directories:

- `touchprint_lab/dataset/`
- `touchprint_lab/processed/features/`
- `touchprint_lab/processed/protocols/`
- `touchprint_lab/processed/studies/`
- `touchprint_lab/processed/reports/`

## Tips

- Keep template versions stable during a study.
- Do not rename exported session files manually if you want clean provenance.
- Use the study templates for repeatable experiments instead of manually assembling protocols.

