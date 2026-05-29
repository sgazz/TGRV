from __future__ import annotations

import csv
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
try:  # pragma: no cover - optional Qt fallback for GUI runtimes
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
except Exception:  # pragma: no cover - headless fallback
    QRectF = Qt = QColor = QFont = QImage = QPainter = QPen = None  # type: ignore

try:  # pragma: no cover - optional headless rendering dependency
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - keep analyzer importable without Pillow
    Image = ImageDraw = ImageFont = None  # type: ignore

try:  # pragma: no cover - optional plotting dependency
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.lines import Line2D
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover - optional dependency fallback
    plt = None  # type: ignore
    Line2D = None  # type: ignore

from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.models import TouchSessionRecord
from touchprint_lab.analyzer.similarity import cluster_projection, cosine_similarity, euclidean_distance, normalized_distance_score, normalized_feature_matrix
from touchprint_lab.utils.numeric import safe_nanstd, safe_nanvar

logger = logging.getLogger(__name__)

EPSILON = 1e-12


@dataclass(slots=True)
class AnalysisFilters:
    user_ids: set[str] | None = None
    device_types: set[str] | None = None
    session_types: set[str] | None = None
    started_after: float | None = None
    started_before: float | None = None
    exported_after: float | None = None
    exported_before: float | None = None

    @classmethod
    def from_strings(
        cls,
        *,
        user_ids: str = "",
        device_types: str = "",
        session_types: str = "",
        started_after: str = "",
        started_before: str = "",
        exported_after: str = "",
        exported_before: str = "",
    ) -> "AnalysisFilters":
        def split_values(raw: str) -> set[str] | None:
            values = {value.strip() for value in raw.replace(";", ",").split(",") if value.strip()}
            return values or None

        def parse_float(raw: str) -> float | None:
            raw = raw.strip()
            if not raw:
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        return cls(
            user_ids=split_values(user_ids),
            device_types=split_values(device_types),
            session_types=split_values(session_types),
            started_after=parse_float(started_after),
            started_before=parse_float(started_before),
            exported_after=parse_float(exported_after),
            exported_before=parse_float(exported_before),
        )

    def matches(self, session: TouchSessionRecord) -> bool:
        if self.user_ids is not None and session.user_id not in self.user_ids:
            return False
        if self.device_types is not None and session.device_type not in self.device_types:
            return False
        if self.session_types is not None and session.session_type not in self.session_types:
            return False
        if self.started_after is not None and session.started_at < self.started_after:
            return False
        if self.started_before is not None and session.started_at > self.started_before:
            return False
        if self.exported_after is not None and session.exported_at < self.exported_after:
            return False
        if self.exported_before is not None and session.exported_at > self.exported_before:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "userIds": sorted(self.user_ids) if self.user_ids else [],
            "deviceTypes": sorted(self.device_types) if self.device_types else [],
            "sessionTypes": sorted(self.session_types) if self.session_types else [],
            "startedAfter": self.started_after,
            "startedBefore": self.started_before,
            "exportedAfter": self.exported_after,
            "exportedBefore": self.exported_before,
        }


@dataclass(slots=True)
class AnalysisSample:
    session: TouchSessionRecord
    vector: TouchFeatureVector


@dataclass(slots=True)
class PlotRect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(slots=True)
class BatchAnalysisReport:
    run_id: str
    generated_at: str
    filters: dict[str, Any]
    sample_count: int
    user_count: int
    session_labels: list[str]
    pairwise_rows: list[dict[str, Any]]
    similarity_summary: dict[str, Any]
    feature_importance_rows: list[dict[str, Any]]
    feature_correlation_matrix: np.ndarray
    similarity_matrix: np.ndarray
    distance_matrix: np.ndarray
    cluster_rows: list[dict[str, Any]]
    distribution_series: dict[str, dict[str, list[float]]]
    roc_preview: dict[str, Any]
    files: dict[str, str] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "generatedAt": self.generated_at,
            "filters": self.filters,
            "sampleCount": self.sample_count,
            "userCount": self.user_count,
            "similaritySummary": self.similarity_summary,
            "topFeatures": self.feature_importance_rows[:10],
            "weakFeatures": list(reversed(self.feature_importance_rows[-10:])),
            "files": self.files,
            "rocPreview": self.roc_preview,
        }

    def markdown_summary(self) -> str:
        lines = [
            "# Touchprint Batch Analysis Report",
            "",
            f"- Run ID: `{self.run_id}`",
            f"- Generated At: `{self.generated_at}`",
            f"- Samples: `{self.sample_count}`",
            f"- Users: `{self.user_count}`",
            "",
            "## Filters",
        ]
        for key, value in self.filters.items():
            lines.append(f"- {key}: `{value}`")
        lines.extend(
            [
                "",
                "## Similarity Summary",
            ]
        )
        for metric_name, stats in self.similarity_summary.items():
            lines.append(
                f"- {metric_name}: intra={stats['meanIntra']:.4f}, inter={stats['meanInter']:.4f}, "
                f"separation={stats['separationMargin']:.4f}, overlap={stats['overlapRatio']:.4f}"
            )
        lines.extend(["", "## Strongest Features"])
        for row in self.feature_importance_rows[:10]:
            lines.append(
                f"- {row['feature']}: discriminative={row['discriminativePower']:.4f}, "
                f"redundancy={row['redundancy']:.4f}"
            )
        lines.extend(["", "## Weakest / Noisiest Features"])
        for row in list(reversed(self.feature_importance_rows[-10:])):
            lines.append(
                f"- {row['feature']}: discriminative={row['discriminativePower']:.4f}, "
                f"noise={row['noiseRatio']:.4f}"
            )
        lines.append("")
        return "\n".join(lines)


