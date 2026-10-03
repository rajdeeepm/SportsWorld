"""Acceptance checks for synthetic, offline season archives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from sportsworld.ingest.espn import GameRecord, TeamLine, archive_path, write_archive
from sportsworld.ingest.f1 import F1RatingBook
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.ratings import default_params, result_known_time
from sportsworld.season.engine import SeasonScenario, build_setup, run_season
from sportsworld.season.f1_season import run_f1_season
from sportsworld.season.rules import POSTSEASON
from sportsworld.season.structure import LeagueStructure, TeamSlot, save_structure


AS_OF = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def _game(league: str, game_id: str, home: str, away: str, start: datetime, *,
          completed: bool = False, home_score: int = 0, away_score: int = 0) -> GameRecord:
    return GameRecord(
        league=league, game_id=game_id, season=2026, season_type=2,
        start_time=start, state="post" if completed else "pre",
        status_name="STATUS_FINAL" if completed else "STATUS_SCHEDULED",
        completed=completed,
        home=TeamLine(team_id=home, name=f"Team {home}", abbreviation=home, score=home_score),
        away=TeamLine(team_id=away, name=f"Team {away}", abbreviation=away, score=away_score),
        fetched_at=AS_OF,
    )


def _league_archive(tmp_path, league: str, *, divisions_per_conference: int,
                    teams_per_division: int):
    slots = []
    games = []
    for c in range(2):
        for d in range(divisions_per_conference):
            ids = []
            for t in range(teams_per_division):
                team_id = f"C{c}D{d}T{t}"
                ids.append(team_id)
                slots.append(TeamSlot(team_id=team_id, name=f"Team {team_id}",
                                      abbreviation=team_id, conference=f"C{c}", division=f"C{c}D{d}"))
            # One short round robin within each division gives every team several games.
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    games.append(_game(league, f"g{len(games)}", ids[i], ids[j],
                                       AS_OF + timedelta(days=1 + len(games) // 16)))
    save_structure(tmp_path, LeagueStructure(league=league, espn_season=2026,
                                            teams=slots, fetched_at=AS_OF))
    write_archive(archive_path(tmp_path, league, 2026), games)
    setup = build_setup(league, tmp_path, AS_OF, season=2026,
                        params=default_params(LEAGUES[league]))
    assert setup.T == len(slots) and len(setup.r_home) == len(games)
    return setup


def _run_with_draws(setup, *, draws=2000, seed=7):
    captured = {}

    def postseason(s, regular, key, rng):
        captured["key"] = key
        captured["post"] = POSTSEASON[s.league](s, regular, key, rng)
        return captured["post"]

    result = run_season(setup, draws=draws, seed=seed, postseason=postseason)
    return result, captured["key"], captured["post"]


def _without_runtime(result):
    return {**result, "diagnostics": {k: v for k, v in result["diagnostics"].items()
                                      if k != "runtime_s"}}


def test_g6_nfl_champion_seeds_and_division_winners(tmp_path):
    setup = _league_archive(tmp_path, "nfl", divisions_per_conference=4, teams_per_division=4)
    result, _, post = _run_with_draws(setup)
    seed = post["seed"]
    assert result["draws"] == 2000
    np.testing.assert_array_equal(post["champion"].sum(axis=1), 1)
    for c in range(2):
        in_conference = setup.conf == c
        conf_seeds = seed[:, in_conference]
        np.testing.assert_array_equal(post["playoffs"][:, in_conference].sum(axis=1), 7)
        np.testing.assert_array_equal(np.sort(conf_seeds, axis=1)[:, -7:],
                                      np.broadcast_to(np.arange(1, 8), (2000, 7)))
        np.testing.assert_array_equal(post["division_title"][:, in_conference],
                                      (conf_seeds >= 1) & (conf_seeds <= 4))
        for division in np.unique(setup.div[in_conference]):
            np.testing.assert_array_equal(post["division_title"][:, setup.div == division].sum(axis=1), 1)


def test_nba_playoffs_and_play_in_are_conference_ranks_seven_to_ten(tmp_path):
    setup = _league_archive(tmp_path, "nba", divisions_per_conference=3, teams_per_division=5)
    _, key, post = _run_with_draws(setup, draws=500)
    rows = np.arange(500)[:, None]
    np.testing.assert_array_equal(post["champion"].sum(axis=1), 1)
    np.testing.assert_array_equal(post["playoffs"].sum(axis=1), 16)
    for c in range(2):
        mask = setup.conf == c
        np.testing.assert_array_equal(post["playoffs"][:, mask].sum(axis=1), 8)
        ranked = np.argsort(-np.where(mask[None, :], key, -np.inf), axis=1)
        expected = np.zeros_like(post["play_in"])
        expected[rows, ranked[:, 6:10]] = True
        np.testing.assert_array_equal(post["play_in"][:, mask], expected[:, mask])


def test_g8_rating_shift_does_not_mutate_setup_or_base_run(tmp_path):
    setup = _league_archive(tmp_path, "nfl", divisions_per_conference=4, teams_per_division=4)
    arrays = {name: getattr(setup, name).copy() for name in (
        "mu", "var", "p_home", "p_away", "p_hs", "p_as", "p_ot",
        "r_home", "r_away", "r_neutral", "r_day")}
    base_before = _without_runtime(run_season(setup, draws=300, seed=19))
    scenario = SeasonScenario(rating_shifts=[(setup.team_ids[0], 15.0, None, None)],
                              label="synthetic rating shift")
    shifted = run_season(setup, draws=300, seed=19, scenario=scenario)
    assert shifted["scenario"] == scenario.label
    assert shifted["games"] != base_before["games"]
    for name, before in arrays.items():
        np.testing.assert_array_equal(getattr(setup, name), before)
    assert _without_runtime(run_season(setup, draws=300, seed=19)) == base_before


def test_same_seed_reproduces_results_and_different_seed_changes_them(tmp_path):
    setup = _league_archive(tmp_path, "nfl", divisions_per_conference=4, teams_per_division=4)
    first = _without_runtime(run_season(setup, draws=300, seed=11))
    assert _without_runtime(run_season(setup, draws=300, seed=11)) == first
    other = run_season(setup, draws=300, seed=12)
    assert (other["teams"], other["games"]) != (first["teams"], first["games"])


def test_dynamic_has_at_least_fast_wins_spread_with_large_uncertainty(tmp_path):
    setup = _league_archive(tmp_path, "nba", divisions_per_conference=3, teams_per_division=5)
    setup.var[:] = 900.0
    setup.params.q = 0.0
    dynamic = run_season(setup, draws=4000, seed=41, mode="dynamic")
    fast = run_season(setup, draws=4000, seed=41, mode="fast")
    team = setup.team_ids[0]
    dynamic_row = next(row for row in dynamic["teams"] if row["team_id"] == team)
    fast_row = next(row for row in fast["teams"] if row["team_id"] == team)
    assert dynamic_row["wins_sd"] >= fast_row["wins_sd"]


def test_build_setup_excludes_results_not_known_as_of(tmp_path):
    league = "nfl"
    known = _game(league, "known", "A", "B", AS_OF - timedelta(days=2),
                  completed=True, home_score=21, away_score=10)
    late = _game(league, "late", "A", "B", AS_OF - timedelta(hours=1),
                 completed=True, home_score=30, away_score=0)
    assert result_known_time(known, LEAGUES[league].sport) < AS_OF
    assert result_known_time(late, LEAGUES[league].sport) > AS_OF
    write_archive(archive_path(tmp_path, league, 2026), [known, late])
    setup = build_setup(league, tmp_path, AS_OF, season=2026,
                        params=default_params(LEAGUES[league]))
    assert len(setup.p_home) == 1
    assert setup.p_hs.tolist() == [21.0]
    assert setup.p_as.tolist() == [10.0]
    assert setup.r_event_ids == [late.event_id]


def test_f1_one_driver_and_constructor_champion_per_draw_and_points_only_grow():
    drivers = [
        {"driver_id": f"d{i}", "code": f"D{i}", "name": f"Driver {i}",
         "constructor_id": f"c{i // 2}", "points": float(40 - 5 * i),
         "wins": 0, "position": i + 1}
        for i in range(5)
    ]
    constructors = [
        {"constructor_id": f"c{i}", "name": f"Constructor {i}",
         "points": sum(d["points"] for d in drivers if d["constructor_id"] == f"c{i}"),
         "wins": 0, "position": i + 1}
        for i in range(3)
    ]
    state = {"season": 2026, "standings_round": 1, "drivers": drivers,
             "constructors": constructors, "calendar": [
                 {"round": 2, "name": "Race 2", "start": "2026-10-10T12:00:00Z", "sprint": True},
                 {"round": 3, "name": "Race 3", "start": "2026-10-17T12:00:00Z", "sprint": False},
             ]}
    result = run_f1_season(state, F1RatingBook(), draws=2000, seed=31)
    assert result["diagnostics"]["remaining_races"] == 2
    assert result["diagnostics"]["remaining_sprints"] == 1
    assert result["diagnostics"]["driver_champions_per_draw"] == 1
    assert result["diagnostics"]["constructor_champions_per_draw"] == 1
    assert sum(row["title"] for row in result["drivers"]) == pytest.approx(1, abs=0.001)
    assert sum(row["title"] for row in result["constructors"]) == pytest.approx(1, abs=0.001)
    assert all(row["expected_points"] >= row["points_now"] for row in result["drivers"])
    assert all(row["expected_points"] >= row["points_now"] for row in result["constructors"])
