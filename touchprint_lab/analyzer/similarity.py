from __future__ import annotations

from typing import Any

import numpy as np

from touchprint_lab.utils.numeric import safe_nanstd

try:
    from sklearn.decomposition import PCA  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    class StandardScaler:  # type: ignore
        def fit_transform(self, matrix: np.ndarray) -> np.ndarray:
            self.mean_ = np.mean(matrix, axis=0)
            self.scale_ = np.asarray([safe_nanstd(matrix[:, index]) for index in range(matrix.shape[1])], dtype=np.float64)
            self.scale_ = np.where(self.scale_ == 0, 1.0, self.scale_)
            return (matrix - self.mean_) / self.scale_

    class PCA:  # type: ignore
        def __init__(self, n_components: int):
            self.n_components = n_components

        def fit_transform(self, matrix: np.ndarray) -> np.ndarray:
            centered = matrix - np.mean(matrix, axis=0, keepdims=True)
            u, s, vt = np.linalg.svd(centered, full_matrices=False)
            components = vt[: self.n_components]
            return centered @ components.T

from touchprint_lab.analyzer.features import TouchFeatureVector


def normalized_feature_matrix(vectors: list[TouchFeatureVector]) -> np.ndarray:
    if not vectors:
        return np.zeros((0, 0), dtype=np.float64)
    matrix = np.stack([np.nan_to_num(vector.feature_array(), nan=0.0, posinf=0.0, neginf=0.0) for vector in vectors], axis=0)
    return matrix.astype(np.float64, copy=False)


def cosine_similarity(left: TouchFeatureVector, right: TouchFeatureVector) -> float:
    left_vector = normalized_feature_matrix([left])[0]
    right_vector = normalized_feature_matrix([right])[0]
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator <= 1e-12:
        return 0.0
    return float(np.clip(np.dot(left_vector, right_vector) / denominator, -1.0, 1.0))


def euclidean_distance(left: TouchFeatureVector, right: TouchFeatureVector) -> float:
    left_vector = normalized_feature_matrix([left])[0]
    right_vector = normalized_feature_matrix([right])[0]
    return float(np.linalg.norm(left_vector - right_vector))


def normalized_distance_score(left: TouchFeatureVector, right: TouchFeatureVector) -> float:
    distance = euclidean_distance(left, right)
    return float(1.0 / (1.0 + distance))


def similarity_matrix(vectors: list[TouchFeatureVector], metric: str = "cosine") -> np.ndarray:
    matrix = normalized_feature_matrix(vectors)
    if matrix.size == 0:
        return np.zeros((0, 0), dtype=np.float64)
    if metric == "euclidean":
        distances = np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)
        return 1.0 / (1.0 + distances)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = np.divide(matrix, np.where(norms == 0, 1.0, norms))
    return np.clip(normalized @ normalized.T, -1.0, 1.0)


def similarity_table(reference: TouchFeatureVector, candidates: list[TouchFeatureVector]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        rows.append(
            {
                "sessionId": candidate.session_id,
                "userId": candidate.user_id,
                "cosineSimilarity": cosine_similarity(reference, candidate),
                "euclideanDistance": euclidean_distance(reference, candidate),
                "normalizedDistanceScore": normalized_distance_score(reference, candidate),
                "sameUser": candidate.user_id == reference.user_id,
            }
        )
    rows.sort(key=lambda row: row["normalizedDistanceScore"], reverse=True)
    return rows


def top_matches(reference: TouchFeatureVector, candidates: list[TouchFeatureVector], same_user: bool | None = None) -> list[dict[str, Any]]:
    rows = similarity_table(reference, candidates)
    if same_user is True:
        rows = [row for row in rows if row["sameUser"]]
    elif same_user is False:
        rows = [row for row in rows if not row["sameUser"]]
    return rows


def cluster_projection(vectors: list[TouchFeatureVector]) -> list[dict[str, Any]]:
    if len(vectors) < 2:
        return []
    matrix = normalized_feature_matrix(vectors)
    scaled = StandardScaler().fit_transform(matrix)
    component_count = min(2, scaled.shape[0], scaled.shape[1])
    projection = PCA(n_components=component_count).fit_transform(scaled)
    if component_count == 1:
        projection = np.column_stack([projection[:, 0], np.zeros(len(projection))])
    rows: list[dict[str, Any]] = []
    for index, vector in enumerate(vectors):
        rows.append(
            {
                "sessionId": vector.session_id,
                "userId": vector.user_id,
                "x": float(projection[index, 0]),
                "y": float(projection[index, 1]),
            }
        )
    return rows