class BatchAnalyzer:
    def __init__(self, bootstrap_samples: int = 750, kde_points: int = 200):
        self.bootstrap_samples = bootstrap_samples
        self.kde_points = kde_points

    def analyze(
        self,
        sessions: list[TouchSessionRecord],
        filters: AnalysisFilters | None = None,
    ) -> BatchAnalysisReport:
        filters = filters or AnalysisFilters()
        samples = self._prepare_samples(sessions, filters)
        vectors = [sample.vector for sample in samples]
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        generated_at = datetime.now(timezone.utc).isoformat()

        pairwise_rows = self._pairwise_rows(samples)
        similarity_summary = self._summarize_pairwise(pairwise_rows)
        feature_importance_rows, feature_correlation_matrix = self._feature_importance(vectors)
        similarity_matrix = self._pairwise_similarity_matrix(vectors)
        distance_matrix = self._pairwise_distance_matrix(vectors)
        cluster_rows = cluster_projection(vectors)
        distribution_series = self._distribution_series(pairwise_rows)
        roc_preview = self._roc_preview(pairwise_rows)

        return BatchAnalysisReport(
            run_id=run_id,
            generated_at=generated_at,
            filters=filters.to_dict(),
            sample_count=len(samples),
            user_count=len({sample.session.user_id for sample in samples}),
            session_labels=[sample.session.session_id for sample in samples],
            pairwise_rows=pairwise_rows,
            similarity_summary=similarity_summary,
            feature_importance_rows=feature_importance_rows,
            feature_correlation_matrix=feature_correlation_matrix,
            similarity_matrix=similarity_matrix,
            distance_matrix=distance_matrix,
            cluster_rows=cluster_rows,
            distribution_series=distribution_series,
            roc_preview=roc_preview,
        )

    def export_report(self, report: BatchAnalysisReport, output_dir: Path) -> BatchAnalysisReport:
        output_dir.mkdir(parents=True, exist_ok=True)
        run_dir = output_dir / f"batch_analysis_{report.run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        summary_path = run_dir / "summary.json"
        pairs_path = run_dir / "pairwise_comparisons.csv"
        features_path = run_dir / "feature_importance.csv"
        correlation_path = run_dir / "feature_correlation.csv"
        similarity_matrix_path = run_dir / "similarity_matrix.csv"
        distance_matrix_path = run_dir / "session_distance_matrix.csv"
        markdown_path = run_dir / "report.md"

        summary_path.write_text(json.dumps(report.summary_dict(), indent=2, sort_keys=True), encoding="utf-8")
        self._write_csv(pairs_path, report.pairwise_rows)
        self._write_csv(features_path, report.feature_importance_rows)
        self._write_matrix_csv(correlation_path, report.feature_correlation_matrix, TouchFeatureVector.FEATURE_FIELDS)
        self._write_matrix_csv(similarity_matrix_path, report.similarity_matrix, report.session_labels)
        self._write_matrix_csv(distance_matrix_path, report.distance_matrix, report.session_labels)
        markdown_path.write_text(report.markdown_summary(), encoding="utf-8")

        files = {
            "summaryJson": str(summary_path),
            "pairwiseComparisonsCsv": str(pairs_path),
            "featureImportanceCsv": str(features_path),
            "featureCorrelationCsv": str(correlation_path),
            "similarityMatrixCsv": str(similarity_matrix_path),
            "sessionDistanceMatrixCsv": str(distance_matrix_path),
            "markdownReport": str(markdown_path),
        }

        plot_files = self._render_plots(run_dir, report)
        files.update(plot_files)
        report.files = files

        summary_path.write_text(json.dumps(report.summary_dict(), indent=2, sort_keys=True), encoding="utf-8")
        markdown_path.write_text(report.markdown_summary(), encoding="utf-8")
        return report

    def _prepare_samples(self, sessions: list[TouchSessionRecord], filters: AnalysisFilters) -> list[AnalysisSample]:
        samples: list[AnalysisSample] = []
        for session in sessions:
            if not filters.matches(session):
                continue
            feature_payload = session.feature_vector
            if not feature_payload:
                continue
            vector = TouchFeatureVector.from_dict(feature_payload)
            samples.append(AnalysisSample(session=session, vector=vector))
        return samples

    def _pairwise_rows(self, samples: list[AnalysisSample]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for left_index, left in enumerate(samples):
            for right in samples[left_index + 1 :]:
                same_user = left.session.user_id == right.session.user_id
                row = {
                    "leftSessionId": left.session.session_id,
                    "rightSessionId": right.session.session_id,
                    "leftUserId": left.session.user_id,
                    "rightUserId": right.session.user_id,
                    "leftDeviceType": left.session.device_type,
                    "rightDeviceType": right.session.device_type,
                    "leftSessionType": left.session.session_type,
                    "rightSessionType": right.session.session_type,
                    "sameUser": same_user,
                    "sameDeviceType": left.session.device_type == right.session.device_type,
                    "sameSessionType": left.session.session_type == right.session.session_type,
                    "cosineSimilarity": cosine_similarity(left.vector, right.vector),
                    "euclideanDistance": euclidean_distance(left.vector, right.vector),
                    "normalizedSimilarityScore": normalized_distance_score(left.vector, right.vector),
                    "timeDeltaSeconds": abs(right.session.started_at - left.session.started_at),
                }
                rows.append(row)
        return rows

    def _summarize_pairwise(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {}

        metrics = {
            "cosineSimilarity": True,
            "normalizedSimilarityScore": True,
            "euclideanDistance": False,
        }
        summary: dict[str, Any] = {}
        for metric_name, higher_is_better in metrics.items():
            intra_values = _array([row[metric_name] for row in rows if row["sameUser"]])
            inter_values = _array([row[metric_name] for row in rows if not row["sameUser"]])
            summary[metric_name] = self._distribution_stats(metric_name, intra_values, inter_values, higher_is_better)

        normalized = summary["normalizedSimilarityScore"]
        normalized_intra = _array([row["normalizedSimilarityScore"] for row in rows if row["sameUser"]])
        normalized_inter = _array([row["normalizedSimilarityScore"] for row in rows if not row["sameUser"]])
        normalized_effect = _effect_size(normalized_intra, normalized_inter)
        normalized["repeatabilityScore"] = _clip01(float(np.mean(normalized_intra)) if len(normalized_intra) else 0.0)
        normalized["stabilityScore"] = _clip01(1.0 / (1.0 + float(safe_nanstd(normalized_intra)))) if len(normalized_intra) else 0.0
        normalized["separabilityScore"] = _clip01(1.0 / (1.0 + math.exp(-normalized_effect)))
        return summary

    def _distribution_stats(
        self,
        metric_name: str,
        intra_values: np.ndarray,
        inter_values: np.ndarray,
        higher_is_better: bool,
    ) -> dict[str, Any]:
        intra_mean = _mean(intra_values)
        inter_mean = _mean(inter_values)
        intra_std = _std(intra_values)
        inter_std = _std(inter_values)
        overlap_ratio = _histogram_overlap(intra_values, inter_values)
        if higher_is_better:
            separation_margin = intra_mean - inter_mean
        else:
            separation_margin = inter_mean - intra_mean
        pooled_std = math.sqrt(((intra_std**2) + (inter_std**2)) / 2.0)
        effect_size = separation_margin / (pooled_std + EPSILON)
        ci_intra = _bootstrap_ci(intra_values, samples=self.bootstrap_samples)
        ci_inter = _bootstrap_ci(inter_values, samples=self.bootstrap_samples)
        return {
            "metric": metric_name,
            "meanIntra": intra_mean,
            "meanInter": inter_mean,
            "stdIntra": intra_std,
            "stdInter": inter_std,
            "overlapRatio": overlap_ratio,
            "separationMargin": separation_margin,
            "effectSize": effect_size,
            "meanIntraCI": list(ci_intra),
            "meanInterCI": list(ci_inter),
        }

    def _roc_preview(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scores = _array([row["normalizedSimilarityScore"] for row in rows])
        labels = np.asarray([1 if row["sameUser"] else 0 for row in rows], dtype=np.int8)
        if len(scores) == 0:
            return {}

        thresholds = np.unique(scores)[::-1]
        thresholds = np.concatenate(([scores.max() + EPSILON], thresholds, [scores.min() - EPSILON]))
        tpr: list[float] = []
        fpr: list[float] = []
        fnr: list[float] = []
        youden: list[float] = []
        best_threshold = float(thresholds[0])
        best_j = -1.0
        best_index = 0

        for index, threshold in enumerate(thresholds):
            predicted = scores >= threshold
            tp = int(np.sum((predicted == 1) & (labels == 1)))
            fp = int(np.sum((predicted == 1) & (labels == 0)))
            tn = int(np.sum((predicted == 0) & (labels == 0)))
            fn = int(np.sum((predicted == 0) & (labels == 1)))
            current_tpr = tp / max(tp + fn, 1)
            current_fpr = fp / max(fp + tn, 1)
            current_fnr = fn / max(tp + fn, 1)
            current_j = current_tpr - current_fpr
            tpr.append(current_tpr)
            fpr.append(current_fpr)
            fnr.append(current_fnr)
            youden.append(current_j)
            if current_j > best_j:
                best_j = current_j
                best_threshold = float(threshold)
                best_index = index

        order = np.argsort(fpr)
        sorted_fpr = np.asarray(fpr, dtype=np.float64)[order]
        sorted_tpr = np.asarray(tpr, dtype=np.float64)[order]
        auc = float(np.trapezoid(sorted_tpr, sorted_fpr)) if len(sorted_fpr) > 1 else 0.0
        eer_index = int(np.argmin(np.abs(np.asarray(fpr) - np.asarray(fnr))))
        return {
            "thresholds": thresholds.tolist(),
            "tpr": tpr,
            "fpr": fpr,
            "fnr": fnr,
            "youdenJ": youden,
            "auc": auc,
            "bestThreshold": best_threshold,
            "bestYoudenJ": best_j,
            "bestThresholdIndex": best_index,
            "equalErrorRate": float((fpr[eer_index] + fnr[eer_index]) / 2.0),
            "equalErrorRateThreshold": float(thresholds[eer_index]),
        }

    def _feature_importance(self, vectors: list[TouchFeatureVector]) -> tuple[list[dict[str, Any]], np.ndarray]:
        if not vectors:
            return [], np.zeros((0, 0), dtype=np.float64)

        matrix = normalized_feature_matrix(vectors)
        if matrix.size == 0:
            return [], np.zeros((0, 0), dtype=np.float64)

        feature_names = TouchFeatureVector.FEATURE_FIELDS
        user_ids = np.asarray([vector.user_id for vector in vectors], dtype=object)
        correlation_matrix = _correlation_matrix(matrix)
        rows: list[dict[str, Any]] = []

        for index, feature_name in enumerate(feature_names):
            values = matrix[:, index]
            overall_variance = safe_nanvar(values)
            user_groups = [values[user_ids == user_id] for user_id in sorted(set(user_ids.tolist()))]
            user_groups = [group for group in user_groups if len(group)]
            user_means = np.asarray([float(np.mean(group)) for group in user_groups], dtype=np.float64) if user_groups else np.zeros(0)
            within_user_variance = float(np.mean([safe_nanvar(group) for group in user_groups])) if user_groups else 0.0
            between_user_variance = safe_nanvar(user_means)
            discriminative_power = between_user_variance / (within_user_variance + EPSILON)
            abs_correlations = [abs(float(correlation_matrix[index, other])) for other in range(len(feature_names)) if other != index]
            redundancy = float(np.mean(abs_correlations)) if abs_correlations else 0.0
            noise_ratio = within_user_variance / (overall_variance + EPSILON)
            rows.append(
                {
                    "feature": feature_name,
                    "overallVariance": overall_variance,
                    "withinUserVariance": within_user_variance,
                    "betweenUserVariance": between_user_variance,
                    "discriminativePower": discriminative_power,
                    "redundancy": redundancy,
                    "noiseRatio": noise_ratio,
                }
            )

        rows.sort(key=lambda row: (row["discriminativePower"], -row["redundancy"]), reverse=True)
        return rows, correlation_matrix

    def _pairwise_similarity_matrix(self, vectors: list[TouchFeatureVector]) -> np.ndarray:
        if not vectors:
            return np.zeros((0, 0), dtype=np.float64)
        matrix = normalized_feature_matrix(vectors)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        normalized = np.divide(matrix, np.where(norms == 0.0, 1.0, norms))
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            similarity = normalized @ normalized.T
        similarity = np.nan_to_num(similarity, nan=0.0, posinf=1.0, neginf=-1.0)
        return np.clip(similarity, -1.0, 1.0)

    def _pairwise_distance_matrix(self, vectors: list[TouchFeatureVector]) -> np.ndarray:
        if not vectors:
            return np.zeros((0, 0), dtype=np.float64)
        matrix = normalized_feature_matrix(vectors)
        return np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)

    def _distribution_series(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
        intra = _array([row["normalizedSimilarityScore"] for row in rows if row["sameUser"]])
        inter = _array([row["normalizedSimilarityScore"] for row in rows if not row["sameUser"]])
        if len(intra) and len(inter):
            lo = float(min(intra.min(), inter.min()))
            hi = float(max(intra.max(), inter.max()))
        elif len(intra):
            lo = float(intra.min())
            hi = float(intra.max())
        elif len(inter):
            lo = float(inter.min())
            hi = float(inter.max())
        else:
            return {"normalizedSimilarityScore": {"grid": [], "sameUserKde": [], "crossUserKde": []}}

        grid = np.linspace(lo, hi, self.kde_points)
        _, intra_kde = _gaussian_kde(intra, grid)
        _, inter_kde = _gaussian_kde(inter, grid)
        return {
            "normalizedSimilarityScore": {
                "grid": grid.tolist(),
                "sameUserKde": intra_kde.tolist(),
                "crossUserKde": inter_kde.tolist(),
            }
        }

    def _render_plots(self, output_dir: Path, report: BatchAnalysisReport) -> dict[str, str]:
        if plt is None:
            if Image is not None:
                return self._render_plots_pil(output_dir, report)
            if QImage is not None:
                return self._render_plots_qt(output_dir, report)
            logger.warning("No rendering backend is available; skipping PNG export.")
            return {}

        plot_files: dict[str, str] = {}
        intra = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if row["sameUser"]])
        inter = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if not row["sameUser"]])
        similarity_path = output_dir / "similarity_distribution.png"
        roc_path = output_dir / "roc_preview.png"
        similarity_heatmap_path = output_dir / "pairwise_similarity_heatmap.png"
        distance_heatmap_path = output_dir / "session_distance_matrix.png"
        correlation_heatmap_path = output_dir / "feature_correlation_heatmap.png"
        cluster_path = output_dir / "session_clustering.png"
        feature_importance_path = output_dir / "feature_importance.png"

        self._plot_similarity_distribution(similarity_path, intra, inter, report.distribution_series["normalizedSimilarityScore"])
        self._plot_roc_curve(roc_path, report.roc_preview)
        self._plot_heatmap(similarity_heatmap_path, report.similarity_matrix, "Pairwise Similarity", report.session_labels)
        self._plot_heatmap(distance_heatmap_path, report.distance_matrix, "Session Distance", report.session_labels)
        self._plot_heatmap(
            correlation_heatmap_path,
            report.feature_correlation_matrix,
            "Feature Correlation",
            list(TouchFeatureVector.FEATURE_FIELDS),
        )
        self._plot_cluster(cluster_path, report.cluster_rows)
        self._plot_feature_importance(feature_importance_path, report.feature_importance_rows)

        plot_files.update(
            {
                "similarityDistributionPng": str(similarity_path),
                "rocPreviewPng": str(roc_path),
                "pairwiseSimilarityHeatmapPng": str(similarity_heatmap_path),
                "sessionDistanceMatrixPng": str(distance_heatmap_path),
                "featureCorrelationHeatmapPng": str(correlation_heatmap_path),
                "sessionClusteringPng": str(cluster_path),
                "featureImportancePng": str(feature_importance_path),
            }
        )
        return plot_files

    def _render_plots_qt(self, output_dir: Path, report: BatchAnalysisReport) -> dict[str, str]:
        intra = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if row["sameUser"]])
        inter = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if not row["sameUser"]])
        similarity_path = output_dir / "similarity_distribution.png"
        roc_path = output_dir / "roc_preview.png"
        similarity_heatmap_path = output_dir / "pairwise_similarity_heatmap.png"
        distance_heatmap_path = output_dir / "session_distance_matrix.png"
        correlation_heatmap_path = output_dir / "feature_correlation_heatmap.png"
        cluster_path = output_dir / "session_clustering.png"
        feature_importance_path = output_dir / "feature_importance.png"

        self._draw_distribution_png(similarity_path, intra, inter, report.distribution_series["normalizedSimilarityScore"])
        self._draw_roc_png(roc_path, report.roc_preview)
        self._draw_heatmap_png(similarity_heatmap_path, report.similarity_matrix, "Pairwise Similarity", report.session_labels)
        self._draw_heatmap_png(distance_heatmap_path, report.distance_matrix, "Session Distance", report.session_labels)
        self._draw_heatmap_png(
            correlation_heatmap_path,
            report.feature_correlation_matrix,
            "Feature Correlation",
            list(TouchFeatureVector.FEATURE_FIELDS),
        )
        self._draw_cluster_png(cluster_path, report.cluster_rows)
        self._draw_feature_importance_png(feature_importance_path, report.feature_importance_rows)

        return {
            "similarityDistributionPng": str(similarity_path),
            "rocPreviewPng": str(roc_path),
            "pairwiseSimilarityHeatmapPng": str(similarity_heatmap_path),
            "sessionDistanceMatrixPng": str(distance_heatmap_path),
            "featureCorrelationHeatmapPng": str(correlation_heatmap_path),
            "sessionClusteringPng": str(cluster_path),
            "featureImportancePng": str(feature_importance_path),
        }

    def _render_plots_pil(self, output_dir: Path, report: BatchAnalysisReport) -> dict[str, str]:
        intra = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if row["sameUser"]])
        inter = _array([row["normalizedSimilarityScore"] for row in report.pairwise_rows if not row["sameUser"]])
        similarity_path = output_dir / "similarity_distribution.png"
        roc_path = output_dir / "roc_preview.png"
        similarity_heatmap_path = output_dir / "pairwise_similarity_heatmap.png"
        distance_heatmap_path = output_dir / "session_distance_matrix.png"
        correlation_heatmap_path = output_dir / "feature_correlation_heatmap.png"
        cluster_path = output_dir / "session_clustering.png"
        feature_importance_path = output_dir / "feature_importance.png"

        self._draw_distribution_png_pil(similarity_path, intra, inter, report.distribution_series["normalizedSimilarityScore"])
        self._draw_roc_png_pil(roc_path, report.roc_preview)
        self._draw_heatmap_png_pil(similarity_heatmap_path, report.similarity_matrix, "Pairwise Similarity", report.session_labels)
        self._draw_heatmap_png_pil(distance_heatmap_path, report.distance_matrix, "Session Distance", report.session_labels)
        self._draw_heatmap_png_pil(
            correlation_heatmap_path,
            report.feature_correlation_matrix,
            "Feature Correlation",
            list(TouchFeatureVector.FEATURE_FIELDS),
        )
        self._draw_cluster_png_pil(cluster_path, report.cluster_rows)
        self._draw_feature_importance_png_pil(feature_importance_path, report.feature_importance_rows)

        return {
            "similarityDistributionPng": str(similarity_path),
            "rocPreviewPng": str(roc_path),
            "pairwiseSimilarityHeatmapPng": str(similarity_heatmap_path),
            "sessionDistanceMatrixPng": str(distance_heatmap_path),
            "featureCorrelationHeatmapPng": str(correlation_heatmap_path),
            "sessionClusteringPng": str(cluster_path),
            "featureImportancePng": str(feature_importance_path),
        }

    def _draw_distribution_png_pil(
        self,
        output_path: Path,
        intra: np.ndarray,
        inter: np.ndarray,
        series: dict[str, list[float]],
    ) -> None:
        canvas = self._pil_canvas(1200, 800)
        draw = ImageDraw.Draw(canvas)
        self._pil_title(draw, "Normalized Similarity Distribution")
        rect = self._pil_plot_rect(1200, 800)
        self._pil_axes(draw, rect, "Score", "Density")
        bins = min(40, max(10, int(math.sqrt(max(len(intra) + len(inter), 1)))))
        y_max = 1.0
        if len(intra):
            intra_hist, edges = np.histogram(intra, bins=bins, density=True)
            y_max = max(y_max, float(np.max(intra_hist)))
            self._pil_histogram(draw, rect, edges, intra_hist, (0, 122, 255, 90))
        if len(inter):
            inter_hist, edges = np.histogram(inter, bins=bins, density=True)
            y_max = max(y_max, float(np.max(inter_hist)))
            self._pil_histogram(draw, rect, edges, inter_hist, (255, 59, 48, 90))
        grid = np.asarray(series.get("grid", []), dtype=np.float64)
        same_kde = np.asarray(series.get("sameUserKde", []), dtype=np.float64)
        cross_kde = np.asarray(series.get("crossUserKde", []), dtype=np.float64)
        if len(grid) and len(same_kde):
            self._pil_line(draw, rect, grid, same_kde, (0, 81, 213), y_max)
        if len(grid) and len(cross_kde):
            self._pil_line(draw, rect, grid, cross_kde, (214, 45, 32), y_max)
        canvas.save(str(output_path))

    def _draw_roc_png_pil(self, output_path: Path, roc_preview: dict[str, Any]) -> None:
        canvas = self._pil_canvas(900, 700)
        draw = ImageDraw.Draw(canvas)
        self._pil_title(draw, "ROC-Style Separation Preview")
        rect = self._pil_plot_rect(900, 700)
        self._pil_axes(draw, rect, "False Positive Rate", "True Positive Rate")
        self._pil_line(draw, rect, np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0]), (142, 142, 147), 1.0, dashed=True)
        fpr = np.asarray(roc_preview.get("fpr", []), dtype=np.float64)
        tpr = np.asarray(roc_preview.get("tpr", []), dtype=np.float64)
        if len(fpr) and len(tpr):
            order = np.argsort(fpr)
            auc = float(roc_preview.get("auc", 0.0))
            self._pil_line(draw, rect, fpr[order], tpr[order], (52, 199, 89), 1.0)
            draw.text((rect.left + 12, rect.top + 12), f"AUC={auc:.3f}", fill=(28, 28, 30), font=self._pil_font(14))
        canvas.save(str(output_path))

    def _draw_heatmap_png_pil(self, output_path: Path, matrix: np.ndarray, title: str, labels: list[str]) -> None:
        size = 900 if len(labels) > 12 else 800
        canvas = self._pil_canvas(size, size)
        draw = ImageDraw.Draw(canvas)
        self._pil_title(draw, title)
        rect = self._pil_plot_rect(size, size, top=80, right=40, bottom=100)
        self._pil_axes(draw, rect, "", "")
        if matrix.size:
            normalized = self._normalize_matrix(matrix)
            rows, cols = normalized.shape
            cell_width = rect.width / max(cols, 1)
            cell_height = rect.height / max(rows, 1)
            for row_index in range(rows):
                for col_index in range(cols):
                    value = float(normalized[row_index, col_index])
                    left = int(rect.left + col_index * cell_width)
                    top = int(rect.top + row_index * cell_height)
                    right = int(rect.left + (col_index + 1) * cell_width) + 1
                    bottom = int(rect.top + (row_index + 1) * cell_height) + 1
                    draw.rectangle([left, top, right, bottom], fill=self._heat_rgb(value))
            if labels:
                font = self._pil_font(8 if len(labels) > 12 else 10)
                max_labels = min(len(labels), 20)
                step = max(1, len(labels) // max_labels)
                for index in range(0, len(labels), step):
                    x = rect.left + (index + 0.5) * cell_width
                    y = rect.bottom + 6
                    draw.text((x, y), labels[index][:16], fill=(28, 28, 30), font=font)
                    y_left = rect.top + (index + 0.5) * cell_height
                    draw.text((8, y_left), labels[index][:16], fill=(28, 28, 30), font=font)
        canvas.save(str(output_path))

    def _draw_cluster_png_pil(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = self._pil_canvas(1000, 800)
        draw = ImageDraw.Draw(canvas)
        self._pil_title(draw, "Session Clustering Preview")
        rect = self._pil_plot_rect(1000, 800)
        self._pil_axes(draw, rect, "Component 1", "Component 2")
        if rows:
            xs = np.asarray([row["x"] for row in rows], dtype=np.float64)
            ys = np.asarray([row["y"] for row in rows], dtype=np.float64)
            user_ids = [row["userId"] for row in rows]
            unique_users = {user_id: index for index, user_id in enumerate(sorted(set(user_ids)))}
            x_min, x_max = float(xs.min()), float(xs.max())
            y_min, y_max = float(ys.min()), float(ys.max())
            x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
            y_span = y_max - y_min if not math.isclose(y_min, y_max) else 1.0
            palette = [(0, 122, 255), (255, 59, 48), (52, 199, 89), (255, 149, 0), (175, 82, 222), (100, 210, 255), (255, 45, 85), (142, 142, 147)]
            for row in rows:
                color = palette[unique_users[row["userId"]] % len(palette)]
                x = rect.left + ((row["x"] - x_min) / x_span) * rect.width
                y = rect.bottom - ((row["y"] - y_min) / y_span) * rect.height
                self._pil_circle(draw, int(x), int(y), 5, color)
        canvas.save(str(output_path))

    def _draw_feature_importance_png_pil(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = self._pil_canvas(1100, 800)
        draw = ImageDraw.Draw(canvas)
        self._pil_title(draw, "Feature Discriminative Power")
        rect = self._pil_plot_rect(1100, 800, right=240)
        self._pil_axes(draw, rect, "Discriminative power", "")
        top_rows = rows[:15]
        if top_rows:
            max_value = max(float(row["discriminativePower"]) for row in top_rows) or 1.0
            bar_height = rect.height / len(top_rows)
            font = self._pil_font(11)
            for index, row in enumerate(reversed(top_rows)):
                value = float(row["discriminativePower"])
                width = (value / max_value) * rect.width
                top = rect.top + index * bar_height
                draw.rectangle([rect.left, top, rect.left + width, top + bar_height * 0.72], fill=(52, 199, 89))
                draw.text((rect.right + 12, top + bar_height * 0.25), row["feature"], fill=(28, 28, 30), font=font)
        canvas.save(str(output_path))

    def _pil_canvas(self, width: int, height: int):
        image = Image.new("RGB", (width, height), "white")
        return image

    def _pil_plot_rect(self, width: int, height: int, left: int = 90, top: int = 70, right: int = 60, bottom: int = 90) -> PlotRect:
        return PlotRect(left, top, width - right, height - bottom)

    def _pil_font(self, size: int):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

    def _pil_title(self, draw, title: str) -> None:
        draw.text((24, 18), title, fill=(28, 28, 30), font=self._pil_font(18))

    def _pil_axes(self, draw, rect, xlabel: str, ylabel: str) -> None:
        draw.rectangle([rect.left, rect.top, rect.right, rect.bottom], outline=(209, 209, 214), width=1)
        font = self._pil_font(11)
        if xlabel:
            draw.text(((rect.left + rect.right) / 2 - 40, rect.bottom + 44), xlabel, fill=(28, 28, 30), font=font)
        if ylabel:
            draw.text((rect.left - 48, (rect.top + rect.bottom) / 2), ylabel, fill=(28, 28, 30), font=font)

    def _pil_histogram(self, draw, rect, edges: np.ndarray, values: np.ndarray, color: tuple[int, int, int, int]) -> None:
        if len(values) == 0:
            return
        max_value = max(float(np.max(values)), 1e-9)
        x_min, x_max = float(edges[0]), float(edges[-1])
        x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
        for index, value in enumerate(values):
            left = rect.left + ((edges[index] - x_min) / x_span) * rect.width
            right = rect.left + ((edges[index + 1] - x_min) / x_span) * rect.width
            bar_height = (float(value) / max_value) * rect.height
            draw.rectangle([left, rect.bottom - bar_height, right, rect.bottom], fill=color[:3])

    def _pil_line(self, draw, rect, x_values: np.ndarray, y_values: np.ndarray, color: tuple[int, int, int], y_scale: float, dashed: bool = False) -> None:
        if len(x_values) == 0 or len(y_values) == 0:
            return
        x_min, x_max = float(np.min(x_values)), float(np.max(x_values))
        y_min, y_max = 0.0, max(float(np.max(y_values)), y_scale)
        x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
        y_span = y_max - y_min if not math.isclose(y_min, y_max) else 1.0
        points = []
        for x_value, y_value in zip(x_values, y_values):
            x = rect.left + ((float(x_value) - x_min) / x_span) * rect.width
            y = rect.bottom - ((float(y_value) - y_min) / y_span) * rect.height
            points.append((x, y))
        if dashed:
            for index in range(1, len(points)):
                if index % 2 == 0:
                    continue
                draw.line([points[index - 1], points[index]], fill=color, width=2)
        else:
            if len(points) >= 2:
                draw.line(points, fill=color, width=2)

    def _pil_circle(self, draw, x: int, y: int, radius: int, color: tuple[int, int, int]) -> None:
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color, outline=(255, 255, 255))

    def _heat_rgb(self, value: float) -> tuple[int, int, int]:
        value = float(np.clip(value, 0.0, 1.0))
        red = int(255 * value)
        blue = int(255 * (1.0 - value))
        green = int(180 * (1.0 - abs(value - 0.5) * 2.0))
        return red, green, blue

    def _plot_rect(self, width: int, height: int, left: int = 90, top: int = 70, right: int = 60, bottom: int = 90) -> Any:
        return QRectF(left, top, width - left - right, height - top - bottom)

    def _plot_similarity_distribution(
        self,
        output_path: Path,
        intra: np.ndarray,
        inter: np.ndarray,
        series: dict[str, list[float]],
    ) -> None:
        fig, ax = plt.subplots(figsize=(10, 6))
        bins = min(40, max(10, int(math.sqrt(max(len(intra) + len(inter), 1)))))
        if len(intra):
            ax.hist(intra, bins=bins, density=True, alpha=0.35, color="#007aff", label="same-user")
        if len(inter):
            ax.hist(inter, bins=bins, density=True, alpha=0.35, color="#ff3b30", label="cross-user")
        grid = np.asarray(series.get("grid", []), dtype=np.float64)
        same_kde = np.asarray(series.get("sameUserKde", []), dtype=np.float64)
        cross_kde = np.asarray(series.get("crossUserKde", []), dtype=np.float64)
        if len(grid) and len(same_kde):
            ax.plot(grid, same_kde, color="#007aff", linewidth=2)
        if len(grid) and len(cross_kde):
            ax.plot(grid, cross_kde, color="#ff3b30", linewidth=2)
        ax.set_title("Normalized Similarity Distribution")
        ax.set_xlabel("Normalized similarity score")
        ax.set_ylabel("Density")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

    def _plot_roc_curve(self, output_path: Path, roc_preview: dict[str, Any]) -> None:
        fig, ax = plt.subplots(figsize=(7, 6))
        fpr = np.asarray(roc_preview.get("fpr", []), dtype=np.float64)
        tpr = np.asarray(roc_preview.get("tpr", []), dtype=np.float64)
        if len(fpr) and len(tpr):
            order = np.argsort(fpr)
            ax.plot(fpr[order], tpr[order], color="#007aff", linewidth=2, label=f"AUC={roc_preview.get('auc', 0.0):.3f}")
            ax.plot([0, 1], [0, 1], linestyle="--", color="#8e8e93", linewidth=1)
        ax.set_title("ROC-Style Separation Preview")
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.legend(loc="lower right")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

    def _plot_heatmap(self, output_path: Path, matrix: np.ndarray, title: str, labels: list[str] | None = None) -> None:
        fig, ax = plt.subplots(figsize=(8, 7))
        if matrix.size:
            image = ax.imshow(matrix, cmap="viridis", aspect="auto")
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
            if labels:
                tick_positions = list(range(len(labels)))
                ax.set_xticks(tick_positions)
                ax.set_yticks(tick_positions)
                ax.set_xticklabels(labels, rotation=90, fontsize=7)
                ax.set_yticklabels(labels, fontsize=7)
        ax.set_title(title)
        ax.set_xlabel("Session / Feature")
        ax.set_ylabel("Session / Feature")
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

    def _plot_cluster(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        fig, ax = plt.subplots(figsize=(8, 6))
        if rows:
            colors = [row["userId"] for row in rows]
            unique_users = {user_id: index for index, user_id in enumerate(sorted(set(colors)))}
            scatter = ax.scatter(
                [row["x"] for row in rows],
                [row["y"] for row in rows],
                c=[unique_users[row["userId"]] for row in rows],
                cmap="tab10",
                s=40,
                alpha=0.85,
            )
            legend_items = []
            for user_id, index in unique_users.items():
                legend_items.append((user_id, index))
            handles = []
            for user_id, index in legend_items[:10]:
                color = plt.get_cmap("tab10")(index % 10)
                handles.append(Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markersize=8, label=user_id))
            if handles:
                ax.legend(handles=handles, loc="best", fontsize="small")
        ax.set_title("Session Clustering Preview")
        ax.set_xlabel("Component 1")
        ax.set_ylabel("Component 2")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

    def _plot_feature_importance(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        fig, ax = plt.subplots(figsize=(10, 6))
        top_rows = rows[:15]
        if top_rows:
            labels = [row["feature"] for row in top_rows][::-1]
            values = [row["discriminativePower"] for row in top_rows][::-1]
            ax.barh(labels, values, color="#34c759")
        ax.set_title("Feature Discriminative Power")
        ax.set_xlabel("Between / Within Variance Ratio")
        ax.grid(True, axis="x", alpha=0.2)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

    def _draw_distribution_png(
        self,
        output_path: Path,
        intra: np.ndarray,
        inter: np.ndarray,
        series: dict[str, list[float]],
    ) -> None:
        canvas = self._create_canvas(1200, 800)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_title(painter, "Normalized Similarity Distribution")
        plot_rect = self._plot_rect(1200, 800)
        self._draw_axes(painter, plot_rect, "Score", "Density")
        bins = min(40, max(10, int(math.sqrt(max(len(intra) + len(inter), 1)))))
        y_max = 1.0
        if len(intra):
            intra_hist, edges = np.histogram(intra, bins=bins, density=True)
            y_max = max(y_max, float(np.max(intra_hist)) if len(intra_hist) else 1.0)
            self._draw_histogram_bars(painter, plot_rect, edges, intra_hist, QColor("#007aff", 120))
        if len(inter):
            inter_hist, edges = np.histogram(inter, bins=bins, density=True)
            y_max = max(y_max, float(np.max(inter_hist)) if len(inter_hist) else 1.0)
            self._draw_histogram_bars(painter, plot_rect, edges, inter_hist, QColor("#ff3b30", 120))
        grid = np.asarray(series.get("grid", []), dtype=np.float64)
        same_kde = np.asarray(series.get("sameUserKde", []), dtype=np.float64)
        cross_kde = np.asarray(series.get("crossUserKde", []), dtype=np.float64)
        if len(grid) and len(same_kde):
            self._draw_line(painter, plot_rect, grid, same_kde, QColor("#0051d5"), y_max)
        if len(grid) and len(cross_kde):
            self._draw_line(painter, plot_rect, grid, cross_kde, QColor("#d62d20"), y_max)
        painter.end()
        canvas.save(str(output_path))

    def _draw_roc_png(self, output_path: Path, roc_preview: dict[str, Any]) -> None:
        canvas = self._create_canvas(900, 700)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_title(painter, "ROC-Style Separation Preview")
        plot_rect = self._plot_rect(900, 700)
        self._draw_axes(painter, plot_rect, "False Positive Rate", "True Positive Rate")
        self._draw_line(painter, plot_rect, np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0]), QColor("#8e8e93"), 1.0, dashed=True)
        fpr = np.asarray(roc_preview.get("fpr", []), dtype=np.float64)
        tpr = np.asarray(roc_preview.get("tpr", []), dtype=np.float64)
        if len(fpr) and len(tpr):
            order = np.argsort(fpr)
            auc = float(roc_preview.get("auc", 0.0))
            self._draw_line(painter, plot_rect, fpr[order], tpr[order], QColor("#34c759"), 1.0)
            painter.setPen(QColor("#1c1c1e"))
            painter.drawText(plot_rect.adjusted(12, 12, -12, -12), f"AUC={auc:.3f}")
        painter.end()
        canvas.save(str(output_path))

    def _draw_heatmap_png(self, output_path: Path, matrix: np.ndarray, title: str, labels: list[str]) -> None:
        size = 900 if len(labels) > 12 else 800
        canvas = self._create_canvas(size, size)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_title(painter, title)
        plot_rect = self._plot_rect(size, size, top=80, right=40, bottom=100)
        self._draw_axes(painter, plot_rect, "", "")
        if matrix.size:
            normalized = self._normalize_matrix(matrix)
            rows, cols = normalized.shape
            cell_width = plot_rect.width() / max(cols, 1)
            cell_height = plot_rect.height() / max(rows, 1)
            for row_index in range(rows):
                for col_index in range(cols):
                    value = float(normalized[row_index, col_index])
                    painter.fillRect(
                        int(plot_rect.left() + col_index * cell_width),
                        int(plot_rect.top() + row_index * cell_height),
                        int(math.ceil(cell_width)),
                        int(math.ceil(cell_height)),
                        self._heat_color(value),
                    )
            if labels:
                painter.setPen(QColor("#1c1c1e"))
                font = QFont()
                font.setPointSize(7)
                painter.setFont(font)
                max_labels = min(len(labels), 24)
                step = max(1, len(labels) // max_labels)
                for index in range(0, len(labels), step):
                    x = plot_rect.left() + (index + 0.5) * cell_width
                    y = plot_rect.bottom() + 10
                    painter.save()
                    painter.translate(int(x), int(y))
                    painter.rotate(90)
                    painter.drawText(0, 0, labels[index])
                    painter.restore()
                    y_left = plot_rect.top() + (index + 0.5) * cell_height
                    painter.drawText(10, int(y_left), labels[index][:18])
        painter.end()
        canvas.save(str(output_path))

    def _draw_cluster_png(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = self._create_canvas(1000, 800)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_title(painter, "Session Clustering Preview")
        plot_rect = self._plot_rect(1000, 800)
        self._draw_axes(painter, plot_rect, "Component 1", "Component 2")
        if rows:
            xs = np.asarray([row["x"] for row in rows], dtype=np.float64)
            ys = np.asarray([row["y"] for row in rows], dtype=np.float64)
            user_ids = [row["userId"] for row in rows]
            unique_users = {user_id: index for index, user_id in enumerate(sorted(set(user_ids)))}
            x_min, x_max = float(xs.min()), float(xs.max())
            y_min, y_max = float(ys.min()), float(ys.max())
            x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
            y_span = y_max - y_min if not math.isclose(y_min, y_max) else 1.0
            palette = ["#007aff", "#ff3b30", "#34c759", "#ff9500", "#af52de", "#64d2ff", "#ff2d55", "#8e8e93"]
            for row in rows:
                color = QColor(palette[unique_users[row["userId"]] % len(palette)])
                x = plot_rect.left() + ((row["x"] - x_min) / x_span) * plot_rect.width()
                y = plot_rect.bottom() - ((row["y"] - y_min) / y_span) * plot_rect.height()
                painter.setBrush(color)
                painter.setPen(QColor("#ffffff"))
                painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)
        painter.end()
        canvas.save(str(output_path))

    def _draw_feature_importance_png(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        canvas = self._create_canvas(1100, 800)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_title(painter, "Feature Discriminative Power")
        plot_rect = self._plot_rect(1100, 800, right=220)
        self._draw_axes(painter, plot_rect, "Discriminative power", "")
        top_rows = rows[:15]
        if top_rows:
            max_value = max(float(row["discriminativePower"]) for row in top_rows) or 1.0
            bar_height = plot_rect.height() / len(top_rows)
            for index, row in enumerate(reversed(top_rows)):
                value = float(row["discriminativePower"])
                width = (value / max_value) * plot_rect.width()
                top = plot_rect.top() + index * bar_height
                painter.fillRect(int(plot_rect.left()), int(top), int(width), int(bar_height * 0.75), QColor("#34c759"))
                painter.setPen(QColor("#1c1c1e"))
                painter.drawText(int(plot_rect.right()) + 12, int(top + bar_height * 0.5), row["feature"])
        painter.end()
        canvas.save(str(output_path))

    def _draw_title(self, painter: QPainter, title: str) -> None:
        painter.setPen(QColor("#1c1c1e"))
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(30, 35, title)

    def _draw_axes(self, painter: QPainter, rect: Any, xlabel: str, ylabel: str) -> None:
        painter.setPen(QColor("#d1d1d6"))
        painter.drawRect(rect)
        painter.setPen(QColor("#1c1c1e"))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        if xlabel:
            painter.drawText(int(rect.left() + rect.width() / 2 - 40), int(rect.bottom() + 50), xlabel)
        if ylabel:
            painter.save()
            painter.translate(int(rect.left() - 55), int(rect.top() + rect.height() / 2 + 40))
            painter.rotate(-90)
            painter.drawText(0, 0, ylabel)
            painter.restore()

    def _draw_histogram_bars(self, painter: QPainter, rect: Any, edges: np.ndarray, values: np.ndarray, color: QColor) -> None:
        if len(values) == 0:
            return
        max_value = max(float(np.max(values)), 1e-9)
        x_min, x_max = float(edges[0]), float(edges[-1])
        x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
        for index, value in enumerate(values):
            left = rect.left() + ((edges[index] - x_min) / x_span) * rect.width()
            right = rect.left() + ((edges[index + 1] - x_min) / x_span) * rect.width()
            bar_height = (float(value) / max_value) * rect.height()
            painter.fillRect(int(left), int(rect.bottom() - bar_height), max(1, int(right - left)), int(bar_height), color)

    def _draw_line(
        self,
        painter: QPainter,
        rect: Any,
        x_values: np.ndarray,
        y_values: np.ndarray,
        color: QColor,
        y_scale: float,
        dashed: bool = False,
    ) -> None:
        if len(x_values) == 0 or len(y_values) == 0:
            return
        x_min, x_max = float(np.min(x_values)), float(np.max(x_values))
        y_min, y_max = 0.0, max(float(np.max(y_values)), y_scale)
        x_span = x_max - x_min if not math.isclose(x_min, x_max) else 1.0
        y_span = y_max - y_min if not math.isclose(y_min, y_max) else 1.0
        pen = QPen(color)
        pen.setWidth(2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)  # type: ignore[attr-defined]
        painter.setPen(pen)
        previous_point: tuple[int, int] | None = None
        for x_value, y_value in zip(x_values, y_values):
            x = rect.left() + ((float(x_value) - x_min) / x_span) * rect.width()
            y = rect.bottom() - ((float(y_value) - y_min) / y_span) * rect.height()
            current_point = (int(x), int(y))
            if previous_point is not None:
                painter.drawLine(previous_point[0], previous_point[1], current_point[0], current_point[1])
            previous_point = current_point

    def _normalize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        if matrix.size == 0:
            return matrix
        finite = np.nan_to_num(matrix.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
        span = maximum - minimum if not math.isclose(minimum, maximum) else 1.0
        return (finite - minimum) / span

    def _heat_color(self, value: float) -> QColor:
        value = float(np.clip(value, 0.0, 1.0))
        red = int(255 * value)
        blue = int(255 * (1.0 - value))
        green = int(180 * (1.0 - abs(value - 0.5) * 2.0))
        return QColor(red, green, blue)

    def _create_canvas(self, width: int, height: int) -> QImage:
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        return image

    def _plot_rect(self, width: int, height: int, left: int = 90, top: int = 70, right: int = 60, bottom: int = 90) -> Any:
        return QRectF(left, top, width - left - right, height - top - bottom)

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_matrix_csv(path: Path, matrix: np.ndarray, labels: Iterable[str]) -> None:
        labels_list = list(labels)
        if matrix.size == 0:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["label", *labels_list])
            for label, row in zip(labels_list, matrix.tolist()):
                writer.writerow([label, *row])


def _array(values: Iterable[float]) -> np.ndarray:
    return np.asarray([float(value) for value in values if value is not None and np.isfinite(float(value))], dtype=np.float64)


def _mean(values: np.ndarray) -> float:
    return float(np.mean(values)) if len(values) else 0.0


def _std(values: np.ndarray) -> float:
    return safe_nanstd(values)


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _bootstrap_ci(values: np.ndarray, confidence: float = 0.95, samples: int = 750) -> tuple[float, float]:
    if len(values) == 0:
        return 0.0, 0.0
    if len(values) == 1:
        single = float(values[0])
        return single, single
    rng = np.random.default_rng(1337)
    bootstrap_means = np.empty(samples, dtype=np.float64)
    for index in range(samples):
        drawn = rng.choice(values, size=len(values), replace=True)
        bootstrap_means[index] = float(np.mean(drawn))
    alpha = (1.0 - confidence) / 2.0
    return float(np.quantile(bootstrap_means, alpha)), float(np.quantile(bootstrap_means, 1.0 - alpha))


def _histogram_overlap(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) == 0 or len(right) == 0:
        return 0.0
    lo = float(min(left.min(), right.min()))
    hi = float(max(left.max(), right.max()))
    if math.isclose(lo, hi):
        return 1.0
    bins = min(40, max(10, int(math.sqrt(len(left) + len(right)))))
    left_hist, edges = np.histogram(left, bins=bins, range=(lo, hi), density=True)
    right_hist, _ = np.histogram(right, bins=edges, density=True)
    bin_widths = np.diff(edges)
    overlap = float(np.sum(np.minimum(left_hist, right_hist) * bin_widths))
    return _clip01(overlap)


def _gaussian_kde(values: np.ndarray, grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(values) == 0 or len(grid) == 0:
        return grid, np.zeros_like(grid, dtype=np.float64)
    std = safe_nanstd(values)
    if std <= EPSILON:
        bandwidth = max(float(np.ptp(values)) / 20.0, 1e-3)
    else:
        bandwidth = max(1.06 * std * (len(values) ** (-1.0 / 5.0)), 1e-3)
    diffs = (grid[:, None] - values[None, :]) / bandwidth
    density = np.exp(-0.5 * diffs**2).sum(axis=1) / (len(values) * bandwidth * math.sqrt(2.0 * math.pi))
    return grid, density


def _effect_size(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) == 0 or len(right) == 0:
        return 0.0
    left_mean = float(np.mean(left))
    right_mean = float(np.mean(right))
    left_var = safe_nanvar(left)
    right_var = safe_nanvar(right)
    pooled_std = math.sqrt((left_var + right_var) / 2.0)
    return (left_mean - right_mean) / (pooled_std + EPSILON)


def _correlation_matrix(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.zeros((0, 0), dtype=np.float64)
    centered = matrix - np.mean(matrix, axis=0, keepdims=True)
    scale = np.asarray([safe_nanstd(centered[:, index]) for index in range(centered.shape[1])], dtype=np.float64).reshape(1, -1)
    standardized = np.divide(centered, np.where(scale == 0.0, 1.0, scale))
    denominator = max(standardized.shape[0] - 1, 1)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        correlation = (standardized.T @ standardized) / denominator
    correlation = np.nan_to_num(correlation, nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(correlation, 1.0)
    return correlation
