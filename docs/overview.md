# Project Overview

TGRV is a touchprint research platform for studying whether human touch interactions contain stable, user-specific micro-dynamics.

The project is intentionally split into two layers:

- **iOS acquisition layer** — captures raw touch data with UIKit at high fidelity.
- **Python analysis layer** — ingests exported sessions, computes feature vectors, runs similarity/statistics, orchestrates studies, and generates reports.

## Research goals

The platform is designed to support scientific questions such as:

- Are touch events stable enough to characterize repeatable behavior?
- Which touch dynamics are consistent within a participant?
- Which features separate participants most clearly?
- How do device type, input modality, fatigue, pacing, and time of day affect repeatability?

## What the system captures

The iOS logger records:

- touch location and phase
- timestamp precision
- force and maximum possible force
- major radius
- altitude and azimuth angles when available
- coalesced and predicted touch counts
- session, protocol, trial, and study metadata

## What the Python analyzer does

The analyzer:

- auto-ingests JSON files from `incoming/`
- organizes sessions into a reproducible dataset layout
- extracts interpretable touch feature vectors
- computes similarity metrics and batch statistics
- validates same-user vs cross-user separation
- generates report bundles
- manages controlled experiment runs and reusable study templates

## Core design principles

- **Reproducibility** — template versioning, deterministic schedules, and explicit metadata.
- **Transparency** — interpretable features and statistical reports instead of black-box models.
- **Traceability** — every session carries the provenance needed to reconstruct the study context.
- **No authentication logic** — this platform does not decide whether a user is who they claim to be.

## Main components

- `TGRV/` — iOS app and touch logger
- `touchprint_lab/` — Python research tool
- `processed/` — generated outputs, reports, and persistent study state
- `incoming/` — drop zone for exported iOS JSON sessions

