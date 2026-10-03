"""Durable history in Neon Postgres: every season run, live win probabilities and the world-update feed.

The engine keeps working state in memory and the shared live copy in SpacetimeDB; Neon is the system of record
for history. It survives restarts and powers the odds-over-time charts, which need what the model believed at
each moment, not just now. Writes happen in a background loop and never block the engine.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("sportsworld.neon")

DDL = """
create table if not exists season_run (
  run_id text primary key,
  league text not null,
  state_version bigint not null,
  as_of timestamptz not null,
  draws integer not null,
  teams jsonb not null,
  diagnostics jsonb,
  archived_at timestamptz not null default now()
);
create index if not exists season_run_league_asof on season_run (league, as_of);
create table if not exists win_prob_point (
  id bigserial primary key,
  event_id text not null,
  league text not null,
  at timestamptz not null,
  p_home double precision not null,
  state_version bigint,
  home_score integer,
  away_score integer
);
create index if not exists win_prob_point_event on win_prob_point (event_id, at);
create table if not exists world_update (
  id bigserial primary key,
  league text not null,
  at timestamptz not null,
  reason text not null,
  teams text[] not null default '{}',
  state_version bigint
);
create index if not exists world_update_league_at on world_update (league, at);
"""

QUALIFY = {"mens-college-basketball": "tournament", "womens-college-basketball": "tournament", "mens-college-hockey": "tournament"}
CONF = ("conference_champion", "conference_title")


def _ts(x: Any) -> datetime:
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


class NeonArchive:
    def __init__(self, database_url: str, service, *, interval: float = 15.0, min_run_gap_s: float = 240.0):
        self.url = database_url
        self.service = service
        self.interval = interval
        self.min_run_gap_s = min_run_gap_s
        self.last_run: dict[str, tuple[str, int, float]] = {}
        self.feed_seen: dict[str, int] = {}
        self.wp_last: dict[str, float] = {}
        self.writes = 0
        self.errors = 0
        self.last_error: str | None = None
        self.ready = False

    def _connect(self):
        import psycopg
        return psycopg.connect(self.url, connect_timeout=15, autocommit=True)

    def status(self) -> dict:
        return {"ready": self.ready, "writes": self.writes, "errors": self.errors, "last_error": self.last_error}

    async def run(self) -> None:
        await asyncio.to_thread(self._init)
        while True:
            try:
                await asyncio.to_thread(self._tick)
            except Exception as exc:
                self.errors += 1
                self.last_error = str(exc)[:300]
                log.warning("neon archive tick failed: %s", exc)
            await asyncio.sleep(self.interval)

    def _init(self) -> None:
        with self._connect() as c:
            c.execute(DDL)
        self.ready = True

    def _tick(self) -> None:
        with self._connect() as c:
            for league, st in list(self.service.states.items()):
                run = st.run or {}
                if league == "f1" or not run.get("teams"):
                    continue
                self._archive_run(c, league, st, run)
                self._archive_live(c, league, st)
                self._archive_feed(c, league, st)

    def _archive_run(self, c, league: str, st, run: dict) -> None:
        rid, ver = run.get("run_id"), int(st.global_state_version or 0)
        prev = self.last_run.get(league)
        now = time.time()
        # keep every state-version change (a final, an injury), and live re-conditioning at most every few minutes
        if prev and (prev[0] == rid or (prev[1] == ver and now - prev[2] < self.min_run_gap_s)):
            return
        q = QUALIFY.get(league, "playoffs")
        teams = [{"id": t["team_id"], "r": round(float(t.get("rating") or 0), 2), "sd": round(float(t.get("rating_sd") or 0), 2),
                  "ew": round(float(t.get("expected_wins") or 0), 2), "q": round(float(t.get(q) or 0), 4),
                  "c": round(float(next((t[k] for k in CONF if k in t), 0) or 0), 4), "t": round(float(t.get("champion") or 0), 4)}
                 for t in run["teams"]]
        c.execute("insert into season_run (run_id, league, state_version, as_of, draws, teams, diagnostics) values (%s,%s,%s,%s,%s,%s,%s) "
                  "on conflict (run_id) do nothing",
                  (rid, league, ver, _ts(run.get("as_of")), int(run.get("draws") or 0), json.dumps(teams), json.dumps(run.get("diagnostics") or {})))
        self.writes += 1
        self.last_run[league] = (rid, ver, now)

    def _archive_live(self, c, league: str, st) -> None:
        tracker = self.service.trackers.get(league)
        live = {g.event_id: g for g in getattr(tracker, "games", {}).values() if g.state == "in"}
        rows = []
        for eid, g in live.items():
            r = st.board.get(eid)
            if not r or r.get("p_home") is None:
                continue
            p = float(r["p_home"])
            if abs(self.wp_last.get(eid, -1.0) - p) > 1e-4:
                rows.append((eid, league, datetime.now(timezone.utc), p, int(st.global_state_version or 0), int(g.home.score), int(g.away.score)))
                self.wp_last[eid] = p
        if rows:
            with c.cursor() as cur:
                cur.executemany("insert into win_prob_point (event_id, league, at, p_home, state_version, home_score, away_score) values (%s,%s,%s,%s,%s,%s,%s)", rows)
            self.writes += len(rows)

    def _archive_feed(self, c, league: str, st) -> None:
        feed = list(st.feed)
        seen = self.feed_seen.get(league, 0)
        rows = [(league, _ts(u.get("at")), str(u.get("reason") or "")[:500], [str(x) for x in u.get("teams") or []], int(u.get("global_state_version") or 0))
                for u in feed[seen:] if not (u.get("news") and not u["news"].get("player"))]
        if rows:
            with c.cursor() as cur:
                cur.executemany("insert into world_update (league, at, reason, teams, state_version) values (%s,%s,%s,%s,%s)", rows)
            self.writes += len(rows)
        self.feed_seen[league] = len(feed)

    # ---------------------------------------------------------------- reads

    def team_history(self, league: str, team_id: str, limit: int = 400) -> list[dict]:
        with self._connect() as c:
            rows = c.execute(
                "select as_of, state_version, t, run_id from season_run, jsonb_array_elements(teams) t "
                "where league = %s and t->>'id' = %s order by as_of desc limit %s", (league, team_id, limit)).fetchall()
        return [{"at": a.isoformat(), "state_version": v, "rating": t["r"], "rating_sd": t["sd"], "expected_wins": t["ew"],
                 "qualify": t["q"], "conference": t["c"], "title": t["t"], "replay": rid.startswith("pit-")} for a, v, t, rid in reversed(rows)]

    def game_history(self, event_id: str) -> list[dict]:
        with self._connect() as c:
            rows = c.execute("select at, p_home, home_score, away_score from win_prob_point where event_id = %s order by at", (event_id,)).fetchall()
        return [{"at": a.isoformat(), "p_home": p, "home_score": h, "away_score": w} for a, p, h, w in rows]
