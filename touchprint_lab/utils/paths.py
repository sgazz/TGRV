from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TouchprintPaths:
    root: Path
    incoming: Path
    dataset: Path
    processed: Path
    reports: Path
    protocols: Path
    protocol_reports: Path
    studies: Path
    study_reports: Path
    features: Path
    analyzer: Path
    ui: Path
    plots: Path
    utils: Path

    @classmethod
    def create_default(cls) -> "TouchprintPaths":
        root = Path(__file__).resolve().parents[1]
        return cls(
            root=root,
            incoming=root / "incoming",
            dataset=root / "dataset",
            processed=root / "processed",
            reports=root / "processed" / "reports",
            protocols=root / "processed" / "protocols",
            protocol_reports=root / "processed" / "protocols" / "reports",
            studies=root / "processed" / "studies",
            study_reports=root / "processed" / "studies" / "reports",
            features=root / "processed" / "features",
            analyzer=root / "analyzer",
            ui=root / "ui",
            plots=root / "plots",
            utils=root / "utils",
        )

    def ensure_directories(self) -> None:
        for path in [
            self.incoming,
            self.dataset,
            self.processed,
            self.reports,
            self.protocols,
            self.protocol_reports,
            self.studies,
            self.study_reports,
            self.features,
            self.analyzer,
            self.ui,
            self.plots,
            self.utils,
        ]:
            path.mkdir(parents=True, exist_ok=True)
