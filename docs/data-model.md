# Data Model Guide

This document describes the main exported objects and how they are used in analysis.

## iOS session export

Each exported touch session is a JSON object containing:

- `sessionId`
- `startedAt`
- `exportedAt`
- `deviceType`
- `sessionType`
- `participantId`
- `experimentId`
- `trialId`
- `trialIndex`
- `protocolSessionId`
- `protocolType`
- `studyId`
- `studyTemplateId`
- `studyTemplateVersion`
- `studySessionId`
- `studyStepId`
- `studyStepIndex`
- `studyLabels`
- `protocolMetadata`
- `participantMetadata`
- `environmentLabels`
- `timingMetadata`
- `touchEventCount`
- `events`

## Touch event schema

Each event records:

- `sessionId`
- `touchId`
- `phase`
- `timestamp`
- `x`, `y`
- `force`
- `maximumPossibleForce`
- `majorRadius`
- `altitudeAngle`
- `azimuthAngle`
- `touchType`
- `deviceType`
- `coalescedTouchesCount`
- `predictedTouchesCount`

The analyzer keeps the event list intact so later feature engineering can use the raw signal trace.

## Feature vector schema

Each touch session can be transformed into a feature vector containing:

- temporal metrics
- spatial metrics
- force/contact metrics
- micro-dynamic metrics
- session summary metrics

These vectors are exported as:

- JSON
- CSV

## Protocol metadata

Protocol metadata describes the experimental context of a session:

- participant identity labels
- experiment identity labels
- trial identity labels
- protocol type
- trial instructions
- timing metadata
- environment labels
- study labels

## Study metadata

Study metadata is used for reproducible research presets and longitudinal studies:

- `studyId`
- `studyTemplateId`
- `studyTemplateVersion`
- `studySessionId`
- `studyStepId`
- `studyStepIndex`
- `studyLabels`

## Dataset organization

Imported sessions are organized under the dataset root with stable identifiers and deduplication metadata.

Relevant persistent outputs include:

- `dataset/` — normalized session records
- `processed/features/` — extracted vectors
- `processed/protocols/` — protocol state and reports
- `processed/studies/` — study plans, templates, and reports
- `processed/reports/` — batch statistical analysis reports

