from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from sportsworld.config import Settings
from sportsworld.api.context import build_context
from sportsworld.ingest.espn import GameRecord, TeamLine, drop_exhibitions, parse_event
from sportsworld.ingest.f1 import F1Race, F1RatingBook, F1Result, lap_snapshot
from sportsworld.ingest.features import league_features, possession_value
from sportsworld.ingest.football_ep import next_score_targets
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.ratings import RatingBook
from sportsworld.ingest.tracker import LeagueTracker, live_payload
from sportsworld.models.linear import NumpyConditionalSoftmaxModel
from sportsworld.schemas import Sport

T0 = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
NFL = LEAGUES["nfl"]


def game(gid: str, home: str, away: str, start: datetime, hs: int = 0, as_: int = 0, state: str = "post", season_type: int = 2, **kw) -> GameRecord:
    return GameRecord(
        league="nfl", game_id=gid, season=2026, season_type=season_type, start_time=start, state=state, status_name="STATUS_FINAL" if state == "post" else "STATUS_IN_PROGRESS",
        completed=state == "post", home=TeamLine(team_id=home, name=f"Team {home}", abbreviation=home, score=hs),
        away=TeamLine(team_id=away, name=f"Team {away}", abbreviation=away, score=as_), fetched_at=start, **kw,
    )


def test_parse_espn_event_and_yardline_perspective():
    raw = {
        "id": "1", "date": "2026-10-03T17:00Z", "season": {"year": 2026, "type": 2}, "week": {"number": 5},
        "competitions": [{
            "neutralSite": False, "venue": {"fullName": "Field"},
            "status": {"clock": 166.0, "period": 4, "type": {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}},
            "situation": {"down": 2, "distance": 10, "yardLine": 43, "possession": "A", "homeTimeouts": 2, "awayTimeouts": 1, "lastPlay": {"x": 1}},
            "competitors": [
                {"homeAway": "home", "score": "24", "team": {"id": "H", "displayName": "Home U", "abbreviation": "HU"}, "linescores": [{"value": 7}, {"value": 17}]},
                {"homeAway": "away", "score": "7", "team": {"id": "A", "displayName": "Away U", "abbreviation": "AU"}},
            ],
        }],
    }
    g = parse_event("college-football", raw, T0)
    assert g.event_id == "college-football-1" and g.state == "in" and g.home.score == 24
    assert "lastPlay" not in g.situation
    p = live_payload(LEAGUES["college-football"], g)
    # Away offense at the home 43 is 57 yards from its own goal line.
    assert p["possession"] == "away" and p["yard_line"] == 57.0
    assert p["seconds_remaining"] == 166.0 and p["quarter"] == 4


def test_rating_book_is_point_in_time_for_same_day_games():
    early = game("1", "A", "B", T0, 30, 0)
    late = game("2", "A", "C", T0 + timedelta(hours=3), 10, 3)  # starts before early's result is "known" (+4h)
    seen = {}
    RatingBook(NFL).replay([early, late], on_pregame=lambda g, st: seen.__setitem__(g.game_id, st["home_rating"]))
    assert seen["2"] == 0.0  # early result not yet applied
    later = game("3", "A", "D", T0 + timedelta(days=7))
    RatingBook(NFL).replay([early, late, later], on_pregame=lambda g, st: seen.__setitem__(g.game_id, st["home_rating"]))
    assert seen["3"] > 0.0


def test_exhibitions_and_preseason_are_dropped():
    season = [game(f"r{i}", "A", "B", T0 + timedelta(days=7 * i)) for i in range(10)]
    pro_bowl = game("pb", "AFC", "NFC", T0, season_type=3)
    all_star = game("as", "SHAQ", "CHUCK", T0)  # filed as regular season by ESPN, but a one-off side
    pre = game("pre", "A", "B", T0, season_type=1)
    kept = {g.game_id for g in drop_exhibitions(season + [pro_bowl, all_star, pre])}
    assert kept == {g.game_id for g in season}


def test_league_features_terminal_and_possession_symmetry():
    base = {"league": "nfl", "home_rating": 0.0, "away_rating": 0.0, "margin_sd": 13.5, "obs_sd": 12.0, "hfa": 0.0,
            "regulation_seconds": 3600, "ep_coef": [6.0, -5.0, 0.0, 0, 0, 0, 0], "down": 1, "distance": 10}
    done = league_features({**base, "home_score": 21, "away_score": 20, "seconds_remaining": 0, "completed": 1.0})
    assert done["live_margin_z"] == 2.0
    home_ball = {**base, "home_score": 0, "away_score": 0, "seconds_remaining": 1800, "possession": "home", "yard_line": 90}
    away_ball = {**home_ball, "possession": "away"}
    assert possession_value(home_ball) > 0 and abs(possession_value(home_ball) + possession_value(away_ball)) < 1e-9
    assert possession_value({**home_ball, "down": 0}) == 0.0  # unknown situation contributes nothing


