# Study Templates Guide

Study templates define deterministic experimental protocols for standardized touchprint research.

## Purpose

Study templates eliminate inconsistent ad hoc experiment setup by providing reusable, versioned protocol presets with fixed timing and pacing rules.

## Built-in templates

### `baseline_identity_study`

Baseline stable identity protocol with tap, intentional, and signature blocks.

Use when you want a general-purpose reference study for participant comparison.

### `pin_behavior_study`

Deterministic PIN-entry protocol with paced repetition and pause control.

Use when you want to study structured sequential touch behavior.

### `motor_fatigue_study`

Progressive pacing protocol for drift and fatigue adaptation analysis.

Use when studying how prolonged use affects touch stability.

### `pencil_precision_study`

High-fidelity Apple Pencil protocol focused on geometry and precision.

Use when analyzing stylus behavior rather than finger input.

### `replayability_study`

Repeated protocol designed to probe within-subject replayability over time.

Use when evaluating repeatability across multiple sessions.

## Template contents

Every template defines:

- experiment structure
- trial order
- repetitions
- timing rules
- pauses
- pacing mode
- required metadata labels
- deterministic seed
- session scheduling rules

## Pacing modes

Supported pacing strategies:

- `fixed`
- `randomized`
- `fatigue`
- `adaptive`

## Scheduling options

Templates can define:

- same-day sessions
- multi-day sessions
- delayed retesting
- session spacing

## Serialization

Templates can be exported and imported as:

- JSON
- YAML

## Versioning

Templates are versioned explicitly so a study can be reproduced later with the same protocol definition.

Recommended practice:

- keep the template version fixed during a study run
- export the template alongside the study report
- never silently mutate a template after data collection has started

