"""Learned football expected points (EP) from real play-by-play.

Target for each snap: net points of the next score in the same half, from the
offense's perspective (+ if the offense scores next, - if the defense does, 0 if
nobody scores before half-time).  A touchdown's extra point is approximated as
+1 because ESPN records the PAT as a separate score change.  The fit is ordinary
least squares on `features.ep_design`, i.e. a smooth function of yards-to-go,
down and distance.

Play row layout (see scripts/backfill_pbp.py):
    [period, clock_s, home_score, away_score, poss, down, distance, yards_to_endzone, espn_home_wp]
"""
from __future__ import annotations

import numpy as np

from .features import ep_design


def _half(period: int) -> int:
    return 0 if period <= 2 else 1 if period <= 4 else 2


def before_scores(plays: list[list]) -> list[tuple[int, int]]:
    """ESPN play scores are post-snap; the state *at* the snap is the previous play's score."""
    out, hs, as_ = [], 0, 0
    for row in plays:
        out.append((hs, as_))
        hs, as_ = int(row[2]), int(row[3])
    return out


def next_score_targets(plays: list[list]) -> list[float | None]:
    before = before_scores(plays)
    out: list[float | None] = [None] * len(plays)
    nxt: tuple[int, int] | None = None  # (half, home-perspective points) of the first score at or after play i
    for i in range(len(plays) - 1, -1, -1):
        period, _, hs, as_, poss, down, _, ytg, _ = plays[i]
        half = _half(period)
        if nxt and nxt[0] != half:
            nxt = None
        pts = (hs - before[i][0]) - (as_ - before[i][1])
        if pts:
            if abs(pts) == 6:
                pts += 1 if pts > 0 else -1
            nxt = (half, pts)
        if poss and 1 <= down <= 4 and 0 < ytg < 100:
            out[i] = float((nxt[1] if nxt else 0) * poss)
    return out


def fit_expected_points(games: list[list[list]]) -> tuple[list[float], dict]:
    X, y = [], []
    for plays in games:
        for row, target in zip(plays, next_score_targets(plays)):
            if target is None:
                continue
            X.append(ep_design(float(row[7]), int(row[5]), float(row[6])))
            y.append(target)
    A = np.asarray(X)
    b = np.asarray(y)
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ coef
    info = {"n_plays": int(len(b)), "rmse": float(np.sqrt(np.mean(resid ** 2))),
            "ep_own_25_1st10": float(np.dot(coef, ep_design(75, 1, 10))), "ep_opp_10_1st10": float(np.dot(coef, ep_design(10, 1, 10)))}
    return [float(c) for c in coef], info
