from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from sportsworld.core.math import sigmoid


@dataclass(slots=True)
class NumpyLogisticModel:
    features: list[str]
    weights: np.ndarray
    bias: float = 0.0

    @classmethod
    def create(cls, features: list[str]) -> "NumpyLogisticModel":
        return cls(features=list(features), weights=np.zeros(len(features), dtype=float), bias=0.0)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        lr: float = 0.08,
        epochs: int = 900,
        l2: float = 1e-3,
    ) -> "NumpyLogisticModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2 or X.shape[1] != len(self.features) or len(y) != len(X):
            raise ValueError("invalid training shape")
        for _ in range(epochs):
            z = X @ self.weights + self.bias
            p = sigmoid(z)
            err = p - y
            self.weights -= lr * ((X.T @ err) / len(X) + l2 * self.weights)
            self.bias -= lr * float(np.mean(err))
        return self

    def predict_home_probability(self, features: dict[str, float]) -> float:
        x = np.asarray([float(features.get(name, 0.0)) for name in self.features], dtype=float)
        return float(sigmoid(x @ self.weights + self.bias))

    def to_dict(self) -> dict:
        return {"features": self.features, "weights": self.weights.tolist(), "bias": self.bias}

    @classmethod
    def from_dict(cls, data: dict) -> "NumpyLogisticModel":
        return cls(features=list(data["features"]), weights=np.asarray(data["weights"], dtype=float), bias=float(data["bias"]))


