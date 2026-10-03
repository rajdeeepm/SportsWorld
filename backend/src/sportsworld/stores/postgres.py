from __future__ import annotations

import json
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


class PostgresStore(Store):
    """Neon/Postgres durable store for live history and contextual memory.

    JSONB keeps flexible sport-specific payloads while explicit point-in-time
    columns make leakage rules queryable/auditable. Apply infra/sql/001_init.sql
    before selecting STORE_BACKEND=postgres.
    """

    def __init__(self, database_url: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install sportsworld[postgres] to use PostgresStore") from exc
        self.psycopg = psycopg
        self.url = database_url

    def _conn(self):
        return self.psycopg.connect(self.url)

    def create_event(self, event: EventRecord, initial_state: WorldState) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events(event_id,sport,competition,season,participants,venue,start_time,status,metadata) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                (event.event_id, event.sport.value, event.competition, event.season, json.dumps(event.participants), event.venue, event.start_time, event.status, json.dumps(event.metadata)),
            )
            self._insert_state(cur, initial_state)

    def _insert_state(self, cur, s: WorldState):
        cur.execute(
            "INSERT INTO state_snapshots(event_id,state_version,as_of,features_json,observation_cursor,prediction_cutoff,metadata_json) VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb) ON CONFLICT(event_id,state_version) DO NOTHING",
            (s.event_id, s.state_version, s.updated_at, json.dumps(s.features), s.observation_cursor, s.prediction_cutoff, json.dumps(s.metadata)),
        )

    def list_events(self) -> list[EventRecord]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT event_id,sport,competition,season,participants,venue,start_time,status,metadata FROM events ORDER BY start_time")
            rows = cur.fetchall()
        return [EventRecord(event_id=r[0], sport=r[1], competition=r[2], season=r[3], outcomes=self.get_state(r[0], 0).outcomes, participants=r[4], venue=r[5], start_time=r[6], status=r[7], metadata=r[8]) for r in rows]

    def update_event(self, event_id: str, status: str | None = None, metadata: dict | None = None) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            if status is not None:
                cur.execute("UPDATE events SET status=%s WHERE event_id=%s", (status, event_id))
            if metadata:
                cur.execute("UPDATE events SET metadata = metadata || %s::jsonb WHERE event_id=%s", (json.dumps(metadata), event_id))

    def get_event(self, event_id: str) -> EventRecord:
        for e in self.list_events():
            if e.event_id == event_id:
                e.current_state_version = self.get_state(event_id).state_version
                return e
        raise KeyError(event_id)

    def get_state(self, event_id: str, version: int | None = None) -> WorldState:
        with self._conn() as conn, conn.cursor() as cur:
            if version is None:
                cur.execute("SELECT state_version,as_of,features_json,observation_cursor,prediction_cutoff,metadata_json FROM state_snapshots WHERE event_id=%s ORDER BY state_version DESC LIMIT 1", (event_id,))
            else:
                cur.execute("SELECT state_version,as_of,features_json,observation_cursor,prediction_cutoff,metadata_json FROM state_snapshots WHERE event_id=%s AND state_version=%s", (event_id, version))
            r = cur.fetchone()
            if not r:
                raise KeyError(event_id)
            cur.execute("SELECT sport,competition,season,metadata FROM events WHERE event_id=%s", (event_id,))
            ev = cur.fetchone()
        outcomes = r[5].get("outcomes") or ev[3].get("outcomes") or ["home", "away"]
        return WorldState(event_id=event_id, sport=ev[0], competition=ev[1], season=ev[2], outcomes=outcomes, features=r[2], state_version=r[0], observation_cursor=r[3], created_at=r[1], updated_at=r[1], prediction_cutoff=r[4], metadata=r[5])

    def save_state(self, state: WorldState) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            self._insert_state(cur, state)

    def append_observation(self, obs: Observation) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO observations(observation_id,event_id,sport,kind,payload_json,source_id,source_type,source_url_or_ref,confidence,event_time,known_to_model_time,ingestion_time,sequence_no,dedupe_key,parser_version,raw_record_ref,verified) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(event_id,dedupe_key) DO NOTHING RETURNING observation_id",
                (obs.observation_id, obs.event_id, obs.sport.value, obs.kind, json.dumps(obs.payload), obs.source_id, obs.source_type.value, obs.source_url_or_ref, obs.confidence, obs.event_time, obs.known_to_model_time, obs.ingestion_time, obs.sequence_no, obs.dedupe_key, obs.parser_version, obs.raw_record_ref, obs.verified),
            )
            return cur.fetchone() is not None

    def list_observations(self, event_id: str) -> list[Observation]:
        with self._conn() as conn, conn.cursor(row_factory=self.psycopg.rows.dict_row) as cur:
            cur.execute("SELECT * FROM observations WHERE event_id=%s ORDER BY sequence_no,known_to_model_time", (event_id,))
            rows = cur.fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["payload"] = r.pop("payload_json")
            out.append(Observation.model_validate(r))
        return out

    def save_forecast(self, forecast: Forecast) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO forecasts(forecast_id,event_id,state_version,model_version,calibration_version,as_of,data_cutoff,payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)", (forecast.forecast_id, forecast.event_id, forecast.state_version, forecast.model_version, forecast.calibration_version, forecast.as_of, forecast.data_cutoff, forecast.model_dump_json()))

    def list_forecasts(self, event_id: str) -> list[Forecast]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload_json FROM forecasts WHERE event_id=%s ORDER BY as_of", (event_id,))
            return [Forecast.model_validate(r[0]) for r in cur.fetchall()]

    def save_counterfactual(self, result: CounterfactualResult) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO counterfactual_runs(run_id,event_id,base_state_version,overrides_json,draws,seed,payload_json) VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)", (result.run_id, result.event_id, result.base_state_version, json.dumps([x.model_dump(mode="json") for x in result.assumptions]), result.draws, result.seed, result.model_dump_json()))

    # Historical/context memory -------------------------------------------------
    def upsert_entity_profile(self, profile: EntityProfile) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entity_profiles(entity_id,sport,entity_type,display_name,team_id,role,attributes_json,capabilities_json,importance,source_ids,valid_from,valid_to,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT(entity_id) DO UPDATE SET sport=EXCLUDED.sport,entity_type=EXCLUDED.entity_type,display_name=EXCLUDED.display_name,team_id=EXCLUDED.team_id,role=EXCLUDED.role,attributes_json=EXCLUDED.attributes_json,capabilities_json=EXCLUDED.capabilities_json,importance=EXCLUDED.importance,source_ids=EXCLUDED.source_ids,valid_from=EXCLUDED.valid_from,valid_to=EXCLUDED.valid_to,updated_at=EXCLUDED.updated_at
                """,
                (profile.entity_id, profile.sport.value, profile.entity_type.value, profile.display_name, profile.team_id, profile.role, json.dumps(profile.attributes), json.dumps(profile.capabilities), profile.importance, json.dumps(profile.source_ids), profile.valid_from, profile.valid_to, profile.updated_at),
            )

    def get_entity_profile(self, entity_id: str) -> EntityProfile:
        with self._conn() as conn, conn.cursor(row_factory=self.psycopg.rows.dict_row) as cur:
            cur.execute("SELECT * FROM entity_profiles WHERE entity_id=%s", (entity_id,))
            row = cur.fetchone()
        if not row:
            raise KeyError(entity_id)
        r = dict(row)
        r["attributes"] = r.pop("attributes_json")
        r["capabilities"] = r.pop("capabilities_json")
        return EntityProfile.model_validate(r)

    def list_entity_profiles(self, sport: Sport | None = None, team_id: str | None = None) -> list[EntityProfile]:
        query = "SELECT * FROM entity_profiles WHERE TRUE"
        args = []
        if sport is not None:
            query += " AND sport=%s"
            args.append(sport.value)
        if team_id is not None:
            query += " AND team_id=%s"
            args.append(team_id)
        query += " ORDER BY display_name"
        with self._conn() as conn, conn.cursor(row_factory=self.psycopg.rows.dict_row) as cur:
            cur.execute(query, tuple(args))
            rows = cur.fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["attributes"] = r.pop("attributes_json")
            r["capabilities"] = r.pop("capabilities_json")
            out.append(EntityProfile.model_validate(r))
        return out

    def append_entity_metric(self, metric: EntityMetric) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entity_metrics(metric_id,entity_id,sport,metric,dimension,raw_value_json,normalized_value,unit,sample_size,occurred_at,known_to_model_time,ingestion_time,source_id,source_type,source_url_or_ref,confidence,event_id,opponent_id,season,competition,tags_json,dedupe_key)
                VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(entity_id,dedupe_key) DO NOTHING RETURNING metric_id
                """,
                (metric.metric_id, metric.entity_id, metric.sport.value, metric.metric, metric.dimension, json.dumps(metric.raw_value), metric.normalized_value, metric.unit, metric.sample_size, metric.occurred_at, metric.known_to_model_time, metric.ingestion_time, metric.source_id, metric.source_type.value, metric.source_url_or_ref, metric.confidence, metric.event_id, metric.opponent_id, metric.season, metric.competition, json.dumps(metric.tags), metric.dedupe_key),
            )
            return cur.fetchone() is not None

    def list_entity_metrics(self, entity_id: str, as_of: datetime | None = None) -> list[EntityMetric]:
        query = "SELECT * FROM entity_metrics WHERE entity_id=%s"
        args: list = [entity_id]
        if as_of is not None:
            query += " AND known_to_model_time<=%s"
            args.append(as_of)
        query += " ORDER BY known_to_model_time,occurred_at"
        with self._conn() as conn, conn.cursor(row_factory=self.psycopg.rows.dict_row) as cur:
            cur.execute(query, tuple(args))
            rows = cur.fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["raw_value"] = r.pop("raw_value_json")
            r["tags"] = r.pop("tags_json")
            out.append(EntityMetric.model_validate(r))
        return out

    def append_context_signal(self, signal: ContextSignal) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO context_signals(signal_id,event_id,sport,category,effect,label,summary,target_entity_id,direction,strength,volatility,sentiment,observed_at,known_to_model_time,ingestion_time,source_id,source_type,source_url_or_ref,confidence,verified,public_evidence_only,parser_version,metadata_json,dedupe_key)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(event_id,dedupe_key) DO NOTHING RETURNING signal_id
                """,
                (signal.signal_id, signal.event_id, signal.sport.value, signal.category.value, signal.effect.value, signal.label, signal.summary, signal.target_entity_id, signal.direction, signal.strength, signal.volatility, signal.sentiment, signal.observed_at, signal.known_to_model_time, signal.ingestion_time, signal.source_id, signal.source_type.value, signal.source_url_or_ref, signal.confidence, signal.verified, signal.public_evidence_only, signal.parser_version, json.dumps(signal.metadata), signal.dedupe_key),
            )
            return cur.fetchone() is not None

    def list_context_signals(self, event_id: str, as_of: datetime | None = None) -> list[ContextSignal]:
        query = "SELECT * FROM context_signals WHERE event_id=%s"
        args: list = [event_id]
        if as_of is not None:
            query += " AND known_to_model_time<=%s"
            args.append(as_of)
        query += " ORDER BY known_to_model_time"
        with self._conn() as conn, conn.cursor(row_factory=self.psycopg.rows.dict_row) as cur:
            cur.execute(query, tuple(args))
            rows = cur.fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["metadata"] = r.pop("metadata_json")
            out.append(ContextSignal.model_validate(r))
        return out

    def save_context_snapshot(self, snapshot: ContextSnapshot) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO context_snapshots(event_id,state_version,as_of,payload_json) VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT(event_id,state_version) DO UPDATE SET as_of=EXCLUDED.as_of,payload_json=EXCLUDED.payload_json",
                (snapshot.event_id, snapshot.state_version, snapshot.as_of, snapshot.model_dump_json()),
            )

    def get_context_snapshot(self, event_id: str, state_version: int | None = None) -> ContextSnapshot:
        with self._conn() as conn, conn.cursor() as cur:
            if state_version is None:
                cur.execute("SELECT payload_json FROM context_snapshots WHERE event_id=%s ORDER BY state_version DESC LIMIT 1", (event_id,))
            else:
                cur.execute("SELECT payload_json FROM context_snapshots WHERE event_id=%s AND state_version=%s", (event_id, state_version))
            row = cur.fetchone()
        if not row:
            raise KeyError(event_id)
        return ContextSnapshot.model_validate(row[0])

    def list_context_snapshots(self, event_id: str) -> list[ContextSnapshot]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload_json FROM context_snapshots WHERE event_id=%s ORDER BY state_version", (event_id,))
            return [ContextSnapshot.model_validate(r[0]) for r in cur.fetchall()]

    def clear_event_runtime(self, event_id: str) -> None:
        raise RuntimeError("Postgres replay reset is intentionally not destructive; create a new replay event id")
