"""Win-probability model bake-off on real football play-by-play (spec §13.1 M1 vs M3).

Same point-in-time rows, same chronological split (train 60% | calibration 20% | test 20% by
game start), same temperature calibration, same test plays. Candidates:
  logistic  — bootstrap logistic ensemble on the league feature schema (current production)
  lgbm      — gradient-boosted trees on league features + raw game state
  mlp       — 3-layer MLP (torch) on the same inputs
  gru       — causal GRU over the game's play sequence so far + pregame state
External benchmark: ESPN's published win probability on the identical plays (never a feature).

Usage (GPU host): python scripts/wp_bakeoff.py --league nfl --gpu 0
Writes data/fixtures/backtests/bakeoff_<league>.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sportsworld.backtest.metrics import log_loss, multiclass_brier, top_label_ece  # noqa: E402
from sportsworld.ingest.espn import drop_exhibitions, read_archive  # noqa: E402
from sportsworld.ingest.features import FOOTBALL_LEAGUE_FEATURES  # noqa: E402
from sportsworld.ingest.football_ep import fit_expected_points  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import RatingBook, fit_params, result_known_time  # noqa: E402
from train_real import DATA, build_rows, load_pbp  # noqa: E402

RAW = ["score_diff", "seconds_remaining", "period", "poss", "down", "distance", "ytg"]


def metrics(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    P = np.column_stack([p, 1 - p])
    cls = np.where(y == 1, 0, 1)
    ece, _ = top_label_ece(P, cls)
    return {"log_loss": round(log_loss(P, cls), 5), "brier": round(multiclass_brier(P, cls), 5), "ece": round(ece, 5),
            "accuracy": round(float(np.mean((p >= 0.5) == (y == 1))), 5), "n": int(len(y))}


def temperature(logit_cal: np.ndarray, y_cal: np.ndarray) -> float:
    best, bt = 1e9, 1.0
    for t in np.geomspace(0.3, 4, 120):
        p = 1 / (1 + np.exp(-logit_cal / t))
        ll = -np.mean(y_cal * np.log(np.clip(p, 1e-9, 1)) + (1 - y_cal) * np.log(np.clip(1 - p, 1e-9, 1)))
        if ll < best:
            best, bt = ll, t
    return float(bt)


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="nfl")
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--models", default="logistic,lgbm,mlp,gru")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    want = set(a.models.split(","))
    t_start = time.time()
    spec = LEAGUES[a.league]
    games = drop_exhibitions(read_archive(DATA, a.league))
    done = [g for g in games if g.completed]
    times = sorted(g.start_time for g in done)
    train_end, cal_end = times[int(len(times) * 0.6)], times[int(len(times) * 0.8)]
    params, _ = fit_params(spec, [g for g in done if result_known_time(g, spec.sport) <= train_end])
    pbp = load_pbp(a.league)
    train_ids = {g.game_id for g in done if result_known_time(g, spec.sport) <= train_end}
    ep_coef, _ = fit_expected_points([p for gid, p in pbp.items() if gid in train_ids])
    rows = build_rows(spec, games, RatingBook(spec, params), pbp, ep_coef)
    rows = [r for r in rows if r["horizon"] in ("pregame", "in_play")]
    start_of = {g.event_id: g.start_time.isoformat() for g in games}
    split = np.asarray([0 if start_of[r["event_id"]] <= train_end.isoformat() else 1 if start_of[r["event_id"]] <= cal_end.isoformat() else 2 for r in rows])
    F = FOOTBALL_LEAGUE_FEATURES
    X = np.asarray([[r["features"][k] for k in F] + [float(r["raw"][k]) for k in RAW] for r in rows], dtype=np.float32)
    y = np.asarray([r["target_home_win"] for r in rows], dtype=np.float32)
    espn = np.asarray([np.nan if r.get("external_home_wp") is None else float(r["external_home_wp"]) for r in rows])
    tr, ca, te = split == 0, split == 1, split == 2
    mu, sd = X[tr].mean(0), np.maximum(X[tr].std(0), 1e-2)  # floor: near-constant train features must not explode at test time
    Xs = (X - mu) / sd
    preds: dict[str, np.ndarray] = {}
    report: dict = {"league": a.league, "rows": int(len(rows)), "train": int(tr.sum()), "calibration": int(ca.sum()), "test": int(te.sum()),
                    "features": F + RAW, "models": {}}

    def finish(name, raw_cal, raw_test, extra=None):
        t = temperature(logit(raw_cal), y[ca])
        p = 1 / (1 + np.exp(-logit(raw_test) / t))
        m = metrics(p, y[te])
        mask = ~np.isnan(espn[te])
        m["same_plays_as_espn"] = metrics(p[mask], y[te][mask])
        m["temperature"] = round(t, 3)
        if extra:
            m.update(extra)
        report["models"][name] = m
        preds[name] = p
        print(name, json.dumps(m), flush=True)
        return p

    # 1. logistic (production-equivalent, league features only)
    from sportsworld.models.linear import BootstrapBinaryEnsemble
    if "logistic" not in want:
        BootstrapBinaryEnsemble = None  # noqa: N806
    nf = len(F)
    if BootstrapBinaryEnsemble is not None:
        ens = BootstrapBinaryEnsemble.fit_bootstrap(X[tr][:, :nf].astype(float), y[tr].astype(int), F, n_members=7, seed=3)
        pred = lambda M: np.asarray([ens.predict(dict(zip(F, row)))[0]["home"] for row in M[:, :nf].astype(float)])  # noqa: E731
        finish("logistic_bootstrap", pred(X[ca]), pred(X[te]))

    # 2. LightGBM
    try:
        if "lgbm" not in want:
            raise ImportError("skipped")
        import lightgbm as lgb
        d = lgb.Dataset(X[tr], y[tr])
        dv = lgb.Dataset(X[ca], y[ca])
        booster = lgb.train({"objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
                             "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1},
                            d, num_boost_round=2000, valid_sets=[dv], callbacks=[lgb.early_stopping(100, verbose=False)])
        finish("lightgbm", booster.predict(X[ca]), booster.predict(X[te]), {"trees": booster.best_iteration})
    except ImportError:
        print("lightgbm unavailable", flush=True)

    # 3/4. torch models
    import torch
    import torch.nn as nn
    dev = torch.device(f"cuda:{a.gpu}" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(a.seed)
    Xt = torch.tensor(Xs, device=dev)
    yt = torch.tensor(y, device=dev)

    layers, d_in = [], Xs.shape[1]
    for _ in range(a.layers):
        layers += [nn.Linear(d_in, a.hidden), nn.GELU(), nn.Dropout(a.dropout)]
        d_in = a.hidden
    mlp = nn.Sequential(*layers, nn.Linear(d_in, 1)).to(dev)
    opt = torch.optim.AdamW(mlp.parameters(), lr=a.lr, weight_decay=1e-4)
    idx = torch.nonzero(torch.tensor(tr, device=dev)).squeeze(1)
    for ep in range(a.epochs):
        perm = idx[torch.randperm(len(idx), device=dev)]
        for b in range(0, len(perm), 4096):
            j = perm[b:b + 4096]
            loss = nn.functional.binary_cross_entropy_with_logits(mlp(Xt[j]).squeeze(1), yt[j])
            opt.zero_grad(); loss.backward(); opt.step()
    mlp.eval()
    with torch.no_grad():
        pm = torch.sigmoid(mlp(Xt).squeeze(1)).cpu().numpy()
    if "mlp" in want:
        finish("mlp", pm[ca], pm[te], {"device": str(dev), "config": {"hidden": a.hidden, "layers": a.layers, "dropout": a.dropout, "lr": a.lr, "seed": a.seed},
                                       "calibration_log_loss": metrics(1 / (1 + np.exp(-logit(pm[ca]) / temperature(logit(pm[ca]), y[ca]))), y[ca])["log_loss"]})

    # GRU over each game's sampled play sequence (causal: output at t sees plays <= t)
    order: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        order.setdefault(r["event_id"], []).append(i)
    for k in order:
        order[k].sort(key=lambda i: rows[i]["play_index"])

    class GRUWP(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.inp = nn.Linear(d, 96)
            self.gru = nn.GRU(96, 96, batch_first=True)
            self.out = nn.Sequential(nn.Linear(96 + d, 96), nn.GELU(), nn.Linear(96, 1))

        def forward(self, x):
            h, _ = self.gru(torch.relu(self.inp(x)))
            return self.out(torch.cat([h, x], dim=-1)).squeeze(-1)

    if "gru" not in want:
        a.epochs_gru = 0
    gru = GRUWP(Xs.shape[1]).to(dev)
    opt = torch.optim.AdamW(gru.parameters(), lr=1e-3, weight_decay=1e-4)
    seqs = list(order.values())
    seq_split = [split[s[0]] for s in seqs]
    maxlen = max(len(s) for s in seqs)

    def batch(group):
        L = max(len(s) for s in group)
        xb = torch.zeros(len(group), L, Xs.shape[1], device=dev)
        yb = torch.zeros(len(group), L, device=dev)
        mb = torch.zeros(len(group), L, device=dev)
        for i, s in enumerate(group):
            xb[i, :len(s)] = Xt[s]
            yb[i, :len(s)] = yt[s]
            mb[i, :len(s)] = 1
        return xb, yb, mb

    train_seqs = [s for s, sp in zip(seqs, seq_split) if sp == 0]
    rng = np.random.default_rng(0)
    for ep in range(a.epochs if "gru" in want else 0):
        rng.shuffle(train_seqs)
        gru.train()
        for b in range(0, len(train_seqs), 64):
            xb, yb, mb = batch(train_seqs[b:b + 64])
            l = nn.functional.binary_cross_entropy_with_logits(gru(xb), yb, reduction="none")
            loss = (l * mb).sum() / mb.sum()
            opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(gru.parameters(), 1.0); opt.step()
    gru.eval()
    pg = np.zeros(len(rows))
    with torch.no_grad():
        for b in range(0, len(seqs), 256):
            group = seqs[b:b + 256]
            xb, _, _ = batch(group)
            out = torch.sigmoid(gru(xb)).cpu().numpy()
            for i, s in enumerate(group):
                pg[s] = out[i, :len(s)]
    if "gru" in want:
        finish("gru_sequence", pg[ca], pg[te], {"max_seq_len": maxlen})

    mask = ~np.isnan(espn[te])
    report["models"]["external_espn_published_wp"] = {"same_plays_as_espn": metrics(np.clip(espn[te][mask], 1e-4, 1 - 1e-4), y[te][mask])}
    # Game-clustered paired bootstrap: plays within a game are strongly correlated, so resample games.
    games_te = np.asarray([rows[i]["event_id"] for i in np.nonzero(te)[0]])
    yte = y[te]
    def ll_vec(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(yte * np.log(p) + (1 - yte) * np.log(1 - p))
    losses = {k: ll_vec(v) for k, v in preds.items()}
    losses["external_espn_published_wp"] = np.where(mask, ll_vec(np.where(mask, espn[te], 0.5)), np.nan)
    uniq = np.unique(games_te)
    gidx = {g: np.nonzero(games_te == g)[0] for g in uniq}
    rng_b = np.random.default_rng(0)
    comparisons = {}
    pairs = [(k, "external_espn_published_wp") for k in preds] + ([(k, "logistic_bootstrap") for k in preds if k != "logistic_bootstrap"] if "logistic_bootstrap" in preds else [])
    for a_name, b_name in pairs:
        diffs = []
        both = mask if "espn" in b_name else np.ones_like(mask)
        elig = np.asarray([g for g in uniq if both[gidx[g]].any()])  # games with at least one comparable play
        for _ in range(2000):
            pick = np.concatenate([gidx[g] for g in rng_b.choice(elig, size=len(elig), replace=True)])
            pick = pick[both[pick]]
            diffs.append(float(np.mean(losses[a_name][pick] - losses[b_name][pick])))
        d = np.asarray(diffs)
        sel = both
        comparisons[f"{a_name} - {b_name}"] = {"mean_log_loss_diff": round(float(np.mean(losses[a_name][sel] - losses[b_name][sel])), 5),
                                               "ci95": [round(float(np.quantile(d, .025)), 5), round(float(np.quantile(d, .975)), 5)],
                                               "share_of_bootstrap_draws_favoring_a": round(float(np.mean(d < 0)), 4), "games": int(len(elig))}
        print("compare", a_name, "vs", b_name, comparisons[f"{a_name} - {b_name}"], flush=True)
    report["paired_game_bootstrap"] = comparisons
    (ROOT / "data" / "fixtures" / "backtests").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ROOT / "data" / "fixtures" / "backtests" / f"bakeoff_{a.league}{a.tag}_preds.npz", y=yte, espn=espn[te], games=games_te, **preds)
    import hashlib
    report["data_fingerprint"] = {"rows": int(len(rows)), "games": int(len({r["event_id"] for r in rows})),
                                  "hash": hashlib.sha256("|".join(sorted({r["event_id"] for r in rows})).encode()).hexdigest()[:16]}
    report["runtime_s"] = round(time.time() - t_start, 1)
    out = ROOT / "data" / "fixtures" / "backtests" / (f"sweeps/bakeoff_{a.league}{a.tag}.json" if a.tag else f"bakeoff_{a.league}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
