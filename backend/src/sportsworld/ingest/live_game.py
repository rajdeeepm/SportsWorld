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

import re
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
            plays_out.append({"id": str(p.get("id") or ""), "text": p.get("text"), "type": (p.get("type") or {}).get("text"), "down": st.get("down"),
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
        out.append({"id": str(p.get("id") or ""), "x": c["x"], "y": c["y"], "type": typ, "team_id": str((p.get("team") or {}).get("id") or ""),
                    "made": bool(p.get("scoringPlay")), "points": p.get("scoreValue"), "text": p.get("text"),
                    "period": (p.get("period") or {}).get("number"), "clock": (p.get("clock") or {}).get("displayValue")})
    return out[-400:]


def play_stream(league: str, game_id: str) -> dict[str, Any]:
    """Every play in order (id, text, type, scoring, period, clock, score after) for live commentary."""
    spec = LEAGUES[league]
    s = _get(f"{BASE}/{spec.espn_path}/summary", {"event": game_id}, ttl=5.0)
    comp = (s.get("header", {}).get("competitions") or [{}])[0]
    teams = {c.get("homeAway"): {"id": str(c.get("team", {}).get("id")), "abbr": c.get("team", {}).get("abbreviation"),
                                 "name": c.get("team", {}).get("shortDisplayName") or c.get("team", {}).get("displayName")} for c in comp.get("competitors", [])}
    plays: list[dict] = []
    if spec.sport.value == "football":
        drives = (s.get("drives") or {})
        seq = list(drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else [])
        seen: set[str] = set()
        for d in seq:
            for p in d.get("plays") or []:
                pid = str(p.get("id") or "")
                if pid and pid not in seen:
                    seen.add(pid)
                    plays.append(_play(p))
    else:
        plays = [_play(p) for p in s.get("plays") or []]
    status = comp.get("status", {})
    return {"teams": teams, "plays": plays, "state": status.get("type", {}).get("state"), "detail": status.get("type", {}).get("detail")}


def _play(p: dict) -> dict:
    return {"id": str(p.get("id") or ""), "text": p.get("text") or "", "type": (p.get("type") or {}).get("text") or "",
            "scoring": bool(p.get("scoringPlay")), "period": (p.get("period") or {}).get("number"),
            "clock": (p.get("clock") or {}).get("displayValue"), "home_score": p.get("homeScore"), "away_score": p.get("awayScore"),
            "team_id": str((p.get("team") or {}).get("id") or ""), "turnover": bool(p.get("isTurnover"))}


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


# ---------------------------------------------------------------- box scores and season player stats

def _box_raw(league: str, game_id: str, root, final: bool) -> dict:
    """ESPN summary for one game; finals are cached on disk (box scores never change once final)."""
    import json as _json
    spec = LEAGUES[league]
    p = root / "boxscores" / league / f"{game_id}.json"
    if final and p.exists():
        return _json.loads(p.read_text())
    s = _get(f"{BASE}/{spec.espn_path}/summary", {"event": game_id}, ttl=15.0)
    box = {"players": (s.get("boxscore") or {}).get("players") or [], "state": ((s.get("header", {}).get("competitions") or [{}])[0].get("status", {}).get("type", {}).get("state"))}
    if final and box["state"] == "post" and box["players"]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_json.dumps(box))
    return box


def box_score(league: str, game_id: str, root) -> dict[str, Any]:
    box = _box_raw(league, game_id, root, final=False)
    teams = []
    for t in box["players"]:
        cats = []
        for st in t.get("statistics") or []:
            rows = [{"id": str(a.get("athlete", {}).get("id")), "name": a.get("athlete", {}).get("displayName"),
                     "starter": a.get("starter"), "dnp": a.get("didNotPlay"), "stats": a.get("stats") or []}
                    for a in st.get("athletes") or [] if a.get("stats") and not _placeholder(str(a.get("athlete", {}).get("id")), a.get("athlete", {}).get("displayName"))]
            if rows:
                cats.append({"name": st.get("name") or "players", "labels": st.get("labels") or [], "rows": rows})
        teams.append({"team_id": str(t.get("team", {}).get("id")), "abbreviation": t.get("team", {}).get("abbreviation"), "categories": cats})
    return {"league": league, "game_id": game_id, "state": box["state"], "teams": teams, "source": "ESPN box score"}


def _placeholder(aid: str, name) -> bool:
    """ESPN's team-total row (negative id, name ' Team')."""
    return not name or str(name).strip() == "Team" or aid in ("None", "") or aid.startswith("-")


DERIVED = {"AVG", "PCT", "QBR", "RTG", "FO%", "SV%", "YTDG", "SOS", "SOSA", "LONG"}


def _parse(v: str):
    v = str(v).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", v.replace("+", "")):
        return ("n", float(v.replace("+", "")))
    m = re.fullmatch(r"(\d+)[-/](\d+)", v)
    if m:
        return ("pair", (float(m.group(1)), float(m.group(2))), "-" if "-" in v else "/")
    m = re.fullmatch(r"(\d+):(\d{2})", v)
    if m:
        return ("time", int(m.group(1)) * 60 + int(m.group(2)))
    return None


def season_stats(league: str, team_id: str, game_ids: list[str], root) -> dict[str, Any]:
    """Totals per player and category over a team's completed games, summed column by column."""
    agg: dict[str, dict] = {}
    games = 0
    for gid in game_ids:
        try:
            box = _box_raw(league, gid, root, final=True)
        except Exception:
            continue
        mine = next((t for t in box["players"] if str(t.get("team", {}).get("id")) == str(team_id)), None)
        if not mine:
            continue
        games += 1
        for st in mine.get("statistics") or []:
            cat = st.get("name") or "players"
            labels = st.get("labels") or []
            c = agg.setdefault(cat, {"labels": labels, "players": {}})
            for a in st.get("athletes") or []:
                stats = a.get("stats") or []
                if not stats or a.get("didNotPlay"):
                    continue
                aid = str(a.get("athlete", {}).get("id"))
                pl = c["players"].setdefault(aid, {"name": a.get("athlete", {}).get("displayName"), "gp": 0, "vals": {}})
                pl["gp"] += 1
                for lab, v in zip(labels, stats):
                    if lab in DERIVED and lab != "LONG":
                        continue
                    pv = _parse(v)
                    if pv is None:
                        continue
                    cur = pl["vals"].get(lab)
                    if lab == "LONG":
                        pl["vals"][lab] = ("n", max(cur[1], pv[1]) if cur else pv[1])
                    elif pv[0] == "pair":
                        pl["vals"][lab] = ("pair", ((cur[1][0] if cur else 0) + pv[1][0], (cur[1][1] if cur else 0) + pv[1][1]), pv[2])
                    else:
                        pl["vals"][lab] = (pv[0], (cur[1] if cur else 0) + pv[1])
    out = []
    for cat, c in agg.items():
        labels = [lab for lab in c["labels"] if lab not in DERIVED or lab == "LONG"]
        rows = []
        avg_from = {"rushing": ("YDS", "CAR"), "receiving": ("YDS", "REC")}.get(cat)
        if cat == "passing" and "C/ATT" in labels:
            labels = labels + ["Y/A"]
        elif avg_from and "AVG" in c["labels"]:
            labels = labels + ["AVG"]
        for aid, pl in c["players"].items():
            if _placeholder(aid, pl["name"]):
                continue  # ESPN's team-total placeholder row
            if cat == "passing" and pl["vals"].get("C/ATT") and pl["vals"].get("YDS"):
                att = pl["vals"]["C/ATT"][1][1]
                pl["vals"]["Y/A"] = ("n", round(pl["vals"]["YDS"][1] / att, 1) if att else 0.0)
            if avg_from and pl["vals"].get(avg_from[0]) and pl["vals"].get(avg_from[1]):
                n = pl["vals"][avg_from[1]][1]
                pl["vals"]["AVG"] = ("n", round(pl["vals"][avg_from[0]][1] / n, 1) if n else 0.0)
            vals = []
            for lab in labels:
                v = pl["vals"].get(lab)
                if v is None:
                    vals.append("")
                elif v[0] == "pair":
                    vals.append(f"{int(v[1][0])}{v[2]}{int(v[1][1])}")
                elif v[0] == "time":
                    vals.append(f"{int(v[1] // 60)}:{int(v[1] % 60):02d}")
                else:
                    vals.append(f"{v[1]:.0f}" if float(v[1]).is_integer() else f"{v[1]:.1f}")
            rows.append({"id": aid, "name": pl["name"], "gp": pl["gp"], "stats": vals,
                         "sort": next((v[1] if v[0] != "pair" else v[1][0] for lab in ("YDS", "PTS", "G", "SV", "TOT", "MIN", "TOI") if (v := pl["vals"].get(lab))), 0)})
        rows.sort(key=lambda r: -float(r["sort"] if not isinstance(r["sort"], tuple) else r["sort"][0]))
        out.append({"name": cat, "labels": ["GP"] + labels, "rows": [{**r, "stats": [str(r["gp"])] + r["stats"]} for r in rows[:12]]})
    return {"league": league, "team_id": team_id, "games": games, "categories": out, "source": "ESPN box scores, summed per game"}
