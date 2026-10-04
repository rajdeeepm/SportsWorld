"""Pooled absence effects by role share (football): what a team loses when its regular ball carriers,
receivers (WR/TE/RB targets) or defenders (DB/LB/DL, by tackles) sit out.

For every game, chronologically and point-in-time:
  expected margin = Kalman rating book prediction made before kickoff (results known before it only)
  residual        = actual margin - expected margin (home perspective)
  regulars        = players with >= 3 earlier games this season and >= 8 % average share of the team's
                    carries / receptions / tackles in those games
  missing share   = sum of the average shares of regulars who appear NOWHERE in this game's box score
                    (no carry, catch, tackle, pass, kick: absence, not a quiet day)
OLS: residual ~ b_qb * QB_absent + b_rush * rush_share_missing + b_rec * rec_share_missing + b_def * def_share_missing
(home minus away). Coefficients are points per 100 % of share missing; a player's effect is b * his share.
Offensive linemen record no individual stats, so their absences cannot be measured from box scores.

Usage: PYTHONPATH=backend/src python scripts/player_share_impact.py --leagues nfl college-football
Adds "share_effects" to models/artifacts/player_impact/<league>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from player_impact import load_summaries, key_players, absent  # noqa: E402
from sportsworld.ingest.espn import drop_exhibitions, read_archive, season_start_year  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import RatingBook, load_params  # noqa: E402

DATA = ROOT / "data" / "real"
OUT = ROOT / "models" / "artifacts" / "player_impact"
CATS = {"RUSH": "rushing", "REC": "receiving", "DEF": "defensive"}
MIN_GAMES, MIN_SHARE = 3, 0.08


def shares(history: list[list[list]]) -> dict[str, dict[str, float]]:
    """{role: {athlete_id: average share}} over a team's earlier games (regulars only)."""
    out = {}
    for role, cat in CATS.items():
        tot = defaultdict(float)
        apps = defaultdict(int)
        for rows in history:
            team_total = sum(r[5] for r in rows if r[6] == cat and not str(r[1]).startswith("-"))
            if team_total <= 0:
                continue
            for r in rows:
                if r[6] == cat and not str(r[1]).startswith("-"):
                    tot[r[1]] += r[5] / team_total
                    apps[r[1]] += 1
        n = len(history)
        out[role] = {a: tot[a] / n for a in tot if apps[a] >= MIN_GAMES and tot[a] / n >= MIN_SHARE}
    return out


def missing(sh: dict[str, dict[str, float]], rows: list[list]) -> dict[str, float]:
    present = {r[1] for r in rows}
    return {role: sum(s for a, s in d.items() if a not in present) for role, d in sh.items()}


def run(league: str) -> dict:
    spec = LEAGUES[league]
    summ = load_summaries(league)
    params = load_params(ROOT / "models" / "artifacts" / "ratings" / f"{league}.json")
    games = [g for g in drop_exhibitions(read_archive(DATA, league)) if g.completed and g.season_type in (2, 3)]
    hist: dict[tuple[str, int], list] = defaultdict(list)
    X, y = [], []
    names = ["QB"] + list(CATS)

    def pre(g, state):
        rows = summ.get(g.game_id)
        if rows is None:
            return
        season = season_start_year(spec, g.start_time)
        tr = {t: [r for r in rows if r[0] == t] for t in (g.home.team_id, g.away.team_id)}
        hh, ha = hist[(g.home.team_id, season)], hist[(g.away.team_id, season)]
        if len(hh) >= MIN_GAMES and len(ha) >= MIN_GAMES and tr[g.home.team_id] and tr[g.away.team_id]:
            qh = absent("football", key_players("football", hh), tr[g.home.team_id]).get("QB", 0.0)
            qa = absent("football", key_players("football", ha), tr[g.away.team_id]).get("QB", 0.0)
            mh, ma = missing(shares(hh), tr[g.home.team_id]), missing(shares(ha), tr[g.away.team_id])
            X.append([qh - qa] + [mh[k] - ma[k] for k in CATS])
            expected = state["hfa"] * state["home_field"] + state["home_rating"] - state["away_rating"]
            y.append(max(-spec.margin_cap, min(spec.margin_cap, g.margin())) - expected)
        for t in (g.home.team_id, g.away.team_id):
            if tr[t]:
                hist[(t, season)].append(tr[t])

    RatingBook(spec, params).replay(games, on_pregame=pre)
    # current regulars per team (latest season): who each role's share belongs to, for live serving
    latest = max((k[1] for k in hist), default=None)
    names_of = {r[1]: r[2] for rows_list in hist.values() for rows in rows_list for r in rows}
    current = {}
    for (team, season), rows_list in hist.items():
        if season == latest and rows_list:
            sh = shares(rows_list) if len(rows_list) >= MIN_GAMES else {}
            current[team] = {role: sorted([{"athlete_id": a, "name": names_of.get(a), "share": round(s, 3)} for a, s in d.items()], key=lambda x: -x["share"])
                             for role, d in sh.items() if d}
    X, y = np.asarray(X), np.asarray(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma2 = float(resid @ resid / max(1, len(y) - X.shape[1]))
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(X.T @ X)))
    eff = {n: {"points_per_full_share": round(float(b), 3), "se": round(float(s), 3), "t": round(float(b / s), 2) if s > 0 else None,
               "significant": bool(s > 0 and abs(b / s) >= 2.0), "games_with_missing": int((X[:, i] != 0).sum()),
               "mean_abs_missing_share": round(float(np.abs(X[:, i][X[:, i] != 0]).mean()), 3) if (X[:, i] != 0).any() else 0.0}
           for i, (n, b, s) in enumerate(zip(names, beta, se))}
    p = OUT / f"{league}.json"
    art = json.loads(p.read_text())
    art["share_effects"] = {"n_games": int(len(y)), "by_role": {k: v for k, v in eff.items() if k != "QB"}, "qb_with_shares": eff["QB"],
                            "definition": "points per 100% of the team's carries (RUSH), receptions (REC) or tackles (DEF) held by regulars "
                                          "(>=3 earlier games, >=8% average share) who appear nowhere in the box score; offensive line not measurable",
                            "min_games": MIN_GAMES, "min_share": MIN_SHARE, "current_season": latest, "current_shares": current}
    p.write_text(json.dumps(art, indent=1))
    return {"league": league, "n_games": int(len(y)), **eff}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="+", required=True)
    for lg in ap.parse_args().leagues:
        print(json.dumps(run(lg)), flush=True)