def test_next_score_targets_use_pre_snap_scores():
    plays = [
        [1, 900, 0, 0, 1, 1, 10, 75, None],
        [1, 860, 6, 0, 1, 1, 10, 5, None],   # home TD on this snap
        [1, 855, 7, 0, 1, 0, 0, 15, None],   # PAT (no down)
        [1, 850, 7, 0, -1, 1, 10, 75, None],  # away ball, nobody scores again
    ]
    t = next_score_targets(plays)
    assert t[0] == 7.0 and t[1] == 7.0 and t[2] is None and t[3] == 0.0


def test_tracker_lifecycle_creates_updates_and_settles(tmp_path):
    ctx = build_context(Settings(sportsworld_env="test"))
    tracker = LeagueTracker(NFL, ctx, tmp_path, now=T0)
    upcoming_next_week = game("9", "A", "Z", T0 + timedelta(days=7), state="pre")
    tracker.handle(upcoming_next_week, T0)
    pre = game("1", "A", "B", T0, state="pre")
    assert tracker.handle(pre, T0) is not None
    ev = ctx.store.get_event("nfl-1")
    assert ev.status == "upcoming" and ev.metadata["data_mode"] == "real_espn"
    live = game("1", "A", "B", T0, 7, 3, state="in", period=2, clock_seconds=300.0, situation={"possession": "A", "yardLine": 80, "down": 1, "distance": 10})
    row = tracker.handle(live, T0 + timedelta(minutes=50))
    assert row["status"] == "live" and row["probabilities"]["home"] > 0.5
    assert tracker.handle(live, T0 + timedelta(minutes=51)) is None  # unchanged snapshot -> no new observation
    final = game("1", "A", "B", T0, 27, 3, state="post", period=4)
    row = tracker.handle(final, T0 + timedelta(hours=3, minutes=10))
    assert row["probabilities"] == {"home": 1.0, "away": 0.0}
    assert ctx.store.get_event("nfl-1").status == "completed"
    assert tracker.book.teams["A"].mean > 0  # result assimilated into the latent rating
    kinds = [o.kind for o in ctx.store.list_observations("nfl-9")]
    assert "team_state" in kinds  # A's upcoming game received the updated latent state


def test_f1_lap_snapshot_orders_by_laps_then_time():
    t = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    drivers = [{"driver_number": 1, "name_acronym": "AAA"}, {"driver_number": 2, "name_acronym": "BBB"}, {"driver_number": 3, "name_acronym": "CCC"}]
    laps = []
    for n in range(1, 4):
        laps.append({"driver_number": 1, "lap_number": n, "date_start": (t + timedelta(seconds=90 * (n - 1))).isoformat(), "lap_duration": 90})
        laps.append({"driver_number": 2, "lap_number": n, "date_start": (t + timedelta(seconds=90 * (n - 1) + 2)).isoformat(), "lap_duration": 90})
    laps.append({"driver_number": 3, "lap_number": 1, "date_start": t.isoformat(), "lap_duration": 95})
    lead, snap = lap_snapshot(laps, drivers)
    assert lead == 3
    assert [snap[c]["position"] for c in ("AAA", "BBB", "CCC")] == [1, 2, 3]
    assert snap["BBB"]["gap_to_leader"] == 2.0 and snap["CCC"]["laps_completed"] == 1


def test_f1_rating_book_rewards_winner_and_tracks_reliability():
    res = [F1Result(driver_id=f"d{i}", code=f"D{i}", name=f"D{i}", constructor_id=f"c{i % 2}", constructor="x", grid=i, position=i if i < 4 else None,
                    status="Finished" if i < 4 else "Engine") for i in range(1, 5)]
    book = F1RatingBook()
    book.apply_race(F1Race(season=2026, round=1, race_name="GP", circuit="c", start_time=T0, results=res))
    assert book.drivers["d1"].mean > book.drivers["d3"].mean
    assert book.driver_view("d4", "c0")["reliability"] < book.driver_view("d1", "c1")["reliability"]


def test_masked_softmax_ignores_padded_slots():
    X = np.zeros((40, 3, 1))
    X[:, 0, 0] = 1.0
    X[:, 2, 0] = 50.0  # padded slot with an extreme feature value
    mask = np.array([[True, True, False]] * 40)
    y = np.zeros(40, dtype=int)
    m = NumpyConditionalSoftmaxModel.create(["x"]).fit(X, y, epochs=200, lr=0.2, mask=mask)
    assert m.weights[0] > 0  # learned "x helps", not "x hurts" (which the padded slot would push)
