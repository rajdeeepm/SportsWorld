"""Historical season replay (spec v3.0 §19.3).

For every evaluated league-season and checkpoint (share of the regular season
already played), rebuild the world state *as it was* at that cutoff (rating
hyper-parameters fit only on earlier seasons; results only once known), run the
season simulator, and score its distributions against what actually happened:

* playoff qualification: Brier / log loss over every team (vs a slots/teams base rate)
* champion: log loss of the eventual champion's probability
* final wins: MAE, and coverage of the stated 90% interval (uncertainty calibration)
  vs a naive "current win% pace" extrapolation

FAST and DYNAMIC modes are scored on identical states, which directly tests
whether modelling latent-strength uncertainty (correlated futures) is calibrated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from sportsworld.ingest.espn import GameRecord, drop_exhibitions, read_archive, season_start_year
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.ratings import fit_params, result_known_time

from .engine import build_setup, run_season

CHECKPOINTS = (0.0, 0.25, 0.5, 0.75)
# Leagues whose ESPN postseason (season_type 3) equals the playoff field we simulate.
# College postseasons also contain bowls / NIT etc., so only wins and champion are scored there.
PLAYOFF_SCORED = {"nfl", "nba", "nhl"}


@dataclass
class SeasonTruth:
    wins: dict[str, float]
    playoff_teams: set[str]
    champion: str | None


def season_truth(games: list[GameRecord], league: str, season: int) -> SeasonTruth:
    spec = LEAGUES[league]
    gs = [g for g in games if season_start_year(spec, g.start_time) == season and g.completed]
    wins: dict[str, float] = {}
    for g in gs:
        if g.season_type != 2:
            continue
        for t in (g.home, g.away):
            wins.setdefault(t.team_id, 0.0)
        if g.home.score > g.away.score:
            wins[g.home.team_id] += 1
        elif g.away.score > g.home.score:
            wins[g.away.team_id] += 1
        # ties add no win: identical definition to the simulator's expected_wins
    post = [g for g in gs if g.season_type == 3]
    teams = {t.team_id for g in post for t in (g.home, g.away)}
    final = max(post, key=lambda g: g.start_time) if post else None
    champ = None
    if final:
        champ = final.home.team_id if final.home.score > final.away.score else final.away.team_id
    return SeasonTruth(wins=wins, playoff_teams=teams, champion=champ)


def _ll(p: float, y: int) -> float:
    p = min(1 - 1e-4, max(1e-4, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def evaluate_season(league: str, season: int, root: Path, *, draws: int = 5000, seed: int = 11) -> list[dict[str, Any]]:
    spec = LEAGUES[league]
    games = read_archive(root, league)
    history = drop_exhibitions(games)
    regular = sorted([g for g in games if season_start_year(spec, g.start_time) == season and g.season_type == 2 and g.completed],
                     key=lambda g: g.start_time)
    if len(regular) < 50:
        return []
    first = regular[0].start_time
    prior = [g for g in history if g.completed and result_known_time(g, spec.sport) < first - timedelta(days=1)]
    params, _ = fit_params(spec, prior)  # strictly pre-season hyper-parameters
    truth = season_truth(games, league, season)
    out = []
    for frac in CHECKPOINTS:
        k = int(len(regular) * frac)
        as_of = (regular[k].start_time - timedelta(minutes=1)) if k < len(regular) else regular[-1].start_time
        if frac == 0.0:
            as_of = first - timedelta(days=1)
        setup = build_setup(league, root, as_of, season=season, params=params, games=games)
        members = [i for i, m in enumerate(setup.member) if m]
        n_slots = len(truth.playoff_teams & {setup.team_ids[i] for i in members})
        base_rate = n_slots / max(1, len(members))
        played = {}
        for h, a, hs, as_ in zip(setup.p_home, setup.p_away, setup.p_hs, setup.p_as):
            for t, w in ((h, hs > as_), (a, as_ > hs)):
                played.setdefault(t, [0, 0])
                played[t][0] += w
                played[t][1] += 1
        for mode in ("dynamic", "fast"):
            r = run_season(setup, draws=draws, seed=seed, mode=mode)
            rows = {t["team_id"]: t for t in r["teams"]}
            pl_b, pl_ll, base_b, base_ll, mae, pace_mae, cover, n = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0
            n_pl = 0
            for i in members:
                tid = setup.team_ids[i]
                row = rows.get(tid)
                if row is None or tid not in truth.wins:
                    continue
                y = int(tid in truth.playoff_teams)
                if "playoffs" in row and league in PLAYOFF_SCORED and truth.playoff_teams:  # e.g. 2019-20 bubble playoffs fall outside the archive window
                    pl_b += (row["playoffs"] - y) ** 2
                    pl_ll += _ll(row["playoffs"], y)
                    base_b += (base_rate - y) ** 2
                    base_ll += _ll(base_rate, y)
                    n_pl += 1
                actual = truth.wins[tid]
                mae += abs(row["expected_wins"] - actual)
                w, g = played.get(i, [0, 0])
                pace = (w / g) * row["games"] if g else 0.5 * row["games"]
                pace_mae += abs(pace - actual)
                cover += int(row["wins_p05"] - 0.5 <= actual <= row["wins_p95"] + 0.5)
                n += 1
            champ_p = rows.get(truth.champion, {}).get("champion") if (truth.champion and truth.playoff_teams) else None
            out.append({
                "league": league, "season": season, "checkpoint": frac, "as_of": as_of.isoformat(), "mode": mode, "teams": n,
                "playoff_brier": pl_b / n_pl if n_pl else None, "playoff_log_loss": pl_ll / n_pl if n_pl else None,
                "playoff_brier_base_rate": base_b / n_pl if n_pl else None, "playoff_log_loss_base_rate": base_ll / n_pl if n_pl else None,
                "wins_mae": mae / n if n else None, "wins_mae_pace_baseline": pace_mae / n if n else None,
                "wins_90_coverage": cover / n if n else None,
                "champion_prob": champ_p, "champion_log_loss": -math.log(max(champ_p, 1e-4)) if (truth.champion and champ_p is not None) else None,
                "champion_uniform_log_loss": math.log(max(1, len(members))),
                "rating_params": params.to_dict(), "runtime_s": r["diagnostics"]["runtime_s"],
            })
    return out


def summarize(rows: list[dict]) -> list[dict]:
    """Average metrics by (league, checkpoint, mode)."""
    keys = sorted({(r["league"], r["checkpoint"], r["mode"]) for r in rows})
    metrics = ["playoff_brier", "playoff_log_loss", "playoff_brier_base_rate", "playoff_log_loss_base_rate", "wins_mae",
               "wins_mae_pace_baseline", "wins_90_coverage", "champion_log_loss", "champion_uniform_log_loss", "champion_prob"]
    out = []
    for lg, cp, mode in keys:
        sub = [r for r in rows if (r["league"], r["checkpoint"], r["mode"]) == (lg, cp, mode)]
        agg = {"league": lg, "checkpoint": cp, "mode": mode, "seasons": [r["season"] for r in sub]}
        for m in metrics:
            vals = [r[m] for r in sub if r.get(m) is not None]
            agg[m] = round(float(np.mean(vals)), 4) if vals else None
        out.append(agg)
    return out
