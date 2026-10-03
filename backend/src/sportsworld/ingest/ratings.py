"""League-wide Kalman rating book: a learned latent team-strength state for every team.

State per team i:  r_i ~ N(m_i, v_i)          (points relative to league average)
Dynamics:          r_i(t+dt) = r_i(t) + w,     w ~ N(0, q * dt_days)
Season rollover:   r_i <- rho * r_i,           v_i <- v_i + season_var
Observation:       margin_home = hfa * (1 - neutral) + r_h - r_a + e,   e ~ N(0, obs_sd^2)

Updates are a (diagonal) Kalman filter over the two teams in each game.  The
hyper-parameters (hfa, obs_sd, q, rho, season_var, newcomer_mean) are fit by
maximizing the one-step-ahead predictive log-likelihood of margins on a training
window only, so a backtest never tunes on its own test games.

Point-in-time rule: a game's result is applied only once it is "known", i.e. at
`result_known_time(game)`.  A 1pm kickoff therefore never informs the prior of a
4:25pm kickoff on the same day.
"""
from __future__ import annotations

import heapq
import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from sportsworld.schemas import Sport

from .espn import GameRecord
from .leagues import LeagueSpec

GAME_DURATION = {Sport.FOOTBALL: timedelta(hours=4), Sport.BASKETBALL: timedelta(hours=3), Sport.HOCKEY: timedelta(hours=3)}
FORM_DECAY = 0.65  # EWMA weight on previous form; ~2-game half-life
MAX_REST_DAYS = 10.0


def result_known_time(game: GameRecord, sport: Sport) -> datetime:
    """Conservative upper bound on when a final score was public."""
    return game.start_time + GAME_DURATION.get(sport, timedelta(hours=4))


@dataclass
class RatingParams:
    hfa: float
    obs_sd: float
    q: float = 0.02
    rho: float = 0.7
    season_var: float = 20.0
    init_var: float = 100.0
    newcomer_mean: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TeamState:
    team_id: str
    name: str
    mean: float
    var: float
    season: int
    last_game: datetime | None = None
    form: float = 0.0
    prior_season_rating: float = 0.0
    games: int = 0
    season_games: int = 0
    wins: int = 0
    losses: int = 0
    abbreviation: str | None = None
    history: list[tuple[str, float, float]] = field(default_factory=list)


def default_params(spec: LeagueSpec) -> RatingParams:
    hfa = {Sport.FOOTBALL: 2.0, Sport.BASKETBALL: 2.5, Sport.HOCKEY: 0.2}.get(spec.sport, 1.0)
    scale = (spec.margin_sd / 12.0) ** 2
    return RatingParams(hfa=hfa, obs_sd=spec.margin_sd, q=0.02 * scale, season_var=20.0 * scale, init_var=(spec.margin_sd * 0.9) ** 2)


