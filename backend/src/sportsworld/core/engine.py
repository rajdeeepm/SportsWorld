from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Callable

from sportsworld.context import ContextEngine
from sportsworld.core.attribution import transition_driver
from sportsworld.core.math import normalized_entropy
from sportsworld.models.registry import ModelRegistry
from sportsworld.schemas import EventCreate, EventRecord, Forecast, ForecastDriver, Observation, Sport, UncertaintySummary, WorldState
from sportsworld.stores.base import Store


class ForecastEngine:
    def __init__(
        self,
        store: Store,
        adapters: dict[Sport, object],
        registry: ModelRegistry,
        context_engine: ContextEngine | None = None,
        publish: Callable[[str, str, dict], None] | None = None,
    ):
        self.store = store
        self.adapters = adapters
        self.registry = registry
        self.context_engine = context_engine
        self.publish = publish
        self._recent_drivers: dict[str, deque[ForecastDriver]] = {}

    def create_event(self, req: EventCreate, status: str = "replay") -> WorldState:
        initial_time = req.as_of or req.start_time
        state = WorldState(
            event_id=req.event_id,
            sport=req.sport,
            competition=req.competition,
            season=req.season,
            outcomes=req.outcomes,
            features=req.initial_features,
            state_version=0,
            observation_cursor=0,
            created_at=initial_time,
            updated_at=initial_time,
            prediction_cutoff=initial_time,
            metadata={**req.metadata, "participants": req.participants, "venue": req.venue, "outcomes": req.outcomes},
        )
        self.adapters[req.sport].validate_state(state)
        context_snapshot = None
        if self.context_engine:
            state, context_snapshot = self.context_engine.enrich_state(state, persist_snapshot=False)

        event = EventRecord(
            event_id=req.event_id,
            sport=req.sport,
            competition=req.competition,
            season=req.season,
            outcomes=req.outcomes,
            participants=req.participants,
            venue=req.venue,
            start_time=req.start_time,
            status=status,
            metadata=req.metadata,
        )
        self.store.create_event(event, state)
        if context_snapshot is not None:
            self.store.save_context_snapshot(context_snapshot)
        self._recent_drivers[req.event_id] = deque(maxlen=12)
        forecast = self.forecast_state(state)
        self.store.save_forecast(forecast)
        return state

    def forecast_state(self, state: WorldState) -> Forecast:
        bundle = self.registry.predict(state)
        probs = bundle.probabilities
        entropy = normalized_entropy(probs.values())
        base_state_unc = 1 - float(state.features.get("state_confidence", 0.9))
        context_conf = float(state.features.get("context_confidence", 1.0))
        context_volatility = float(state.features.get("context_volatility", 0.0))
        context_unc = 0.6 * (1.0 - context_conf) + 0.4 * context_volatility
        state_unc = min(1.0, max(base_state_unc, context_unc))
        epi = bundle.epistemic
        total = min(1.0, max(entropy * 0.68 + state_unc * 0.32, epi or 0.0))
        drivers = list(self._recent_drivers.get(state.event_id, deque()))
        drivers = sorted(drivers, key=lambda d: abs(d.probability_delta), reverse=True)[:6]
        return Forecast(
            event_id=state.event_id,
            sport=state.sport,
            as_of=state.updated_at,
            state_version=state.state_version,
            model_version=bundle.model_version,
            calibration_version=bundle.calibration_version,
            probabilities=probs,
            intervals_90=bundle.intervals_90,
            uncertainty=UncertaintySummary(
                total=total,
                predictive_entropy=entropy,
                epistemic=epi,
                state=state_unc,
                method="bootstrap_ensemble+context_state" if epi is not None else "entropy+context_state",
            ),
            drivers=drivers,
            data_cutoff=state.prediction_cutoff,
        )

    def latest_forecast(self, event_id: str) -> Forecast:
        fs = self.store.list_forecasts(event_id)
        if fs:
            return fs[-1]
        f = self.forecast_state(self.store.get_state(event_id))
        self.store.save_forecast(f)
        return f

    def ingest(self, obs: Observation) -> Forecast:
        state = self.store.get_state(obs.event_id)
        if obs.sport != state.sport:
            raise ValueError("sport mismatch")
        if obs.known_to_model_time < state.prediction_cutoff:
            raise ValueError("stale observation: known_to_model_time precedes current prediction cutoff; use correction/replay rebuild")
        inserted = self.store.append_observation(obs)
        if not inserted:
            return self.latest_forecast(obs.event_id)

        before_f = self.forecast_state(state)
        context_only = bool(self.context_engine and self.context_engine.handles(obs.kind))
        if context_only:
            updated = state.clone()
        else:
            updated = self.adapters[state.sport].apply_observation(state, obs)

        # Context ingestion happens after the canonical observation has been
        # accepted, but before the next belief snapshot is compiled.
        if self.context_engine:
            self.context_engine.ingest_observation(obs, updated)

        updated.state_version = state.state_version + 1
        updated.observation_cursor = state.observation_cursor + 1
        updated.prediction_cutoff = obs.known_to_model_time
        updated.updated_at = max(obs.ingestion_time, obs.known_to_model_time)
        if self.context_engine:
            updated, snapshot = self.context_engine.enrich_state(updated, persist_snapshot=False)
        else:
            snapshot = None

        self.store.save_state(updated)
        if snapshot is not None:
            snapshot.state_version = updated.state_version
            self.store.save_context_snapshot(snapshot)

        after_bundle = self.registry.predict(updated)
        driver = transition_driver(before_f.probabilities, after_bundle.probabilities, obs)
        if context_only:
            driver.label = str(obs.payload.get("label", obs.kind)).replace("_", " ")
            driver.explanation = "Historical/context belief update; model revision, not a causal claim."
        self._recent_drivers.setdefault(obs.event_id, deque(maxlen=12)).appendleft(driver)
        forecast = self.forecast_state(updated)
        self.store.save_forecast(forecast)
        if self.publish:
            self.publish(obs.event_id, "observation.ingested", {"observation": obs.model_dump(mode="json"), "state_version": updated.state_version})
            self.publish(obs.event_id, "state.updated", {"state": updated.model_dump(mode="json")})
            if snapshot is not None:
                self.publish(obs.event_id, "context.updated", {"context": snapshot.model_dump(mode="json")})
            self.publish(obs.event_id, "forecast.updated", {"forecast": forecast.model_dump(mode="json")})
        return forecast

    def rebuild(self, event_id: str, until: datetime | None = None) -> Forecast:
        observations = self.store.list_observations(event_id)
        base = self.store.get_state(event_id, 0)
        self._recent_drivers[event_id] = deque(maxlen=12)
        state = base.clone()
        state.state_version = 0
        state.observation_cursor = 0
        for obs in observations:
            if until and obs.known_to_model_time > until:
                break
            before = self.registry.predict(state).probabilities
            if self.context_engine and self.context_engine.handles(obs.kind):
                nxt = state.clone()
            else:
                nxt = self.adapters[state.sport].apply_observation(state, obs)
            nxt.state_version = state.state_version + 1
            nxt.observation_cursor = state.observation_cursor + 1
            nxt.prediction_cutoff = obs.known_to_model_time
            nxt.updated_at = obs.ingestion_time
            if self.context_engine:
                nxt, _ = self.context_engine.enrich_state(nxt, persist_snapshot=False)
            after = self.registry.predict(nxt).probabilities
            self._recent_drivers[event_id].appendleft(transition_driver(before, after, obs))
            state = nxt
        return self.forecast_state(state)
