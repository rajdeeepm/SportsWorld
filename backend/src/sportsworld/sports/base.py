from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import numpy as np

from sportsworld.schemas import Observation, WorldState


class SportAdapter(ABC):
    sport_name: str
    schema_version: str = "v1"

    @abstractmethod
    def validate_state(self, state: WorldState) -> None: ...

    @abstractmethod
    def apply_observation(self, state: WorldState, observation: Observation) -> WorldState: ...

    @abstractmethod
    def build_features(self, state: WorldState, prediction_time: datetime) -> dict[str, float]: ...

    @abstractmethod
    def predict_raw(self, state: WorldState, model: Any | None) -> dict[str, float]: ...

    @abstractmethod
    def simulate_transition(self, state: WorldState, rng: np.random.Generator) -> str: ...

    @abstractmethod
    def supported_observation_kinds(self) -> set[str]: ...

    def explain_update(self, before_state: WorldState, observation: Observation, after_state: WorldState, model: Any | None = None) -> dict[str, Any]:
        return {"label": observation.kind, "method": "replay_delta", "source_id": observation.source_id}

    def _check_observation(self, state: WorldState, obs: Observation) -> None:
        if obs.event_id != state.event_id:
            raise ValueError("observation event_id mismatch")
        if obs.sport != state.sport:
            raise ValueError("observation sport mismatch")
        if obs.kind not in self.supported_observation_kinds():
            raise ValueError(f"unsupported observation kind {obs.kind!r} for {state.sport.value}")
        if obs.known_to_model_time < state.created_at:
            # Historical replays can begin before process startup, so this is not
            # globally invalid. Keep chronological ordering check in the engine.
            pass