class RatingBook:
    def __init__(self, spec: LeagueSpec, params: RatingParams | None = None, *, keep_history: bool = False):
        self.spec = spec
        self.params = params or default_params(spec)
        self.teams: dict[str, TeamState] = {}
        self.keep_history = keep_history
        self.seasons_seen: set[int] = set()
        self.applied: set[str] = set()
        self.games_applied = 0
        self.loglik = 0.0
        self.as_of: datetime | None = None

    # ------------------------------------------------------------------
    def _team(self, line, season: int) -> TeamState:
        p = self.params
        t = self.teams.get(line.team_id)
        if t is None:
            mean = p.newcomer_mean if len(self.seasons_seen) > 1 else 0.0
            t = TeamState(line.team_id, line.name, mean, p.init_var, season, abbreviation=line.abbreviation)
            self.teams[line.team_id] = t
        t.name = line.name or t.name
        t.abbreviation = line.abbreviation or t.abbreviation
        if season != t.season:
            t.prior_season_rating = t.mean
            t.mean *= p.rho
            t.var = min(p.init_var, t.var + p.season_var)
            t.season = season
            t.season_games = t.wins = t.losses = 0
            t.form = 0.0
        return t

    def _drift_var(self, t: TeamState, at: datetime) -> float:
        if t.last_game is None:
            return t.var
        days = max(0.0, (at - t.last_game).total_seconds() / 86400.0)
        return min(self.params.init_var, t.var + self.params.q * days)

    def _rest(self, t: TeamState, at: datetime) -> float:
        if t.last_game is None:
            return MAX_REST_DAYS
        return min(MAX_REST_DAYS, max(0.0, (at - t.last_game).total_seconds() / 86400.0))

    # ------------------------------------------------------------------
    def pregame_state(self, game: GameRecord) -> dict[str, float | str | bool]:
        """Point-in-time world-state fields for a game, without mutating the book."""
        p = self.params
        h = self.teams.get(game.home.team_id)
        a = self.teams.get(game.away.team_id)

        def view(t: TeamState | None) -> tuple[float, float, float, float, float]:
            if t is None:
                mean = p.newcomer_mean if len(self.seasons_seen) > 1 else 0.0
                return mean, p.init_var, 0.0, 0.0, MAX_REST_DAYS
            mean, var, prior, form = t.mean, self._drift_var(t, game.start_time), t.prior_season_rating, t.form
            if game.season != t.season:  # first game of a new season: apply rollover in the view
                prior, mean, var, form = t.mean, t.mean * p.rho, min(p.init_var, var + p.season_var), 0.0
            return mean, var, prior, form, self._rest(t, game.start_time)

        hm, hv, hp, hf, hr = view(h)
        am, av, ap, af, ar = view(a)
        return {
            "league": self.spec.league_id,
            "home_rating": hm, "away_rating": am,
            "home_rating_var": hv, "away_rating_var": av,
            "home_prior_rating": hp, "away_prior_rating": ap,
            "home_form": hf, "away_form": af,
            "home_rest_days": hr, "away_rest_days": ar,
            "hfa": p.hfa, "obs_sd": p.obs_sd, "margin_sd": self.spec.margin_sd,
            "neutral_site": bool(game.neutral_site),
            "home_field": 0.0 if game.neutral_site else 1.0,
            "regulation_seconds": self.spec.regulation_seconds,
            "home_games_played": float(h.games if h else 0), "away_games_played": float(a.games if a else 0),
        }

    def apply_result(self, game: GameRecord) -> None:
        if game.game_id in self.applied or not game.completed or game.cancelled or game.season_type == 1:
            return
        p = self.params
        self.seasons_seen.add(game.season)
        h = self._team(game.home, game.season)
        a = self._team(game.away, game.season)
        hv = self._drift_var(h, game.start_time)
        av = self._drift_var(a, game.start_time)
        expected = (0.0 if game.neutral_site else p.hfa) + h.mean - a.mean
        cap = self.spec.margin_cap
        margin = max(-cap, min(cap, float(game.margin())))
        s = hv + av + p.obs_sd ** 2
        innov = margin - expected
        self.loglik += -0.5 * (math.log(2 * math.pi * s) + innov * innov / s)
        h.mean += hv / s * innov
        a.mean -= av / s * innov
        h.var = hv - hv * hv / s
        a.var = av - av * av / s
        h.form = FORM_DECAY * h.form + (1 - FORM_DECAY) * innov
        a.form = FORM_DECAY * a.form - (1 - FORM_DECAY) * innov
        when = game.start_time
        for t, won in ((h, game.margin() > 0), (a, game.margin() < 0)):
            t.last_game = when
            t.games += 1
            t.season_games += 1
            t.wins += int(won)
            t.losses += int(not won and game.margin() != 0)
            if self.keep_history:
                t.history.append((game.start_time.isoformat(), round(t.mean, 3), round(t.var, 3)))
        self.applied.add(game.game_id)
        self.games_applied += 1

    # ------------------------------------------------------------------
    def replay(
        self,
        games: Iterable[GameRecord],
        on_pregame: Callable[[GameRecord, dict], None] | None = None,
        until: datetime | None = None,
    ) -> "RatingBook":
        """Chronological point-in-time replay.

        `on_pregame(game, state)` is called at each game's start with a state
        computed only from results known strictly before that start time.
        """
        pending: list[tuple[datetime, int, GameRecord]] = []
        counter = itertools.count()
        for g in sorted(games, key=lambda x: (x.start_time, x.game_id)):
            if until and g.start_time > until:
                break
            while pending and pending[0][0] <= g.start_time:
                self.apply_result(heapq.heappop(pending)[2])
            if g.cancelled:
                continue
            if on_pregame is not None:
                on_pregame(g, self.pregame_state(g))
            if g.completed:
                heapq.heappush(pending, (result_known_time(g, self.spec.sport), next(counter), g))
        while pending and (until is None or pending[0][0] <= until):
            self.apply_result(heapq.heappop(pending)[2])
        self.as_of = until
        return self

    def table(self) -> list[dict]:
        rows = []
        for t in self.teams.values():
            rows.append({
                "team_id": t.team_id, "name": t.name, "abbreviation": t.abbreviation,
                "rating": round(t.mean, 2), "rating_sd": round(math.sqrt(max(t.var, 0.0)), 2),
                "form": round(t.form, 2), "season": t.season, "wins": t.wins, "losses": t.losses,
                "games": t.games, "last_game": t.last_game.isoformat() if t.last_game else None,
            })
        return sorted(rows, key=lambda r: r["rating"], reverse=True)

    def to_dict(self) -> dict:
        return {"league": self.spec.league_id, "params": self.params.to_dict(), "games_applied": self.games_applied}


