"""ESPN public scoreboard client: every game, every team, one request per league-day.

The scoreboard endpoint is unofficial and undocumented, so this module keeps the
parsing defensive and normalizes everything into `GameRecord`.  Observed limits
(probed 2026-10-02): one calendar day per request (date ranges return nothing),
`limit` must be <= 500 (larger values silently fall back to 25 rows), and the
`groups` filter selects FBS (80) / Division I basketball (50).
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .leagues import LeagueSpec

BASE = "https://site.api.espn.com/apis/site/v2/sports"
PARSER_VERSION = "espn-scoreboard-v1"
SOURCE_ID = "espn-scoreboard"


class TeamLine(BaseModel):
    team_id: str
    name: str
    abbreviation: str | None = None
    score: int = 0
    linescores: list[float] = Field(default_factory=list)
    record: str | None = None
    rank: int | None = None


class GameRecord(BaseModel):
    league: str
    game_id: str
    season: int
    season_type: int
    week: int | None = None
    start_time: datetime
    state: Literal["pre", "in", "post"]
    status_name: str
    completed: bool
    period: int = 0
    clock_seconds: float = 0.0
    home: TeamLine
    away: TeamLine
    neutral_site: bool = False
    conference_game: bool = False
    venue: str | None = None
    situation: dict[str, Any] = Field(default_factory=dict)
    weather: dict[str, Any] = Field(default_factory=dict)
    # External consensus is kept but deliberately never used as a model feature.
    odds: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime

    @property
    def event_id(self) -> str:
        return f"{self.league}-{self.game_id}"

    @property
    def cancelled(self) -> bool:
        return self.status_name in {"STATUS_CANCELED", "STATUS_POSTPONED", "STATUS_FORFEIT", "STATUS_SUSPENDED"}

    def margin(self) -> int:
        return self.home.score - self.away.score


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _team(comp: dict) -> TeamLine:
    team = comp.get("team", {})
    records = comp.get("records") or []
    overall = next((r.get("summary") for r in records if r.get("type") == "total"), None)
    rank = (comp.get("curatedRank") or {}).get("current")
    return TeamLine(
        team_id=str(team.get("id") or comp.get("id")),
        name=team.get("displayName") or team.get("name") or str(team.get("id")),
        abbreviation=team.get("abbreviation"),
        score=_int(comp.get("score")),
        linescores=[float(x.get("value", 0) or 0) for x in comp.get("linescores") or []],
        record=overall,
        rank=rank if isinstance(rank, int) and 0 < rank < 99 else None,
    )


def parse_event(league: str, event: dict, fetched_at: datetime) -> GameRecord | None:
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None
    status = comp.get("status") or event.get("status") or {}
    stype = status.get("type", {})
    situation = {k: v for k, v in (comp.get("situation") or {}).items() if k != "lastPlay"}
    weather = event.get("weather") or comp.get("weather") or {}
    odds = (comp.get("odds") or [{}])[0] if comp.get("odds") else {}
    start = datetime.fromisoformat(str(event.get("date")).replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return GameRecord(
        league=league,
        game_id=str(event["id"]),
        season=_int((event.get("season") or {}).get("year"), start.year),
        season_type=_int((event.get("season") or {}).get("type"), 2),
        week=(event.get("week") or {}).get("number"),
        start_time=start,
        state=stype.get("state", "pre") if stype.get("state") in {"pre", "in", "post"} else "pre",
        status_name=str(stype.get("name", "")),
        completed=bool(stype.get("completed", False)),
        period=_int(status.get("period")),
        clock_seconds=float(status.get("clock") or 0.0),
        home=_team(sides["home"]),
        away=_team(sides["away"]),
        neutral_site=bool(comp.get("neutralSite", False)),
        conference_game=bool(comp.get("conferenceCompetition", False)),
        venue=(comp.get("venue") or {}).get("fullName"),
        situation=situation,
        weather={k: weather.get(k) for k in ("displayValue", "temperature", "conditionId") if k in weather},
        odds={k: odds.get(k) for k in ("details", "spread", "overUnder", "provider") if k in odds},
        fetched_at=fetched_at,
    )


class ESPNClient:
    def __init__(self, *, timeout: float = 15.0, concurrency: int = 6, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "SportsWorld/1.2 (MHacks research)"})
        self._sem = asyncio.Semaphore(concurrency)

    async def aclose(self) -> None:
        await self._client.aclose()

    def url(self, spec: LeagueSpec, day: date | None = None) -> str:
        params = ["limit=500"]
        if spec.groups:
            params.append(f"groups={spec.groups}")
        if day is not None:
            params.append(f"dates={day:%Y%m%d}")
        return f"{BASE}/{spec.espn_path}/scoreboard?{'&'.join(params)}"

    async def scoreboard(self, spec: LeagueSpec, day: date | None = None) -> list[GameRecord]:
        if not spec.espn_path:
            raise ValueError(f"{spec.league_id} is not an ESPN-backed league")
        url = self.url(spec, day)
        delay = 1.0
        async with self._sem:
            for attempt in range(4):
                try:
                    resp = await self._client.get(url)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                    resp.raise_for_status()
                    payload = resp.json()
                    break
                except (httpx.HTTPError, json.JSONDecodeError):
                    if attempt == 3:
                        raise
                    await asyncio.sleep(delay)
                    delay *= 2
        fetched = datetime.now(timezone.utc)
        games = [parse_event(spec.league_id, ev, fetched) for ev in payload.get("events", [])]
        return [g for g in games if g is not None]


def season_days(spec: LeagueSpec, season_start_year: int) -> list[date]:
    """All calendar days a league's season can span, starting in `season_start_year`."""
    start = date(season_start_year, spec.season_start_month, 1)
    end_year = season_start_year + (1 if spec.season_end_month < spec.season_start_month else 0)
    end_month_last = (date(end_year + (spec.season_end_month == 12), spec.season_end_month % 12 + 1, 1) - timedelta(days=1))
    return [start + timedelta(days=i) for i in range((end_month_last - start).days + 1)]


