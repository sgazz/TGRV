from __future__ import annotations

import json
import logging

import numpy as np
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from touchprint_lab.analyzer.features import TouchFeatureVector
from touchprint_lab.analyzer.similarity import (
    cosine_similarity,
    euclidean_distance,
    normalized_distance_score,
    top_matches,
)
from touchprint_lab.plots.feature_plots import FeaturePlotWidget
from touchprint_lab.utils.numeric import safe_nanvar

logger = logging.getLogger(__name__)


class FeatureInspectorWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.vectors: list[TouchFeatureVector] = []
        self.current_vector: TouchFeatureVector | None = None

        self.feature_selector = QComboBox()
        self.comparison_selector = QComboBox()
        self.scope_selector = QComboBox()
        self.scope_selector.addItems(["all", "same user", "cross user"])

        self.selected_features = QPlainTextEdit()
        self.selected_features.setReadOnly(True)
        self.selected_features.setMinimumHeight(140)

        self.variance_label = QLabel("Variance: —")
        self.similarity_label = QLabel("Similarity: —")
        self.distance_label = QLabel("Distance: —")
        self.same_user_label = QLabel("Same-user best: —")
        self.cross_user_label = QLabel("Cross-user best: —")
        self.scope_summary = QLabel("Comparison scope: all")

        self.feature_plots = FeaturePlotWidget()

        controls = QFormLayout()
        controls.addRow("Feature", self.feature_selector)
        controls.addRow("Compare With", self.comparison_selector)
        controls.addRow("Scope", self.scope_selector)

        header = QVBoxLayout()
        header.addLayout(controls)
        header.addWidget(self.scope_summary)
        header.addWidget(self.variance_label)
        header.addWidget(self.similarity_label)
        header.addWidget(self.distance_label)
        header.addWidget(self.same_user_label)
        header.addWidget(self.cross_user_label)
        header.addWidget(QLabel("Selected Feature Values"))
        header.addWidget(self.selected_features)

        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container_layout = QVBoxLayout(container)
        container_layout.addLayout(header)
        container_layout.addWidget(self.feature_plots, 1)

        root_layout = QHBoxLayout(self)
        root_layout.addWidget(container)

        self.feature_selector.currentTextChanged.connect(self._update_inspector)
        self.comparison_selector.currentIndexChanged.connect(self._update_inspector)
        self.scope_selector.currentTextChanged.connect(self._update_inspector)

    def set_sessions(self, vectors: list[TouchFeatureVector]) -> None:
        self.vectors = vectors
        self.feature_selector.blockSignals(True)
        self.comparison_selector.blockSignals(True)
        self.feature_selector.clear()
        self.comparison_selector.clear()

        if vectors:
            for feature_name in TouchFeatureVector.FEATURE_FIELDS:
                self.feature_selector.addItem(feature_name)
            for vector in vectors:
                label = f"{vector.session_id} • {vector.user_id}"
                self.comparison_selector.addItem(label, vector.session_id)

        self.feature_selector.blockSignals(False)
        self.comparison_selector.blockSignals(False)
        if self.feature_selector.count() > 0:
            self.feature_selector.setCurrentIndex(0)
        if self.comparison_selector.count() > 0:
            self.comparison_selector.setCurrentIndex(0)
        self._update_inspector()

    def set_current_vector(self, vector: TouchFeatureVector | None) -> None:
        self.current_vector = vector
        self._update_inspector()

    def _update_inspector(self, *_args: object) -> None:
        if not self.vectors:
            self.selected_features.setPlainText("No feature vectors loaded.")
            self.feature_plots.update_feature_views(None, [], "")
            self.variance_label.setText("Variance: —")
            self.similarity_label.setText("Similarity: —")
            self.distance_label.setText("Distance: —")
            self.same_user_label.setText("Same-user best: —")
            self.cross_user_label.setText("Cross-user best: —")
            return

        feature_name = self.feature_selector.currentText() or TouchFeatureVector.FEATURE_FIELDS[0]
        current_vector = self.current_vector or self.vectors[0]
        comparison_vector = self._selected_comparison_vector()
        scope = self.scope_selector.currentText()
        candidates = self._filtered_candidates(current_vector, scope)

        self.selected_features.setPlainText(
            json.dumps(
                {
                    "sessionId": current_vector.session_id,
                    "userId": current_vector.user_id,
                    "feature": feature_name,
                    "value": getattr(current_vector, feature_name, 0.0),
                    "vector": current_vector.to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
        )

        feature_values = np.asarray([getattr(vector, feature_name, 0.0) for vector in candidates], dtype=np.float64)
        feature_values = feature_values[np.isfinite(feature_values)]
        variance = safe_nanvar(feature_values)
        self.variance_label.setText(f"Variance: {variance:.6f}")

        if comparison_vector is None:
            self.similarity_label.setText("Similarity: —")
            self.distance_label.setText("Distance: —")
        else:
            cosine = cosine_similarity(current_vector, comparison_vector)
            distance = euclidean_distance(current_vector, comparison_vector)
            normalized = normalized_distance_score(current_vector, comparison_vector)
            self.similarity_label.setText(f"Similarity: cosine={cosine:.4f} normalized={normalized:.4f}")
            self.distance_label.setText(f"Distance: euclidean={distance:.4f}")

        same_user_matches = top_matches(current_vector, candidates, same_user=True)
        cross_user_matches = top_matches(current_vector, candidates, same_user=False)
        same_user_score = float(same_user_matches[0]["normalizedDistanceScore"]) if same_user_matches else 0.0
        cross_user_score = float(cross_user_matches[0]["normalizedDistanceScore"]) if cross_user_matches else 0.0
        self.same_user_label.setText(f"Same-user best: {same_user_score:.4f}")
        self.cross_user_label.setText(f"Cross-user best: {cross_user_score:.4f}")
        self.scope_summary.setText(f"Comparison scope: {scope}")

        self.feature_plots.update_feature_views(current_vector, self.vectors, feature_name)
        logger.debug("Updated feature inspector for %s", current_vector.session_id)

    def _selected_comparison_vector(self) -> TouchFeatureVector | None:
        session_id = self.comparison_selector.currentData()
        if not session_id:
            return None
        return next((vector for vector in self.vectors if vector.session_id == session_id), None)

    def _filtered_candidates(self, current_vector: TouchFeatureVector, scope: str) -> list[TouchFeatureVector]:
        candidates = [vector for vector in self.vectors if vector.session_id != current_vector.session_id]
        if scope == "same user":
            return [vector for vector in candidates if vector.user_id == current_vector.user_id]
        if scope == "cross user":
            return [vector for vector in candidates if vector.user_id != current_vector.user_id]
        return candidates
