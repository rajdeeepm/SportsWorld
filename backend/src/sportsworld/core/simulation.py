from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from sportsworld.core.math import wilson_interval
from sportsworld.schemas import CounterfactualRequest, CounterfactualResult, Observation, ScenarioOperation, SourceType, Sport, WorldState
from sportsworld.simulators import BasketballSequentialSimulator, F1SequentialSimulator, FootballSequentialSimulator
from sportsworld.simulators.base import SequentialSimulationResult


@dataclass(slots=True)
class Simulator:
    adapters: dict
    registry: Any
    context_engine: Any | None = None
    sequential: dict[Sport, Any] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if Sport.FOOTBALL in self.adapters:
            self.sequential[Sport.FOOTBALL] = FootballSequentialSimulator(self.adapters[Sport.FOOTBALL])
        if Sport.BASKETBALL in self.adapters:
            self.sequential[Sport.BASKETBALL] = BasketballSequentialSimulator(self.adapters[Sport.BASKETBALL])
        if Sport.F1 in self.adapters:
            self.sequential[Sport.F1] = F1SequentialSimulator(self.adapters[Sport.F1])

    def apply_operation(self, state: WorldState, op: ScenarioOperation, sequence_no: int = 0) -> WorldState:
        payload = dict(op.payload)
        if op.effective_lap is not None:
            payload.setdefault("lap", op.effective_lap)
        if op.kind == "feature_override":
            s = state.clone(); s.features.update(payload); return s

        if self.context_engine and self.context_engine.handles(op.kind):
            return self.context_engine.apply_scenario_proxy(state, op.kind, payload)

        obs = Observation(
            event_id=state.event_id, sport=state.sport, kind=op.kind, payload=payload,
            source_id="counterfactual", source_type=SourceType.MANUAL, confidence=1.0,
            event_time=op.effective_time, known_to_model_time=state.prediction_cutoff,
            sequence_no=sequence_no, verified=True,
        )
        branch = self.adapters[state.sport].apply_observation(state, obs)
        if self.context_engine:
            branch = self.context_engine.apply_scenario_proxy(branch, op.kind, payload)
        return branch

    def _fallback_draw(self, state: WorldState, draws: int, seed: int) -> SequentialSimulationResult:
        rng = np.random.default_rng(seed); bundle = self.registry.predict(state); labels=list(bundle.probabilities)
        probs=np.asarray([bundle.probabilities[k] for k in labels],dtype=float);idx=rng.choice(len(labels),size=draws,p=probs)
        outcomes=[labels[i] for i in idx.tolist()]
        return SequentialSimulationResult.from_outcomes(outcomes,labels,draws,steps=np.ones(draws),transition_kind="terminal_distribution_fallback",diagnostics={"reason":"no sport-specific sequential simulator"})

    def _draw(self, state: WorldState, draws: int, seed: int, *, capture_paths: int = 3) -> SequentialSimulationResult:
        sim = self.sequential.get(state.sport)
        if sim is None:
            return self._fallback_draw(state,draws,seed)
        return sim.simulate(state,draws,seed,capture_paths=capture_paths)

    def run(self, base: WorldState, request: CounterfactualRequest, seed_default: int = 7) -> CounterfactualResult:
        seed=request.seed if request.seed is not None else seed_default
        branch=base.clone()
        for i,op in enumerate(request.overrides,1): branch=self.apply_operation(branch,op,i)

        # Counterfactual probability is now the empirical distribution of full
        # sequential futures, not a terminal categorical resample of the static
        # model probability.  The predictive models still inform transition
        # strengths/context, while the simulator explicitly evolves state.
        current=self._draw(base,request.draws,seed,capture_paths=2)
        scenario=self._draw(branch,request.draws,seed+1,capture_paths=3)
        labels=list(base.outcomes)
        return CounterfactualResult(
            event_id=base.event_id,base_state_version=base.state_version,label=request.label,
            assumptions=request.overrides,draws=request.draws,seed=seed,
            current_probabilities=current.probabilities,scenario_probabilities=scenario.probabilities,
            probability_delta_pp={k:100*(scenario.probabilities.get(k,0)-current.probabilities.get(k,0)) for k in labels},
            current_intervals_90=current.intervals_90,scenario_intervals_90=scenario.intervals_90,
            simulation_counts=scenario.counts,standard_error=scenario.standard_error,
            simulation_method=scenario.transition_kind,current_mean_steps=current.mean_steps,scenario_mean_steps=scenario.mean_steps,
            representative_paths=scenario.representative_paths,
            simulation_diagnostics={"current":current.diagnostics,"scenario":scenario.diagnostics},
        )
