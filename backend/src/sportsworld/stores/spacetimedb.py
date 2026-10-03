from __future__ import annotations

from datetime import datetime
import httpx

from sportsworld.schemas import (
    ContextSignal,
    ContextSnapshot,
    CounterfactualResult,
    EntityMetric,
    EntityProfile,
    EventRecord,
    Forecast,
    Observation,
    Sport,
    WorldState,
)
from .base import Store


class SpacetimeDBStore(Store):
    """Adapter for a deployed SportsWorld SpacetimeDB gateway.

    The included TypeScript module owns live/event/context tables.  A tiny HTTP
    gateway generated around that module exposes this stable Python contract so
    SDK revisions do not leak into the forecasting core.
    """

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _get(self, p):
        r = httpx.get(self.base_url + p, headers=self.headers, timeout=5)
        r.raise_for_status()
        return r.json()

    def _post(self, p, data):
        r = httpx.post(self.base_url + p, headers=self.headers, json=data, timeout=5)
        r.raise_for_status()
        return r.json() if r.content else {}

    def create_event(self, event: EventRecord, initial_state: WorldState) -> None:
        self._post("/events", {"event": event.model_dump(mode="json"), "state": initial_state.model_dump(mode="json")})

    def list_events(self) -> list[EventRecord]:
        return [EventRecord.model_validate(x) for x in self._get("/events")]

    def get_event(self, event_id: str) -> EventRecord:
        return EventRecord.model_validate(self._get(f"/events/{event_id}"))

    def get_state(self, event_id: str, version: int | None = None) -> WorldState:
        return WorldState.model_validate(self._get(f"/events/{event_id}/state" + (f"?version={version}" if version is not None else "")))

    def save_state(self, state: WorldState) -> None:
        self._post(f"/events/{state.event_id}/state", state.model_dump(mode="json"))

    def append_observation(self, obs: Observation) -> bool:
        return bool(self._post(f"/events/{obs.event_id}/observations", obs.model_dump(mode="json")).get("inserted", True))

    def list_observations(self, event_id: str) -> list[Observation]:
        return [Observation.model_validate(x) for x in self._get(f"/events/{event_id}/observations")]

    def save_forecast(self, forecast: Forecast) -> None:
        self._post(f"/events/{forecast.event_id}/forecasts", forecast.model_dump(mode="json"))

    def list_forecasts(self, event_id: str) -> list[Forecast]:
        return [Forecast.model_validate(x) for x in self._get(f"/events/{event_id}/forecasts")]

    def save_counterfactual(self, result: CounterfactualResult) -> None:
        self._post(f"/events/{result.event_id}/counterfactuals", result.model_dump(mode="json"))

    # Historical/context memory -------------------------------------------------
    def upsert_entity_profile(self, profile: EntityProfile) -> None:
        self._post(f"/context/entities/{profile.entity_id}", profile.model_dump(mode="json"))

    def get_entity_profile(self, entity_id: str) -> EntityProfile:
        return EntityProfile.model_validate(self._get(f"/context/entities/{entity_id}"))

    def list_entity_profiles(self, sport: Sport | None = None, team_id: str | None = None) -> list[EntityProfile]:
        qs = []
        if sport is not None:
            qs.append(f"sport={sport.value}")
        if team_id is not None:
            qs.append(f"team_id={team_id}")
        suffix = ("?" + "&".join(qs)) if qs else ""
        return [EntityProfile.model_validate(x) for x in self._get("/context/entities" + suffix)]

    def append_entity_metric(self, metric: EntityMetric) -> bool:
        return bool(self._post(f"/context/entities/{metric.entity_id}/metrics", metric.model_dump(mode="json")).get("inserted", True))

    def list_entity_metrics(self, entity_id: str, as_of: datetime | None = None) -> list[EntityMetric]:
        suffix = f"?as_of={as_of.isoformat()}" if as_of else ""
        return [EntityMetric.model_validate(x) for x in self._get(f"/context/entities/{entity_id}/metrics{suffix}")]

    def append_context_signal(self, signal: ContextSignal) -> bool:
        return bool(self._post(f"/events/{signal.event_id}/context/signals", signal.model_dump(mode="json")).get("inserted", True))

    def list_context_signals(self, event_id: str, as_of: datetime | None = None) -> list[ContextSignal]:
        suffix = f"?as_of={as_of.isoformat()}" if as_of else ""
        return [ContextSignal.model_validate(x) for x in self._get(f"/events/{event_id}/context/signals{suffix}")]

    def save_context_snapshot(self, snapshot: ContextSnapshot) -> None:
        self._post(f"/events/{snapshot.event_id}/context/snapshots", snapshot.model_dump(mode="json"))

    def get_context_snapshot(self, event_id: str, state_version: int | None = None) -> ContextSnapshot:
        suffix = f"?state_version={state_version}" if state_version is not None else ""
        return ContextSnapshot.model_validate(self._get(f"/events/{event_id}/context{suffix}"))

    def list_context_snapshots(self, event_id: str) -> list[ContextSnapshot]:
        return [ContextSnapshot.model_validate(x) for x in self._get(f"/events/{event_id}/context/history")]

    def clear_event_runtime(self, event_id: str) -> None:
        self._post(f"/events/{event_id}/reset", {})