@dataclass(slots=True)
class BootstrapBinaryEnsemble:
    members: list[NumpyLogisticModel]
    positive_label: str = "home"
    negative_label: str = "away"

    @classmethod
    def fit_bootstrap(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        features: list[str],
        *,
        n_members: int = 15,
        seed: int = 7,
    ) -> "BootstrapBinaryEnsemble":
        rng = np.random.default_rng(seed)
        members: list[NumpyLogisticModel] = []
        n = len(X)
        for i in range(n_members):
            idx = rng.integers(0, n, size=n)
            model = NumpyLogisticModel.create(features)
            model.fit(X[idx], y[idx], lr=0.07, epochs=650, l2=2e-3)
            members.append(model)
        return cls(members=members)

    def member_probabilities(self, features: dict[str, float]) -> np.ndarray:
        return np.asarray([m.predict_home_probability(features) for m in self.members], dtype=float)

    def predict(self, features: dict[str, float]) -> tuple[dict[str, float], dict[str, tuple[float, float]], float]:
        p = self.member_probabilities(features)
        mean = float(np.mean(p))
        lo, hi = np.quantile(p, [0.05, 0.95]).tolist()
        probs = {self.positive_label: mean, self.negative_label: 1.0 - mean}
        intervals = {
            self.positive_label: (max(0.0, lo), min(1.0, hi)),
            self.negative_label: (max(0.0, 1.0 - hi), min(1.0, 1.0 - lo)),
        }
        return probs, intervals, float(np.std(p))

    def to_dict(self) -> dict:
        return {
            "kind": "bootstrap_binary_logistic",
            "positive_label": self.positive_label,
            "negative_label": self.negative_label,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BootstrapBinaryEnsemble":
        return cls(
            members=[NumpyLogisticModel.from_dict(m) for m in data["members"]],
            positive_label=str(data.get("positive_label", "home")),
            negative_label=str(data.get("negative_label", "away")),
        )


@dataclass(slots=True)
class NumpyConditionalSoftmaxModel:
    """Shared linear scorer for a variable number of outcomes.

    Each outcome is represented by the same feature schema.  This is a better fit
    for F1 than a fixed-label multinomial model because the learned scorer can be
    applied to any driver list while preserving a single calibrated race-level
    softmax distribution.
    """

    features: list[str]
    weights: np.ndarray

    @classmethod
    def create(cls, features: list[str]) -> "NumpyConditionalSoftmaxModel":
        return cls(features=list(features), weights=np.zeros(len(features), dtype=float))

    def fit(self, X: np.ndarray, y: np.ndarray, *, lr: float = 0.05, epochs: int = 900, l2: float = 1e-3, mask: np.ndarray | None = None) -> "NumpyConditionalSoftmaxModel":
        """`mask[n, k]` marks real outcomes; padded slots (variable field sizes) get zero probability."""
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        if X.ndim != 3 or X.shape[2] != len(self.features) or X.shape[0] != len(y):
            raise ValueError("X must be [n, outcomes, features] and y [n]")
        n = X.shape[0]
        neg = None if mask is None else np.where(np.asarray(mask, dtype=bool), 0.0, -1e9)
        for _ in range(epochs):
            scores = np.einsum("nkd,d->nk", X, self.weights)
            if neg is not None:
                scores = scores + neg
            scores -= np.max(scores, axis=1, keepdims=True)
            exp = np.exp(scores)
            probs = exp / np.sum(exp, axis=1, keepdims=True)
            probs[np.arange(n), y] -= 1.0
            grad = np.einsum("nkd,nk->d", X, probs) / n + l2 * self.weights
            self.weights -= lr * grad
        return self

    def predict_probabilities(self, outcome_features: dict[str, dict[str, float]]) -> dict[str, float]:
        labels = list(outcome_features)
        X = np.asarray([[float(outcome_features[label].get(name, 0.0)) for name in self.features] for label in labels], dtype=float)
        scores = X @ self.weights
        scores -= np.max(scores)
        exp = np.exp(scores)
        p = exp / np.sum(exp)
        return dict(zip(labels, p.tolist()))

    def to_dict(self) -> dict:
        return {"features": self.features, "weights": self.weights.tolist()}

    @classmethod
    def from_dict(cls, data: dict) -> "NumpyConditionalSoftmaxModel":
        return cls(features=list(data["features"]), weights=np.asarray(data["weights"], dtype=float))


@dataclass(slots=True)
class BootstrapConditionalSoftmaxEnsemble:
    members: list[NumpyConditionalSoftmaxModel]

    @classmethod
    def fit_bootstrap(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        features: list[str],
        *,
        n_members: int = 15,
        seed: int = 7,
        mask: np.ndarray | None = None,
        lr: float = 0.045,
        epochs: int = 700,
    ) -> "BootstrapConditionalSoftmaxEnsemble":
        rng = np.random.default_rng(seed)
        n = len(X)
        members: list[NumpyConditionalSoftmaxModel] = []
        for _ in range(n_members):
            idx = rng.integers(0, n, size=n)
            m = NumpyConditionalSoftmaxModel.create(features)
            m.fit(X[idx], y[idx], lr=lr, epochs=epochs, l2=2e-3, mask=None if mask is None else np.asarray(mask)[idx])
            members.append(m)
        return cls(members=members)

    def member_probabilities(self, outcome_features: dict[str, dict[str, float]]) -> tuple[list[str], np.ndarray]:
        labels = list(outcome_features)
        rows = []
        for m in self.members:
            p = m.predict_probabilities(outcome_features)
            rows.append([p[label] for label in labels])
        return labels, np.asarray(rows, dtype=float)

    def predict(self, outcome_features: dict[str, dict[str, float]]) -> tuple[dict[str, float], dict[str, tuple[float, float]], float]:
        labels, matrix = self.member_probabilities(outcome_features)
        mean = np.mean(matrix, axis=0)
        lo = np.quantile(matrix, 0.05, axis=0)
        hi = np.quantile(matrix, 0.95, axis=0)
        probs = dict(zip(labels, mean.tolist()))
        intervals = {label: (float(max(0.0, lo[i])), float(min(1.0, hi[i]))) for i, label in enumerate(labels)}
        epistemic = float(np.mean(np.std(matrix, axis=0)))
        return probs, intervals, epistemic

    def to_dict(self) -> dict:
        return {"kind": "bootstrap_conditional_softmax", "members": [m.to_dict() for m in self.members]}

    @classmethod
    def from_dict(cls, data: dict) -> "BootstrapConditionalSoftmaxEnsemble":
        return cls(members=[NumpyConditionalSoftmaxModel.from_dict(m) for m in data["members"]])
