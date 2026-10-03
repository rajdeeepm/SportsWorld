"""Rolling-origin (walk-forward) evaluation of the event models (spec §18.1, Codex review rec. #3).

For each origin season O: rating hyper-parameters fit on games before season O-1; model trained on seasons <= O-2,
temperature-calibrated on season O-1, tested on season O (whole games by kickoff). Reports per-origin metrics,
mean ± sd across origins, and the Kalman-only analytic baseline on the same rows.

Usage: PYTHONPATH=backend/src python scripts/rolling_origin.py --league nfl --origins 2022 2023 2024 2025
Writes data/fixtures/backtests/rolling_<league>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sportsworld.backtest.splitter import ChronologicalSplit  # noqa: E402
from sportsworld.ingest.espn import drop_exhibitions, read_archive, season_start_year  # noqa: E402
from sportsworld.ingest.features import FOOTBALL_LEAGUE_FEATURES, LEAGUE_FEATURES  # noqa: E402
from sportsworld.ingest.football_ep import fit_expected_points  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import RatingBook, fit_params, result_known_time  # noqa: E402
from sportsworld.backtest.runner import run_binary_backtest  # noqa: E402
from sportsworld.schemas import Sport  # noqa: E402
from train_real import DATA, build_rows, kalman_baseline, load_pbp  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--origins", nargs="+", type=int, default=[2022, 2023, 2024, 2025])
    a = ap.parse_args()
    spec = LEAGUES[a.league]
    games = drop_exhibitions(read_archive(DATA, a.league))
    done = [g for g in games if g.completed]
    season_of = lambda g: season_start_year(spec, g.start_time)  # noqa: E731
    pbp = load_pbp(a.league) if spec.sport == Sport.FOOTBALL else {}
    out = {"league": a.league, "origins": []}
    for O in a.origins:
        test_games = [g for g in done if season_of(g) == O]
        cal_games = [g for g in done if season_of(g) == O - 1]
        train_games = [g for g in done if season_of(g) <= O - 2]
        if len(test_games) < 30 or len(cal_games) < 30 or len(train_games) < 100:
            continue
        train_end = max(g.start_time for g in train_games)
        cal_end = max(g.start_time for g in cal_games)
        test_end = max(g.start_time for g in test_games)
        params, _ = fit_params(spec, [g for g in done if result_known_time(g, spec.sport) <= train_end])
        ep_coef = None
        if pbp:
            ids = {g.game_id for g in train_games}
            tp = [p for gid, p in pbp.items() if gid in ids]
            if sum(len(p) for p in tp) > 5000:
                ep_coef, _ = fit_expected_points(tp)
        rows = build_rows(spec, [g for g in games if g.start_time <= test_end + timedelta(days=1)], RatingBook(spec, params), pbp, ep_coef)
        feats = FOOTBALL_LEAGUE_FEATURES if ep_coef else LEAGUE_FEATURES
        split = ChronologicalSplit(train_end, cal_end, test_end)
        model, scaler, report = run_binary_backtest(rows, split, sport=spec.sport, features=feats, model_version=f"rolling_{a.league}_{O}",
                                                    schema_version="league_features_v2_real", competition=a.league, seed=O, data_mode="real_espn",
                                                    ablation_groups=[("A0 venue", ["home_field"]), ("full", feats)])
        _, _, test = split.split(rows)
        kal = kalman_baseline(rows, test)
        out["origins"].append({"origin_season": O, "test_games": len(test_games), "test_rows": len(test),
                               "model": {k: round(v, 5) for k, v in report.metrics.items() if isinstance(v, float) and np.isfinite(v)},
                               "kalman_only": {k: round(v, 5) for k, v in kal.items()}, "leakage_violations": report.leakage_violations})
        print(json.dumps(out["origins"][-1]), flush=True)
    if out["origins"]:
        for key in ("model", "kalman_only"):
            ll = [o[key]["log_loss"] for o in out["origins"]]
            out[f"{key}_log_loss_mean"] = round(float(np.mean(ll)), 5)
            out[f"{key}_log_loss_sd"] = round(float(np.std(ll, ddof=1)) if len(ll) > 1 else 0.0, 5)
        d = [o["model"]["log_loss"] - o["kalman_only"]["log_loss"] for o in out["origins"]]
        out["model_minus_kalman_by_origin"] = [round(x, 5) for x in d]
    p = ROOT / "data" / "fixtures" / "backtests" / f"rolling_{a.league}.json"
    p.write_text(json.dumps(out, indent=1, allow_nan=False))
    print("wrote", p, flush=True)


if __name__ == "__main__":
    main()
