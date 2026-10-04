"""Whole-season Monte Carlo for team leagues (spec v3.0 §16).

Generative model (DYNAMIC mode):
    theta_i ~ N(mu_i, var_i)                       one draw of every team's true strength
    theta_i(t + dt) = theta_i(t) + N(0, q dt)      strength drifts between game days
    margin = hfa (1 - neutral) + theta_h - theta_a + N(0, obs_sd^2)
Every simulated game in a rollout shares that rollout's latent state, so results
are correlated exactly as the rating model says they should be: a team that is
secretly better than its posterior mean wins more of *all* its remaining games.

FAST mode holds theta at the posterior mean and draws each game independently
from its marginal win probability (optionally the calibrated board forecast).
The difference between the two modes is reported, not hidden (spec §17.3).

Everything is vectorized over draws with numpy; standings are accumulated with
bincount, so 10,000 full seasons of a 5,000-game college schedule fit in memory.
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from sportsworld.ingest.espn import GameRecord, drop_exhibitions, read_archive, season_start_year
from sportsworld.ingest.leagues import LEAGUES, LeagueSpec
from sportsworld.ingest.ratings import RatingBook, RatingParams, load_params, result_known_time
from sportsworld.schemas import Sport

from .structure import LeagueStructure, load_structure

SIMULATOR_VERSION = "team_season_sim_v1"


def _phi(x: np.ndarray) -> np.ndarray:
    from math import erf
    return 0.5 * (1.0 + np.vectorize(erf)(x / math.sqrt(2.0)))


@dataclass
class SeasonSetup:
    league: str
    spec: LeagueSpec
    season: int  # season start year (archive key)
    espn_season: int
    as_of: datetime
    structure: LeagueStructure | None
    team_ids: list[str]
    names: list[str]
    abbreviations: list[str | None]
    member: np.ndarray  # bool[T] team belongs to the league structure
    conf: np.ndarray  # int[T], -1 for non-members
    div: np.ndarray  # int[T], -1 if no division
    conf_names: list[str]
    div_names: list[str]
    mu: np.ndarray
    var: np.ndarray
    params: RatingParams
    # played regular-season games (point-in-time at as_of)
    p_home: np.ndarray
    p_away: np.ndarray
    p_hs: np.ndarray
    p_as: np.ndarray
    p_ot: np.ndarray
    # remaining regular-season games
    r_home: np.ndarray
    r_away: np.ndarray
    r_neutral: np.ndarray
    r_day: np.ndarray  # days since as_of (float)
    r_event_ids: list[str]
    r_start: list[datetime]
    structure_note: str | None = None
    contingent_events: int = 0
    postseason_started: bool = False
    ot_rate: float = 0.0
    board_probs: np.ndarray | None = None  # calibrated P(home) per remaining game, for FAST mode
    live_probs: dict[int, float] = field(default_factory=dict)  # remaining-game index -> live in-game P(home)

    @property
    def T(self) -> int:
        return len(self.team_ids)

    def index(self) -> dict[str, int]:
        return {t: i for i, t in enumerate(self.team_ids)}

    def state_hash(self) -> str:
        h = hashlib.sha256()
        for arr in (self.mu, self.var, self.p_home, self.p_away, self.p_hs, self.p_as, self.r_home, self.r_away):
            h.update(np.ascontiguousarray(arr).tobytes())
        return h.hexdigest()[:16]


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def active_season(spec: LeagueSpec, games: list[GameRecord], as_of: datetime) -> int:
    """Current season, or the upcoming one once the current season has no regular-season games left (preseason init)."""
    cur = season_start_year(spec, as_of)
    left = any(season_start_year(spec, g.start_time) == cur and g.season_type in (2, 3) and g.start_time >= as_of for g in games)
    upcoming = any(season_start_year(spec, g.start_time) == cur + 1 for g in games)
    return cur + 1 if not left and upcoming else cur


def build_setup(league: str, data_root: Path, as_of: datetime | None = None, *, season: int | None = None,
                params: RatingParams | None = None, games: list[GameRecord] | None = None, book: RatingBook | None = None) -> SeasonSetup:
    """Reconstruct the competition-season world state at `as_of` from archived evidence only."""
    spec = LEAGUES[league]
    as_of = as_of or datetime.now(timezone.utc)
    all_games = games if games is not None else read_archive(data_root, league)
    history = drop_exhibitions(all_games)
    season = season if season is not None else active_season(spec, all_games, as_of)
    params = params or load_params(_repo() / "models" / "artifacts" / "ratings" / f"{league}.json")
    if book is None:
        book = RatingBook(spec, params)
        book.replay([g for g in history if result_known_time(g, spec.sport) <= as_of], until=as_of)
    else:
        params = book.params

    season_games = [g for g in all_games if season_start_year(spec, g.start_time) == season and g.season_type != 1 and not g.cancelled]
    season_games = [g for g in season_games if not any(t.team_id.startswith("-") or t.name == "TBD" for t in (g.home, g.away))]
    espn_season = max((g.season for g in season_games), default=season)
    structure = load_structure(data_root, league, espn_season)
    structure_note = None
    for back in range(1, 3):  # unpublished upcoming-season standings: fall back to latest membership
        if structure is not None and structure.teams:
            break
        structure = load_structure(data_root, league, espn_season - back)
        structure_note = f"conference membership from ESPN season {espn_season - back} (current not yet published)"

    regular = [g for g in season_games if g.season_type == 2]
    post = [g for g in all_games if season_start_year(spec, g.start_time) == season and g.season_type == 3]
    postseason_started = any(result_known_time(g, spec.sport) <= as_of for g in post if g.completed)
    contingent = sum(1 for g in post if any(t.team_id.startswith("-") or t.name == "TBD" for t in (g.home, g.away)))

    # Team universe: structure members first, then any other opponent that appears.
    team_ids: list[str] = []
    names: dict[str, str] = {}
    abbr: dict[str, str | None] = {}
    if structure:
        for t in structure.teams:
            team_ids.append(t.team_id)
            names[t.team_id] = t.name
            abbr[t.team_id] = t.abbreviation
    for g in regular:
        for t in (g.home, g.away):
            if t.team_id not in names:
                team_ids.append(t.team_id)
                names[t.team_id] = t.name
                abbr[t.team_id] = t.abbreviation
    idx = {t: i for i, t in enumerate(team_ids)}
    T = len(team_ids)
    conf_names = structure.conferences() if structure else []
    div_names = structure.divisions() if structure else []
    conf = np.full(T, -1)
    div = np.full(T, -1)
    member = np.zeros(T, dtype=bool)
    if structure:
        for t in structure.teams:
            i = idx[t.team_id]
            member[i] = True
            conf[i] = conf_names.index(t.conference)
            if t.division:
                div[i] = div_names.index(t.division)

    mu = np.zeros(T)
    var = np.zeros(T)
    for t, i in idx.items():
        st = book.teams.get(t)
        if st is None:
            mu[i] = params.newcomer_mean if len(book.seasons_seen) > 1 else 0.0
            var[i] = params.init_var
        else:
            days = 0.0 if st.last_game is None else max(0.0, (as_of - st.last_game).total_seconds() / 86400)
            mean, v = st.mean, min(params.init_var, st.var + params.q * days)
            if st.season != espn_season and st.season < espn_season:  # preseason: apply rollover
                mean, v = mean * params.rho, min(params.init_var, v + params.season_var)
            mu[i], var[i] = mean, v

    played = [g for g in regular if g.completed and (result_known_time(g, spec.sport) <= as_of or g.game_id in book.applied)]
    played_ids = {g.game_id for g in played}
    remaining = sorted([g for g in regular if g.game_id not in played_ids], key=lambda g: (g.start_time, g.game_id))

    def arr(xs, dtype=int):
        return np.asarray(xs, dtype=dtype)

    ot_games = [g for g in history if g.completed and g.season_type == 2 and result_known_time(g, spec.sport) <= as_of]  # point-in-time
    ot_rate = float(np.mean([g.period > spec.periods for g in ot_games])) if ot_games else 0.0
    return SeasonSetup(
        league=league, spec=spec, season=season, espn_season=espn_season, as_of=as_of, structure=structure,
        team_ids=team_ids, names=[names[t] for t in team_ids], abbreviations=[abbr[t] for t in team_ids],
        member=member, conf=conf, div=div, conf_names=conf_names, div_names=div_names, mu=mu, var=var, params=params,
        p_home=arr([idx[g.home.team_id] for g in played]), p_away=arr([idx[g.away.team_id] for g in played]),
        p_hs=arr([g.home.score for g in played], float), p_as=arr([g.away.score for g in played], float),
        p_ot=arr([g.period > spec.periods for g in played], bool),
        r_home=arr([idx[g.home.team_id] for g in remaining]), r_away=arr([idx[g.away.team_id] for g in remaining]),
        r_neutral=arr([g.neutral_site for g in remaining], bool),
        r_day=arr([(g.start_time - as_of).total_seconds() / 86400 for g in remaining], float),
        r_event_ids=[g.event_id for g in remaining], r_start=[g.start_time for g in remaining],
        contingent_events=contingent, postseason_started=postseason_started, ot_rate=ot_rate, structure_note=structure_note,
    )


# ---------------------------------------------------------------------------
# Scenario overrides (counterfactuals never touch the canonical setup)
# ---------------------------------------------------------------------------
@dataclass
class SeasonScenario:
    """Typed season-level counterfactual.

    rating_shifts: (team_id, delta_points, start, end): e.g. a QB absence for a window.
    forced: event_id -> "home" | "away": hypothetical results.
    """
    rating_shifts: list[tuple[str, float, datetime | None, datetime | None]] = field(default_factory=list)
    forced: dict[str, str] = field(default_factory=dict)
    label: str | None = None

    def is_empty(self) -> bool:
        return not self.rating_shifts and not self.forced


def _shift_arrays(setup: SeasonSetup, scen: SeasonScenario | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per remaining game: rating delta for home and away; per team: delta applying to postseason."""
    G, T = len(setup.r_home), setup.T
    dh, da, post = np.zeros(G), np.zeros(G), np.zeros(T)
    if not scen:
        return dh, da, post
    idx = setup.index()
    for team_id, delta, start, end in scen.rating_shifts:
        if team_id not in idx:
            continue
        i = idx[team_id]
        for g in range(G):
            t = setup.r_start[g]
            if (start is None or t >= start) and (end is None or t <= end):
                if setup.r_home[g] == i:
                    dh[g] += delta
                if setup.r_away[g] == i:
                    da[g] += delta
        last_regular = max(setup.r_start) if setup.r_start else None
        if end is None or (last_regular is not None and end > last_regular):  # window extends into the postseason
            post[i] += delta
    return dh, da, post


