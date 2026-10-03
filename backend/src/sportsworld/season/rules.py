"""Versioned competition rules: seeding, contingent postseason generation and
bracket simulation (spec v3.0 §7).  Each function receives the regular-season
draws and a per-draw standings key, instantiates the postseason *inside each
rollout* from simulated standings, and returns boolean milestone arrays [D, T]
plus an integer seed array [D, T] (0 = did not qualify).

Rules versions (documented approximations are flagged APPROX):
  nfl_rules_2026_v1   7 teams/conference: 4 division winners seeded 1-4, 3 wild cards;
                      #1 bye; WC 2v7 3v6 4v5; reseeded divisional round; conference final;
                      neutral-site Super Bowl. APPROX tiebreak chain (see engine.standings_key).
  nba_rules_2026_v1   1-6 direct; play-in 7v8 / 9v10 / loser78 v winner910; best-of-7 rounds,
                      2-2-1-1-1 home court for the better record.
  nhl_rules_2026_v1   top 3 per division + 2 wild cards per conference; div winners vs wild cards;
                      best-of-7; points = 2W + OTL.
  cfb_rules_2026_v1   conference title game between the top two conference records (APPROX: one
                      table per conference); 12-team CFP = 5 highest-ranked conference champions +
                      7 at-large, seeded 1-12 by ranking (2025 straight-seeding format);
                      APPROX ranking = learned-free composite of record and rating.
  ncaa_bb_rules_v1    APPROX: 64-team field = best-record champion of each conference + at-large
                      by composite ranking; 4 regions S-curve; neutral single elimination.
"""
from __future__ import annotations

import numpy as np

from .engine import RegularSeasonDraws, SeasonSetup, play_games, play_series

RULES_VERSIONS = {
    "nfl": "nfl_rules_2026_v1", "nba": "nba_rules_2026_v1", "nhl": "nhl_rules_2026_v1",
    "college-football": "cfb_rules_2026_v1", "mens-college-basketball": "ncaa_bb_rules_v1",
    "womens-college-basketball": "ncaa_bb_rules_v1", "wnba": "wnba_regular_season_only_v1",
    "mens-college-hockey": "college_hockey_regular_season_only_v1",
}


def _mark(D: int, T: int, teams: np.ndarray) -> np.ndarray:
    out = np.zeros((D, T), dtype=bool)
    out[np.arange(D), teams] = True
    return out


