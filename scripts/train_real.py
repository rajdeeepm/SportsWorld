"""Train, calibrate and backtest one real-data model per tracked league.

Pipeline per league (all chronological, all point-in-time):
  1. load archived ESPN games, drop exhibitions (teams with no regular-season game)
  2. split completed games by time: train 60% | calibration 20% | test 20%
  3. fit Kalman rating-book hyper-parameters on the TRAIN window only
  4. replay every game; at each kickoff/tip and at the end of each regulation
     period emit a feature row computed only from results known before then
  5. fit bootstrap logistic ensemble -> temperature-scale on calibration -> score test
  6. write artifact + manifest (competition=<league>) + backtest report + rating params

Usage (repo root):
    PYTHONPATH=backend/src python scripts/train_real.py [--leagues nfl nba ...]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.backtest.metrics import multiclass_brier, log_loss  # noqa: E402
from sportsworld.backtest.runner import _metric_dict, run_binary_backtest  # noqa: E402
from sportsworld.backtest.splitter import ChronologicalSplit  # noqa: E402
from sportsworld.ingest.espn import GameRecord, drop_exhibitions, read_archive  # noqa: E402
from sportsworld.ingest.features import (  # noqa: E402
    ABLATION_GROUPS, FOOTBALL_ABLATION_GROUPS, FOOTBALL_LEAGUE_FEATURES, LEAGUE_FEATURES, SCHEMA_VERSION, league_features,
)
from sportsworld.ingest.football_ep import before_scores, fit_expected_points  # noqa: E402
from sportsworld.schemas import Sport  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES, TEAM_LEAGUES, LeagueSpec  # noqa: E402
from sportsworld.ingest.ratings import GAME_DURATION, RatingBook, fit_params, result_known_time, save_params  # noqa: E402
from sportsworld.schemas import ModelCard  # noqa: E402

DATA = ROOT / "data" / "real"
ART = ROOT / "models" / "artifacts"
MAN = ROOT / "models" / "manifests"
BT = ROOT / "data" / "fixtures" / "backtests"
DATA_MODE = "real_espn"


PLAY_STRIDE = 3  # keep every 3rd snap: dense enough for late-game states, small enough to fit quickly


def load_pbp(league: str) -> dict[str, list[list]]:
    out: dict[str, list[list]] = {}
    for f in sorted((DATA / "pbp" / league).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["game_id"]] = d["plays"]
    return out


def play_seconds_remaining(spec: LeagueSpec, period: int, clock: float) -> float:
    if period <= spec.periods:
        return float((spec.periods - period) * spec.period_seconds + clock)
    return float(min(spec.period_seconds, clock))


def build_rows(spec: LeagueSpec, games: list[GameRecord], book: RatingBook, pbp: dict | None = None, ep_coef: list[float] | None = None) -> list[dict]:
    rows: list[dict] = []
    duration = GAME_DURATION[spec.sport]
    last_known: list[datetime] = [datetime(1970, 1, 1, tzinfo=timezone.utc)]

    def latest_known(at: datetime) -> datetime:
        return last_known[0] if last_known[0] <= at else at

    def on_pregame(g: GameRecord, state: dict) -> None:
        if not g.completed or g.home.score == g.away.score:
            return
        target = int(g.home.score > g.away.score)
        base = {"event_id": g.event_id, "league": spec.league_id, "competition": spec.league_id, "season": g.season, "split_time": g.start_time.isoformat(),
                "feature_schema_version": SCHEMA_VERSION, "target_home_win": target}
        pre_t = g.start_time  # state is computed at kickoff from results known strictly before it
        base["new_team"] = min(float(state["home_games_played"]), float(state["away_games_played"])) <= 3
        if ep_coef:
            state = {**state, "ep_coef": ep_coef}
        f = {**state, "home_score": 0, "away_score": 0, "seconds_remaining": spec.regulation_seconds}
        rows.append({**base, "horizon": "pregame", "prediction_time": pre_t.isoformat(),
                     "max_known_to_model_time": latest_known(pre_t).isoformat(), "features": league_features(f), "play_index": -1,
                     "raw": {"score_diff": 0, "seconds_remaining": spec.regulation_seconds, "period": 0, "poss": 0, "down": 0, "distance": 0, "ytg": -1}})
        plays = (pbp or {}).get(g.game_id)
        if plays:
            before = before_scores(plays)
            for i in range(0, len(plays), PLAY_STRIDE):
                period, clock, _, _, poss, down, distance, ytg, espn_wp = plays[i]
                rem = play_seconds_remaining(spec, period, clock)
                if period < 1 or (period > spec.periods and rem <= 0):
                    continue
                t = g.start_time + duration * min(1.0, 1.0 - rem / spec.regulation_seconds if period <= spec.periods else 1.0)
                f = {**state, "home_score": before[i][0], "away_score": before[i][1], "seconds_remaining": rem,
                     "possession": "home" if poss > 0 else "away" if poss < 0 else None,
                     "down": down if poss else 0, "distance": distance, "yard_line": 100 - ytg if 0 < ytg < 100 else 75}
                rows.append({**base, "horizon": "in_play", "prediction_time": t.isoformat(), "max_known_to_model_time": t.isoformat(),
                             "features": league_features(f), "external_home_wp": espn_wp, "play_index": i,
                             "raw": {"score_diff": before[i][0] - before[i][1], "seconds_remaining": rem, "period": period, "poss": poss,
                                     "down": down if poss else 0, "distance": distance, "ytg": ytg if 0 < ytg < 100 else -1}})
            return
        hl, al = g.home.linescores, g.away.linescores
        if len(hl) < spec.periods or len(al) < spec.periods:
            return
        for k in range(1, spec.periods):
            t = g.start_time + duration * (k / spec.periods)
            f = {**state, "home_score": sum(hl[:k]), "away_score": sum(al[:k]),
                 "seconds_remaining": spec.regulation_seconds - k * spec.period_seconds}
            rows.append({**base, "horizon": f"end_period_{k}", "prediction_time": t.isoformat(),
                         "max_known_to_model_time": t.isoformat(), "features": league_features(f)})

    # Track the latest result-known time actually applied to the book.
    original_apply = book.apply_result

    def tracked_apply(g: GameRecord) -> None:
        before = book.games_applied
        original_apply(g)
        if book.games_applied > before:
            last_known[0] = max(last_known[0], result_known_time(g, spec.sport))

    book.apply_result = tracked_apply  # type: ignore[method-assign]
    book.replay(games, on_pregame=on_pregame)
    return rows


def kalman_baseline(rows: list[dict], test_rows: list[dict]) -> dict[str, float]:
    """Pure state-space probability P(margin > 0) with no learned outcome model."""
    def phi(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    probs = []
    for r in test_rows:
        z = float(r["features"]["live_margin_z"]) * 3.0
        p = min(1 - 1e-4, max(1e-4, phi(z)))
        probs.append([p, 1 - p])
    y = np.asarray([0 if r["target_home_win"] else 1 for r in test_rows])
    return _metric_dict(np.asarray(probs), y)


def train_league(league: str, seed: int) -> dict:
    spec = LEAGUES[league]
    games = drop_exhibitions(read_archive(DATA, league))
    done = [g for g in games if g.completed and not g.cancelled]
    if len(done) < 200:
        return {"league": league, "status": f"skipped: only {len(done)} completed games archived"}
    times = sorted(g.start_time for g in done)
    train_end = times[int(len(times) * 0.6)]
    cal_end = times[int(len(times) * 0.8)]
    params, score = fit_params(spec, [g for g in done if result_known_time(g, spec.sport) <= train_end])
    pbp = load_pbp(league) if spec.sport == Sport.FOOTBALL else {}
    ep_coef, ep_info = None, None
    if pbp:
        train_ids = {g.game_id for g in done if result_known_time(g, spec.sport) <= train_end}
        train_pbp = [p for gid, p in pbp.items() if gid in train_ids]
        if sum(len(p) for p in train_pbp) > 5000:  # EP must be fit on the training window only
            ep_coef, ep_info = fit_expected_points(train_pbp)
        else:
            print(f"{league}: no play-by-play inside the training window; run backfill_pbp.py for earlier seasons. EP disabled.", flush=True)
    save_params(ART / "ratings" / f"{league}.json", spec, params, score, len(done), {"end": train_end.isoformat()}, extra={"ep_coef": ep_coef, "ep_fit": ep_info})
    rows = build_rows(spec, games, RatingBook(spec, params), pbp, ep_coef)
    features = FOOTBALL_LEAGUE_FEATURES if ep_coef else LEAGUE_FEATURES
    groups = FOOTBALL_ABLATION_GROUPS if ep_coef else ABLATION_GROUPS
    split = ChronologicalSplit(train_end, cal_end)
    version = f"{league.replace('-', '_')}_bootstrap_real_v1"
    slices = [
        ("pregame", lambda r: r["horizon"] == "pregame"),
        ("in_game", lambda r: r["horizon"] != "pregame"),
        ("neutral_site", lambda r: r["features"]["home_field"] == 0.0),
        ("home_underdog", lambda r: r["features"]["rating_diff"] < -0.25),
        ("close_late", lambda r: r["features"]["game_elapsed"] >= 0.7 and abs(r["features"]["score_margin_scaled"]) < 0.5),
        ("new_team (<=3 games rated)", lambda r: r.get("new_team", False)),
        ("final_2_minutes", lambda r: r["features"]["game_elapsed"] >= 1 - 120 / spec.regulation_seconds and r["horizon"] != "pregame"),
    ]
    model, scaler, report = run_binary_backtest(
        rows, split, sport=spec.sport, features=features, model_version=version, schema_version=SCHEMA_VERSION,
        competition=league, seed=seed, data_mode=DATA_MODE, ablation_groups=groups, slice_specs=slices,
    )
    _, cal_rows, test = split.split(rows)
    report.baselines["kalman_state_space_only"] = kalman_baseline(rows, test)
    # M4 model selection on the CALIBRATION window only (never the test window).
    cal_y = np.asarray([0 if r["target_home_win"] else 1 for r in cal_rows])
    cal_learned = np.asarray([[ (q := scaler.transform_probabilities(model.predict(r["features"])[0])["home"]), 1 - q] for r in cal_rows])
    sel_learned = _metric_dict(cal_learned, cal_y)["log_loss"]
    sel_kalman = kalman_baseline(rows, cal_rows)["log_loss"]
    selected = "bootstrap_logistic" if sel_learned <= sel_kalman else "kalman_analytic"
    report.baselines["model_selection_calibration_window"] = {"learned_log_loss": sel_learned, "kalman_log_loss": sel_kalman}
    pre = [r for r in test if r["horizon"] == "pregame"]
    report.baselines["kalman_state_space_only_pregame"] = kalman_baseline(rows, pre) if pre else {}
    ext = [r for r in test if r.get("external_home_wp") is not None]
    if ext:
        y = np.asarray([0 if r["target_home_win"] else 1 for r in ext])
        espn = np.clip(np.asarray([float(r["external_home_wp"]) for r in ext]), 1e-4, 1 - 1e-4)
        ours = np.asarray([scaler.transform_probabilities(model.predict(r["features"])[0])["home"] for r in ext])
        report.baselines["external_espn_published_wp (same plays)"] = _metric_dict(np.column_stack([espn, 1 - espn]), y)
        report.baselines["sportsworld (same plays)"] = _metric_dict(np.column_stack([ours, 1 - ours]), y)
    for k in list(report.metrics):
        if isinstance(report.metrics[k], float) and math.isnan(report.metrics[k]):
            del report.metrics[k]

    artifact = {"model": model.to_dict(), "calibrator": scaler.to_dict(), "data_mode": DATA_MODE,
                "rating_params": params.to_dict(), "ep_coef": ep_coef, "ep_fit": ep_info, "source": "ESPN public scoreboard archive",
                "warning": "Trained on real archived results. Live use depends on the unofficial ESPN feed staying available."}
    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"{version}.json").write_text(json.dumps(artifact, indent=2))
    card = ModelCard(
        model_version=version if selected == "bootstrap_logistic" else f"{league.replace('-', '_')}_kalman_analytic_real_v1", sport=spec.sport, competition=league, algorithm=selected,
        feature_schema_version=SCHEMA_VERSION, features=features, train_window=report.train_window,
        calibration_window=report.calibration_window, test_window=report.test_window, artifact_uri=f"{version}.json",
        calibration_version=scaler.version if selected == "bootstrap_logistic" else "analytic",
        metrics=report.metrics if selected == "bootstrap_logistic" else report.baselines["kalman_state_space_only"], data_mode=DATA_MODE,
        notes=[f"{spec.display_name}: {len(done)} completed games, {len(rows)} point-in-time rows (pregame + end of each regulation period).",
               "Latent team strength is a Kalman-filtered rating whose dynamics were fit on the training window only.",
               "Market odds are archived but excluded from features so SportsWorld can be compared against external consensus.",
               f"M4 selection on the calibration window: learned {sel_learned:.4f} vs Kalman analytic {sel_kalman:.4f} -> serving {selected}. "
               "Caveat: the learned model's 1-parameter temperature is fit on the same window, which slightly favours it; card metrics are the held-out test metrics of the SERVED model."],
    )
    (MAN / f"league_{league}.json").write_text(card.model_dump_json(indent=2))
    BT.mkdir(parents=True, exist_ok=True)
    (BT / f"{league}_real.json").write_text(report.model_dump_json(indent=2))
    return {"league": league, "games": len(done), "rows": len(rows), "params": params.to_dict(),
            "selected": selected, "selection": {"learned": round(sel_learned, 4), "kalman": round(sel_kalman, 4)},
            "test": {k: round(v, 4) for k, v in report.metrics.items()},
            "kalman_only": {k: round(v, 4) for k, v in report.baselines["kalman_state_space_only"].items()},
            "ablations": [(a["stage"], round(a["log_loss"], 4)) for a in report.ablations], "ep": ep_info,
            "external": {k: {m: round(v, 4) for m, v in report.baselines[k].items()} for k in report.baselines if "same plays" in k},
            "slices": [(x["name"], x["count"], round(x.get("log_loss", float("nan")), 4)) for x in report.slices]}


# ---------------------------------------------------------------------------
# Formula 1
# ---------------------------------------------------------------------------
F1_CHECKPOINTS = (0.25, 0.5, 0.75, 0.9)
F1_ABLATIONS = [
    ("A0 grid / running position", ["position_advantage", "progress_position"]),
    ("A1 + latent driver & car state", ["position_advantage", "progress_position", "driver_rating", "car_rating", "rating_uncertainty"]),
    ("A2 + car reliability", ["position_advantage", "progress_position", "driver_rating", "car_rating", "rating_uncertainty", "reliability_remaining"]),
]


def f1_rows(races, book, laps_by_event) -> list[dict]:
    from sportsworld.ingest.f1 import RACE_DURATION, lap_snapshot
    from sportsworld.schemas import WorldState
    from sportsworld.sports.f1 import F1Adapter

    adapter = F1Adapter()
    rows = []
    last_known = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for race in races:
        winner = race.winner()
        if winner and len(race.results) >= 10:
            n = len(race.results)
            total = max(r.laps for r in race.results) or 57
            base_drivers = {}
            for r in race.results:
                v = book.driver_view(r.driver_id, r.constructor_id)
                base_drivers[r.code] = {**v, "position": r.grid if r.grid > 0 else n, "grid": r.grid, "gap_to_leader": 0.0}

            def emit(drivers: dict, lap: int, t: datetime, known: datetime, horizon: str) -> None:
                if winner.code not in drivers:
                    return
                state = WorldState(event_id=race.event_id, sport=Sport.F1, competition="f1", season=str(race.season), outcomes=list(drivers),
                                   features={"lap": lap, "total_laps": total, "drivers": drivers})
                rows.append({"event_id": race.event_id, "prediction_time": t.isoformat(), "max_known_to_model_time": known.isoformat(),
                             "horizon": horizon, "outcome_features": adapter.build_outcome_features(state, t), "target_winner": winner.code})

            emit(base_drivers, 0, race.start_time - timedelta(minutes=5), min(last_known, race.start_time), "pre_race")
            lap_data = laps_by_event.get(race.event_id)
            if lap_data:
                for frac in F1_CHECKPOINTS:
                    lap = max(1, int(round(total * frac)))
                    _, snap = lap_snapshot(lap_data["laps"], lap_data["drivers"], upto_lap=lap)
                    drivers = {c: {**base_drivers[c], **snap[c]} for c in snap if c in base_drivers and snap[c]["laps_completed"] >= lap - 1}
                    if len(drivers) >= 2:
                        t = race.start_time + RACE_DURATION * frac
                        emit(drivers, lap, t, t, f"lap_{int(frac * 100)}pct")
        book.apply_race(race)
        last_known = max(last_known, race.start_time + RACE_DURATION + timedelta(hours=1))
    return rows


def f1_tensor(rows, features, k):
    X = np.zeros((len(rows), k, len(features)))
    M = np.zeros((len(rows), k), dtype=bool)
    y = np.zeros(len(rows), dtype=int)
    for i, r in enumerate(rows):
        labels = list(r["outcome_features"])
        for j, lab in enumerate(labels[:k]):
            X[i, j] = [float(r["outcome_features"][lab].get(f, 0.0)) for f in features]
            M[i, j] = True
        y[i] = labels.index(r["target_winner"])
    return X, M, y


def f1_probs(model, X, M, temperature=1.0):
    out = []
    for m in model.members:
        s = np.einsum("nkd,d->nk", X, m.weights) / temperature
        s = np.where(M, s, -1e9)
        s -= s.max(axis=1, keepdims=True)
        e = np.exp(s) * M
        out.append(e / e.sum(axis=1, keepdims=True))
    return np.mean(out, axis=0)


def fit_f1_temperature(model, X, M, y):
    best, best_t = float("inf"), 1.0
    for t in np.geomspace(0.35, 4.0, 120):
        p = f1_probs(model, X, M, t)
        loss = -float(np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))
        if loss < best:
            best, best_t = loss, float(t)
    return best_t


def train_f1(seed: int = 13) -> dict:
    from sportsworld.backtest.leakage import audit_rows
    from sportsworld.backtest.runner import _top_reliability
    from sportsworld.core.calibration import TemperatureScaler
    from sportsworld.ingest.f1 import F1RatingBook, fit_f1_params, read_f1_archive, read_f1_laps
    from sportsworld.models.linear import BootstrapConditionalSoftmaxEnsemble
    from sportsworld.schemas import BacktestRun
    from sportsworld.sports.f1 import F1Adapter

    races = [r for r in read_f1_archive(DATA) if r.completed]
    laps = read_f1_laps(DATA)
    if len(races) < 40:
        return {"league": "f1", "status": f"skipped: only {len(races)} races archived"}
    # Split on race boundaries, weighted toward having in-race (lap-timing) rows in training.
    probe = f1_rows(races, F1RatingBook(), laps)
    times = sorted({r["prediction_time"][:10] for r in probe})
    by_day = {d: sum(1 for r in probe if r["prediction_time"][:10] == d) for d in times}
    total, acc, train_end, cal_end = sum(by_day.values()), 0, None, None
    for d in times:
        acc += by_day[d]
        if train_end is None and acc >= 0.6 * total:
            train_end = datetime.fromisoformat(d + "T23:59:59+00:00")
        if cal_end is None and acc >= 0.8 * total:
            cal_end = datetime.fromisoformat(d + "T23:59:59+00:00")
    params, score = fit_f1_params([r for r in races if r.start_time <= train_end])
    rows = f1_rows(races, F1RatingBook(params), laps)
    train = [r for r in rows if datetime.fromisoformat(r["prediction_time"]) <= train_end]
    cal = [r for r in rows if train_end < datetime.fromisoformat(r["prediction_time"]) <= cal_end]
    test = [r for r in rows if datetime.fromisoformat(r["prediction_time"]) > cal_end]
    feats = F1Adapter.REAL_FEATURES
    k = max(len(r["outcome_features"]) for r in rows)
    version = "f1_conditional_softmax_real_v1"

    def fit_eval(fs, n_members, sd):
        Xtr, Mtr, ytr = f1_tensor(train, fs, k)
        model = BootstrapConditionalSoftmaxEnsemble.fit_bootstrap(Xtr, ytr, fs, n_members=n_members, seed=sd, mask=Mtr, lr=0.2, epochs=900)
        Xc, Mc, yc = f1_tensor(cal, fs, k)
        t = fit_f1_temperature(model, Xc, Mc, yc)
        Xte, Mte, yte = f1_tensor(test, fs, k)
        return model, t, f1_probs(model, Xte, Mte, t), yte, Mte

    model, temp, probs, yte, Mte = fit_eval(feats, 15, seed)
    metrics = _metric_dict(probs, yte)
    ablations = []
    for i, (label, fs) in enumerate(F1_ABLATIONS + [("A3 + live gaps to leader", feats)]):
        _, _, p, y, _ = fit_eval(fs, 7, seed + 30 + i)
        ablations.append({"stage": f"A{i}", "label": label, "feature_count": len(fs), **_metric_dict(p, y)})
    # Baseline: empirical win rate by grid position in the training window.
    pole = np.zeros(k + 2)
    for r in train:
        if r["horizon"] == "pre_race":
            g = int(round((1 - r["outcome_features"][r["target_winner"]]["position_advantage"]) / 2 * (len(r["outcome_features"]) - 1))) + 1
            pole[min(g, k + 1)] += 1
    base = []
    for r in test:
        n = len(r["outcome_features"])
        w = [pole[min(int(round((1 - f["position_advantage"]) / 2 * (n - 1))) + 1, k + 1)] + 0.5 for f in r["outcome_features"].values()]
        w = np.asarray(w) / np.sum(w)
        base.append(np.pad(w, (0, k - n)))
    slices = []
    for name in ["pre_race", "lap_25pct", "lap_50pct", "lap_75pct", "lap_90pct"]:
        idx = [i for i, r in enumerate(test) if r["horizon"] == name]
        if len(idx) >= 3:
            slices.append({"name": name, "count": len(idx), **_metric_dict(probs[idx], yte[idx])})
    errors = []
    for r, p, yv in zip(test, probs, yte):
        labels = list(r["outcome_features"])
        j = int(np.argmax(p[:len(labels)]))
        if j != yv:
            errors.append({"event_id": r["event_id"], "prediction_time": r["prediction_time"], "predicted": labels[j], "actual": labels[yv],
                           "confidence": float(p[j]), "probabilities": {l: float(p[i]) for i, l in enumerate(labels)}})
    errors = sorted(errors, key=lambda e: e["confidence"], reverse=True)[:12]
    window = lambda rs: {"start": rs[0]["prediction_time"], "end": rs[-1]["prediction_time"]}
    report = BacktestRun(
        run_id=f"f1-{version}", sport=Sport.F1, competition="f1", model_version=version, feature_schema_version="f1_real_features_v1",
        train_window=window(train), calibration_window=window(cal), test_window=window(test), split_method="chronological_holdout",
        prediction_horizons=["pre_race", "in_race"], sample_counts={"train": len(train), "calibration": len(cal), "test": len(test)},
        metrics=metrics, baselines={"empirical_win_rate_by_grid_slot": _metric_dict(np.asarray(base), yte)}, ablations=ablations, slices=slices,
        leakage_violations=len(audit_rows(rows)), reliability=_top_reliability(probs, yte), errors=errors, data_mode="real_jolpica_openf1",
        data_snapshot_hash=str(len(rows)),
    )
    scaler = TemperatureScaler(temperature=temp, version=f"{version}_temperature_v1")
    (ART / f"{version}.json").write_text(json.dumps({"model": model.to_dict(), "calibrator": scaler.to_dict(), "data_mode": "real_jolpica_openf1", "rating_params": params.to_dict()}, indent=2))
    (ART / "ratings").mkdir(parents=True, exist_ok=True)
    (ART / "ratings" / "f1.json").write_text(json.dumps({"league": "f1", "params": params.to_dict(), "mean_predictive_loglik": score, "fit_window": {"end": train_end.isoformat()}}, indent=2))
    card = ModelCard(model_version=version, sport=Sport.F1, competition="f1", algorithm="bootstrap_conditional_softmax", feature_schema_version="f1_real_features_v1",
                     features=feats, train_window=report.train_window, calibration_window=report.calibration_window, test_window=report.test_window,
                     artifact_uri=f"{version}.json", calibration_version=scaler.version, metrics=metrics, data_mode="real_jolpica_openf1",
                     notes=[f"{len(races)} races since {races[0].season}; in-race checkpoints from OpenF1 lap timing ({len(laps)} races).",
                            "Driver and car are separate Kalman latent states; reliability is a decayed classified-finish rate per car."])
    (MAN / "league_f1.json").write_text(card.model_dump_json(indent=2))
    (BT / "f1_real.json").write_text(report.model_dump_json(indent=2))
    return {"league": "f1", "games": len(races), "rows": len(rows), "params": params.to_dict(), "temperature": temp,
            "test": {k2: round(v, 4) for k2, v in metrics.items()}, "baseline_grid": {k2: round(v, 4) for k2, v in report.baselines["empirical_win_rate_by_grid_slot"].items()},
            "ablations": [(a["stage"], round(a["log_loss"], 4)) for a in ablations], "slices": [(x["name"], x["count"], round(x["log_loss"], 4)) for x in slices]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=TEAM_LEAGUES + ["f1"])
    args = ap.parse_args()
    for i, league in enumerate(args.leagues):
        result = train_f1() if league == "f1" else train_league(league, seed=100 + i)
        print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
