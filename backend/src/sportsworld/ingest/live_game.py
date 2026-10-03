"""Live game view: real on-field / on-court / on-ice / on-track positions for the UI.

Sources (all public, all real):
- Football: ESPN summary drives + plays -> ball position (yards to the end zone), down & distance, drive chart.
- Basketball: ESPN play-by-play shot coordinates (feet, folded onto one half court; free throws carry a sentinel).
- Hockey: ESPN play-by-play event coordinates (feet, rink -100..100 x -42.5..42.5): shots, goals, hits, faceoffs.
- F1: OpenF1 car location samples (x, y, z on the circuit), positions and intervals.

Player tracking (every player's position) is proprietary for football, basketball and hockey and is not shown.
Nothing here feeds a model; it is display evidence with its source named.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .espn import BASE
from .leagues import LEAGUES

_cache: dict[str, tuple[float, Any]] = {}
UA = {"User-Agent": "SportsWorld/1.3"}
OPENF1 = "https://api.openf1.org/v1"


def _get(url: str, params: dict | None = None, ttl: float = 8.0, token: str | None = None) -> Any:
    key = url + repr(sorted((params or {}).items()))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    headers = {**UA, **({"Authorization": f"Bearer {token}"} if token else {})}
    r = httpx.get(url, params=params, timeout=25, headers=headers)
    r.raise_for_status()
    data = r.json()
    _cache[key] = (time.time(), data)
    return data


def _ok_coord(c: dict | None, limit: float) -> bool:
    return bool(c) and c.get("x") is not None and c.get("y") is not None and abs(c["x"]) <= limit and abs(c["y"]) <= limit


def game_view(league: str, game_id: str) -> dict[str, Any]:
    spec = LEAGUES[league]
    s = _get(f"{BASE}/{spec.espn_path}/summary", {"event": game_id})
    comp = (s.get("header", {}).get("competitions") or [{}])[0]
    status = comp.get("status", {})
    teams = {}
    for c in comp.get("competitors", []):
        t = c.get("team", {})
        teams[c.get("homeAway")] = {"team_id": str(t.get("id")), "name": t.get("displayName"), "abbreviation": t.get("abbreviation"),
                                     "score": int(c.get("score") or 0) if str(c.get("score", "")).isdigit() else None}
    out: dict[str, Any] = {
        "league": league, "game_id": game_id, "sport": spec.sport.value, "home": teams.get("home"), "away": teams.get("away"),
        "state": status.get("type", {}).get("state"), "detail": status.get("type", {}).get("detail"),
        "period": status.get("period"), "clock": status.get("displayClock"), "source": "ESPN play-by-play",
        "note": "Ball, shot and event locations only: per-player tracking for this sport is proprietary and not shown.",
    }
    sport = spec.sport.value
    if sport == "football":
        out.update(_football(s, teams))
    elif sport in ("basketball", "hockey"):
        out["events"] = _events(s, sport)
    return out


def _football(s: dict, teams: dict) -> dict[str, Any]:
    home_id = (teams.get("home") or {}).get("team_id")
    drives_raw = s.get("drives", {})
    drives = list(drives_raw.get("previous") or [])
    cur = drives_raw.get("current")
    if cur and (not drives or drives[-1].get("id") != cur.get("id")):
        drives.append(cur)

    def x_of(ytg: Any, offense: str | None) -> float | None:
        # absolute field x in yards from the AWAY goal line (away end zone on the left): away attacks right, home attacks left
        if ytg is None:
            return None
        return float(ytg) if offense == home_id else 100.0 - float(ytg)

    out_drives = []
    for d in drives:
        off = str((d.get("team") or {}).get("id") or "")
        plays = d.get("plays") or []
        start_ytg = (plays[0].get("start") or {}).get("yardsToEndzone") if plays else None
        end_ytg = None
        for p in reversed(plays):
            end_ytg = (p.get("end") or {}).get("yardsToEndzone")
            if end_ytg is not None:
                break
        out_drives.append({"team_id": off, "result": d.get("displayResult") or d.get("result"), "description": d.get("description"),
                           "is_score": d.get("isScore"), "start_x": x_of(start_ytg, off), "end_x": x_of(end_ytg, off)})
    situation, plays_out = None, []
    if drives:
        d = drives[-1]
        off = str((d.get("team") or {}).get("id") or "")
        for p in d.get("plays") or []:
            st, en = p.get("start") or {}, p.get("end") or {}
            plays_out.append({"text": p.get("text"), "type": (p.get("type") or {}).get("text"), "down": st.get("down"),
                              "distance": st.get("distance"), "start_x": x_of(st.get("yardsToEndzone"), off),
                              "end_x": x_of(en.get("yardsToEndzone"), off), "yards": p.get("statYardage"),
                              "scoring": p.get("scoringPlay"), "clock": (p.get("clock") or {}).get("displayValue"),
                              "period": (p.get("period") or {}).get("number")})
        last = next((p for p in reversed(d.get("plays") or []) if (p.get("end") or {}).get("yardsToEndzone") is not None), None)
        if last:
            en = last.get("end") or {}
            ytg = en.get("yardsToEndzone")
            dist = en.get("distance")
            situation = {"offense_id": off, "ball_x": x_of(ytg, off), "yards_to_endzone": ytg, "down": en.get("down"),
                         "distance": dist, "first_down_x": x_of(max(ytg - dist, 0), off) if ytg is not None and dist else None,
                         "red_zone": ytg is not None and ytg <= 20, "last_play": last.get("text"),
                         "direction": "left" if off == home_id else "right"}
    return {"situation": situation, "drives": out_drives[-14:], "drive_plays": plays_out[-12:], "units": "yards from the away goal line"}


def _events(s: dict, sport: str) -> list[dict[str, Any]]:
    limit = 60 if sport == "basketball" else 101
    out = []
    for p in s.get("plays") or []:
        c = p.get("coordinate")
        if not _ok_coord(c, limit):
            continue
        typ = (p.get("type") or {}).get("text") or ""
        if sport == "basketball" and not p.get("shootingPlay"):
            continue
        if sport == "basketball" and "Free Throw" in typ:
            continue
        if sport == "hockey" and typ not in ("Shot", "Goal", "Missed", "Blocked", "Hit", "Face Off", "Giveaway", "Takeaway"):
            continue
        out.append({"x": c["x"], "y": c["y"], "type": typ, "team_id": str((p.get("team") or {}).get("id") or ""),
                    "made": bool(p.get("scoringPlay")), "points": p.get("scoreValue"), "text": p.get("text"),
                    "period": (p.get("period") or {}).get("number"), "clock": (p.get("clock") or {}).get("displayValue")})
    return out[-400:]


# ---------------------------------------------------------------- F1 (OpenF1)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def f1_view(session_key: str = "latest", at: str | None = None, seconds: int = 24, token: str | None = None) -> dict[str, Any]:
    """Session meta, drivers with team colours, a circuit outline and a short window of every car's location."""
    sess = (_get(f"{OPENF1}/sessions", {"session_key": session_key}, ttl=60, token=token) or [{}])[0]
    sk = sess.get("session_key")
    if sk is None:
        return {"error": "no OpenF1 session found"}
    drivers = _get(f"{OPENF1}/drivers", {"session_key": sk}, ttl=600, token=token)
    start = datetime.fromisoformat(sess["date_start"])
    end = datetime.fromisoformat(sess["date_end"])
    now = datetime.now(timezone.utc)
    live = start <= now <= end
    if at:
        t1 = datetime.fromisoformat(at.replace("Z", "+00:00"))
    elif live:
        t1 = now - timedelta(seconds=4)
    else:
        t1 = min(end, now) - timedelta(minutes=8)  # replay a stretch near the end of the session
    t0 = t1 - timedelta(seconds=seconds)

    # circuit outline: one car's path over ~2.5 minutes in the middle of the session (cached for the session)
    mid = start + (end - start) / 2
    ref = next((d["driver_number"] for d in drivers), 1)
    outline_raw = _get(f"{OPENF1}/location", {"session_key": sk, "driver_number": ref,
                                              "date>": _iso(mid), "date<": _iso(mid + timedelta(seconds=150))}, ttl=3600, token=token)
    outline = [[p["x"], p["y"]] for p in outline_raw if p.get("x") or p.get("y")][::3]

    loc = _get(f"{OPENF1}/location", {"session_key": sk, "date>": _iso(t0), "date<": _iso(t1)}, ttl=4 if live else 600, token=token)
    frames: dict[int, list[list[float]]] = {}
    for p in loc:
        if p.get("x") is None:
            continue
        frames.setdefault(p["driver_number"], []).append([round(datetime.fromisoformat(p["date"]).timestamp() - t0.timestamp(), 2), p["x"], p["y"]])
    pos = _get(f"{OPENF1}/position", {"session_key": sk, "date<": _iso(t1)}, ttl=4 if live else 600, token=token)
    order: dict[int, int] = {}
    for p in pos:  # latest position per driver at t1
        order[p["driver_number"]] = p["position"]
    return {
        "session": {k: sess.get(k) for k in ("session_key", "session_name", "session_type", "circuit_short_name", "country_name", "date_start", "date_end", "year")},
        "live": live, "window": {"start": t0.isoformat(), "end": t1.isoformat(), "seconds": seconds},
        "drivers": [{"number": d["driver_number"], "code": d.get("name_acronym"), "name": d.get("full_name"), "team": d.get("team_name"),
                     "colour": f"#{d['team_colour']}" if d.get("team_colour") else None, "position": order.get(d["driver_number"])} for d in drivers],
        "outline": outline, "tracks": frames, "source": "OpenF1 car location (x, y on circuit), positions",
    }