# ---------------------------------------------------------------------------
# On-disk game archive: data/real/games/<league>/<season_start_year>.jsonl
# ---------------------------------------------------------------------------
def archive_path(root: Path, league: str, season_start_year: int) -> Path:
    return root / "games" / league / f"{season_start_year}.jsonl"


def write_archive(path: Path, games: list[GameRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = {g.game_id: g for g in sorted(games, key=lambda g: g.fetched_at)}
    rows = sorted(unique.values(), key=lambda g: (g.start_time, g.game_id))
    path.write_text("".join(g.model_dump_json() + "\n" for g in rows))


def read_archive(root: Path, league: str) -> list[GameRecord]:
    games: list[GameRecord] = []
    folder = root / "games" / league
    if not folder.exists():
        return games
    for path in sorted(folder.glob("*.jsonl"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        games.extend(GameRecord.model_validate_json(line) for line in path.read_text().splitlines() if line.strip())
    return sorted(games, key=lambda g: (g.start_time, g.game_id))


PRO_LEAGUES = {"nfl", "nba", "wnba"}


def drop_exhibitions(games: list[GameRecord]) -> list[GameRecord]:
    """Drop preseason (type 1) and all-star/pro-bowl style games.

    A team must have a regular-season game; in pro leagues (fixed franchises) it
    must also have played >= 10 games in some season, which removes all-star
    sides that ESPN files under the regular season (e.g. "Team Shaq").
    """
    counts: dict[tuple[str, str, int], int] = {}
    for g in games:
        if g.season_type == 2:
            for t in (g.home.team_id, g.away.team_id):
                counts[(g.league, t, g.season)] = counts.get((g.league, t, g.season), 0) + 1
    keep: set[tuple[str, str]] = set()
    for (league, team, _), n in counts.items():
        if league not in PRO_LEAGUES or n >= 10:
            keep.add((league, team))
    return [g for g in games if g.season_type != 1 and (g.league, g.home.team_id) in keep and (g.league, g.away.team_id) in keep]


def season_start_year(spec: LeagueSpec, when: datetime) -> int:
    if spec.season_start_month <= spec.season_end_month:
        return when.year
    return when.year if when.month >= spec.season_start_month else when.year - 1
