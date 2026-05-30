from __future__ import annotations

from typing import Any


REQUIRED_HELP_FIELDS = (
    "title",
    "short_description",
    "why_it_matters",
    "calculation_summary",
    "interpretation_notes",
)


PANEL_HELP: dict[str, dict[str, Any]] = {
    "touch_trajectory": {
        "title": "Touch Trajectory",
        "short_description": "Shows the spatial path of touch movement over time.",
        "why_it_matters": "Trajectory shape and drift patterns can reflect stable motor behavior traits.",
        "calculation_summary": "Plots raw x/y coordinates in capture order without smoothing.",
        "interpretation_notes": "Tighter repeatable paths can indicate consistent motor control; noisy paths may indicate instability or task difficulty.",
        "optional_tips": "Compare trajectories across repeated trials for the same participant and task.",
    },
    "force_radius_timeline": {
        "title": "Force / Radius Timeline",
        "short_description": "Displays force and contact radius as time-series curves.",
        "why_it_matters": "Press/release dynamics and contact size variation can carry behavioral signatures.",
        "calculation_summary": "Uses per-event force and majorRadius values against event timestamps.",
        "interpretation_notes": "Look for ramp-up, peak, and release behavior; perfectly flat curves are often less human-like.",
        "optional_tips": "Evaluate with input type context (finger vs pencil).",
    },
    "signature_layer": {
        "title": "Signature Layer",
        "short_description": "Visualizes normalized force with phase-colored event points.",
        "why_it_matters": "Combines force rhythm, phase transitions, and contact spread in one compact view.",
        "calculation_summary": "Normalizes force per session and overlays phase-colored markers sized by radius.",
        "interpretation_notes": "Clustered consistent patterns can indicate repeatable motor behavior.",
        "optional_tips": "Inspect changes when task difficulty or posture changes.",
    },
    "groove_view": {
        "title": "Groove View",
        "short_description": "Maps touch dynamics into a groove-like radial representation.",
        "why_it_matters": "Highlights temporal-spatial regularity and occupancy tendencies in repeated behavior.",
        "calculation_summary": "Transforms trajectory around centroid into radial coordinates over normalized time.",
        "interpretation_notes": "Stable groove shapes suggest consistent behavior; irregular spread may indicate adaptation or noise.",
        "optional_tips": "Use with Groove Stability for short-term consistency interpretation.",
    },
    "phase_timeline": {
        "title": "Phase Timeline",
        "short_description": "Shows touch phase progression (began/moved/ended/cancelled) over time.",
        "why_it_matters": "Phase sequencing quality helps detect malformed capture and unusual transitions.",
        "calculation_summary": "Maps phase labels to numeric values and plots them against timestamps.",
        "interpretation_notes": "Frequent discontinuities or cancellations may indicate capture or interaction issues.",
        "optional_tips": "Use as a sanity strip before interpreting higher-level metrics.",
    },
    "pin_keyboard_mirror": {
        "title": "PIN Keyboard Mirror",
        "short_description": "Read-only mirror of PIN digit actions from the logger device.",
        "why_it_matters": "Confirms experimental PIN flow and timing alignment during live capture.",
        "calculation_summary": "Uses streamed PIN metadata (digit, index, sequence, actions) to update visual state.",
        "interpretation_notes": "Mismatch between expected and mirrored sequence may indicate protocol deviations.",
        "optional_tips": "Correlate with PIN Rhythm Strip when reviewing entry consistency.",
    },
    "pin_rhythm_strip": {
        "title": "PIN Rhythm Strip",
        "short_description": "Summarizes inter-digit timing intervals for PIN sequences.",
        "why_it_matters": "Timing rhythm is a key behavioral signal for repeatability and separability analysis.",
        "calculation_summary": "Computes adjacent digit timestamp deltas and consistency from interval variance.",
        "interpretation_notes": "Human rhythm is usually similar but not identical across attempts.",
        "optional_tips": "Watch for over-regular intervals in synthetic or scripted inputs.",
    },
    "pressure_fingerprint": {
        "title": "Pressure Fingerprint",
        "short_description": "Shows force distribution and pressure/radius summary statistics.",
        "why_it_matters": "Pressure and contact variability can provide user-specific motor characteristics.",
        "calculation_summary": "Builds force histogram and computes mean/median/std plus radius stability indicators.",
        "interpretation_notes": "Completely flat pressure patterns are typically less natural.",
        "optional_tips": "Interpret alongside input mode and device type.",
    },
    "groove_stability": {
        "title": "Groove Stability",
        "short_description": "Estimates short-term consistency relative to a rolling baseline.",
        "why_it_matters": "Captures whether current behavior remains stable within a session.",
        "calculation_summary": "Compares recent and baseline windows for trajectory, force, timing, and phase occupancy similarity.",
        "interpretation_notes": "Higher values indicate stable behavior; drops may indicate drift, fatigue, or context changes.",
        "optional_tips": "Use trend over time rather than isolated single-frame values.",
    },
    "human_likeness": {
        "title": "Human-Likeness",
        "short_description": "Estimates how natural current touch behavior appears.",
        "why_it_matters": "Human input contains micro-variation that is difficult to replicate perfectly.",
        "calculation_summary": "Combines timing, jitter, pressure variation, repetition diversity, and signal quality into a normalized score.",
        "interpretation_notes": "Higher scores indicate more human-like behavior; lower scores indicate unusually regular patterns.",
        "optional_tips": "Research metric — not definitive human/bot detection and not identity proof.",
    },
    "live_stability": {
        "title": "Live Stability",
        "short_description": "Tracks immediate session stability indicators in real time.",
        "why_it_matters": "Helps identify unstable capture windows before downstream analysis.",
        "calculation_summary": "Uses short-window drift, jitter, force/radius stability, and sample-rate health.",
        "interpretation_notes": "Low stability often means ongoing adaptation, poor contact, or sparse signal.",
    },
    "signal_quality": {
        "title": "Signal Quality",
        "short_description": "Summarizes capture completeness and temporal consistency.",
        "why_it_matters": "Low-quality streams can distort interpretation of all higher-level metrics.",
        "calculation_summary": "Evaluates finite sample coverage, monotonic timestamps, and usable event density.",
        "interpretation_notes": "Prefer analysis windows with sufficient quality to avoid false conclusions.",
    },
}


LIVE_PANEL_HELP_KEY_MAP: dict[str, str] = {
    "trajectory": "touch_trajectory",
    "force_radius": "force_radius_timeline",
    "signature_layer": "signature_layer",
    "groove_view": "groove_view",
    "phase_timeline": "phase_timeline",
    "pin_keyboard_mirror": "pin_keyboard_mirror",
    "pressure_fingerprint": "pressure_fingerprint",
    "groove_stability": "groove_stability",
    "human_likeness": "human_likeness",
}


def panel_help_for_live_panel(panel_id: str) -> dict[str, Any]:
    help_id = LIVE_PANEL_HELP_KEY_MAP.get(panel_id, panel_id)
    payload = PANEL_HELP.get(help_id)
    if payload is None:
        return {
            "title": panel_id.replace("_", " ").title(),
            "short_description": "No help content defined yet.",
            "why_it_matters": "This panel has no registered research explanation yet.",
            "calculation_summary": "N/A",
            "interpretation_notes": "N/A",
        }
    return payload
