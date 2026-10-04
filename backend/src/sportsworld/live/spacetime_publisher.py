"""Publish the live world state to SpacetimeDB (module: infra/spacetimedb).

The engine stays the single source of truth for every number; SpacetimeDB is the shared, transactional,
subscribable copy that browsers and agents read in real time. The publisher diffs what it last sent and
pushes only changed rows, through the module's owner-only reducers. A SpacetimeDB outage is logged and
never blocks or slows the engine.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from sportsworld.text_style import no_em_dash

log = logging.getLogger("sportsworld.spacetime")

QUALIFY = {"mens-college-basketball": "tournament", "womens-college-basketball": "tournament", "mens-college-hockey": "tournament"}
CONF = ("conference_champion", "conference_title")
CHUNK = 400


def _h(x: Any) -> str:
    return hashlib.blake2b(json.dumps(x, sort_keys=True, default=str).encode(), digest_size=10).hexdigest()


def _snake(row: dict) -> dict:
    """Nested product values cross the HTTP API with their canonical snake_case field names."""
    import re
    return {re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in row.items()}


def _f(x: Any) -> float:
    try:
        v = float(x)
        return v if v == v else 0.0  # NaN -> 0
    except (TypeError, ValueError):
        return 0.0


class SpacetimePublisher:
    def __init__(self, url: str, database: str, token: str, service, *, interval: float = 5.0):
        self.base = f"{url.rstrip('/')}/v1/database/{database}/call"
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.service = service
        self.interval = interval
        self.sent: dict[str, str] = {}
        self.feed_seen: dict[str, int] = {}
        self.wp_last: dict[str, float] = {}
        self.calls = 0
        self.errors = 0
        self.last_error: str | None = None

    async def _call(self, client: httpx.AsyncClient, reducer: str, args: dict) -> None:
        r = await client.post(f"{self.base}/{reducer}", headers=self.headers, content=no_em_dash(json.dumps(args, ensure_ascii=False)).encode("utf-8"))
        self.calls += 1
        if r.status_code >= 300:
            raise RuntimeError(f"{reducer} -> {r.status_code}: {r.text[:200]}")

    def status(self) -> dict:
        return {"calls": self.calls, "errors": self.errors, "last_error": self.last_error, "rows_tracked": len(self.sent)}

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                for league, st in list(self.service.states.items()):
                    try:
                        await self._publish_league(client, league, st)
                    except Exception as exc:  # never let the shared copy break the engine
                        self.errors += 1
                        self.last_error = f"{league}: {exc}"
                        log.warning("spacetime publish failed for %s: %s", league, exc)
                await asyncio.sleep(self.interval)

    async def _publish_league(self, client: httpx.AsyncClient, league: str, st) -> None:
        run = st.run or {}
        if league == "f1" or not run.get("teams"):
            return
        version = int(st.global_state_version or 0)
        diag = run.get("diagnostics") or {}
        rows = self._games(league, st)
        live = sum(1 for g in rows if g["state"] == "in")
        comp = {"league": league, "globalStateVersion": version, "runId": run.get("run_id") or "", "asOf": run.get("as_of") or "",
                "status": "recomputing" if st.computing else ("stale" if st.dirty else "fresh"), "draws": int(run.get("draws") or 0),
                "playedGames": int(diag.get("played_games") or 0), "remainingGames": int(diag.get("remaining_games") or len(rows)), "liveGames": live}
        if self.sent.get(f"c:{league}") != _h(comp):
            await self._call(client, "publish_competition", comp)
            self.sent[f"c:{league}"] = _h(comp)

        q = QUALIFY.get(league, "playoffs")
        teams = []
        for t in run["teams"]:
            row = {"teamId": str(t["team_id"]), "name": t.get("name") or "", "conference": t.get("conference") or "",
                   "rating": _f(t.get("rating")), "ratingSd": _f(t.get("rating_sd")), "expectedWins": _f(t.get("expected_wins")),
                   "qualify": _f(t.get(q)), "conferenceTitle": _f(next((t[k] for k in CONF if k in t), 0)), "title": _f(t.get("champion"))}
            key = f"t:{league}:{row['teamId']}"
            if self.sent.get(key) != _h(row):
                teams.append((key, row))
        for i in range(0, len(teams), CHUNK):
            part = teams[i:i + CHUNK]
            await self._call(client, "publish_teams", {"league": league, "stateVersion": version, "rows": [_snake(r) for _, r in part]})
            for key, r in part:
                self.sent[key] = _h(r)

        changed = [(f"g:{g['eventId']}", g) for g in rows if self.sent.get(f"g:{g['eventId']}") != _h(g)]
        for i in range(0, len(changed), CHUNK):
            part = changed[i:i + CHUNK]
            await self._call(client, "publish_games", {"league": league, "stateVersion": version, "rows": [_snake(g) for _, g in part]})
            for key, g in part:
                self.sent[key] = _h(g)

        # win-probability history for live games (persists across API restarts)
        wp = []
        for g in rows:
            if g["state"] == "in" and abs(self.wp_last.get(g["eventId"], -1.0) - g["pHome"]) > 1e-4:
                wp.append({"eventId": g["eventId"], "at": run.get("as_of") or "", "pHome": g["pHome"]})
                self.wp_last[g["eventId"]] = g["pHome"]
        if wp:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            await self._call(client, "add_win_prob", {"rows": [_snake({**w, "at": now}) for w in wp]})

        feed = list(st.feed)
        seen = self.feed_seen.get(league, 0)
        for u in feed[seen:]:
            news = u.get("news")
            if news and not news.get("player"):
                continue  # ungrounded news signals stay out of the shared feed
            await self._call(client, "add_world_update", {"league": league, "at": str(u.get("at") or ""), "reason": str(u.get("reason") or "")[:300],
                                                         "teams": ",".join(map(str, u.get("teams") or [])), "stateVersion": int(u.get("global_state_version") or version)})
        self.feed_seen[league] = len(feed)

    def _games(self, league: str, st) -> list[dict]:
        tracker = self.service.trackers.get(league)
        live = {g.event_id: g for g in getattr(tracker, "games", {}).values()}
        out = []
        for r in st.board.values():
            g = live.get(r["event_id"])
            out.append({"eventId": r["event_id"], "startTime": r["start_time"], "state": g.state if g else r["state"],
                        "homeId": r["home_id"], "awayId": r["away_id"],
                        "homeScore": int(g.home.score) if g else 0, "awayScore": int(g.away.score) if g else 0,
                        "period": int(g.period or 0) if g else 0, "clockSeconds": _f(g.clock_seconds) if g else 0.0,
                        "pHome": _f(r.get("p_home")), "leverageHome": _f(r.get("leverage_home")), "leverageAway": _f(r.get("leverage_away"))})
        return out
