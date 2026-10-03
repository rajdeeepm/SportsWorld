from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from .math import softmax


@dataclass(slots=True)
class TemperatureScaler:
    temperature: float = 1.0
    version: str = "temperature-v1"

    def fit(self, logits: np.ndarray, labels: np.ndarray, *, grid: Iterable[float] | None = None) -> "TemperatureScaler":
        logits = np.asarray(logits, dtype=float)
        labels = np.asarray(labels, dtype=int)
        if logits.ndim != 2 or logits.shape[0] != labels.shape[0]:
            raise ValueError("logits must be [n,k] and labels [n]")
        candidates = np.asarray(list(grid) if grid is not None else np.geomspace(0.35, 4.0, 160), dtype=float)
        best_t, best_loss = 1.0, float("inf")
        for t in candidates:
            probs = np.vstack([softmax(row / t) for row in logits])
            chosen = np.clip(probs[np.arange(len(labels)), labels], 1e-12, 1)
            loss = -float(np.mean(np.log(chosen)))
            if loss < best_loss:
                best_loss, best_t = loss, float(t)
        self.temperature = best_t
        return self

    def transform_logits(self, logits: Iterable[float]) -> np.ndarray:
        return np.asarray(list(logits), dtype=float) / max(self.temperature, 1e-6)

    def transform_probabilities(self, probabilities: dict[str, float]) -> dict[str, float]:
        labels = list(probabilities)
        p = np.asarray([max(1e-12, probabilities[k]) for k in labels], dtype=float)
        logits = np.log(p)
        calibrated = softmax(logits / max(self.temperature, 1e-6))
        return dict(zip(labels, calibrated.tolist()))

    def to_dict(self) -> dict[str, float | str]:
        return {"temperature": self.temperature, "version": self.version}

    @classmethod
    def from_dict(cls, data: dict) -> "TemperatureScaler":
        return cls(temperature=float(data.get("temperature", 1.0)), version=str(data.get("version", "temperature-v1")))


@dataclass(slots=True)
class IdentityCalibrator:
    version: str = "identity-v1"

    def transform_probabilities(self, probabilities: dict[str, float]) -> dict[str, float]:
        return dict(probabilities)
