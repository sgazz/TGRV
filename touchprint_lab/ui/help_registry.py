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
    "groove_view_3d": {
        "title": "Groove View 3D",
        "short_description": "Renders live touch groove as a 3D trace where Z encodes force or pressure proxy.",
        "why_it_matters": "3D representation helps inspect micro-dynamic layering not obvious in 2D trajectory plots.",
        "calculation_summary": "Maps normalized X/Y touch positions and Z from selected mode (force, radius, or layer depth) over recent events.",
        "interpretation_notes": "Higher Z indicates stronger pressure/proxy intensity; use shape consistency across trials for research comparison.",
        "optional_tips": "Visualization only; do not interpret it as identity proof or authentication signal by itself. Optional Metal deps: pyobjc-framework-Metal, pyobjc-framework-MetalKit.",
    },
    "logger_canvas_mirror": {
        "title": "Logger Canvas Mirror",
        "short_description": "Live mirrored reconstruction of the Logger touch canvas.",
        "why_it_matters": "Lets researchers verify what participants actually drew/tapped during capture.",
        "calculation_summary": "Rebuilds touch paths from live x/y/phase/touchId telemetry with inferred or explicit bounds mapping.",
        "interpretation_notes": "Check path continuity, tap locations, and PIN interaction traces; this is a visualization aid only.",
        "optional_tips": "Use Force Thickness and Trails to inspect motor pressure/dynamics without changing capture data.",
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
    "groove_view_3d": "groove_view_3d",
    "logger_canvas_mirror": "logger_canvas_mirror",
    "phase_timeline": "phase_timeline",
    "pin_keyboard_mirror": "pin_keyboard_mirror",
    "pressure_fingerprint": "pressure_fingerprint",
    "groove_stability": "groove_stability",
    "human_likeness": "human_likeness",
}

PANEL_TOOLTIPS: dict[str, str] = {
    "touch_trajectory": "Displays raw touch path in x/y over time for movement consistency analysis.",
    "force_radius_timeline": "Shows force and contact radius over time to inspect press and release behavior.",
    "signature_layer": "Overlays phase, force, and radius cues into a compact behavioral signature view.",
    "groove_view": "Radial groove-like map showing temporal-spatial occupancy and pattern regularity.",
    "groove_view_3d": "3D live groove trace where Z maps force, radius proxy, or layer depth from recent touch events.",
    "logger_canvas_mirror": "Mirrors Logger touch canvas live with reconstructed paths, taps, and latest-touch highlight.",
    "phase_timeline": "Timeline of began/moved/ended/cancelled states for capture sanity and transitions.",
    "pin_keyboard_mirror": "Read-only mirror of PIN digit activity streamed from the iOS logger.",
    "pin_rhythm_strip": "Inter-digit timing strip for PIN rhythm consistency and variance tracking.",
    "pressure_fingerprint": "Force distribution summary with radius stability indicators for pressure behavior.",
    "groove_stability": "Rolling stability score across trajectory, force, timing, and layer occupancy.",
    "human_likeness": "Research score estimating how natural the current touch behavior appears. Not authentication or proof of human presence.",
    "live_stability": "Live micro-metrics for drift, jitter, force/radius stability, and sample-rate health.",
    "signal_quality": "Capture quality indicator showing whether data density and timing support valid interpretation.",
}

LIVE_TELEMETRY_TOOLTIPS: dict[str, str] = {
    "debug_toggle": "Open or hide developer diagnostics for network and telemetry internals.",
    "panel_help": "Open panel research explanation with interpretation guidance.",
    "panel_double_click_focus": "Double-click to open this panel in a larger live focus view.",
    "panel_collapse": "Collapse or expand this panel body in compact layouts.",
    "human_likeness_details": "Open Human-Likeness details, calibration, and validation actions.",
    "human_likeness_research_help": "Open the Human-Likeness Research Guide.",
    "evaluate_current_session": "Evaluate only the currently buffered live session events.",
    "run_calibration": "Run synthetic calibration scenarios for Human-Likeness score behavior.",
    "preview_calibration_pdf": "Open the latest calibration PDF report if available.",
    "run_human_vs_synthetic_validation": "Compare dataset human sessions against synthetic reference scenarios.",
    "groove3d_z_mode": "Choose what Z represents in Groove View 3D: force, radius proxy, or layer depth.",
    "groove3d_reset_camera": "Reset Groove View 3D camera position and angle.",
    "groove3d_auto_rotate": "Rotate Groove View 3D camera slowly for spatial inspection.",
    "groove3d_renderer_selector": "Choose rendering backend preference: Auto, Metal, OpenGL, or 2D fallback.",
    "canvas_clear": "Clear mirrored canvas paths locally without affecting telemetry capture.",
    "canvas_trails": "Toggle trail persistence for mirrored touch strokes.",
    "canvas_force_thickness": "Use force/radius-driven stroke thickness when available.",
    "canvas_fit_surface": "Fit mirrored canvas view to current normalized touch bounds.",
    "close_dialog": "Close this dialog window.",
    "debug_close": "Close the debug diagnostics panel.",
    "debug_copy_ip": "Copy detected Mac LAN IP for iOS logger telemetry host setting.",
    "status_connection": "Current live telemetry connection state from analyzer server.",
    "status_device": "Active source device reported by current live session.",
    "status_input": "Current detected input mode: Finger, Pencil, Mixed, or Unknown.",
    "status_sample_rate": "Estimated incoming event sample rate in Hertz.",
    "status_session": "Current active live session identifier.",
    "status_export": "Export verification state for the active live session.",
}


