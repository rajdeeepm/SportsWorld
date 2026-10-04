"""Daily scorecard: how SportsWorld's pregame forecasts did against what happened, next to ESPN and the market.

SportsWorld: point-in-time reconstruction at kickoff (ratings rebuilt from results known strictly before each
game started, then the served model), i.e. exactly what the engine would have said at kickoff.
ESPN: the first point of ESPN's own win-probability chart for the game (its pregame estimate).
Market: DraftKings moneylines via ESPN's pick center, de-vigged. Benchmarks only; never model inputs.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from sportsworld.ingest.espn import BASE, drop_exhibitions
from sportsworld.ingest.features import league_features
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.ratings import RatingBook, load_params

ET = ZoneInfo("America/New_York")
_cache: dict[str, tuple[float, Any]] = {}


def _summary(spec, game_id: str) -> dict:
    key = f"{spec.league_id}:{game_id}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    r = httpx.get(f"{BASE}/{spec.espn_path}/summary", params={"event": game_id}, timeout=20, headers={"User-Agent": "SportsWorld/1.3"})
    r.raise_for_status()
    d = r.json()
    _cache[key] = (time.time(), d)
    return d


def _market(summary: dict) -> float | None:
    for pc in summary.get("pickcenter") or []:
        h, a = (pc.get("homeTeamOdds") or {}).get("moneyLine"), (pc.get("awayTeamOdds") or {}).get("moneyLine")
        if h is None or a is None:
            continue
        imp = lambda ml: 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)  # noqa: E731
        ph, pa = imp(float(h)), imp(float(a))
        if ph + pa > 0:
            return ph / (ph + pa)
    return None


def _espn(summary: dict) -> float | None:
    wp = summary.get("winprobability") or []
    if wp and wp[0].get("homeWinPercentage") is not None:
        return float(wp[0]["homeWinPercentage"])
    pr = (summary.get("predictor") or {}).get("homeTeam") or {}
    v = pr.get("gameProjection")
    return float(v) / 100 if v is not None else None


def _metrics(rows: list[dict], key: str) -> dict | None:
    xs = [(r[key], r["home_won"]) for r in rows if r.get(key) is not None]
    if not xs:
        return None
    eps = 1e-6
    ll = -sum(math.log(max(eps, p if y else 1 - p)) for p, y in xs) / len(xs)
    brier = sum((p - y) ** 2 for p, y in xs) / len(xs)
    acc = sum(1 for p, y in xs if (p >= 0.5) == bool(y)) / len(xs)
    return {"games": len(xs), "log_loss": round(ll, 4), "brier": round(brier, 4), "accuracy": round(acc, 4)}


def scorecard(league: str, day: str, games_all, registry, root: Path) -> dict[str, Any]:
    """`day` is a calendar date in US Eastern time (YYYY-MM-DD)."""
    spec = LEAGUES[league]
    d0 = datetime.fromisoformat(day).replace(tzinfo=ET)
    lo, hi = d0.astimezone(timezone.utc), (d0 + timedelta(days=1, hours=4)).astimezone(timezone.utc)  # late games finish after midnight ET
    games = drop_exhibitions(list(games_all))
    targets = {g.game_id: g for g in games if lo <= g.start_time < hi and g.completed and not g.cancelled}
    params = load_params(root / "models" / "artifacts" / "ratings" / f"{league}.json")
    states: dict[str, dict] = {}

    def pre(g, state):
        if g.game_id in targets:
            states[g.game_id] = state

    RatingBook(spec, params).replay([g for g in games if g.start_time < hi], on_pregame=pre)
    ids = [gid for gid in targets if gid in states]
    feats = [league_features({**states[gid], "home_score": 0, "away_score": 0, "seconds_remaining": spec.regulation_seconds}) for gid in ids]
    preds = registry.predict_league_features(league, feats) if feats else []
    rows = []
    for gid, pr in zip(ids, preds):
        g = targets[gid]
        try:
            s = _summary(spec, gid)
            espn, market = _espn(s), _market(s)
        except Exception:
            espn = market = None
        if g.home.score == g.away.score:
            continue  # ties are not binary outcomes
        p = float(pr[0])
        home_won = g.home.score > g.away.score
        rows.append({"event_id": g.event_id, "home": g.home.name, "away": g.away.name, "home_id": g.home.team_id, "away_id": g.away.team_id,
                     "home_score": g.home.score, "away_score": g.away.score, "home_won": home_won, "kickoff": g.start_time.isoformat(),
                     "sportsworld": round(p, 4), "espn": round(espn, 4) if espn is not None else None, "market": round(market, 4) if market is not None else None,
                     "sportsworld_correct": (p >= 0.5) == home_won,
                     "upset": (p >= 0.5) != home_won and abs(p - 0.5) >= 0.2})
    common = [r for r in rows if r["espn"] is not None and r["market"] is not None]
    # calibration buckets for SportsWorld (favourite's probability)
    buckets = []
    for lo_b, hi_b in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.001)):
        sel = [r for r in rows if lo_b <= max(r["sportsworld"], 1 - r["sportsworld"]) < hi_b]
        if sel:
            fav_won = sum(1 for r in sel if (r["sportsworld"] >= 0.5) == r["home_won"])
            exp = sum(max(r["sportsworld"], 1 - r["sportsworld"]) for r in sel) / len(sel)
            buckets.append({"range": f"{int(lo_b * 100)}–{min(int(hi_b * 100), 100)}%", "games": len(sel), "expected": round(exp, 3), "actual": round(fav_won / len(sel), 3)})
    return {
        "league": league, "date": day, "games": len(rows),
        "sportsworld": _metrics(rows, "sportsworld"),
        "on_common_games": {"games": len(common), "sportsworld": _metrics(common, "sportsworld"), "espn": _metrics(common, "espn"), "market": _metrics(common, "market")},
        "calibration": buckets,
        "rows": sorted(rows, key=lambda r: r["kickoff"]),
        "method": ("SportsWorld = point-in-time reconstruction at kickoff (results known before each kickoff, served model); "
                   "ESPN = first point of ESPN's win-probability chart; market = DraftKings moneyline via ESPN, de-vigged. "
                   "Benchmarks are never model inputs."),
    }
