"""Live F1 tracker: every race in the season, every driver in the field.

* schedule sync: Jolpica calendar; races starting within [now - 1 day, now + 10 days]
  become events whose outcomes are the current field (driver codes).
* qualifying: once Jolpica publishes it, the grid is pushed as a `driver_state` observation.
* race: OpenF1 lap timing -> running order and gap to leader every live tick
  (`race_state`), plus safety-car and rainfall when available.
* settlement: Jolpica classified results -> `race_end` with the winner, then the
  driver/car Kalman ratings and reliability assimilate the result.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sportsworld.schemas import EventCreate, Observation, SourceType, Sport

from .f1 import (
    RACE_DURATION, F1Params, F1Race, F1RatingBook, JolpicaClient, OpenF1Client, lap_snapshot, read_f1_archive, write_f1_season,
)

SOURCE_JOLPICA = "jolpica-f1"
SOURCE_OPENF1 = "openf1-timing"


class F1Tracker:
    league_id = "f1"

    def __init__(self, ctx, data_root: Path, *, openf1_token: str | None = None, now: datetime | None = None):
        self.ctx = ctx
        self.data_root = data_root
        now = now or datetime.now(timezone.utc)
        self.window_start = now - timedelta(days=1)
        meta = data_root.parents[1] / "models" / "artifacts" / "ratings" / "f1.json"
        params = F1Params(**json.loads(meta.read_text())["params"]) if meta.exists() else F1Params()
        self.book = F1RatingBook(params)
        self.history = read_f1_archive(data_root)
        for race in self.history:
            if race.start_time < self.window_start:
                self.book.apply_race(race)
        self.jolpica = JolpicaClient()
        self.openf1 = OpenF1Client(token=openf1_token, min_interval=1.0)
        self.races: dict[str, F1Race] = {}
        self.sessions: dict[str, int] = {}
        self.grid_applied: set[str] = set()
        self.settled: set[str] = set()
        self.last_lap: dict[str, int] = {}
        self.live_blocked_until: datetime | None = None
        self.last_sync: datetime | None = None
        self.errors: list[str] = []
        self.on_final = None

    # ------------------------------------------------------------------
    def _field(self) -> list[dict]:
        """Current field: entrants of the most recent classified race."""
        latest = max((r for r in self.history if r.completed), key=lambda r: r.start_time, default=None)
        if latest is None:
            return []
        return [{"code": r.code, "driver_id": r.driver_id, "name": r.name, "constructor_id": r.constructor_id, "constructor": r.constructor} for r in latest.results]

    def _driver_fields(self, field: list[dict], grid: dict[str, int] | None = None) -> dict[str, dict]:
        views = {d["code"]: self.book.driver_view(d["driver_id"], d["constructor_id"]) for d in field}
        order = sorted(views, key=lambda c: -(views[c]["rating_driver"] + views[c]["rating_car"]))
        out = {}
        for d in field:
            c = d["code"]
            pos = (grid or {}).get(c) or (order.index(c) + 1)
            out[c] = {**views[c], "position": pos, "grid": pos if grid else 0, "gap_to_leader": 0.0, "name": d["name"], "constructor": d["constructor"],
                      "pace": -0.8 * (views[c]["rating_driver"] + views[c]["rating_car"])}
        return out

    def _exists(self, event_id: str) -> bool:
        try:
            self.ctx.store.get_event(event_id)
            return True
        except KeyError:
            return False

    def _observe(self, event_id: str, kind: str, payload: dict[str, Any], now: datetime, source: str, label: str | None = None) -> None:
        state = self.ctx.store.get_state(event_id)
        known = max(now, state.prediction_cutoff)
        self.ctx.engine.ingest(Observation(
            event_id=event_id, sport=Sport.F1, kind=kind, payload={**payload, **({"label": label} if label else {})}, source_id=source,
            source_type=SourceType.TELEMETRY if source == SOURCE_OPENF1 else SourceType.OFFICIAL, confidence=0.97,
            event_time=now, known_to_model_time=known, ingestion_time=known, parser_version="f1-v1",
        ))

    # ------------------------------------------------------------------
    async def sync_schedule(self, now: datetime) -> list[dict]:
        changed = []
        try:
            schedule = await self.jolpica.schedule(now.year)
        except Exception as exc:
            self.errors = (self.errors + [f"schedule: {exc}"])[-20:]
            return changed
        field = self._field()
        for race in schedule:
            if not (self.window_start <= race.start_time <= now + timedelta(days=10)):
                continue
            self.races[race.event_id] = race
            if not self._exists(race.event_id) and field:
                drivers = self._driver_fields(field)
                laps_hist = [max(x.laps for x in r.results) for r in self.history if r.circuit == race.circuit and r.results]
                total_laps = laps_hist[-1] if laps_hist else 57
                self.ctx.engine.create_event(EventCreate(
                    event_id=race.event_id, sport=Sport.F1, competition="f1", season=str(race.season), outcomes=list(drivers),
                    start_time=race.start_time, participants=[d["name"] for d in field], venue=race.circuit,
                    initial_features={"lap": 0, "total_laps": total_laps, "rain_probability": 0.0, "safety_car": 0.0, "drivers": drivers, "state_confidence": 0.9},
                    as_of=min(now, race.start_time),
                    metadata={"league": "f1", "league_name": "Formula 1", "race_name": race.race_name, "round": race.round,
                              "display_outcomes": {c: f"{d['name']} ({d['constructor']})" for c, d in drivers.items()},
                              "data_mode": "real_jolpica_openf1", "replay_mode": False},
                ), status="upcoming" if race.start_time > now else "live")
                changed.append(race.event_id)
            if race.event_id not in self.grid_applied and race.start_time - now < timedelta(days=2):
                try:
                    grid = await self.jolpica.qualifying_grid(race.season, race.round)
                except Exception:
                    grid = {}
                if grid:
                    fields = self._driver_fields(field, grid)
                    self._observe(race.event_id, "driver_state", {"drivers": {c: {"position": v["position"], "grid": v["grid"]} for c, v in fields.items()}},
                                  now, SOURCE_JOLPICA, label="Qualifying grid published")
                    self.grid_applied.add(race.event_id)
                    changed.append(race.event_id)
            changed += await self._settle(race, now)
        self.last_sync = now
        return changed

    async def _settle(self, race: F1Race, now: datetime) -> list[str]:
        if race.event_id in self.settled or now < race.start_time + RACE_DURATION or not self._exists(race.event_id):
            return []
        try:
            results = await self.jolpica.round_results(race.season, race.round)
        except Exception:
            return []
        if not results:
            return []
        race = race.model_copy(update={"results": results})
        state = self.ctx.store.get_state(race.event_id)
        winner = race.winner()
        classification = {r.code: r.position for r in results if r.position and r.code in state.outcomes}
        self._observe(race.event_id, "race_end", {"winner": winner.code if winner else None, "classification": classification}, now, SOURCE_JOLPICA,
                      label=f"Classified result: {winner.code if winner else 'n/a'} wins")
        self.ctx.store.update_event(race.event_id, status="completed")
        self.book.apply_race(race)
        self.history.append(race)
        write_f1_season(self.data_root, race.season, [r for r in self.history if r.season == race.season])
        self.settled.add(race.event_id)
        try:
            from sportsworld.season.f1_season import fetch_f1_season_state
            await fetch_f1_season_state(race.season, self.data_root)
        except Exception as exc:
            self.errors = (self.errors + [f"season state refresh: {exc}"])[-20:]
        if self.on_final:
            self.on_final("f1", f"Classified: {race.race_name} won by {winner.code if winner else 'n/a'}", [r.driver_id for r in results[:3]], {"event_id": race.event_id})
        return [race.event_id]

    def live_races(self, now: datetime) -> list[F1Race]:
        return [r for r in self.races.values() if r.start_time - timedelta(minutes=10) <= now <= r.start_time + timedelta(hours=3) and r.event_id not in self.settled]

    async def sync_live(self, now: datetime) -> list[dict]:
        changed = []
        if self.live_blocked_until and now < self.live_blocked_until:
            return changed
        for race in self.live_races(now):
            if not self._exists(race.event_id):
                continue
            self.ctx.store.update_event(race.event_id, status="live")
            try:
                key = self.sessions.get(race.event_id)
                if key is None:
                    session = await self.openf1.race_session(race.season, race.start_time)
                    if not session:
                        continue
                    key = self.sessions[race.event_id] = session["session_key"]
                drivers = await self.openf1.get("drivers", session_key=key)
                laps = await self.openf1.get("laps", session_key=key)
                lead_lap, snap = lap_snapshot(laps, drivers)
                if not snap or lead_lap == self.last_lap.get(race.event_id):
                    continue
                payload: dict[str, Any] = {"lap": lead_lap, "drivers": {c: {"position": v["position"], "gap_to_leader": v["gap_to_leader"]} for c, v in snap.items()}}
                try:
                    rc = await self.openf1.get("race_control", session_key=key, category="SafetyCar")
                    if rc:
                        msg = str(rc[-1].get("message", "")).upper()
                        payload["safety_car"] = 0.0 if "ENDING" in msg or "IN THIS LAP" in msg else 1.0
                    weather = await self.openf1.get("weather", session_key=key)
                    if weather:
                        payload["rain_probability"] = 1.0 if weather[-1].get("rainfall") else 0.0
                except Exception:
                    pass
                state = self.ctx.store.get_state(race.event_id)
                payload["drivers"] = {c: v for c, v in payload["drivers"].items() if c in state.outcomes}
                if lead_lap >= 3:  # no timing for this driver any more: retired
                    for c in state.outcomes:
                        if c not in payload["drivers"]:
                            payload["drivers"][c] = {"position": len(state.outcomes), "gap_to_leader": 120.0}
                self._observe(race.event_id, "race_state", {k: v for k, v in payload.items() if k in {"lap", "drivers"}}, now, SOURCE_OPENF1)
                if "safety_car" in payload:
                    self._observe(race.event_id, "safety_car", {"active": bool(payload["safety_car"])}, now, SOURCE_OPENF1)
                if "rain_probability" in payload:
                    self._observe(race.event_id, "weather", {"rain_probability": payload["rain_probability"]}, now, SOURCE_OPENF1)
                self.last_lap[race.event_id] = lead_lap
                changed.append(race.event_id)
            except PermissionError as exc:
                self.errors = (self.errors + [str(exc)])[-20:]
                self.live_blocked_until = now + timedelta(minutes=5)
            except Exception as exc:
                self.errors = (self.errors + [f"{race.event_id}: {type(exc).__name__}: {exc}"])[-20:]
        return changed

    # ------------------------------------------------------------------
    def row(self, event_id: str) -> dict:
        event = self.ctx.store.get_event(event_id)
        state = self.ctx.store.get_state(event_id)
        f = self.ctx.engine.latest_forecast(event_id)
        drivers = state.features.get("drivers", {})
        order = sorted(f.probabilities, key=lambda c: -f.probabilities[c])
        return {
            "event_id": event_id, "league": "f1", "kind": "race", "status": event.status, "start_time": event.start_time.isoformat(),
            "race_name": event.metadata.get("race_name"), "lap": state.features.get("lap", 0), "total_laps": state.features.get("total_laps"),
            "field": [{"code": c, "name": drivers.get(c, {}).get("name", c), "constructor": drivers.get(c, {}).get("constructor"),
                       "position": drivers.get(c, {}).get("position"), "gap_to_leader": drivers.get(c, {}).get("gap_to_leader"),
                       "probability": f.probabilities[c]} for c in order],
            "probabilities": f.probabilities, "uncertainty": f.uncertainty.total, "model_version": f.model_version,
        }

    def board(self) -> list[dict]:
        return [self.row(eid) for eid in sorted(self.races, key=lambda e: self.races[e].start_time) if self._exists(eid)]

    def status(self) -> dict:
        counts: dict[str, int] = {}
        for eid in self.races:
            if self._exists(eid):
                st = self.ctx.store.get_event(eid).status
                counts[st] = counts.get(st, 0) + 1
        return {"league": "f1", "name": "Formula 1", "sport": "f1", "games_tracked": sum(counts.values()), "by_status": counts,
                "teams_rated": len(self.book.drivers), "rating_games_applied": self.book.races_applied, "rating_params": self.book.p.to_dict(),
                "last_sync": self.last_sync.isoformat() if self.last_sync else None, "recent_errors": self.errors[-5:]}

    def persist(self) -> None:  # results are written at settlement time
        return None

    async def aclose(self) -> None:
        await self.jolpica.aclose()
        await self.openf1.aclose()
