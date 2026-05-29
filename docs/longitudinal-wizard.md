# Longitudinal Study Wizard

The Longitudinal Study Wizard is the guided UI used to create deterministic, reproducible multi-day studies inside Touchprint Lab.

It is designed for controlled behavioral biometrics research, not for consumer-facing workflows or authentication decisions.

## Purpose

The wizard standardizes how a researcher defines a longitudinal study so that repeated touch sessions can be compared across time with minimal setup variance.

It enforces:

- required study metadata
- participant metadata
- deterministic protocol selection
- repeatable schedule generation
- environment labeling
- persisted draft state

## Where it lives

- UI component: `touchprint_lab/ui/longitudinal_wizard.py`
- Launcher: `touchprint_lab/ui/study_library.py`
- Integration point: `touchprint_lab/ui/main_window.py`

## Step-by-step flow

### Step 1: Study Definition

Collects:

- study name
- study type
- optional description
- random seed

The study type selects the base template:

- `baseline_identity_study`
- `pin_behavior_study`
- `motor_fatigue_study`
- `pencil_precision_study`
- `replayability_study`

### Step 2: Participant Setup

Collects:

- `participantId`
- dominant hand
- device preference

The participant ID is required and becomes part of all generated study metadata.

### Step 3: Protocol Selection

Lets the researcher choose one or more protocol blocks:

- `random_tap`
- `intentional_tap`
- `signature_tap`
- `pin_entry`
- `line_drawing`
- `pressure_stabilization`
- `hold_and_release`

Also configures:

- repetitions per protocol
- intensity level

### Step 4: Schedule Builder

Builds a longitudinal calendar with deterministic timing.

Supported controls:

- day count
- same-day repetitions
- daily repetitions
- delayed repetition mode
- time windows: morning / afternoon / evening
- random drift toggle
- schedule spacing controls

The wizard generates a structured preview before launch so the researcher can inspect the exact calendar.

### Step 5: Environment Labels

Adds metadata-only labels for:

- device type
- posture
- cognitive state
- input mode

These labels do not change touch acquisition behavior. They are attached to the study context for later analysis.

### Step 6: Review & Launch

Shows:

- full study summary
- participant info
- protocol sequence
- schedule preview
- expected session count

Available actions:

- Start Study
- Save Draft
- Export JSON/YAML

## Determinism

The wizard uses a fixed seed and stable ID generation so the same inputs produce the same study plan and schedule.

Deterministic elements include:

- study ID generation
- derived template ID generation
- session ID generation
- schedule timing drift
- exported metadata payloads

## Persistence

The wizard persists draft state in:

- `touchprint_lab/processed/studies/wizard_state.json`

This allows the operator to resume a partially completed setup later.

## Generated outputs

On launch, the wizard writes a study bundle under:

- `touchprint_lab/processed/studies/<studyId>/`

Generated files include:

- `study_plan.json`
- `study_schedule.json`
- `participant_metadata.json`
- `protocol_manifest.json`

The wizard also persists a draft file for manual review:

- `longitudinal_wizard_draft.json`
- `longitudinal_wizard_draft.yaml` when YAML export is requested

## Queue handoff

When the study is launched, the wizard:

1. creates a `StudyPlan`
2. registers the derived template
3. exports the study bundle
4. queues scheduled sessions in `ExperimentManager`

This keeps study orchestration deterministic while preserving the existing protocol layer.

## Recommended usage

Use the wizard whenever you need:

- multi-day repetition
- delayed retesting
- consistent environment labels
- reproducible participant studies

Use the lighter Study Library controls when you only need to inspect or manually manage an existing study.

