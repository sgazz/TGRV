# Workflows Guide

This document describes how the platform is used in practice.

## 1. Capture workflow

1. Run the iOS logger.
2. Perform a touch task.
3. Export the resulting session as JSON.
4. Transfer the file to the desktop machine.
5. Drop it into `touchprint_lab/incoming/`.

## 2. Ingestion workflow

1. The analyzer watches `incoming/`.
2. New JSON files are detected automatically.
3. Sessions are parsed and deduplicated.
4. Files are organized into the dataset structure.
5. Feature extraction runs automatically.

## 3. Analysis workflow

1. Open the Python app.
2. Select a session or user.
3. Inspect the raw plots and metadata.
4. Review extracted feature vectors.
5. Run batch statistics and similarity analysis.
6. Export report bundles when needed.

## 4. Protocol workflow

1. Create or start an experiment run.
2. The protocol layer attaches labels to each session.
3. Trials are recorded as sessions complete.
4. The protocol history is saved in `processed/protocols/`.

## 5. Study workflow

1. Choose a study template from the Study Library.
2. Create a study plan for a participant.
3. Start, pause, resume, or clone the study as needed.
4. Use deterministic timing and pacing.
5. Track session completion and longitudinal drift.
6. Export the study report bundle.

## 6. Longitudinal study workflow

Longitudinal studies reuse the same participant and template across repeated sessions.

For multi-day studies, use the Longitudinal Study Wizard instead of manual creation.

The wizard produces:

- a deterministic study plan
- a structured schedule preview
- participant metadata
- environment labels
- protocol manifest
- queued study sessions

Its 6-step flow is documented in [Longitudinal Study Wizard](longitudinal-wizard.md).

Recommended setup:

- keep the participant identifier stable
- keep the template version stable
- keep the study seed stable
- record environmental metadata explicitly
- avoid hidden manual adjustments between sessions

## 7. Wizard launch path

Open the wizard from:

- `Study Library` tab
- `Longitudinal Wizard` button

If the wizard is used, the following output files are created under `touchprint_lab/processed/studies/<studyId>/`:

- `study_plan.json`
- `study_schedule.json`
- `participant_metadata.json`
- `protocol_manifest.json`

## 8. Report workflow

Reports are written as bundles containing:

- JSON summary
- CSV tables
- Markdown summary
- PNG plots

Typical report locations:

- `touchprint_lab/processed/reports/`
- `touchprint_lab/processed/protocols/reports/`
- `touchprint_lab/processed/studies/reports/`