def _ranked(key: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Team indices sorted best-first per draw, restricted to mask[T] (others pushed last)."""
    k = np.where(mask[None, :], key, -np.inf)
    return np.argsort(-k, axis=1)


def _better(key: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    rows = np.arange(key.shape[0])
    return key[rows, a] >= key[rows, b]


# ---------------------------------------------------------------------------
# NFL
# ---------------------------------------------------------------------------
def nfl(setup: SeasonSetup, reg: RegularSeasonDraws, key: np.ndarray, rng) -> dict[str, np.ndarray]:
    D, T = key.shape
    rows = np.arange(D)
    theta, shift = reg.theta_end, reg.post_shift
    seed = np.zeros((D, T), dtype=int)
    playoff = np.zeros((D, T), dtype=bool)
    div_title = np.zeros((D, T), dtype=bool)
    conf_title = np.zeros((D, T), dtype=bool)
    finalists = []
    for c in range(len(setup.conf_names)):
        cmask = setup.conf == c
        divs = sorted({int(d) for d in setup.div[cmask] if d >= 0})
        winners = np.stack([_ranked(key, setup.div == d)[:, 0] for d in divs], axis=1)  # [D, 4]
        for j in range(winners.shape[1]):
            div_title[rows, winners[:, j]] = True
        wk = key[rows[:, None], winners]
        winners = np.take_along_axis(winners, np.argsort(-wk, axis=1), axis=1)
        rest_key = np.where(cmask[None, :], key, -np.inf)
        rest_key[rows[:, None], winners] = -np.inf
        wild = np.argsort(-rest_key, axis=1)[:, :3]
        seeds = np.concatenate([winners, wild], axis=1)  # [D, 7]
        for s in range(7):
            seed[rows, seeds[:, s]] = s + 1
            playoff[rows, seeds[:, s]] = True
        # Wild card round: 2v7, 3v6, 4v5 (higher seed hosts)
        w27 = play_games(theta, seeds[:, 1], seeds[:, 6], setup, rng, shift=shift)
        w36 = play_games(theta, seeds[:, 2], seeds[:, 5], setup, rng, shift=shift)
        w45 = play_games(theta, seeds[:, 3], seeds[:, 4], setup, rng, shift=shift)
        alive = np.stack([seeds[:, 0], w27, w36, w45], axis=1)
        alive_seed = seed[rows[:, None], alive]
        order = np.argsort(alive_seed, axis=1)
        alive = np.take_along_axis(alive, order, axis=1)  # reseed: best plays worst remaining
        d1 = play_games(theta, alive[:, 0], alive[:, 3], setup, rng, shift=shift)
        d2 = play_games(theta, alive[:, 1], alive[:, 2], setup, rng, shift=shift)
        s1, s2 = seed[rows, d1], seed[rows, d2]
        home = np.where(s1 <= s2, d1, d2)
        away = np.where(s1 <= s2, d2, d1)
        champ = play_games(theta, home, away, setup, rng, shift=shift)
        conf_title[rows, champ] = True
        finalists.append(champ)
    sb = play_games(theta, finalists[0], finalists[1], setup, rng, neutral=True, shift=shift)
    bye = seed == 1
    return {"playoffs": playoff, "division_title": div_title, "first_round_bye": bye, "conference_title": conf_title,
            "champion": _mark(D, T, sb), "seed": seed}


# ---------------------------------------------------------------------------
# NBA
# ---------------------------------------------------------------------------
def nba(setup: SeasonSetup, reg: RegularSeasonDraws, key: np.ndarray, rng) -> dict[str, np.ndarray]:
    D, T = key.shape
    rows = np.arange(D)
    theta, shift = reg.theta_end, reg.post_shift
    seed = np.zeros((D, T), dtype=int)
    playoff = np.zeros((D, T), dtype=bool)
    play_in = np.zeros((D, T), dtype=bool)
    conf_title = np.zeros((D, T), dtype=bool)
    finals = []
    for c in range(len(setup.conf_names)):
        ranked = _ranked(key, setup.conf == c)[:, :10]
        for s in range(6):
            seed[rows, ranked[:, s]] = s + 1
        for s in range(6, 10):
            play_in[rows, ranked[:, s]] = True
        w78 = play_games(theta, ranked[:, 6], ranked[:, 7], setup, rng, shift=shift)
        l78 = np.where(w78 == ranked[:, 6], ranked[:, 7], ranked[:, 6])
        w910 = play_games(theta, ranked[:, 8], ranked[:, 9], setup, rng, shift=shift)
        eighth = play_games(theta, l78, w910, setup, rng, shift=shift)
        seed[rows, w78] = 7
        seed[rows, eighth] = 8
        bracket = [ranked[:, 0], eighth, ranked[:, 3], ranked[:, 4], ranked[:, 2], ranked[:, 5], ranked[:, 1], w78]
        for t in bracket:
            playoff[rows, t] = True
        while len(bracket) > 1:
            nxt = []
            for i in range(0, len(bracket), 2):
                a, b = bracket[i], bracket[i + 1]
                hi = np.where(_better(key, a, b), a, b)
                lo = np.where(_better(key, a, b), b, a)
                nxt.append(play_series(theta, hi, lo, setup, rng, shift=shift))
            bracket = nxt
        conf_title[rows, bracket[0]] = True
        finals.append(bracket[0])
    hi = np.where(_better(key, finals[0], finals[1]), finals[0], finals[1])
    lo = np.where(_better(key, finals[0], finals[1]), finals[1], finals[0])
    champ = play_series(theta, hi, lo, setup, rng, shift=shift)
    return {"playoffs": playoff, "play_in": play_in, "conference_title": conf_title, "champion": _mark(D, T, champ), "seed": seed}


# ---------------------------------------------------------------------------
# NHL
# ---------------------------------------------------------------------------
def nhl(setup: SeasonSetup, reg: RegularSeasonDraws, key: np.ndarray, rng) -> dict[str, np.ndarray]:
    D, T = key.shape
    rows = np.arange(D)
    theta, shift = reg.theta_end, reg.post_shift
    seed = np.zeros((D, T), dtype=int)
    playoff = np.zeros((D, T), dtype=bool)
    div_title = np.zeros((D, T), dtype=bool)
    conf_title = np.zeros((D, T), dtype=bool)
    finals = []
    for c in range(len(setup.conf_names)):
        cmask = setup.conf == c
        divs = sorted({int(d) for d in setup.div[cmask] if d >= 0})
        tops = [_ranked(key, setup.div == d)[:, :3] for d in divs]  # 2 x [D, 3]
        rest = np.where(cmask[None, :], key, -np.inf)
        for t in tops:
            rest[rows[:, None], t] = -np.inf
            div_title[rows, t[:, 0]] = True
        wc = np.argsort(-rest, axis=1)[:, :2]
        # best division winner plays WC2, the other WC1
        a_better = _better(key, tops[0][:, 0], tops[1][:, 0])
        opp0 = np.where(a_better, wc[:, 1], wc[:, 0])
        opp1 = np.where(a_better, wc[:, 0], wc[:, 1])
        sides = []
        for t, opp in ((tops[0], opp0), (tops[1], opp1)):
            for s, team in enumerate([t[:, 0], t[:, 1], t[:, 2], opp]):
                playoff[rows, team] = True
            seed[rows, t[:, 0]] = 1
            seed[rows, t[:, 1]] = 2
            seed[rows, t[:, 2]] = 3
            r1a = play_series(theta, t[:, 0], opp, setup, rng, shift=shift)
            r1b = play_series(theta, t[:, 1], t[:, 2], setup, rng, shift=shift)
            hi = np.where(_better(key, r1a, r1b), r1a, r1b)
            lo = np.where(_better(key, r1a, r1b), r1b, r1a)
            sides.append(play_series(theta, hi, lo, setup, rng, shift=shift))
        seed[rows, wc[:, 0]] = 4
        seed[rows, wc[:, 1]] = 5
        hi = np.where(_better(key, sides[0], sides[1]), sides[0], sides[1])
        lo = np.where(_better(key, sides[0], sides[1]), sides[1], sides[0])
        cf = play_series(theta, hi, lo, setup, rng, shift=shift)
        conf_title[rows, cf] = True
        finals.append(cf)
    hi = np.where(_better(key, finals[0], finals[1]), finals[0], finals[1])
    lo = np.where(_better(key, finals[0], finals[1]), finals[1], finals[0])
    champ = play_series(theta, hi, lo, setup, rng, shift=shift)
    return {"playoffs": playoff, "division_title": div_title, "conference_title": conf_title, "champion": _mark(D, T, champ), "seed": seed}


# ---------------------------------------------------------------------------
# College football
# ---------------------------------------------------------------------------
def _cfb_ranking(setup: SeasonSetup, reg: RegularSeasonDraws, champs: np.ndarray) -> np.ndarray:
    """APPROX committee proxy: overall win%, simulated end-of-season rating, conference title."""
    wp = reg.wins / np.maximum(reg.games, 1)
    rating = reg.theta_end / setup.spec.margin_sd
    return wp + 0.35 * rating + 0.04 * champs


def college_football(setup: SeasonSetup, reg: RegularSeasonDraws, key: np.ndarray, rng) -> dict[str, np.ndarray]:
    D, T = key.shape
    rows = np.arange(D)
    theta, shift = reg.theta_end, reg.post_shift
    conf_wp = reg.conf_wins / np.maximum(reg.conf_games, 1)
    ckey = conf_wp + 1e-3 * (reg.wins / np.maximum(reg.games, 1)) + 1e-6 * rng.random((D, T))
    champs = np.zeros((D, T), dtype=bool)
    title_game = np.zeros((D, T), dtype=bool)
    for c, name in enumerate(setup.conf_names):
        cmask = setup.conf == c
        if "independent" in name.lower() or cmask.sum() < 4:
            continue
        top2 = _ranked(ckey, cmask)[:, :2]
        title_game[rows, top2[:, 0]] = True
        title_game[rows, top2[:, 1]] = True
        w = play_games(theta, top2[:, 0], top2[:, 1], setup, rng, neutral=True, shift=shift)
        champs[rows, w] = True
    rank = _cfb_ranking(setup, reg, champs)
    rank = np.where(setup.member[None, :], rank, -np.inf)
    champ_rank = np.where(champs, rank, -np.inf)
    auto = np.argsort(-champ_rank, axis=1)[:, :5]
    rest = rank.copy()
    rest[rows[:, None], auto] = -np.inf
    at_large = np.argsort(-rest, axis=1)[:, :7]
    field = np.concatenate([auto, at_large], axis=1)
    fr = rank[rows[:, None], field]
    field = np.take_along_axis(field, np.argsort(-fr, axis=1), axis=1)  # seeds 1..12
    seed = np.zeros((D, T), dtype=int)
    for s in range(12):
        seed[rows, field[:, s]] = s + 1
    cfp = seed > 0
    r1 = {s: play_games(theta, field[:, s - 1], field[:, 16 - s], setup, rng, shift=shift) for s in (5, 6, 7, 8)}  # 5v12 ... 8v9
    qf = [play_games(theta, field[:, 0], r1[8], setup, rng, neutral=True, shift=shift),
          play_games(theta, field[:, 3], r1[5], setup, rng, neutral=True, shift=shift),
          play_games(theta, field[:, 1], r1[7], setup, rng, neutral=True, shift=shift),
          play_games(theta, field[:, 2], r1[6], setup, rng, neutral=True, shift=shift)]
    sf1 = play_games(theta, qf[0], qf[1], setup, rng, neutral=True, shift=shift)
    sf2 = play_games(theta, qf[2], qf[3], setup, rng, neutral=True, shift=shift)
    champ = play_games(theta, sf1, sf2, setup, rng, neutral=True, shift=shift)
    return {"conference_title_game": title_game, "conference_champion": champs, "playoffs": cfp,
            "first_round_bye": (seed >= 1) & (seed <= 4), "semifinal": _mark(D, T, sf1) | _mark(D, T, sf2),
            "champion": _mark(D, T, champ), "seed": seed}


# ---------------------------------------------------------------------------
# NCAA basketball tournament (APPROX selection)
# ---------------------------------------------------------------------------
def ncaa_basketball(setup: SeasonSetup, reg: RegularSeasonDraws, key: np.ndarray, rng) -> dict[str, np.ndarray]:
    D, T = key.shape
    rows = np.arange(D)
    theta, shift = reg.theta_end, reg.post_shift
    conf_wp = reg.conf_wins / np.maximum(reg.conf_games, 1)
    ckey = conf_wp + 1e-3 * (reg.wins / np.maximum(reg.games, 1)) + 1e-6 * rng.random((D, T))
    auto_list = []
    for c in range(len(setup.conf_names)):
        cmask = setup.conf == c
        if cmask.sum() < 4:
            continue
        auto_list.append(_ranked(ckey, cmask)[:, 0])
    auto = np.stack(auto_list, axis=1)
    rank = (reg.wins / np.maximum(reg.games, 1)) + 0.45 * reg.theta_end / setup.spec.margin_sd
    rank = np.where(setup.member[None, :], rank, -np.inf)
    rest = rank.copy()
    rest[rows[:, None], auto] = -np.inf
    n_at_large = 64 - auto.shape[1]
    field = np.concatenate([auto, np.argsort(-rest, axis=1)[:, :n_at_large]], axis=1)
    fr = rank[rows[:, None], field]
    field = np.take_along_axis(field, np.argsort(-fr, axis=1), axis=1)  # overall 1..64
    seed = np.zeros((D, T), dtype=int)
    line = np.arange(64) // 4 + 1
    for k in range(64):
        seed[rows, field[:, k]] = line[k]
    order = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]
    regions = []
    for r in range(4):
        snake = [field[:, (s - 1) * 4 + (r if (s % 2) else 3 - r)] for s in order]
        regions.append(snake)
    sweet16 = np.zeros((D, T), dtype=bool)
    final4 = np.zeros((D, T), dtype=bool)
    region_champs = []
    for teams in regions:
        rnd = 0
        while len(teams) > 1:
            teams = [play_games(theta, teams[i], teams[i + 1], setup, rng, neutral=True, shift=shift) for i in range(0, len(teams), 2)]
            rnd += 1
            if len(teams) == 4:
                for t in teams:
                    sweet16[rows, t] = True
        final4[rows, teams[0]] = True
        region_champs.append(teams[0])
    s1 = play_games(theta, region_champs[0], region_champs[1], setup, rng, neutral=True, shift=shift)
    s2 = play_games(theta, region_champs[2], region_champs[3], setup, rng, neutral=True, shift=shift)
    champ = play_games(theta, s1, s2, setup, rng, neutral=True, shift=shift)
    return {"tournament": seed > 0, "sweet_16": sweet16, "final_four": final4, "champion": _mark(D, T, champ), "seed": seed}


POSTSEASON = {
    "nfl": nfl, "nba": nba, "nhl": nhl, "college-football": college_football,
    "mens-college-basketball": ncaa_basketball, "womens-college-basketball": ncaa_basketball,
}
