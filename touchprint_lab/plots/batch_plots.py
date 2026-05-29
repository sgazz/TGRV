from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from touchprint_lab.analyzer.batch import BatchAnalysisReport


class BatchPlotsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.tabs = QTabWidget()

        self.distribution_tab = QWidget()
        self.matrices_tab = QWidget()
        self.cluster_tab = QWidget()

        self._build_distribution_tab()
        self._build_matrices_tab()
        self._build_cluster_tab()

        self.tabs.addTab(self.distribution_tab, "Distributions")
        self.tabs.addTab(self.matrices_tab, "Matrices")
        self.tabs.addTab(self.cluster_tab, "Clustering")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    def _build_distribution_tab(self) -> None:
        self.similarity_distribution_plot = pg.PlotWidget(title="Normalized Similarity Distribution")
        self.similarity_distribution_plot.setBackground("w")
        self.similarity_distribution_plot.showGrid(x=True, y=True, alpha=0.2)
        self.intra_hist_curve = self.similarity_distribution_plot.plot([], [], pen=pg.mkPen("#007aff", width=2))
        self.inter_hist_curve = self.similarity_distribution_plot.plot([], [], pen=pg.mkPen("#ff3b30", width=2))
        self.intra_kde_curve = self.similarity_distribution_plot.plot([], [], pen=pg.mkPen("#0051d5", width=3))
        self.inter_kde_curve = self.similarity_distribution_plot.plot([], [], pen=pg.mkPen("#d62d20", width=3))

        self.roc_plot = pg.PlotWidget(title="ROC-Style Separation Preview")
        self.roc_plot.setBackground("w")
        self.roc_plot.showGrid(x=True, y=True, alpha=0.2)
        self.roc_curve = self.roc_plot.plot([], [], pen=pg.mkPen("#34c759", width=2))
        self.roc_baseline = self.roc_plot.plot([], [], pen=pg.mkPen("#8e8e93", width=1, style=Qt.PenStyle.DashLine))

        layout = QVBoxLayout(self.distribution_tab)
        layout.addWidget(self.similarity_distribution_plot, 1)
        layout.addWidget(self.roc_plot, 1)

    def _build_matrices_tab(self) -> None:
        self.similarity_heatmap_plot = pg.PlotWidget(title="Pairwise Similarity Heatmap")
        self.similarity_heatmap_plot.setBackground("w")
        self.similarity_image = pg.ImageItem()
        self.similarity_heatmap_plot.addItem(self.similarity_image)

        self.distance_heatmap_plot = pg.PlotWidget(title="Session Distance Matrix")
        self.distance_heatmap_plot.setBackground("w")
        self.distance_image = pg.ImageItem()
        self.distance_heatmap_plot.addItem(self.distance_image)

        self.correlation_heatmap_plot = pg.PlotWidget(title="Feature Correlation Heatmap")
        self.correlation_heatmap_plot.setBackground("w")
        self.correlation_image = pg.ImageItem()
        self.correlation_heatmap_plot.addItem(self.correlation_image)

        layout = QVBoxLayout(self.matrices_tab)
        layout.addWidget(self.similarity_heatmap_plot, 1)
        layout.addWidget(self.distance_heatmap_plot, 1)
        layout.addWidget(self.correlation_heatmap_plot, 1)

    def _build_cluster_tab(self) -> None:
        self.cluster_plot = pg.PlotWidget(title="Session Clustering Preview")
        self.cluster_plot.setBackground("w")
        self.cluster_plot.showGrid(x=True, y=True, alpha=0.2)
        self.cluster_scatter = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None))
        self.cluster_highlight = pg.ScatterPlotItem(size=14, pen=pg.mkPen("#ff2d55", width=1))
        self.cluster_plot.addItem(self.cluster_scatter)
        self.cluster_plot.addItem(self.cluster_highlight)

        self.feature_importance_plot = pg.PlotWidget(title="Feature Discriminative Power")
        self.feature_importance_plot.setBackground("w")
        self.feature_importance_plot.showGrid(x=True, y=True, alpha=0.2)
        self.feature_importance_bars = None

        layout = QVBoxLayout(self.cluster_tab)
        layout.addWidget(self.cluster_plot, 1)
        layout.addWidget(self.feature_importance_plot, 1)

    def update_report(self, report: BatchAnalysisReport | None, current_session_id: str | None = None) -> None:
        if report is None or not report.pairwise_rows:
            self._clear()
            return

        self._update_distribution_plots(report)
        self._update_matrix_plots(report)
        self._update_cluster_plots(report, current_session_id)

    def _update_distribution_plots(self, report: BatchAnalysisReport) -> None:
        intra = np.asarray([row["normalizedSimilarityScore"] for row in report.pairwise_rows if row["sameUser"]], dtype=np.float64)
        inter = np.asarray([row["normalizedSimilarityScore"] for row in report.pairwise_rows if not row["sameUser"]], dtype=np.float64)
        bins = min(40, max(10, int(math.sqrt(max(len(intra) + len(inter), 1)))))

        if len(intra):
            intra_hist, edges = np.histogram(intra, bins=bins, density=True)
            centers = (edges[:-1] + edges[1:]) / 2.0
            self.intra_hist_curve.setData(centers, intra_hist)
        else:
            self.intra_hist_curve.setData([], [])

        if len(inter):
            inter_hist, edges = np.histogram(inter, bins=bins, density=True)
            centers = (edges[:-1] + edges[1:]) / 2.0
            self.inter_hist_curve.setData(centers, inter_hist)
        else:
            self.inter_hist_curve.setData([], [])

        series = report.distribution_series.get("normalizedSimilarityScore", {})
        grid = np.asarray(series.get("grid", []), dtype=np.float64)
        same_kde = np.asarray(series.get("sameUserKde", []), dtype=np.float64)
        cross_kde = np.asarray(series.get("crossUserKde", []), dtype=np.float64)
        self.intra_kde_curve.setData(grid, same_kde)
        self.inter_kde_curve.setData(grid, cross_kde)

        roc = report.roc_preview
        fpr = np.asarray(roc.get("fpr", []), dtype=np.float64)
        tpr = np.asarray(roc.get("tpr", []), dtype=np.float64)
        if len(fpr) and len(tpr):
            order = np.argsort(fpr)
            self.roc_curve.setData(fpr[order], tpr[order])
        else:
            self.roc_curve.setData([], [])
        self.roc_baseline.setData([0, 1], [0, 1])

    def _update_matrix_plots(self, report: BatchAnalysisReport) -> None:
        if report.similarity_matrix.size:
            self.similarity_image.setImage(report.similarity_matrix, autoLevels=True)
            self.similarity_image.setRect(QRectF(0, 0, report.similarity_matrix.shape[1], report.similarity_matrix.shape[0]))
        else:
            self.similarity_image.setImage(np.zeros((1, 1)), autoLevels=True)

        if report.distance_matrix.size:
            self.distance_image.setImage(report.distance_matrix, autoLevels=True)
            self.distance_image.setRect(QRectF(0, 0, report.distance_matrix.shape[1], report.distance_matrix.shape[0]))
        else:
            self.distance_image.setImage(np.zeros((1, 1)), autoLevels=True)

        if report.feature_correlation_matrix.size:
            self.correlation_image.setImage(report.feature_correlation_matrix, autoLevels=True)
            self.correlation_image.setRect(QRectF(0, 0, report.feature_correlation_matrix.shape[1], report.feature_correlation_matrix.shape[0]))
        else:
            self.correlation_image.setImage(np.zeros((1, 1)), autoLevels=True)

    def _update_cluster_plots(self, report: BatchAnalysisReport, current_session_id: str | None) -> None:
        if not report.cluster_rows:
            self.cluster_scatter.setData([], [])
            self.cluster_highlight.setData([], [])
            self._clear_feature_importance()
            return

        palette = ["#007aff", "#ff3b30", "#34c759", "#ff9500", "#af52de", "#64d2ff", "#ff2d55", "#8e8e93"]
        user_index: dict[str, int] = {}
        spots = []
        for row in report.cluster_rows:
            user_id = row["userId"]
            user_index.setdefault(user_id, len(user_index))
            spots.append(
                {
                    "pos": (row["x"], row["y"]),
                    "data": row,
                    "brush": pg.mkBrush(palette[user_index[user_id] % len(palette)]),
                    "pen": pg.mkPen(None),
                }
            )
        self.cluster_scatter.setData(spots)

        highlight_rows = [row for row in report.cluster_rows if row["sessionId"] == current_session_id] if current_session_id else []
        if highlight_rows:
            self.cluster_highlight.setData([row["x"] for row in highlight_rows], [row["y"] for row in highlight_rows], brush=pg.mkBrush("#ff2d55"))
        else:
            self.cluster_highlight.setData([], [])

        self._update_feature_importance(report)

    def _update_feature_importance(self, report: BatchAnalysisReport) -> None:
        self.feature_importance_plot.clear()
        top_rows = report.feature_importance_rows[:15]
        if not top_rows:
            return

        labels = [row["feature"] for row in top_rows][::-1]
        values = [row["discriminativePower"] for row in top_rows][::-1]
        positions = np.arange(len(values), dtype=np.float64)
        bars = pg.BarGraphItem(x=positions, height=values, width=0.6, brush=pg.mkBrush("#34c759"))
        self.feature_importance_plot.addItem(bars)
        axis = self.feature_importance_plot.getAxis("bottom")
        axis.setTicks([[((float(position), label)) for position, label in zip(positions, labels)]])

    def _clear_feature_importance(self) -> None:
        self.feature_importance_plot.clear()

    def _clear(self) -> None:
        self.intra_hist_curve.setData([], [])
        self.inter_hist_curve.setData([], [])
        self.intra_kde_curve.setData([], [])
        self.inter_kde_curve.setData([], [])
        self.roc_curve.setData([], [])
        self.roc_baseline.setData([], [])
        self.similarity_image.setImage(np.zeros((1, 1)), autoLevels=True)
        self.distance_image.setImage(np.zeros((1, 1)), autoLevels=True)
        self.correlation_image.setImage(np.zeros((1, 1)), autoLevels=True)
        self.cluster_scatter.setData([], [])
        self.cluster_highlight.setData([], [])
        self._clear_feature_importance()
