from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from sportsworld.core.math import wilson_interval
from sportsworld.schemas import WorldState


@dataclass(slots=True)
class SequentialSimulationResult:
    counts: dict[str, int]
    probabilities: dict[str, float]
    intervals_90: dict[str, tuple[float, float]]
    standard_error: dict[str, float]
    mean_steps: float
    transition_kind: str
    representative_paths: list[list[dict[str, Any]]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_outcomes(
        cls,
        outcomes: list[str],
        labels: list[str],
        draws: int,
        *,
        steps: list[int] | np.ndarray | None = None,
        transition_kind: str,
        representative_paths: list[list[dict[str, Any]]] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> "SequentialSimulationResult":
        counts = {label: int(sum(1 for x in outcomes if x == label)) for label in labels}
        probs = {label: counts[label] / draws for label in labels}
        intervals = {label: wilson_interval(counts[label], draws) for label in labels}
        se = {label: float(np.sqrt(probs[label] * (1.0 - probs[label]) / max(draws, 1))) for label in labels}
        mean_steps = float(np.mean(steps)) if steps is not None and len(steps) else 0.0
        return cls(
            counts=counts,
            probabilities=probs,
            intervals_90=intervals,
            standard_error=se,
            mean_steps=mean_steps,
            transition_kind=transition_kind,
            representative_paths=representative_paths or [],
            diagnostics=diagnostics or {},
        )


class SportSequentialSimulator(Protocol):
    transition_kind: str

    def simulate(self, state: WorldState, draws: int, seed: int, *, capture_paths: int = 3) -> SequentialSimulationResult: ...
