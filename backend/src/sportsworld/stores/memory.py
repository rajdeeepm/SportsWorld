from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime

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


class MemoryStore(Store):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, EventRecord] = {}
        self._states: dict[str, dict[int, WorldState]] = defaultdict(dict)
        self._obs: dict[str, list[Observation]] = defaultdict(list)
        self._forecasts: dict[str, list[Forecast]] = defaultdict(list)
        self._counterfactuals: dict[str, list[CounterfactualResult]] = defaultdict(list)
        self._dedupe: set[tuple[str, str]] = set()

        self._profiles: dict[str, EntityProfile] = {}
        self._metrics: dict[str, list[EntityMetric]] = defaultdict(list)
        self._metric_dedupe: set[tuple[str, str]] = set()
        self._signals: dict[str, list[ContextSignal]] = defaultdict(list)
        self._signal_dedupe: set[tuple[str, str]] = set()
        self._context_snapshots: dict[str, dict[int, ContextSnapshot]] = defaultdict(dict)

    def create_event(self, event: EventRecord, initial_state: WorldState) -> None:
        with self._lock:
            if event.event_id in self._events:
                raise ValueError(f"event {event.event_id} already exists")
            self._events[event.event_id] = event.model_copy(deep=True)
            self._states[event.event_id][0] = initial_state.model_copy(deep=True)

    def list_events(self) -> list[EventRecord]:
        with self._lock:
            return [e.model_copy(deep=True) for e in self._events.values()]

    def get_event(self, event_id: str) -> EventRecord:
        with self._lock:
            if event_id not in self._events:
                raise KeyError(event_id)
            e = self._events[event_id].model_copy(deep=True)
            versions = self._states[event_id]
            e.current_state_version = max(versions) if versions else 0
            return e

    def update_event(self, event_id: str, status: str | None = None, metadata: dict | None = None) -> None:
        with self._lock:
            event = self._events[event_id]
            if status is not None:
                event.status = status
            if metadata:
                event.metadata = {**event.metadata, **metadata}

    def get_state(self, event_id: str, version: int | None = None) -> WorldState:
        with self._lock:
            versions = self._states.get(event_id)
            if not versions:
                raise KeyError(event_id)
            v = max(versions) if version is None else version
            if v not in versions:
                raise KeyError(f"state version {v}")
            return versions[v].model_copy(deep=True)

    def save_state(self, state: WorldState) -> None:
        with self._lock:
            self._states[state.event_id][state.state_version] = state.model_copy(deep=True)

    def append_observation(self, obs: Observation) -> bool:
        with self._lock:
            key = (obs.event_id, obs.dedupe_key or str(obs.observation_id))
            if key in self._dedupe:
                return False
            existing = self._obs[obs.event_id]
            if existing and obs.sequence_no and obs.sequence_no <= existing[-1].sequence_no:
                raise ValueError("observation sequence_no must be monotonic")
            self._dedupe.add(key)
            existing.append(obs.model_copy(deep=True))
            return True

    def list_observations(self, event_id: str) -> list[Observation]:
        with self._lock:
            return [o.model_copy(deep=True) for o in self._obs.get(event_id, [])]

    def save_forecast(self, forecast: Forecast) -> None:
        with self._lock:
            self._forecasts[forecast.event_id].append(forecast.model_copy(deep=True))

    def list_forecasts(self, event_id: str) -> list[Forecast]:
        with self._lock:
            return [f.model_copy(deep=True) for f in self._forecasts.get(event_id, [])]

    def save_counterfactual(self, result: CounterfactualResult) -> None:
        with self._lock:
            self._counterfactuals[result.event_id].append(result.model_copy(deep=True))

    # Historical/context memory -------------------------------------------------
    def upsert_entity_profile(self, profile: EntityProfile) -> None:
        with self._lock:
            self._profiles[profile.entity_id] = profile.model_copy(deep=True)

    def get_entity_profile(self, entity_id: str) -> EntityProfile:
        with self._lock:
            if entity_id not in self._profiles:
                raise KeyError(entity_id)
            return self._profiles[entity_id].model_copy(deep=True)

    def list_entity_profiles(self, sport: Sport | None = None, team_id: str | None = None) -> list[EntityProfile]:
        with self._lock:
            items = list(self._profiles.values())
            if sport is not None:
                items = [p for p in items if p.sport == sport]
            if team_id is not None:
                items = [p for p in items if p.team_id == team_id]
            return [p.model_copy(deep=True) for p in items]

    def append_entity_metric(self, metric: EntityMetric) -> bool:
        with self._lock:
            key = (metric.entity_id, metric.dedupe_key or str(metric.metric_id))
            if key in self._metric_dedupe:
                return False
            self._metric_dedupe.add(key)
            self._metrics[metric.entity_id].append(metric.model_copy(deep=True))
            self._metrics[metric.entity_id].sort(key=lambda m: (m.known_to_model_time, m.occurred_at))
            return True

    def list_entity_metrics(self, entity_id: str, as_of: datetime | None = None) -> list[EntityMetric]:
        with self._lock:
            items = self._metrics.get(entity_id, [])
            if as_of is not None:
                items = [m for m in items if m.known_to_model_time <= as_of]
            return [m.model_copy(deep=True) for m in items]

    def append_context_signal(self, signal: ContextSignal) -> bool:
        with self._lock:
            # UUID is enough for explicit writes; derived runtime signals include
            # a source-observation id in metadata so replayed duplicates dedupe.
            source_obs = str(signal.metadata.get("derived_from_observation", ""))
            key = (signal.event_id, source_obs or signal.dedupe_key or str(signal.signal_id))
            if key in self._signal_dedupe:
                return False
            self._signal_dedupe.add(key)
            self._signals[signal.event_id].append(signal.model_copy(deep=True))
            self._signals[signal.event_id].sort(key=lambda s: s.known_to_model_time)
            return True

    def list_context_signals(self, event_id: str, as_of: datetime | None = None) -> list[ContextSignal]:
        with self._lock:
            items = self._signals.get(event_id, [])
            if as_of is not None:
                items = [s for s in items if s.known_to_model_time <= as_of]
            return [s.model_copy(deep=True) for s in items]

    def save_context_snapshot(self, snapshot: ContextSnapshot) -> None:
        with self._lock:
            self._context_snapshots[snapshot.event_id][snapshot.state_version] = snapshot.model_copy(deep=True)

    def get_context_snapshot(self, event_id: str, state_version: int | None = None) -> ContextSnapshot:
        with self._lock:
            versions = self._context_snapshots.get(event_id)
            if not versions:
                raise KeyError(event_id)
            version = max(versions) if state_version is None else state_version
            if version not in versions:
                raise KeyError(f"context snapshot version {version}")
            return versions[version].model_copy(deep=True)

    def list_context_snapshots(self, event_id: str) -> list[ContextSnapshot]:
        with self._lock:
            versions = self._context_snapshots.get(event_id, {})
            return [versions[k].model_copy(deep=True) for k in sorted(versions)]

    def clear_event_runtime(self, event_id: str) -> None:
        with self._lock:
            if event_id not in self._events:
                return
            base = self._states[event_id].get(0)
            self._states[event_id] = {0: base.model_copy(deep=True)} if base else {}
            for o in self._obs.get(event_id, []):
                self._dedupe.discard((event_id, o.dedupe_key or str(o.observation_id)))
            self._obs[event_id] = []
            self._forecasts[event_id] = []
            self._counterfactuals[event_id] = []

            # Drop only live-derived context. Pregame historical/context fixture
            # memory remains intact, allowing a deterministic reset to rebuild
            # the same prior belief state.
            kept_signals = []
            self._signal_dedupe = {k for k in self._signal_dedupe if k[0] != event_id}
            for signal in self._signals.get(event_id, []):
                if not bool(signal.metadata.get("runtime")):
                    kept_signals.append(signal)
                    source_obs = str(signal.metadata.get("derived_from_observation", ""))
                    self._signal_dedupe.add((event_id, source_obs or signal.dedupe_key or str(signal.signal_id)))
            self._signals[event_id] = kept_signals

            for entity_id, metrics in list(self._metrics.items()):
                kept = []
                for metric in metrics:
                    if metric.event_id == event_id and "runtime" in metric.tags:
                        self._metric_dedupe.discard((entity_id, metric.dedupe_key or str(metric.metric_id)))
                    else:
                        kept.append(metric)
                self._metrics[entity_id] = kept

            snapshots = self._context_snapshots.get(event_id, {})
            self._context_snapshots[event_id] = {0: snapshots[0]} if 0 in snapshots else {}
