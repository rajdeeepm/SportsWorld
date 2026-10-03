from __future__ import annotations

"""Learned linear-Gaussian latent-state estimation.

The historical/context layer observes noisy proxies (box-score statistics,
practice availability, live pace, etc.) rather than an entity's true current
competitive state.  This module therefore models each latent capability as a
continuous state-space process and learns its persistence/process/observation
noise parameters from chronological sequences.

The implementation is deliberately dependency-light (NumPy only) so the same
filter runs in training, replay, and serving.  Parameters learned from synthetic
demo sequences are bundled for offline verification; production deployments
should refit them on real point-in-time sequences.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Any
import json
import math

import numpy as np


@dataclass(slots=True)
class DimensionDynamics:
    phi: float = 0.985
    process_var: float = 0.018
    observation_var: float = 0.080
    prior_var: float = 0.25
    time_unit_days: float = 7.0

    def to_dict(self) -> dict[str, float]:
        return {
            "phi": float(self.phi),
            "process_var": float(self.process_var),
            "observation_var": float(self.observation_var),
            "prior_var": float(self.prior_var),
            "time_unit_days": float(self.time_unit_days),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DimensionDynamics":
        return cls(**{k: float(v) for k, v in data.items()})


DEFAULT_PARAMS: dict[str, DimensionDynamics] = {
    "skill": DimensionDynamics(phi=0.997, process_var=0.004, observation_var=0.085, prior_var=0.20, time_unit_days=30.0),
    "form": DimensionDynamics(phi=0.90, process_var=0.050, observation_var=0.090, prior_var=0.30, time_unit_days=7.0),
    "health": DimensionDynamics(phi=0.78, process_var=0.090, observation_var=0.075, prior_var=0.35, time_unit_days=7.0),
    "usage": DimensionDynamics(phi=0.88, process_var=0.045, observation_var=0.080, prior_var=0.30, time_unit_days=7.0),
    "experience": DimensionDynamics(phi=0.999, process_var=0.001, observation_var=0.100, prior_var=0.18, time_unit_days=30.0),
    "potential": DimensionDynamics(phi=0.994, process_var=0.006, observation_var=0.120, prior_var=0.28, time_unit_days=30.0),
    "chemistry": DimensionDynamics(phi=0.96, process_var=0.018, observation_var=0.095, prior_var=0.30, time_unit_days=14.0),
    "coaching": DimensionDynamics(phi=0.985, process_var=0.012, observation_var=0.100, prior_var=0.28, time_unit_days=30.0),
}


@dataclass(slots=True)
class Posterior:
    mean: float
    variance: float
    evidence_weight: float
    innovations: list[dict[str, float]]


class LatentStateSpaceModel:
    """Independent 1-D Kalman filters for named latent capability dimensions.

    The dimensions are conditionally independent inside this filter.  Cross-
    entity and cross-dimension interactions are handled separately by the
    matchup graph and sport model.  This separation makes posterior uncertainty
    auditable and prevents arbitrary narrative signals from being treated as a
    direct latent-state measurement.
    """

    def __init__(self, params: dict[str, DimensionDynamics] | None = None, *, version: str = "latent_state_default_v1", data_mode: str = "default"):
        self.params = dict(DEFAULT_PARAMS)
        if params:
            self.params.update(params)
        self.version = version
        self.data_mode = data_mode

    def params_for(self, dimension: str) -> DimensionDynamics:
        return self.params.get(dimension, DimensionDynamics())

    @staticmethod
    def _transition(phi: float, process_var: float, delta_days: float, unit_days: float) -> tuple[float, float]:
        steps = max(0.0, float(delta_days)) / max(float(unit_days), 1e-6)
        if steps <= 0:
            return 1.0, 0.0
        a = float(phi) ** steps
        # Continuous accumulation approximation.  Keeps q meaningful for
        # irregularly-spaced public/historical evidence.
        q = float(process_var) * max(steps, 1e-6)
        return a, q

    def filter(
        self,
        *,
        dimension: str,
        prior_mean: float,
        observations: Iterable[dict[str, Any]],
        as_of: datetime,
    ) -> Posterior:
        p = self.params_for(dimension)
        mean = float(np.clip(prior_mean, -1.0, 1.0))
        var = float(max(p.prior_var, 1e-6))
        innovations: list[dict[str, float]] = []
        last_time: datetime | None = None
        total_weight = 0.0

        valid = sorted(
            [o for o in observations if o["time"] <= as_of],
            key=lambda o: o["time"],
        )
        for obs in valid:
            t: datetime = obs["time"]
            if last_time is not None:
                dt = max(0.0, (t - last_time).total_seconds() / 86400.0)
                a, q = self._transition(p.phi, p.process_var, dt, p.time_unit_days)
                mean = a * mean
                var = a * a * var + q

            confidence = max(0.03, min(1.0, float(obs.get("confidence", 1.0))))
            sample_size = max(1.0, float(obs.get("sample_size", 1.0)))
            relevance = max(0.10, float(obs.get("relevance", 1.0)))
            # Higher confidence, more samples, and matchup relevance reduce
            # observation variance, but never to zero.
            effective_precision = confidence * relevance * (1.0 + min(4.0, math.log1p(sample_size)))
            r = max(1e-5, p.observation_var / max(effective_precision, 1e-4))
            y = float(np.clip(obs["value"], -1.0, 1.0))
            innovation = y - mean
            innovation_var = var + r
            k = var / max(innovation_var, 1e-9)
            mean = mean + k * innovation
            var = max(1e-8, (1.0 - k) * var)
            total_weight += effective_precision
            innovations.append({
                "innovation": float(innovation),
                "kalman_gain": float(k),
                "observation_variance": float(r),
                "posterior_variance": float(var),
            })
            last_time = t

        if last_time is not None and last_time < as_of:
            dt = max(0.0, (as_of - last_time).total_seconds() / 86400.0)
            a, q = self._transition(p.phi, p.process_var, dt, p.time_unit_days)
            mean = a * mean
            var = a * a * var + q

        return Posterior(
            mean=float(np.clip(mean, -1.0, 1.0)),
            variance=float(max(var, 1e-8)),
            evidence_weight=float(total_weight),
            innovations=innovations,
        )

    # ------------------------------------------------------------------
    # Parameter learning from chronological sequences
    # ------------------------------------------------------------------
    @staticmethod
    def _sequence_nll(values: np.ndarray, deltas: np.ndarray, params: DimensionDynamics) -> float:
        if len(values) < 2:
            return float("inf")
        m = float(values[0])
        v = max(params.prior_var, 1e-5)
        nll = 0.0
        for i in range(1, len(values)):
            a, q = LatentStateSpaceModel._transition(params.phi, params.process_var, float(deltas[i]), params.time_unit_days)
            m = a * m
            v = a * a * v + q
            s = max(v + params.observation_var, 1e-8)
            innov = float(values[i]) - m
            nll += 0.5 * (math.log(2.0 * math.pi * s) + innov * innov / s)
            k = v / s
            m = m + k * innov
            v = max(1e-8, (1.0 - k) * v)
        return float(nll)

    @classmethod
    def fit_sequences(
        cls,
        sequences: list[dict[str, Any]],
        *,
        version: str = "latent_state_learned_v1",
        data_mode: str = "historical",
    ) -> "LatentStateSpaceModel":
        by_dim: dict[str, list[dict[str, Any]]] = {}
        for seq in sequences:
            by_dim.setdefault(str(seq["dimension"]), []).append(seq)

        learned: dict[str, DimensionDynamics] = {}
        phi_grid = np.asarray([0.72, 0.80, 0.88, 0.93, 0.96, 0.985, 0.995, 0.999], dtype=float)
        q_grid = np.asarray([0.002, 0.006, 0.015, 0.035, 0.070, 0.120], dtype=float)
        r_grid = np.asarray([0.025, 0.050, 0.085, 0.130, 0.200], dtype=float)

        for dim, dim_sequences in by_dim.items():
            base = DEFAULT_PARAMS.get(dim, DimensionDynamics())
            best = (float("inf"), base)
            for phi in phi_grid:
                for q in q_grid:
                    for r in r_grid:
                        params = DimensionDynamics(
                            phi=float(phi), process_var=float(q), observation_var=float(r),
                            prior_var=base.prior_var, time_unit_days=base.time_unit_days,
                        )
                        loss = 0.0
                        usable = 0
                        for seq in dim_sequences:
                            values = np.asarray(seq["values"], dtype=float)
                            deltas = np.asarray(seq.get("delta_days", [0.0] + [base.time_unit_days] * (len(values)-1)), dtype=float)
                            if len(deltas) != len(values):
                                continue
                            score = cls._sequence_nll(values, deltas, params)
                            if math.isfinite(score):
                                loss += score
                                usable += 1
                        if usable and loss < best[0]:
                            best = (loss, params)
            learned[dim] = best[1]

        return cls(learned, version=version, data_mode=data_mode)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "linear_gaussian_latent_state",
            "version": self.version,
            "data_mode": self.data_mode,
            "dimensions": {k: v.to_dict() for k, v in sorted(self.params.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LatentStateSpaceModel":
        params = {k: DimensionDynamics.from_dict(v) for k, v in data.get("dimensions", {}).items()}
        return cls(params, version=str(data.get("version", "latent_state_loaded_v1")), data_mode=str(data.get("data_mode", "unknown")))

    @classmethod
    def load(cls, path: str | Path) -> "LatentStateSpaceModel":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2))
