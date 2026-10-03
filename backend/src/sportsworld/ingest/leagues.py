"""League registry for full-season, every-team tracking.

Each league is tracked independently (its own team universe, rating book and
calibrated model) but shares the sport adapter/simulator of its parent sport.
`margin_sd` and the home advantage are only initial values; the rating book
fits its own hyper-parameters from history (see `ratings.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

from sportsworld.schemas import Sport


@dataclass(frozen=True)
class LeagueSpec:
    league_id: str
    sport: Sport
    display_name: str
    espn_path: str | None
    groups: str | None
    periods: int
    period_seconds: int
    margin_sd: float
    margin_cap: float
    # Month (1-12) in which a new season begins; used to decide the date window
    # for backfills and when the rating book applies between-season regression.
    season_start_month: int
    season_end_month: int

    @property
    def regulation_seconds(self) -> int:
        return self.periods * self.period_seconds


LEAGUES: dict[str, LeagueSpec] = {
    spec.league_id: spec
    for spec in [
        LeagueSpec("nfl", Sport.FOOTBALL, "NFL", "football/nfl", None, 4, 900, 13.5, 35.0, 9, 2),
        LeagueSpec("college-football", Sport.FOOTBALL, "College Football (FBS)", "football/college-football", "80", 4, 900, 16.0, 38.0, 8, 1),
        LeagueSpec("nba", Sport.BASKETBALL, "NBA", "basketball/nba", None, 4, 720, 12.5, 30.0, 10, 6),
        LeagueSpec("wnba", Sport.BASKETBALL, "WNBA", "basketball/wnba", None, 4, 600, 11.5, 30.0, 5, 10),
        LeagueSpec("mens-college-basketball", Sport.BASKETBALL, "Men's College Basketball (D-I)", "basketball/mens-college-basketball", "50", 2, 1200, 11.5, 30.0, 11, 4),
        LeagueSpec("womens-college-basketball", Sport.BASKETBALL, "Women's College Basketball (D-I)", "basketball/womens-college-basketball", "50", 4, 600, 12.5, 32.0, 11, 4),
        LeagueSpec("nhl", Sport.HOCKEY, "NHL", "hockey/nhl", None, 3, 1200, 2.4, 6.0, 10, 6),
        LeagueSpec("mens-college-hockey", Sport.HOCKEY, "Men's College Hockey", "hockey/mens-college-hockey", None, 3, 1200, 2.6, 6.0, 10, 4),
        LeagueSpec("f1", Sport.F1, "Formula 1", None, None, 1, 0, 0.0, 0.0, 3, 12),
    ]
}

TEAM_LEAGUES = [k for k, v in LEAGUES.items() if v.espn_path]


def get_league(league_id: str) -> LeagueSpec:
    try:
        return LEAGUES[league_id]
    except KeyError as exc:
        raise KeyError(f"unknown league {league_id!r}; known: {sorted(LEAGUES)}") from exc
