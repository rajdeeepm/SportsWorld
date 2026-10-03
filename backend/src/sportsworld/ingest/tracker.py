"""Concurrent every-team / every-game tracker for all ESPN-backed leagues.

One `LeagueTracker` per league owns that league's Kalman rating book and the
set of games inside its tracking window.  `TrackerService` runs them all
concurrently:

* schedule loop (every ~10 min): pull the scoreboard for yesterday..+lookahead
  days, create an event for every new game, refresh status of every game.
* live loop (every ~20 s): for leagues with a game in progress (or about to
  start), pull only the relevant days; one request covers every game that day.

Every change becomes a normalized `Observation` (score_state / game_end /
team_state) ingested through the ordinary ForecastEngine path, so live games
get the same versioned state, forecast history, drivers and WebSocket stream
as any other event.  League boards are also published on the WebSocket channel
`league:<league_id>`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sportsworld.schemas import EventCreate, Observation, SourceType, Sport

from .espn import (
    PARSER_VERSION, SOURCE_ID, ESPNClient, GameRecord, archive_path, drop_exhibitions, read_archive,
    season_start_year, write_archive,
)
from .f1_tracker import F1Tracker
from .leagues import LEAGUES, TEAM_LEAGUES, LeagueSpec
from .ratings import RatingBook, load_meta, load_params

log = logging.getLogger("sportsworld.tracker")
ET = ZoneInfo("America/New_York")
STATUS = {"pre": "upcoming", "in": "live", "post": "completed"}
LOOKAHEAD_DAYS = {Sport.FOOTBALL: 8, Sport.BASKETBALL: 2, Sport.HOCKEY: 2}


def _et_day(t: datetime) -> date:
    return t.astimezone(ET).date()


def seconds_remaining(spec: LeagueSpec, g: GameRecord) -> float:
    if g.state == "pre" or g.period <= 0:
        return float(spec.regulation_seconds)
    if g.state == "post":
        return 0.0
    if g.period <= spec.periods:
        return float((spec.periods - g.period) * spec.period_seconds + max(0.0, g.clock_seconds))
    return float(max(0.0, min(spec.period_seconds, g.clock_seconds)))  # overtime


def live_payload(spec: LeagueSpec, g: GameRecord) -> dict[str, Any]:
    p: dict[str, Any] = {"home_score": g.home.score, "away_score": g.away.score, "seconds_remaining": seconds_remaining(spec, g)}
    if spec.sport == Sport.FOOTBALL:
        p["quarter"] = max(1, g.period)
        s = g.situation
        if s.get("possession"):
            home_has = str(s["possession"]) == g.home.team_id
            p["possession"] = "home" if home_has else "away"
            if s.get("yardLine") is not None:
                # ESPN yardLine is measured from the home goal line; the adapter
                # expects yards from the possessing team's own goal line.
                yl = float(s["yardLine"])
                p["yard_line"] = yl if home_has else 100.0 - yl
        for src, dst in (("down", "down"), ("distance", "distance"), ("homeTimeouts", "home_timeouts"), ("awayTimeouts", "away_timeouts")):
            if s.get(src) is not None and int(s[src]) >= 0:
                p[dst] = int(s[src])
    return p


class LeagueTracker:
    def __init__(self, spec: LeagueSpec, ctx, data_root: Path, *, now: datetime | None = None):
        self.spec = spec
        self.ctx = ctx
        self.data_root = data_root
        self.games: dict[str, GameRecord] = {}
        self.fingerprints: dict[str, tuple] = {}
        self.completed_applied: set[str] = set()
        self.dirty_seasons: set[int] = set()
        self.last_sync: datetime | None = None
        self.errors: list[str] = []
        now = now or datetime.now(timezone.utc)
        self.window_start = datetime.combine(_et_day(now) - timedelta(days=1), datetime.min.time(), ET).astimezone(timezone.utc)
        meta_path = self._repo() / "models" / "artifacts" / "ratings" / f"{spec.league_id}.json"
        params = load_params(meta_path)
        self.ep_coef = load_meta(meta_path).get("ep_coef")
        self.book = RatingBook(spec, params, keep_history=True)
        self.on_final: Callable[[str, str, list[str], dict], None] | None = None
        self.availability = None  # ingest.availability.LeagueAvailability
        self.on_live: Callable[[str], None] | None = None
        history = drop_exhibitions(read_archive(data_root, spec.league_id))
        # Everything before the window is history; games inside the window are
        # replayed live through the engine so their forecasts are point-in-time.
        self.book.replay([g for g in history if g.start_time < self.window_start], until=self.window_start)

    @staticmethod
    def _repo() -> Path:
        return Path(__file__).resolve().parents[4]

    # ------------------------------------------------------------------
    def refresh_availability(self, team_ids: set[str], cause: str) -> None:
        self._refresh_upcoming(team_ids, cause, datetime.now(timezone.utc))

    def _team_fields(self, g: GameRecord) -> dict[str, Any]:
        st = self.book.pregame_state(g)
        if self.availability is not None:
            for side in ("home", "away"):
                tid = getattr(g, side).team_id
                nxt = min((x.start_time for x in self.games.values() if x.state == "pre" and tid in (x.home.team_id, x.away.team_id)), default=None)
                d = self.availability.delta_for(tid, g.start_time, nxt)
                st[f"{side}_availability_delta"] = d
                st[f"{side}_rating"] = float(st[f"{side}_rating"]) + d
        sd = self.spec.margin_sd
        st["home_strength"] = max(-1.0, min(1.0, float(st["home_rating"]) / (2 * sd)))
        st["away_strength"] = max(-1.0, min(1.0, float(st["away_rating"]) / (2 * sd)))
        return st

    def _create(self, g: GameRecord, now: datetime) -> None:
        features = {**self._team_fields(g), "home_score": 0, "away_score": 0, "seconds_remaining": float(self.spec.regulation_seconds)}
        if self.spec.sport == Sport.FOOTBALL:
            # down=0 marks the possession as unknown until ESPN reports a live situation.
            features.update({"quarter": 1, "possession": "home", "yard_line": 25, "down": 0, "weather_severity": 0.0})
            if self.ep_coef:
                features["ep_coef"] = self.ep_coef
        elif self.spec.sport == Sport.BASKETBALL:
            features.update({"pace": 100.0})
        req = EventCreate(
            event_id=g.event_id, sport=self.spec.sport, competition=self.spec.league_id, season=str(g.season),
            outcomes=["home", "away"], start_time=g.start_time, participants=[g.home.name, g.away.name], venue=g.venue,
            initial_features=features, as_of=min(now, g.start_time),
            metadata={
                "league": self.spec.league_id, "league_name": self.spec.display_name, "espn_game_id": g.game_id,
                "display_outcomes": {"home": g.home.name, "away": g.away.name},
                "abbreviations": {"home": g.home.abbreviation, "away": g.away.abbreviation},
                "outcome_entity_ids": {"home": f"{self.spec.league_id}:team:{g.home.team_id}", "away": f"{self.spec.league_id}:team:{g.away.team_id}"},
                "team_ids": {"home": g.home.team_id, "away": g.away.team_id},
                "records": {"home": g.home.record, "away": g.away.record}, "ranks": {"home": g.home.rank, "away": g.away.rank},
                "week": g.week, "season_type": g.season_type, "neutral_site": g.neutral_site, "conference_game": g.conference_game,
                "weather": g.weather, "external_consensus": g.odds, "data_mode": "real_espn", "replay_mode": False,
                "source_ref": f"https://www.espn.com/{self.spec.espn_path.split('/')[1]}/game/_/gameId/{g.game_id}",
            },
        )
        self.ctx.engine.create_event(req, status=STATUS[g.state])

    def _observe(self, g: GameRecord, kind: str, payload: dict[str, Any], now: datetime, *, label: str | None = None) -> None:
        state = self.ctx.store.get_state(g.event_id)
        known = max(now, state.prediction_cutoff)
        obs = Observation(
            event_id=g.event_id, sport=self.spec.sport, kind=kind, payload={**payload, **({"label": label} if label else {})},
            source_id=SOURCE_ID, source_type=SourceType.STATS, source_url_or_ref=f"espn:{self.spec.league_id}:{g.game_id}",
            confidence=0.97, event_time=now, known_to_model_time=known, ingestion_time=known, parser_version=PARSER_VERSION,
        )
        self.ctx.engine.ingest(obs)

    def _refresh_upcoming(self, team_ids: set[str], cause: str, now: datetime) -> None:
        """Push updated latent team state into every not-yet-started event for these teams."""
        for eid, g in self.games.items():
            if g.state != "pre" or not ({g.home.team_id, g.away.team_id} & team_ids):
                continue
            try:
                self._observe(g, "team_state", self._team_fields(g), now, label=f"Rating update: {cause}")
            except Exception as exc:  # pragma: no cover - defensive
                self.errors.append(f"{eid}: {exc}")

    def handle(self, g: GameRecord, now: datetime) -> dict | None:
        """Apply one scoreboard snapshot. Returns a board row if something changed."""
        if g.season_type == 1 and self.spec.sport == Sport.FOOTBALL:
            return None  # NFL/CFB preseason is not tracked
        if any(t.team_id.startswith("-") or t.name == "TBD" for t in (g.home, g.away)):
            return None  # playoff placeholder; created once ESPN resolves the matchup
        existing = self._exists(g.event_id)
        if not existing:
            if g.cancelled:
                return None
            self._create(g, now)
        prev = self.games.get(g.event_id)
        if prev is not None and g.fetched_at < prev.fetched_at:
            return None  # an older response arrived after a newer one: never regress state
        self.games[g.event_id] = g
        if g.cancelled:
            self.ctx.store.update_event(g.event_id, status="completed", metadata={"cancelled": g.status_name})
            return self._row(g)
        fp = (g.state, g.home.score, g.away.score, g.period, round(g.clock_seconds), tuple(sorted(g.situation.items())) if g.situation else ())
        changed = fp != self.fingerprints.get(g.event_id)
        self.fingerprints[g.event_id] = fp
        if prev is None or prev.state != g.state:
            self.ctx.store.update_event(g.event_id, status=STATUS[g.state], metadata={"records": {"home": g.home.record, "away": g.away.record}})
        if g.state in {"in", "post"} and changed:
            self._observe(g, "score_state", live_payload(self.spec, g), now)
            if g.state == "in" and self.on_live:
                self.on_live(self.spec.league_id)
        if g.state == "post" and g.completed and g.event_id not in self.completed_applied:
            self._observe(g, "game_end", {"home_score": g.home.score, "away_score": g.away.score}, now)
            self.completed_applied.add(g.event_id)
            before = self.book.games_applied
            self.book.apply_result(g)
            self.dirty_seasons.add(season_start_year(self.spec, g.start_time))
            if self.book.games_applied > before:
                winner = g.home if g.home.score > g.away.score else g.away
                loser = g.away if winner is g.home else g.home
                desc = f"{winner.abbreviation or winner.name} {max(g.home.score, g.away.score)}-{min(g.home.score, g.away.score)} {loser.abbreviation or loser.name}"
                self._refresh_upcoming({g.home.team_id, g.away.team_id}, desc, now)
                if self.on_final:
                    self.on_final(self.spec.league_id, f"Final: {desc}", [g.home.team_id, g.away.team_id],
                                  {"event_id": g.event_id, "rating_after": {t: round(self.book.teams[t].mean, 2) for t in (g.home.team_id, g.away.team_id) if t in self.book.teams}})
        return self._row(g) if changed or prev is None else None

    def _exists(self, event_id: str) -> bool:
        try:
            self.ctx.store.get_event(event_id)
            return True
        except KeyError:
            return False

    def _row(self, g: GameRecord) -> dict:
        try:
            f = self.ctx.engine.latest_forecast(g.event_id)
            probs, unc, model = f.probabilities, f.uncertainty.total, f.model_version
        except Exception:
            probs, unc, model = {}, None, None
        return {
            "event_id": g.event_id, "league": self.spec.league_id, "status": STATUS[g.state], "status_detail": g.status_name,
            "start_time": g.start_time.isoformat(), "period": g.period, "clock_seconds": g.clock_seconds,
            "home": {"name": g.home.name, "abbreviation": g.home.abbreviation, "score": g.home.score, "record": g.home.record, "rank": g.home.rank},
            "away": {"name": g.away.name, "abbreviation": g.away.abbreviation, "score": g.away.score, "record": g.away.record, "rank": g.away.rank},
            "probabilities": probs, "uncertainty": unc, "model_version": model, "neutral_site": g.neutral_site,
        }

    def board(self) -> list[dict]:
        return [self._row(g) for g in sorted(self.games.values(), key=lambda x: (x.start_time, x.game_id))]

    def persist(self) -> None:
        """Merge completed tracked games into the on-disk archive (the training source of truth)."""
        for season in sorted(self.dirty_seasons):
            path = archive_path(self.data_root, self.spec.league_id, season)
            existing = [GameRecord.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
            fresh = [g for g in self.games.values() if season_start_year(self.spec, g.start_time) == season]
            write_archive(path, existing + fresh)
        self.dirty_seasons.clear()

    # ------------------------------------------------------------------
    async def fetch_days(self, client: ESPNClient, days: list[date]) -> list[GameRecord]:
        results = await asyncio.gather(*(client.scoreboard(self.spec, d) for d in days), return_exceptions=True)
        snapshot: dict[str, GameRecord] = {}
        for r in results:
            if isinstance(r, Exception):
                self.errors = (self.errors + [f"{type(r).__name__}: {r}"])[-20:]
                continue
            for g in r:
                if g.start_time >= self.window_start:
                    snapshot[g.event_id] = g
        return sorted(snapshot.values(), key=lambda x: (x.start_time, x.game_id))

    def apply(self, games: list[GameRecord]) -> list[dict]:
        """Synchronous (no awaits), so it is atomic on the event loop."""
        now = datetime.now(timezone.utc)
        changed = []
        for g in games:
            try:
                row = self.handle(g, now)
                if row:
                    changed.append(row)
            except Exception as exc:
                log.exception("tracker %s failed on %s", self.spec.league_id, g.event_id)
                self.errors = (self.errors + [f"{g.event_id}: {exc}"])[-20:]
        self.last_sync = now
        return changed

    async def sync_days(self, client: ESPNClient, days: list[date]) -> list[dict]:
        return self.apply(await self.fetch_days(client, days))

    def schedule_days(self, now: datetime) -> list[date]:
        today = _et_day(now)
        ahead = LOOKAHEAD_DAYS.get(self.spec.sport, 2)
        return [today + timedelta(days=i) for i in range(-1, ahead + 1)]

    def live_days(self, now: datetime) -> list[date]:
        soon = now + timedelta(minutes=20)
        return sorted({_et_day(g.start_time) for g in self.games.values() if g.state == "in" or (g.state == "pre" and g.start_time <= soon)})

    def status(self) -> dict:
        counts: dict[str, int] = {}
        for g in self.games.values():
            counts[STATUS[g.state]] = counts.get(STATUS[g.state], 0) + 1
        return {
            "league": self.spec.league_id, "name": self.spec.display_name, "sport": self.spec.sport.value,
            "games_tracked": len(self.games), "by_status": counts, "teams_rated": len(self.book.teams),
            "rating_games_applied": self.book.games_applied, "rating_params": self.book.params.to_dict(),
            "last_sync": self.last_sync.isoformat() if self.last_sync else None, "recent_errors": self.errors[-5:],
        }


class TrackerService:
    def __init__(self, ctx, data_root: Path, leagues: list[str] | None = None, *, schedule_interval: float = 600.0,
                 live_interval: float = 20.0, publish: Callable[[str, str, dict], None] | None = None, openf1_token: str | None = None):
        self.ctx = ctx
        self.data_root = data_root
        self.league_ids = leagues or TEAM_LEAGUES + ["f1"]
        self.openf1_token = openf1_token
        self.schedule_interval = schedule_interval
        self.live_interval = live_interval
        self.publish = publish
        self.trackers: dict[str, LeagueTracker | F1Tracker] = {}
        self.client = ESPNClient()
        self._tasks: list[asyncio.Task] = []
        self._f1_lock = asyncio.Lock()

    def build(self) -> None:
        for lid in self.league_ids:
            if lid in self.trackers or lid not in LEAGUES:
                continue
            if LEAGUES[lid].espn_path:
                self.trackers[lid] = LeagueTracker(LEAGUES[lid], self.ctx, self.data_root)
            elif lid == "f1":
                self.trackers[lid] = F1Tracker(self.ctx, self.data_root, openf1_token=self.openf1_token)

    async def _sync(self, tracker: LeagueTracker, days: list[date]) -> None:
        if not days:
            return
        changed = tracker.apply(await tracker.fetch_days(self.client, days))
        if changed and self.publish:
            self.publish(f"league:{tracker.spec.league_id}", "board.updated", {"league": tracker.spec.league_id, "games": changed})

    async def _sync_f1(self, tracker: F1Tracker, live: bool) -> None:
        now = datetime.now(timezone.utc)
        async with self._f1_lock:  # F1 sync interleaves awaits with mutations
            ids = await (tracker.sync_live(now) if live else tracker.sync_schedule(now))
        if ids and self.publish:
            self.publish("league:f1", "board.updated", {"league": "f1", "games": [tracker.row(i) for i in dict.fromkeys(ids)]})

    def _team_trackers(self) -> list[LeagueTracker]:
        return [t for t in self.trackers.values() if isinstance(t, LeagueTracker)]

    async def sync_all(self) -> None:
        now = datetime.now(timezone.utc)
        jobs = [self._sync(t, t.schedule_days(now)) for t in self._team_trackers()]
        jobs += [self._sync_f1(t, live=False) for t in self.trackers.values() if isinstance(t, F1Tracker)]
        await asyncio.gather(*jobs)
        for t in self.trackers.values():
            t.persist()

    async def _schedule_loop(self) -> None:
        while True:
            try:
                await self.sync_all()
            except Exception:
                log.exception("schedule sync failed")
            await asyncio.sleep(self.schedule_interval)

    async def _live_loop(self) -> None:
        while True:
            await asyncio.sleep(self.live_interval)
            now = datetime.now(timezone.utc)
            try:
                jobs = [self._sync(t, t.live_days(now)) for t in self._team_trackers()]
                jobs += [self._sync_f1(t, live=True) for t in self.trackers.values() if isinstance(t, F1Tracker) and t.live_races(now)]
                await asyncio.gather(*jobs)
            except Exception:
                log.exception("live sync failed")

    def start(self) -> None:
        self.build()
        self._tasks = [asyncio.create_task(self._schedule_loop()), asyncio.create_task(self._live_loop())]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for t in self.trackers.values():
            t.persist()
            if isinstance(t, F1Tracker):
                await t.aclose()
        await self.client.aclose()
