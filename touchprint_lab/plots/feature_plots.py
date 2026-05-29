from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.similarity import cluster_projection, similarity_matrix


class FeaturePlotWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.histogram_plot = pg.PlotWidget(title="Feature Distribution")
        self.histogram_plot.setBackground("w")
        self.histogram_plot.showGrid(x=True, y=True, alpha=0.2)
        self.histogram_curve = self.histogram_plot.plot([], [], pen=pg.mkPen("#007aff", width=2), fillLevel=0, brush=(0, 122, 255, 60))
        self.histogram_marker = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ff3b30", width=2))
        self.histogram_plot.addItem(self.histogram_marker)

        self.heatmap_plot = pg.PlotWidget(title="Similarity Heatmap")
        self.heatmap_plot.setBackground("w")
        self.heatmap_image = pg.ImageItem()
        self.heatmap_plot.addItem(self.heatmap_image)

        self.cluster_plot = pg.PlotWidget(title="Session Clustering Preview")
        self.cluster_plot.setBackground("w")
        self.cluster_plot.showGrid(x=True, y=True, alpha=0.2)
        self.cluster_scatter = pg.ScatterPlotItem(size=8, brush=pg.mkBrush("#34c759"), pen=pg.mkPen(None))
        self.cluster_highlight = pg.ScatterPlotItem(size=14, brush=pg.mkBrush("#ff2d55"), pen=pg.mkPen(None))
        self.cluster_plot.addItem(self.cluster_scatter)
        self.cluster_plot.addItem(self.cluster_highlight)

        layout = QVBoxLayout(self)
        layout.addWidget(self.histogram_plot, 1)
        layout.addWidget(self.heatmap_plot, 1)
        layout.addWidget(self.cluster_plot, 1)

    def update_feature_views(
        self,
        current_vector: TouchFeatureVector | None,
        all_vectors: list[TouchFeatureVector],
        feature_name: str,
    ) -> None:
        if not all_vectors or not feature_name:
            self._clear()
            return

        values = np.asarray([getattr(vector, feature_name, 0.0) for vector in all_vectors], dtype=np.float64)
        values = values[np.isfinite(values)]
        if len(values):
            bins = min(20, max(5, int(np.sqrt(len(values)))))
            histogram, edges = np.histogram(values, bins=bins)
            centers = (edges[:-1] + edges[1:]) / 2.0
            self.histogram_curve.setData(centers, histogram)
        else:
            self.histogram_curve.setData([], [])

        if current_vector is not None:
            self.histogram_marker.setPos(float(getattr(current_vector, feature_name, 0.0)))
        else:
            self.histogram_marker.setPos(0.0)

        similarity = similarity_matrix(all_vectors)
        if similarity.size:
            self.heatmap_image.setImage(similarity, autoLevels=True)
            self.heatmap_image.setRect(QRectF(0, 0, similarity.shape[1], similarity.shape[0]))
        else:
            self.heatmap_image.setImage(np.zeros((1, 1)), autoLevels=True)

        cluster = cluster_projection(all_vectors)
        if not cluster:
            self.cluster_scatter.setData([], [])
            self.cluster_highlight.setData([], [])
            return

        self.cluster_scatter.setData([row["x"] for row in cluster], [row["y"] for row in cluster])
        if current_vector is not None:
            highlight_row = [row for row in cluster if row["sessionId"] == current_vector.session_id]
            self.cluster_highlight.setData([row["x"] for row in highlight_row], [row["y"] for row in highlight_row])
        else:
            self.cluster_highlight.setData([], [])

    def _clear(self) -> None:
        self.histogram_curve.setData([], [])
        self.heatmap_image.setImage(np.zeros((1, 1)), autoLevels=True)
        self.cluster_scatter.setData([], [])
        self.cluster_highlight.setData([], [])