HUMAN_LIKENESS_RESEARCH_GUIDE: dict[str, dict[str, Any]] = {
    "en": {
        "title": "Human-Likeness Research Guide",
        "subtitle": "Interpretation aid for behavioral signal research",
        "sections": [
            {
                "heading": "What is Human-Likeness?",
                "body": "Human-Likeness is a research score that estimates how natural the current touch behavior appears based on interpretable signal dynamics.",
            },
            {
                "heading": "Why does it matter?",
                "body": "Human motor input typically contains non-perfect micro-variation. This score helps flag whether captured behavior is rich enough for touchprint research.",
            },
            {
                "heading": "Timing Naturalness",
                "body": "Measures inter-event and inter-digit timing variation. Suspiciously perfect intervals reduce this subscore.",
            },
            {
                "heading": "Jitter Naturalness",
                "body": "Measures small spatial micro-variation in x/y dynamics. Completely static or overly linear movement lowers this component.",
            },
            {
                "heading": "Pressure Naturalness",
                "body": "Measures force and contact-radius variation. Flat pressure/radius patterns are less human-like than naturally varying profiles.",
            },
            {
                "heading": "Release Dynamics",
                "body": "Measures press-release shape consistency, including ramp-up and decay behavior around touch end.",
            },
            {
                "heading": "Repetition Diversity",
                "body": "Compares repeated attempts. Human attempts are usually similar but not identical; near-identical repeats are suspicious.",
            },
            {
                "heading": "Signal Quality",
                "body": "Measures whether the current data window is sufficient and stable enough for reliable scoring.",
            },
            {
                "heading": "Automation Suspicion",
                "body": "Inverse perspective of Human-Likeness. Higher suspicion indicates stronger signs of over-regular or synthetic-like patterns.",
            },
            {
                "heading": "Confidence",
                "body": "Confidence reflects data sufficiency and signal robustness. Low confidence means the score should be treated as provisional.",
            },
            {
                "heading": "Interpretation Guide",
                "body": (
                    "0–30: Highly regular or poor-quality signal; strong caution.\n"
                    "31–50: Likely irregularity/suspicion or insufficient natural variation.\n"
                    "51–70: Mixed signal; partially natural but inconclusive.\n"
                    "71–85: Generally natural behavioral variation.\n"
                    "86–100: Strong naturalness signature in current window."
                ),
            },
            {
                "heading": "Research Warning",
                "body": (
                    "Human-Likeness is not authentication, not identity verification, "
                    "and not proof of human presence. It is a research metric only."
                ),
            },
        ],
    }
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


def panel_tooltip_for_live_panel(panel_id: str) -> str:
    help_id = LIVE_PANEL_HELP_KEY_MAP.get(panel_id, panel_id)
    return PANEL_TOOLTIPS.get(help_id, "Live telemetry panel.")


def live_telemetry_tooltip(key: str, default: str = "") -> str:
    if key in LIVE_TELEMETRY_TOOLTIPS:
        return LIVE_TELEMETRY_TOOLTIPS[key]
    return default


def human_likeness_research_guide(locale: str = "en") -> dict[str, Any]:
    normalized = str(locale or "en").strip().lower()
    if normalized in HUMAN_LIKENESS_RESEARCH_GUIDE:
        return HUMAN_LIKENESS_RESEARCH_GUIDE[normalized]
    return HUMAN_LIKENESS_RESEARCH_GUIDE["en"]
