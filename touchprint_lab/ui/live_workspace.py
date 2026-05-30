from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class LiveWorkspaceState:
    active_preset: str = "Research Cockpit"
    panel_order: list[str] = field(default_factory=list)
    collapsed: dict[str, bool] = field(default_factory=dict)
    panel_heights: dict[str, int] = field(default_factory=dict)
    visible_panels: dict[str, bool] = field(default_factory=dict)


class LiveWorkspaceLayoutManager:
    PRESETS: dict[str, list[str]] = {
        "Research Cockpit": [
            "trajectory",
            "force_radius",
            "signature_layer",
            "groove_view",
            "groove_view_3d",
            "pin_keyboard_mirror",
            "phase_timeline",
            "pressure_fingerprint",
            "groove_stability",
            "human_likeness",
        ],
        "PIN Study": [
            "pin_keyboard_mirror",
            "force_radius",
            "trajectory",
            "phase_timeline",
            "pressure_fingerprint",
            "groove_stability",
            "human_likeness",
            "signature_layer",
            "groove_view",
            "groove_view_3d",
        ],
        "Human-Likeness Focus": [
            "human_likeness",
            "force_radius",
            "pressure_fingerprint",
            "groove_stability",
            "trajectory",
            "signature_layer",
            "phase_timeline",
            "pin_keyboard_mirror",
            "groove_view",
            "groove_view_3d",
        ],
        "Groove Analysis": [
            "groove_view",
            "groove_view_3d",
            "signature_layer",
            "trajectory",
            "force_radius",
            "phase_timeline",
            "pressure_fingerprint",
            "groove_stability",
            "human_likeness",
            "pin_keyboard_mirror",
        ],
        "Compact Screen": [
            "trajectory",
            "force_radius",
            "pin_keyboard_mirror",
            "groove_stability",
            "human_likeness",
            "phase_timeline",
            "pressure_fingerprint",
            "signature_layer",
            "groove_view",
            "groove_view_3d",
        ],
        "Custom": [],
    }

    def __init__(self, settings_path: Path, panel_ids: list[str]) -> None:
        self.settings_path = settings_path
        self.panel_ids = list(panel_ids)
        self.state = LiveWorkspaceState(
            panel_order=self._sanitize_order(self.PRESETS["Research Cockpit"]),
            visible_panels={panel_id: True for panel_id in panel_ids},
        )
        self.load()

    def _sanitize_order(self, ordered_ids: list[str]) -> list[str]:
        dedup: list[str] = []
        seen: set[str] = set()
        for panel_id in ordered_ids:
            if panel_id in self.panel_ids and panel_id not in seen:
                dedup.append(panel_id)
                seen.add(panel_id)
        for panel_id in self.panel_ids:
            if panel_id not in seen:
                dedup.append(panel_id)
        return dedup

    def load(self) -> None:
        if not self.settings_path.exists():
            return
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.state.active_preset = str(payload.get("activePreset", "Custom"))
        self.state.panel_order = self._sanitize_order(list(payload.get("panelOrder", [])))
        self.state.collapsed = {k: bool(v) for k, v in dict(payload.get("collapsed", {})).items() if k in self.panel_ids}
        self.state.panel_heights = {
            k: int(v)
            for k, v in dict(payload.get("panelHeights", {})).items()
            if k in self.panel_ids and isinstance(v, (int, float))
        }
        self.state.visible_panels = {
            panel_id: bool(dict(payload.get("visiblePanels", {})).get(panel_id, True))
            for panel_id in self.panel_ids
        }

    def save(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "activePreset": self.state.active_preset,
            "panelOrder": self.state.panel_order,
            "collapsed": self.state.collapsed,
            "panelHeights": self.state.panel_heights,
            "visiblePanels": self.state.visible_panels,
        }
        self.settings_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def apply_preset(self, preset_name: str) -> None:
        name = preset_name if preset_name in self.PRESETS else "Research Cockpit"
        if name == "Custom":
            self.state.active_preset = "Custom"
            return
        self.state.active_preset = name
        self.state.panel_order = self._sanitize_order(self.PRESETS[name])
        self.state.collapsed = {}
        self.state.visible_panels = {panel_id: True for panel_id in self.panel_ids}

    def reset_default(self) -> None:
        self.state = LiveWorkspaceState(
            active_preset="Research Cockpit",
            panel_order=self._sanitize_order(self.PRESETS["Research Cockpit"]),
            collapsed={},
            panel_heights={},
            visible_panels={panel_id: True for panel_id in self.panel_ids},
        )

    def move_panel(self, panel_id: str, direction: str) -> None:
        if panel_id not in self.state.panel_order:
            return
        index = self.state.panel_order.index(panel_id)
        if direction in {"left", "up"} and index > 0:
            swap_index = index - 1
        elif direction in {"right", "down"} and index < len(self.state.panel_order) - 1:
            swap_index = index + 1
        else:
            return
        self.state.panel_order[index], self.state.panel_order[swap_index] = (
            self.state.panel_order[swap_index],
            self.state.panel_order[index],
        )
        self.state.active_preset = "Custom"
