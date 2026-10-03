"""Learned player-availability impact (spec §18.2 stage A2: player/roster structure).

For every game, chronologically:
  expected margin  = Kalman rating book prediction made before the game (point-in-time)
  residual         = actual margin - expected margin (home perspective)
  key players      = each team's established starters from *earlier* games that season
                     football: primary passer (QB);  basketball: top-2 by minutes ("KEY");
                     hockey: starting goalie ("G") and top-2 skaters by TOI ("KEY")
  absent           = key player did not play in this game (ex-post participation: training only)
OLS: residual ~ sum_pos beta_pos * (absent_home_pos - absent_away_pos)  -> points per absence, with SE.
At serve time the live injury report supplies P(plays) and the expected delta = beta * (1 - P(plays)).

Usage: PYTHONPATH=backend/src python scripts/player_impact.py --leagues nfl college-football nhl
Writes models/artifacts/player_impact/<league>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.ingest.espn import drop_exhibitions, read_archive, season_start_year  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import RatingBook, load_params  # noqa: E402

DATA = ROOT / "data" / "real"
OUT = ROOT / "models" / "artifacts" / "player_impact"


def load_summaries(league: str) -> dict[str, list]:
    out = {}
    for f in sorted((DATA / "summaries" / league).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["game_id"]] = d["players"]
    return out


def key_players(sport: str, history: list[list[list]]) -> dict[str, set[str]]:
    """history: this team's player rows from earlier games this season -> {pos: athlete ids}."""
    if not history:
        return {}
    if sport == "football":
        starts = defaultdict(int)
        for rows in history:
            passers = [r for r in rows if r[6] == "passing"]
            if passers:
                starts[max(passers, key=lambda r: r[5])[1]] += 1
        if not starts:
            return {}
        qb, n = max(starts.items(), key=lambda kv: kv[1])
        return {"QB": {qb}} if n >= 2 else {}
    usage = defaultdict(list)
    goalie = defaultdict(int)
    for rows in history:
        for r in rows:
            if sport == "hockey" and (r[3] == "G" or r[6] == "goalies"):
                if r[5] > 20:
                    goalie[r[1]] += 1
                continue
            usage[r[1]].append(r[5])
    games = len(history)
    avg = {a: sum(v) / games for a, v in usage.items()}
    top = sorted(avg, key=avg.get, reverse=True)[:2]
    out = {"KEY": set(top)} if games >= 5 else {}
    if sport == "hockey" and goalie:
        g, n = max(goalie.items(), key=lambda kv: kv[1])
        if n >= 3 and n / games >= 0.5:
            out["G"] = {g}
    return out


def absent(sport: str, keys: dict[str, set[str]], rows: list[list]) -> dict[str, float]:
    played = {r[1] for r in rows if r[5] > 0}
    out = {}
    for pos, ids in keys.items():
        if pos == "QB":
            passers = [r for r in rows if r[6] == "passing"]
            primary = max(passers, key=lambda r: r[5])[1] if passers else None
            out[pos] = float(primary is not None and primary not in ids)
        elif pos == "G":
            goalies = [r for r in rows if (r[3] == "G" or r[6] == "goalies") and r[5] > 20]
            out[pos] = float(bool(goalies) and not (ids & {r[1] for r in goalies}))
        else:
            out[pos] = float(sum(1 for i in ids if i not in played))
    return out


def run(league: str) -> dict:
    spec = LEAGUES[league]
    sport = spec.sport.value
    summ = load_summaries(league)
    if not summ:
        return {"league": league, "status": "no summaries"}
    params = load_params(ROOT / "models" / "artifacts" / "ratings" / f"{league}.json")
    games = [g for g in drop_exhibitions(read_archive(DATA, league)) if g.completed and g.season_type in (2, 3)]
    book = RatingBook(spec, params)
    hist: dict[tuple[str, int], list] = defaultdict(list)
    X, y, meta = [], [], []
    positions = ["QB"] if sport == "football" else (["G", "KEY"] if sport == "hockey" else ["KEY"])

    def pre(g, state):
        rows = summ.get(g.game_id)
        season = season_start_year(spec, g.start_time)
        if rows is not None and g.completed:
            expected = state["hfa"] * state["home_field"] + state["home_rating"] - state["away_rating"]
            team_rows = {t: [r for r in rows if r[0] == t] for t in (g.home.team_id, g.away.team_id)}
            kh = key_players(sport, hist[(g.home.team_id, season)])
            ka = key_players(sport, hist[(g.away.team_id, season)])
            ah, aa = absent(sport, kh, team_rows[g.home.team_id]), absent(sport, ka, team_rows[g.away.team_id])
            if kh or ka:
                X.append([ah.get(p, 0.0) - aa.get(p, 0.0) for p in positions])
                cap = spec.margin_cap
                y.append(max(-cap, min(cap, g.margin())) - expected)
                meta.append(g.start_time)
            for t in (g.home.team_id, g.away.team_id):
                if team_rows[t]:
                    hist[(t, season)].append(team_rows[t])

    book.replay(games, on_pregame=pre)
    # Current key players per team (latest season seen), for live availability serving.
    latest = max((k[1] for k in hist), default=None)
    names: dict[str, tuple[str, str]] = {}
    for rows_list in hist.values():
        for rows in rows_list:
            for r in rows:
                names[r[1]] = (r[2], r[3])
    current = {}
    for (team, season), rows_list in hist.items():
        if season != latest:
            continue
        keys = key_players(sport, rows_list)
        current[team] = {pos: [{"athlete_id": a, "name": names.get(a, ("?", None))[0], "position": names.get(a, ("?", None))[1]} for a in sorted(ids)] for pos, ids in keys.items()}
    X, y = np.asarray(X), np.asarray(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma2 = float(resid @ resid / max(1, len(y) - X.shape[1]))
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    out = {"league": league, "model_version": f"player_impact_{league}_v1", "data_mode": "real_espn",
           "fit_window": {"start": min(meta).isoformat(), "end": max(meta).isoformat()} if meta else None,
           "n_games": int(len(y)), "residual_sd": round(float(np.sqrt(sigma2)), 3),
           "variance_explained": round(float(1 - resid.var() / max(y.var(), 1e-9)), 5),
           "by_position": {p: {"points": round(float(b), 3), "se": round(float(s), 3), "t": round(float(b / s), 2) if s > 0 else None,
                               "games_with_absence": int((X[:, i] != 0).sum())} for i, (p, b, s) in enumerate(zip(positions, beta, se))},
           "definition": {"football": "primary passer differs from the team's established starter (>=2 prior starts)",
                          "basketball": "count of the team's top-2 minutes players (>=5 prior games) who did not play",
                          "hockey": "G: established starting goalie did not play; KEY: count of top-2 TOI skaters absent"}[sport],
           "created_at": datetime.now(timezone.utc).isoformat(), "current_season": latest, "current_key_players": current}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{league}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="+", required=True)
    for lg in ap.parse_args().leagues:
        print(json.dumps(run(lg)), flush=True)
