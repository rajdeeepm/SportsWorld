"""In-game win-probability bake-off for basketball / hockey from real play-by-play (ESPN summaries).

Production basketball/hockey models are trained only on period-end snapshots; this tests whether
dense play-level states improve live forecasts. Same chronological 60/20/20 split by game, same
temperature calibration on the calibration window, game-clustered paired bootstrap on the test window.

Rows: pregame + every k-th play (pre-play score, clock, last-event side) with league features from a
point-in-time Kalman replay. Models: logistic (production schema), MLP, GRU over the game's play sequence.
Usage: python scripts/wp_bakeoff_pbp.py --league nba --gpu 0 [--models logistic,mlp,gru] [--seed 0] [--tag _x]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sportsworld.ingest.espn import drop_exhibitions, read_archive  # noqa: E402
from sportsworld.ingest.features import LEAGUE_FEATURES, league_features  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import GAME_DURATION, RatingBook, fit_params, result_known_time  # noqa: E402
from wp_bakeoff import logit, metrics, temperature  # noqa: E402

DATA = ROOT / "data" / "real"
RAW = ["score_diff", "seconds_remaining", "period", "side", "overtime"]


def load_plays(league: str) -> dict[str, list]:
    out = {}
    for f in sorted((DATA / "summaries" / league).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("plays"):
                    out[d["game_id"]] = d["plays"]
    return out


def secs_left(spec, period: int, clock: float) -> float:
    if period <= spec.periods:
        return float((spec.periods - period) * spec.period_seconds + clock)
    return float(max(0.0, clock))


def build(spec, games, book, plays, stride):
    rows = []

    def pre(g, state):
        if not g.completed or g.home.score == g.away.score:
            return
        y = int(g.home.score > g.away.score)
        base = {"event_id": g.event_id, "target": y, "start": g.start_time}
        f0 = {**state, "home_score": 0, "away_score": 0, "seconds_remaining": spec.regulation_seconds}
        rows.append({**base, "i": -1, "features": league_features(f0), "raw": [0, spec.regulation_seconds, 0, 0, 0]})
        pl = plays.get(g.game_id)
        if not pl:
            return
        hs = as_ = 0
        for i, p in enumerate(pl):
            period, clock, phs, pas, side = p[0], p[1], p[2], p[3], p[4]
            if i % stride == 0 and period >= 1:
                rem = secs_left(spec, period, clock)
                f = {**state, "home_score": hs, "away_score": as_, "seconds_remaining": rem}
                rows.append({**base, "i": i, "features": league_features(f), "raw": [hs - as_, rem, period, side, int(period > spec.periods)]})
            hs, as_ = phs, pas

    book.replay(games, on_pregame=pre)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--models", default="logistic,mlp,gru")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--tag", default="")
    ap.add_argument("--origin", type=int, default=None, help="walk-forward: train <= O-2, calibrate O-1, test season O")
    a = ap.parse_args()
    want = set(a.models.split(","))
    t0 = time.time()
    spec = LEAGUES[a.league]
    plays = load_plays(a.league)
    games = [g for g in drop_exhibitions(read_archive(DATA, a.league)) if g.game_id in plays or not g.completed]
    done = sorted([g for g in games if g.completed], key=lambda g: g.start_time)
    times = [g.start_time for g in done]
    train_end, cal_end = times[int(len(times) * 0.6)], times[int(len(times) * 0.8)]
    test_end = None
    if a.origin is not None:
        from sportsworld.ingest.espn import season_start_year
        sy = lambda g: season_start_year(spec, g.start_time)  # noqa: E731
        train_end = max(g.start_time for g in done if sy(g) <= a.origin - 2)
        cal_end = max(g.start_time for g in done if sy(g) == a.origin - 1)
        test_end = max(g.start_time for g in done if sy(g) == a.origin)
        done = [g for g in done if g.start_time <= test_end]
    params, _ = fit_params(spec, [g for g in done if result_known_time(g, spec.sport) <= train_end])
    rows = build(spec, done, RatingBook(spec, params), plays, a.stride)
    split = np.asarray([0 if r["start"] <= train_end else 1 if r["start"] <= cal_end else 2 for r in rows])
    X = np.asarray([[r["features"][k] for k in LEAGUE_FEATURES] + r["raw"] for r in rows], dtype=np.float32)
    y = np.asarray([r["target"] for r in rows], dtype=np.float32)
    tr, ca, te = split == 0, split == 1, split == 2
    mu, sd = X[tr].mean(0), np.maximum(X[tr].std(0), 1e-2)  # floor: near-constant train features must not explode at test time
    Xs = (X - mu) / sd
    report = {"league": a.league, "rows": int(len(rows)), "games": len(done), "train": int(tr.sum()), "calibration": int(ca.sum()), "test": int(te.sum()),
              "stride": a.stride, "models": {}}
    preds = {}

    def finish(name, pc, pt, extra=None):
        t = temperature(logit(pc), y[ca])
        p = 1 / (1 + np.exp(-logit(pt) / t))
        m = metrics(p, y[te])
        m["temperature"] = round(t, 3)
        live = np.asarray([rows[i]["i"] >= 0 for i in np.nonzero(te)[0]])
        m["in_game_only"] = metrics(p[live], y[te][live])
        m.update(extra or {})
        report["models"][name] = m
        preds[name] = p
        print(name, json.dumps(m), flush=True)

    nf = len(LEAGUE_FEATURES)
    if "logistic" in want:
        from sportsworld.models.linear import BootstrapBinaryEnsemble
        ens = BootstrapBinaryEnsemble.fit_bootstrap(X[tr][:, :nf].astype(float), y[tr].astype(int), LEAGUE_FEATURES, n_members=5, seed=3)
        pr = lambda M: np.asarray([ens.predict(dict(zip(LEAGUE_FEATURES, r)))[0]["home"] for r in M[:, :nf].astype(float)])  # noqa: E731
        finish("logistic_bootstrap", pr(X[ca]), pr(X[te]))
    import torch
    import torch.nn as nn
    dev = torch.device(f"cuda:{a.gpu}" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(a.seed)
    Xt, yt = torch.tensor(Xs, device=dev), torch.tensor(y, device=dev)
    if "mlp" in want:
        mlp = nn.Sequential(nn.Linear(Xs.shape[1], 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 128), nn.GELU(), nn.Linear(128, 1)).to(dev)
        opt = torch.optim.AdamW(mlp.parameters(), lr=1e-3, weight_decay=1e-4)
        idx = torch.nonzero(torch.tensor(tr, device=dev)).squeeze(1)
        for _ in range(a.epochs):
            perm = idx[torch.randperm(len(idx), device=dev)]
            for b in range(0, len(perm), 8192):
                j = perm[b:b + 8192]
                loss = nn.functional.binary_cross_entropy_with_logits(mlp(Xt[j]).squeeze(1), yt[j])
                opt.zero_grad(); loss.backward(); opt.step()
        mlp.eval()
        with torch.no_grad():
            pm = torch.sigmoid(mlp(Xt).squeeze(1)).cpu().numpy()
        finish("mlp", pm[ca], pm[te], {"device": str(dev)})
    if "gru" in want:
        order: dict[str, list[int]] = {}
        for i, r in enumerate(rows):
            order.setdefault(r["event_id"], []).append(i)
        seqs = [sorted(v, key=lambda i: rows[i]["i"]) for v in order.values()]

        class G(nn.Module):
            def __init__(self, d):
                super().__init__()
                self.inp = nn.Linear(d, 96); self.gru = nn.GRU(96, 96, batch_first=True)
                self.out = nn.Sequential(nn.Linear(96 + d, 96), nn.GELU(), nn.Linear(96, 1))

            def forward(self, x):
                h, _ = self.gru(torch.relu(self.inp(x)))
                return self.out(torch.cat([h, x], -1)).squeeze(-1)

        def batch(group):
            L = max(len(s) for s in group)
            xb = torch.zeros(len(group), L, Xs.shape[1], device=dev); yb = torch.zeros(len(group), L, device=dev); mb = torch.zeros(len(group), L, device=dev)
            for k, s in enumerate(group):
                xb[k, :len(s)] = Xt[s]; yb[k, :len(s)] = yt[s]; mb[k, :len(s)] = 1
            return xb, yb, mb

        net = G(Xs.shape[1]).to(dev)
        opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
        train_seqs = [s for s in seqs if split[s[0]] == 0]
        rng = np.random.default_rng(a.seed)
        for _ in range(a.epochs):
            rng.shuffle(train_seqs)
            for b in range(0, len(train_seqs), 64):
                xb, yb, mb = batch(train_seqs[b:b + 64])
                l = (nn.functional.binary_cross_entropy_with_logits(net(xb), yb, reduction="none") * mb).sum() / mb.sum()
                opt.zero_grad(); l.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
        net.eval()
        pg = np.zeros(len(rows))
        with torch.no_grad():
            for b in range(0, len(seqs), 256):
                group = seqs[b:b + 256]
                out = torch.sigmoid(net(batch(group)[0])).cpu().numpy()
                for k, s in enumerate(group):
                    pg[s] = out[k, :len(s)]
        finish("gru_sequence", pg[ca], pg[te])
    # game-clustered paired bootstrap vs logistic
    if "logistic_bootstrap" in preds:
        g_te = np.asarray([rows[i]["event_id"] for i in np.nonzero(te)[0]])
        yte = y[te]
        ll = lambda p: -(yte * np.log(np.clip(p, 1e-6, 1)) + (1 - yte) * np.log(np.clip(1 - p, 1e-6, 1)))  # noqa: E731
        uniq = np.unique(g_te); gi = {g: np.nonzero(g_te == g)[0] for g in uniq}; rb = np.random.default_rng(0)
        comp = {}
        for k in preds:
            if k == "logistic_bootstrap":
                continue
            d = ll(preds[k]) - ll(preds["logistic_bootstrap"])
            boots = [d[np.concatenate([gi[g] for g in rb.choice(uniq, len(uniq))])].mean() for _ in range(1500)]
            comp[f"{k} - logistic_bootstrap"] = {"mean": round(float(d.mean()), 5), "ci95": [round(float(np.quantile(boots, .025)), 5), round(float(np.quantile(boots, .975)), 5)],
                                                 "share_of_bootstrap_draws_favoring_a": round(float(np.mean(np.asarray(boots) < 0)), 4), "games": int(len(uniq))}
        report["paired_game_bootstrap"] = comp
        print(json.dumps(comp), flush=True)
    import hashlib
    report["data_fingerprint"] = {"rows": int(len(rows)), "games": int(len({r["event_id"] for r in rows})),
                                  "hash": hashlib.sha256("|".join(sorted({r["event_id"] for r in rows})).encode()).hexdigest()[:16]}
    report["runtime_s"] = round(time.time() - t0, 1)
    out = ROOT / "data" / "fixtures" / "backtests" / (f"sweeps/pbp_bakeoff_{a.league}{a.tag}.json" if a.tag else f"pbp_bakeoff_{a.league}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
