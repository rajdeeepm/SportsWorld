from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def softmax(scores: Iterable[float]) -> np.ndarray:
    x = np.asarray(list(scores), dtype=float)
    if x.size == 0:
        raise ValueError("softmax requires at least one score")
    x = x - np.max(x)
    e = np.exp(x)
    return e / e.sum()


def logit(p: float, eps: float = 1e-9) -> float:
    p = min(1 - eps, max(eps, float(p)))
    return math.log(p / (1 - p))


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    out = np.empty_like(x_arr)
    pos = x_arr >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x_arr[pos]))
    e = np.exp(x_arr[~pos])
    out[~pos] = e / (1.0 + e)
    return float(out) if out.ndim == 0 else out


def normalized_entropy(probabilities: Iterable[float]) -> float:
    p = np.asarray(list(probabilities), dtype=float)
    p = p[p > 0]
    if p.size <= 1:
        return 0.0
    h = -float(np.sum(p * np.log(p)))
    return h / math.log(len(p))


def normalize_probabilities(values: dict[str, float]) -> dict[str, float]:
    clipped = {k: max(0.0, float(v)) for k, v in values.items()}
    total = sum(clipped.values())
    if total <= 0:
        n = len(clipped)
        if n == 0:
            raise ValueError("no outcomes")
        return {k: 1.0 / n for k in clipped}
    return {k: v / total for k, v in clipped.items()}


def wilson_interval(successes: int, n: int, z: float = 1.6448536269514722) -> tuple[float, float]:
    """Two-sided ~90% Wilson interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return max(0.0, centre - margin), min(1.0, centre + margin)