# ---------------------------------------------------------------------------
# Hyper-parameter fitting (coordinate search on predictive log-likelihood)
# ---------------------------------------------------------------------------
def _score(spec: LeagueSpec, params: RatingParams, games: list[GameRecord], burn_in_season: int | None) -> float:
    """Mean one-step-ahead predictive log-likelihood of capped margins, scored at kickoff
    through the same result-known queue used for serving (no same-day leakage)."""
    book = RatingBook(spec, params)
    acc = [0.0, 0]

    def pre(g: GameRecord, st: dict) -> None:
        if not g.completed or (burn_in_season is not None and g.season <= burn_in_season):
            return
        mu = float(st["hfa"]) * float(st["home_field"]) + float(st["home_rating"]) - float(st["away_rating"])
        s2 = float(st["home_rating_var"]) + float(st["away_rating_var"]) + params.obs_sd ** 2
        m = max(-spec.margin_cap, min(spec.margin_cap, float(g.margin())))
        acc[0] += -0.5 * (math.log(2 * math.pi * s2) + (m - mu) ** 2 / s2)
        acc[1] += 1

    book.replay(games, on_pregame=pre)
    return acc[0] / max(acc[1], 1)


def fit_params(spec: LeagueSpec, games: list[GameRecord], *, rounds: int = 2) -> tuple[RatingParams, float]:
    games = [g for g in games if g.completed and not g.cancelled]
    first_season = min((g.season for g in games), default=None)
    burn = first_season if len({g.season for g in games}) > 1 else None
    p = default_params(spec)
    sd = spec.margin_sd
    scale = (sd / 12.0) ** 2  # grids below are written in ~12-point margin units
    grid = {
        "hfa": [x * sd / 12.0 for x in (0.0, 1.0, 2.0, 3.0, 4.0)],
        "obs_sd": [sd * f for f in (0.8, 0.9, 1.0, 1.1, 1.2)],
        "q": [x * scale for x in (0.0, 0.01, 0.03, 0.08, 0.2)],
        "rho": [0.4, 0.55, 0.7, 0.85, 1.0],
        "season_var": [x * scale for x in (5.0, 20.0, 50.0, 100.0)],
        "newcomer_mean": [0.0, -0.5 * sd, -1.0 * sd],
    }
    best = _score(spec, p, games, burn)
    for _ in range(rounds):
        for name, values in grid.items():
            for v in values:
                trial = RatingParams(**{**p.to_dict(), name: v})
                sc = _score(spec, trial, games, burn)
                if sc > best + 1e-9:
                    best, p = sc, trial
    return p, best


def save_params(path: Path, spec: LeagueSpec, params: RatingParams, score: float, n_games: int, window: dict, extra: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"league": spec.league_id, "params": params.to_dict(), "mean_predictive_loglik": score, "n_games": n_games, "fit_window": window, "data_mode": "real_espn", **(extra or {})}, indent=2))


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def load_params(path: Path) -> RatingParams | None:
    if not path.exists():
        return None
    return RatingParams(**json.loads(path.read_text())["params"])
