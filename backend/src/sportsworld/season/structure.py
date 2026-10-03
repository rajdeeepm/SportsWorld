"""League structure (conference / division membership) and official standings.

Source: ESPN standings API (`/apis/v2/sports/<path>/standings?level=3&season=<year>`).
The tree is League -> Conference -> Division (NFL/NBA/NHL) or League -> Conference
(FBS, WNBA, college).  Structure is cached per league-season under
data/real/structure/<league>/<espn_season>.json so the season engine and
historical backtests run offline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from sportsworld.ingest.leagues import LeagueSpec

STANDINGS = "https://site.api.espn.com/apis/v2/sports"


class TeamSlot(BaseModel):
    team_id: str
    name: str
    abbreviation: str | None = None
    conference: str
    division: str | None = None


class OfficialRow(BaseModel):
    team_id: str
    wins: int = 0
    losses: int = 0
    ties: int = 0
    ot_losses: int = 0
    points: float | None = None
    seed: int | None = None
    clincher: str | None = None


class LeagueStructure(BaseModel):
    league: str
    espn_season: int
    teams: list[TeamSlot]
    official: list[OfficialRow] = Field(default_factory=list)
    fetched_at: datetime

    def conferences(self) -> list[str]:
        return sorted({t.conference for t in self.teams})

    def divisions(self) -> list[str]:
        return sorted({t.division for t in self.teams if t.division})


def _stat(entry: dict, *names: str) -> float | None:
    for s in entry.get("stats", []):
        if s.get("name") in names or s.get("type") in names:
            try:
                return float(s.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def parse_structure(league: str, espn_season: int, payload: dict) -> LeagueStructure:
    teams: dict[str, TeamSlot] = {}
    official: dict[str, OfficialRow] = {}

    def visit(node: dict, conference: str | None, division: str | None, depth: int) -> None:
        name = node.get("name") or node.get("abbreviation") or "?"
        if depth == 1:
            conference = name
        elif depth == 2:
            division = name
        for e in node.get("standings", {}).get("entries", []):
            t = e.get("team", {})
            tid = str(t.get("id"))
            teams[tid] = TeamSlot(team_id=tid, name=t.get("displayName") or t.get("name") or tid, abbreviation=t.get("abbreviation"),
                                  conference=conference or name, division=division)
            seed = _stat(e, "playoffSeed")
            clincher = next((s.get("displayValue") for s in e.get("stats", []) if s.get("name") == "clincher"), None)
            official[tid] = OfficialRow(
                team_id=tid, wins=int(_stat(e, "wins") or 0), losses=int(_stat(e, "losses") or 0), ties=int(_stat(e, "ties") or 0),
                ot_losses=int(_stat(e, "otLosses", "overtimeLosses") or 0), points=_stat(e, "points"),
                seed=int(seed) if seed else None, clincher=clincher,
            )
        for child in node.get("children", []):
            visit(child, conference, division, depth + 1)

    visit(payload, None, None, 0)
    return LeagueStructure(league=league, espn_season=espn_season, teams=list(teams.values()), official=list(official.values()),
                           fetched_at=datetime.now(timezone.utc))


def structure_path(root: Path, league: str, espn_season: int) -> Path:
    return root / "structure" / league / f"{espn_season}.json"


async def fetch_structure(spec: LeagueSpec, espn_season: int, client: httpx.AsyncClient | None = None) -> LeagueStructure:
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, headers={"User-Agent": "SportsWorld/1.3"})
    try:
        url = f"{STANDINGS}/{spec.espn_path}/standings?level=3&season={espn_season}"
        if spec.groups:
            url += f"&group={spec.groups}"
        r = await client.get(url)
        r.raise_for_status()
        return parse_structure(spec.league_id, espn_season, r.json())
    finally:
        if own:
            await client.aclose()


def save_structure(root: Path, s: LeagueStructure) -> None:
    p = structure_path(root, s.league, s.espn_season)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s.model_dump_json(indent=1))


def load_structure(root: Path, league: str, espn_season: int) -> LeagueStructure | None:
    p = structure_path(root, league, espn_season)
    return LeagueStructure.model_validate_json(p.read_text()) if p.exists() else None
