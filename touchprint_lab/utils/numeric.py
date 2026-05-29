from __future__ import annotations

from typing import Any

import numpy as np


def _finite_array(values: Any) -> np.ndarray:
    if isinstance(values, np.ndarray):
        array = np.asarray(values, dtype=np.float64)
    else:
        array = np.asarray(list(values), dtype=np.float64)
    if array.ndim == 0:
        array = np.asarray([array], dtype=np.float64)
    array = array[np.isfinite(array)]
    return array.astype(np.float64, copy=False)


def safe_nanvar(values: Any, default: float = 0.0) -> float:
    array = _finite_array(values)
    if array.size < 2:
        return float(default)
    with np.errstate(invalid="ignore", divide="ignore"):
        result = np.nanvar(array, ddof=0)
    return float(default) if not np.isfinite(result) else float(result)


def safe_nanstd(values: Any, default: float = 0.0) -> float:
    array = _finite_array(values)
    if array.size < 2:
        return float(default)
    with np.errstate(invalid="ignore", divide="ignore"):
        result = np.nanstd(array, ddof=0)
    return float(default) if not np.isfinite(result) else float(result)
