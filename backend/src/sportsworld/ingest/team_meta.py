"""Team identity metadata from ESPN (official colours, logos, standing summary) for the UI.

Identity only: nothing here enters any model. Cached on disk so the UI renders offline in replay mode.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .espn import BASE
from .leagues import LEAGUES

LIST_TTL_S = 24 * 3600
DETAIL_TTL_S = 5 * 60
_mem: dict[str, tuple[float, Any]] = {}


def _cache_dir(root: Path) -> Path:
    d = root / "meta"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(p: Path, ttl: float) -> Any | None:
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except Exception:
        return None
    return data if time.time() - data.get("_fetched", 0) < ttl else {**data, "_stale": True}


def _logo(logos: list[dict], dark: bool = False) -> str | None:
    """ESPN tags logos with rel lists such as ["full", "default"] and ["full", "dark"] (the version for dark grounds)."""
    for lg in logos or []:
        rel = lg.get("rel") or []
        if dark and "dark" in rel:
            return lg.get("href")
        if not dark and "default" in rel and "dark" not in rel:
            return lg.get("href")
    return (logos or [{}])[0].get("href")


def _team_row(t: dict) -> dict[str, Any]:
    return {"team_id": str(t.get("id")), "name": t.get("displayName"), "short_name": t.get("shortDisplayName"),
            "location": t.get("location"), "nickname": t.get("name"), "abbreviation": t.get("abbreviation"),
            "color": f"#{t['color']}" if t.get("color") else None,
            "alt_color": f"#{t['alternateColor']}" if t.get("alternateColor") else None,
            "logo": _logo(t.get("logos", [])), "logo_dark": _logo(t.get("logos", []), dark=True)}


def league_meta(league: str, root: Path) -> dict[str, dict[str, Any]]:
    """{team_id: identity} for every team ESPN lists in the league. Falls back to the disk cache when offline."""
    spec = LEAGUES[league]
    if not spec.espn_path:
        return {}
    p = _cache_dir(root) / f"{league}.json"
    cached = _read(p, LIST_TTL_S)
    if cached is not None and not cached.get("_stale"):
        return cached["teams"]
    try:
        params = {"limit": 1000}
        if spec.groups:
            params["groups"] = spec.groups
        r = httpx.get(f"{BASE}/{spec.espn_path}/teams", params=params, timeout=20, headers={"User-Agent": "SportsWorld/1.3"})
        r.raise_for_status()
        teams = [x["team"] for sp in r.json().get("sports", []) for lg in sp.get("leagues", []) for x in lg.get("teams", [])]
        out = {row["team_id"]: row for row in map(_team_row, teams)}
        p.write_text(json.dumps({"_fetched": time.time(), "teams": out}))
        return out
    except Exception:
        return cached["teams"] if cached else {}


def team_detail(league: str, team_id: str, root: Path) -> dict[str, Any]:
    """Official record summary, standing summary, poll rank and home venue for one team."""
    spec = LEAGUES[league]
    if not spec.espn_path:
        return {}
    key = f"{league}:{team_id}"
    hit = _mem.get(key)
    if hit and time.time() - hit[0] < DETAIL_TTL_S:
        return hit[1]
    p = _cache_dir(root) / f"{league}_{team_id}.json"
    try:
        r = httpx.get(f"{BASE}/{spec.espn_path}/teams/{team_id}", timeout=15, headers={"User-Agent": "SportsWorld/1.3"})
        r.raise_for_status()
        t = r.json().get("team", {})
        items = (t.get("record") or {}).get("items") or []
        venue = (t.get("franchise") or {}).get("venue") or {}
        out = {**_team_row(t), "record_summary": items[0].get("summary") if items else None,
               "standing_summary": t.get("standingSummary"), "rank": t.get("rank"),
               "venue": venue.get("fullName"), "venue_city": ((venue.get("address") or {}).get("city")),
               "source": "ESPN team API", "_fetched": time.time()}
        p.write_text(json.dumps(out))
    except Exception:
        out = json.loads(p.read_text()) if p.exists() else {}
    _mem[key] = (time.time(), out)
    return out