# ---------------------------------------------------------------------------
# Regular season simulation
# ---------------------------------------------------------------------------
@dataclass
class RegularSeasonDraws:
    theta_end: np.ndarray  # [D, T]
    wins: np.ndarray  # [D, T]
    losses: np.ndarray
    ties: np.ndarray
    ot_losses: np.ndarray
    conf_wins: np.ndarray
    conf_games: np.ndarray
    div_wins: np.ndarray
    div_games: np.ndarray
    points_for: np.ndarray
    points_against: np.ndarray
    games: np.ndarray
    home_win: np.ndarray  # [D, G] remaining games
    post_shift: np.ndarray  # [T]


def _accumulate(D: int, T: int, idx: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Sum weights[D, G] into [D, T] by team index idx[G]."""
    flat = (np.arange(D)[:, None] * T + idx[None, :]).ravel()
    return np.bincount(flat, weights=weights.ravel().astype(float), minlength=D * T).reshape(D, T)


def simulate_regular(setup: SeasonSetup, draws: int, rng: np.random.Generator, mode: str = "dynamic",
                     scenario: SeasonScenario | None = None) -> RegularSeasonDraws:
    D, T, G = draws, setup.T, len(setup.r_home)
    p = setup.params
    hfa, sd = p.hfa, p.obs_sd
    dh, da, post_shift = _shift_arrays(setup, scenario)
    if mode == "dynamic":
        theta = setup.mu[None, :] + np.sqrt(setup.var)[None, :] * rng.standard_normal((D, T))
    else:
        theta = np.repeat(setup.mu[None, :], D, axis=0)
    margin = np.zeros((D, G))
    if G:
        day_keys = np.floor(np.maximum(setup.r_day, 0.0)).astype(int)
        last_day = 0
        for day in np.unique(day_keys):
            sel = np.nonzero(day_keys == day)[0]
            if mode == "dynamic" and p.q > 0 and day > last_day:
                theta = theta + math.sqrt(p.q * (day - last_day)) * rng.standard_normal((D, T))
            last_day = day
            h, a = setup.r_home[sel], setup.r_away[sel]
            mean = hfa * (~setup.r_neutral[sel]) + theta[:, h] + dh[sel] - theta[:, a] - da[sel]
            if mode == "fast" and setup.board_probs is not None:
                pr = np.clip(setup.board_probs[sel], 1e-4, 1 - 1e-4)
                u = rng.random((D, len(sel)))
                # margin sign from calibrated marginals; magnitude from the Gaussian model
                mag = np.abs(mean + sd * rng.standard_normal((D, len(sel))))
                margin[:, sel] = np.where(u < pr[None, :], 1.0, -1.0) * np.maximum(mag, 0.5)
            else:
                margin[:, sel] = mean + sd * rng.standard_normal((D, len(sel)))
        # Games in progress: sample the winner from the live in-game forecast (both modes), so a
        # late lead moves season/title odds before the final whistle.
        for g, pl in setup.live_probs.items():
            u = rng.random(D)
            margin[:, g] = np.where(u < pl, 1.0, -1.0) * np.maximum(np.abs(margin[:, g]), 0.5)
        if scenario and scenario.forced:
            pos = {e: i for i, e in enumerate(setup.r_event_ids)}
            for eid, side in scenario.forced.items():
                if eid in pos:
                    g = pos[eid]
                    margin[:, g] = np.abs(margin[:, g]) * (1 if side == "home" else -1) + (1e-3 if side == "home" else -1e-3)
    home_win = margin > 0
    ot = np.zeros_like(home_win)
    if setup.spec.sport == Sport.HOCKEY and setup.ot_rate > 0 and G:
        tau = sd * _inv_phi(0.5 + setup.ot_rate / 2.0)
        ot = np.abs(margin) < tau

    def acc(idx_arr, w):
        return _accumulate(D, T, idx_arr, w) if G else np.zeros((D, T))

    hw = home_win.astype(float)
    aw = 1.0 - hw
    wins = acc(setup.r_home, hw) + acc(setup.r_away, aw)
    losses = acc(setup.r_home, aw * (1 - ot)) + acc(setup.r_away, hw * (1 - ot))
    ot_losses = acc(setup.r_home, aw * ot) + acc(setup.r_away, hw * ot)
    pts_h = np.round(np.maximum(margin, 0)) if G else margin
    games = acc(setup.r_home, np.ones((D, G))) + acc(setup.r_away, np.ones((D, G)))
    pf = acc(setup.r_home, margin) - acc(setup.r_away, margin)  # store net differential in points_for
    same_conf = (setup.conf[setup.r_home] == setup.conf[setup.r_away]) & (setup.conf[setup.r_home] >= 0)
    same_div = (setup.div[setup.r_home] == setup.div[setup.r_away]) & (setup.div[setup.r_home] >= 0)
    cmask = same_conf[None, :].astype(float)
    dmask = same_div[None, :].astype(float)
    conf_w = acc(setup.r_home, hw * cmask) + acc(setup.r_away, aw * cmask)
    conf_g = acc(setup.r_home, np.ones((D, G)) * cmask) + acc(setup.r_away, np.ones((D, G)) * cmask)
    div_w = acc(setup.r_home, hw * dmask) + acc(setup.r_away, aw * dmask)
    div_g = acc(setup.r_home, np.ones((D, G)) * dmask) + acc(setup.r_away, np.ones((D, G)) * dmask)
    del pts_h

    # add already-played results (identical in every draw)
    base = _played_tables(setup)
    return RegularSeasonDraws(
        theta_end=theta, wins=wins + base["wins"], losses=losses + base["losses"], ties=np.zeros((D, T)) + base["ties"],
        ot_losses=ot_losses + base["otl"], conf_wins=conf_w + base["conf_w"], conf_games=conf_g + base["conf_g"],
        div_wins=div_w + base["div_w"], div_games=div_g + base["div_g"], points_for=pf + base["pd"],
        points_against=np.zeros((D, T)), games=games + base["games"], home_win=home_win, post_shift=post_shift,
    )


def _inv_phi(p: float) -> float:
    # Acklam-free: bisection on erf is plenty for a scalar
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _played_tables(setup: SeasonSetup) -> dict[str, np.ndarray]:
    T = setup.T
    out = {k: np.zeros(T) for k in ("wins", "losses", "ties", "otl", "conf_w", "conf_g", "div_w", "div_g", "pd", "games")}
    for h, a, hs, as_, ot in zip(setup.p_home, setup.p_away, setup.p_hs, setup.p_as, setup.p_ot):
        same_conf = setup.conf[h] == setup.conf[a] and setup.conf[h] >= 0
        same_div = setup.div[h] == setup.div[a] and setup.div[h] >= 0
        for t, o, s_t, s_o in ((h, a, hs, as_), (a, h, as_, hs)):
            out["games"][t] += 1
            out["pd"][t] += s_t - s_o
            if s_t > s_o:
                w, l, tie = 1, 0, 0
            elif s_t < s_o:
                w, l, tie = 0, 1, 0
            else:
                w, l, tie = 0, 0, 1
            out["wins"][t] += w + 0.5 * tie * 0  # ties tracked separately
            if l and ot and setup.spec.sport == Sport.HOCKEY:
                out["otl"][t] += 1
            else:
                out["losses"][t] += l
            out["ties"][t] += tie
            if same_conf:
                out["conf_g"][t] += 1
                out["conf_w"][t] += w + 0.5 * tie
            if same_div:
                out["div_g"][t] += 1
                out["div_w"][t] += w + 0.5 * tie
    return out


def standings_key(setup: SeasonSetup, r: RegularSeasonDraws, rng: np.random.Generator) -> np.ndarray:
    """Composite lexicographic sort key per draw/team (larger is better).

    primary: win% (ties = half a win) or, in hockey, standings points per game
    then division win%, conference win%, scaled point differential, random coin flip.
    This is the documented approximation of each league's tiebreak chain; the
    deterministic official chains (head-to-head, common games, SoV/SoS) are not
    fully reproduced.
    """
    g = np.maximum(r.games, 1)
    if setup.spec.sport == Sport.HOCKEY:
        primary = (2 * r.wins + r.ot_losses) / (2 * g)
    else:
        primary = (r.wins + 0.5 * r.ties) / g
    divp = r.div_wins / np.maximum(r.div_games, 1)
    confp = r.conf_wins / np.maximum(r.conf_games, 1)
    pd = (r.points_for - r.points_for.min()) / max(1e-9, float(np.ptp(r.points_for)) or 1.0)
    return primary + 1e-3 * divp + 1e-6 * confp + 1e-9 * pd + 1e-12 * rng.random(primary.shape)


def play_games(theta: np.ndarray, home: np.ndarray, away: np.ndarray, setup: SeasonSetup, rng: np.random.Generator,
               neutral: bool | np.ndarray = False, shift: np.ndarray | None = None) -> np.ndarray:
    """One game per draw between home[d] and away[d]; returns the winner index [D]."""
    D = theta.shape[0]
    rows = np.arange(D)
    th = theta[rows, home] - theta[rows, away]
    if shift is not None:
        th = th + shift[home] - shift[away]
    hfa = setup.params.hfa * (1.0 - np.asarray(neutral, dtype=float))
    m = hfa + th + setup.params.obs_sd * rng.standard_normal(D)
    return np.where(m > 0, home, away)


def play_series(theta: np.ndarray, high: np.ndarray, low: np.ndarray, setup: SeasonSetup, rng: np.random.Generator,
                best_of: int = 7, shift: np.ndarray | None = None) -> np.ndarray:
    """Best-of-N with 2-2-1-1-1 home pattern for the higher seed; winner index [D]."""
    pattern = [1, 1, 0, 0, 1, 0, 1][:best_of] if best_of == 7 else [1, 0, 1][:best_of]
    wins_high = np.zeros(theta.shape[0])
    for home_is_high in pattern:
        h, a = (high, low) if home_is_high else (low, high)
        w = play_games(theta, h, a, setup, rng, shift=shift)
        wins_high += (w == high)
    return np.where(wins_high > best_of // 2, high, low)


# ---------------------------------------------------------------------------
# Run + aggregate
# ---------------------------------------------------------------------------
def run_season(setup: SeasonSetup, *, draws: int = 10_000, seed: int = 7, mode: str = "dynamic",
               scenario: SeasonScenario | None = None, postseason: Callable | None = None) -> dict[str, Any]:
    from .rules import POSTSEASON

    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    reg = simulate_regular(setup, draws, rng, mode, scenario)
    key = standings_key(setup, reg, rng)
    post_fn = postseason or POSTSEASON.get(setup.league)
    post: dict[str, np.ndarray] = post_fn(setup, reg, key, rng) if post_fn and not setup.postseason_started else {}
    elapsed = time.perf_counter() - t0
    return summarize(setup, reg, post, draws=draws, seed=seed, mode=mode, elapsed=elapsed, scenario=scenario)


def summarize(setup: SeasonSetup, reg: RegularSeasonDraws, post: dict[str, np.ndarray], *, draws: int, seed: int, mode: str,
              elapsed: float, scenario: SeasonScenario | None) -> dict[str, Any]:
    D = draws
    se = lambda p: float(math.sqrt(max(p * (1 - p), 0.0) / D))  # noqa: E731
    teams = []
    total_games = reg.games[0]
    path_key = next((k for k in ("playoffs", "tournament") if k in post and post[k].ndim == 2 and post[k].shape[1] == setup.T), None)
    for i, tid in enumerate(setup.team_ids):
        if not setup.member[i] and setup.structure is not None:
            continue
        w = reg.wins[:, i]
        row: dict[str, Any] = {
            "team_id": tid, "name": setup.names[i], "abbreviation": setup.abbreviations[i],
            "conference": setup.conf_names[setup.conf[i]] if setup.conf[i] >= 0 else None,
            "division": setup.div_names[setup.div[i]] if setup.div[i] >= 0 else None,
            "rating": round(float(setup.mu[i]), 2), "rating_sd": round(float(math.sqrt(setup.var[i])), 2),
            "games": int(total_games[i]),
            "expected_wins": round(float(w.mean()), 2), "wins_sd": round(float(w.std()), 2),
            "wins_p05": float(np.quantile(w, 0.05)), "wins_p95": float(np.quantile(w, 0.95)),
            "win_hist": np.bincount(np.round(w).astype(int), minlength=int(total_games[i]) + 1).tolist(),
        }
        if setup.spec.sport == Sport.HOCKEY:
            pts = 2 * reg.wins[:, i] + reg.ot_losses[:, i]
            row.update({"expected_points": round(float(pts.mean()), 1), "points_p05": float(np.quantile(pts, .05)), "points_p95": float(np.quantile(pts, .95))})
        for k, arr in post.items():
            if arr.ndim == 2 and arr.shape[1] == setup.T:  # boolean milestone per team
                p = float(arr[:, i].mean())
                row[k] = round(p, 4)
                row[f"{k}_se"] = round(se(p), 4)
            elif arr.ndim == 2 and arr.shape[0] == D and k == "seed":
                pass
        if path_key is not None:  # conditional season paths: milestone and title odds by final win total
            m, c = post[path_key][:, i], post["champion"][:, i] if "champion" in post else None
            paths = []
            for k in np.unique(np.round(w).astype(int)):
                sel = np.round(w).astype(int) == k
                pk = float(sel.mean())
                if pk >= 0.005:
                    paths.append({"wins": int(k), "p": round(pk, 4), path_key: round(float(m[sel].mean()), 4),
                                  "champion": round(float(c[sel].mean()), 4) if c is not None else None})
            row["season_paths"] = {"milestone": path_key, "by_wins": paths}
        if "seed" in post:
            s = post["seed"][:, i]
            counts = np.bincount(s.astype(int), minlength=int(s.max()) + 2)[1:] / D
            row["seed_dist"] = [round(float(x), 4) for x in counts]
        teams.append(row)
    order_key = "champion" if any("champion" in t for t in teams) else "expected_wins"
    teams.sort(key=lambda t: (t.get(order_key, 0), t["expected_wins"]), reverse=True)
    # Ripple: for every game, how its result moves every team's milestone odds, P(m | home win) - P(m | home loss).
    # One matrix product over the simulated seasons covers all games and teams at once.
    ripple = None
    if path_key is not None and len(setup.r_event_ids):
        M = post[path_key].astype(np.float32)                      # D x T
        HW = reg.home_win.astype(np.float32)                       # D x G
        nw = HW.sum(axis=0)                                        # G
        S = HW.T @ M                                               # G x T: milestone count in seasons the home side won
        tot = M.sum(axis=0)                                        # T
        with np.errstate(divide="ignore", invalid="ignore"):
            p1, p0 = S / nw[:, None], (tot[None, :] - S) / (D - nw)[:, None]
            ripple = p1 - p0
            # Monte Carlo standard error of that difference; only effects beyond 3 SE are reported
            ripple_se = np.sqrt(p1 * (1 - p1) / nw[:, None] + p0 * (1 - p0) / (D - nw)[:, None])
    games = []
    for g, e in enumerate(setup.r_event_ids):
        hw = reg.home_win[:, g].astype(bool)
        row_g: dict[str, Any] = {"event_id": e, "p_home": round(float(hw.mean()), 4)}
        if path_key is not None and 0 < hw.sum() < D:  # leverage: milestone odds if this game is won minus if lost
            m = post[path_key]
            h, a = int(setup.r_home[g]), int(setup.r_away[g])
            row_g["leverage_home"] = round(float(m[hw, h].mean() - m[~hw, h].mean()), 4)
            row_g["leverage_away"] = round(float(m[~hw, a].mean() - m[hw, a].mean()), 4)
            row_g["leverage_milestone"] = path_key
            if ripple is not None:
                d = ripple[g].copy()
                d[[h, a]] = 0
                d[~np.isfinite(d)] = 0
                se_g = np.nan_to_num(ripple_se[g], nan=1.0)
                real = (np.abs(d) >= 0.01) & (np.abs(d) >= 3 * se_g)
                top = [j for j in np.argsort(-np.abs(d * real))[:3] if real[j]]
                # delta = change in that team's milestone odds when the HOME side wins (vs loses)
                row_g["ripple"] = [{"team_id": setup.team_ids[j], "delta_if_home_wins": round(float(d[j]), 4)} for j in top]
        games.append(row_g)
    diagnostics: dict[str, Any] = {"runtime_s": round(elapsed, 3), "remaining_games": len(setup.r_event_ids), "played_games": int(len(setup.p_home)),
                                   "contingent_postseason_events": setup.contingent_events, "postseason_started": setup.postseason_started,
                                   "structure_note": setup.structure_note, "rules_version": __import__("sportsworld.season.rules", fromlist=["RULES_VERSIONS"]).RULES_VERSIONS.get(setup.league)}
    if "champion" in post:
        per_draw = post["champion"].sum(axis=1)
        diagnostics["champions_per_draw_min_max"] = [int(per_draw.min()), int(per_draw.max())]
    return {
        "league": setup.league, "season": setup.season, "espn_season": setup.espn_season, "as_of": setup.as_of.isoformat(),
        "mode": mode, "draws": D, "seed": seed, "simulator_version": SIMULATOR_VERSION, "rating_params": setup.params.to_dict(),
        "state_hash": setup.state_hash(), "scenario": scenario.label if scenario else None, "teams": teams, "games": games,
        "diagnostics": diagnostics,
    }
