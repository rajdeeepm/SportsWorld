"""Offline integrity checks for live ingest and season state."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from sportsworld.api.context import build_context
from sportsworld.config import Settings
from sportsworld.ingest.availability import LeagueAvailability
from sportsworld.ingest.espn import GameRecord, TeamLine, archive_path, write_archive
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.news import LeagueNews
from sportsworld.ingest.ratings import default_params
from sportsworld.ingest.tracker import LeagueTracker
from sportsworld.season.engine import SeasonScenario, build_setup, simulate_regular
from sportsworld.season.service import SeasonService


NOW = datetime(2026, 10, 3, 17, tzinfo=timezone.utc)
BETA_QB = -6.0


def _availability() -> LeagueAvailability:
    book = LeagueAvailability("nfl")
    book.impact = {"by_position": {"QB": {"points": BETA_QB}}, "model_version": "test"}
    book.keys = {"KC": {"QB": [{"athlete_id": "15", "name": "Patrick Mahomes"}]}}
    return book


def _injury(status: str, *, athlete_id: str = "15", name: str = "Patrick Mahomes", reported_at: str | None = None) -> dict:
    return {"athlete_id": athlete_id, "name": name, "status": status, "reported_at": reported_at}


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.payload


class _Client:
    async def get(self, url: str) -> _Response:
        assert url.endswith("/injuries")
        return _Response({"injuries": []})


def test_empty_injury_refresh_keeps_previous_deltas() -> None:
    book = _availability()
    previous = book.team_delta("KC", [_injury("Out")], NOW)
    book.deltas = {"KC": previous}
    book.report = {"KC": [_injury("Out")]}
    book.fetched_at = NOW
    saved_deltas = deepcopy(book.deltas)
    saved_report = deepcopy(book.report)

    with pytest.raises(ValueError, match="empty injury report"):
        asyncio.run(book.refresh(_Client()))

    assert book.deltas == saved_deltas
    assert book.report == saved_report
    assert book.fetched_at == NOW


@pytest.mark.parametrize("status, expected", [("Out", BETA_QB), ("Questionable", BETA_QB * 0.5)])
def test_key_qb_status_changes_team_delta(status: str, expected: float) -> None:
    rec = _availability().team_delta("KC", [_injury(status)], NOW)
    assert rec["delta_points"] == expected
    assert rec["absences"][0]["delta_points"] == expected


def test_unknown_player_has_no_team_delta() -> None:
    rec = _availability().team_delta("KC", [_injury("Out", athlete_id="99", name="Unknown Player")], NOW)
    assert rec["delta_points"] == 0.0
    assert rec["absences"] == []


def test_stale_report_contributes_no_delta() -> None:
    book = _availability()
    book.deltas["KC"] = book.team_delta("KC", [_injury("Out")], NOW)
    book.fetched_at = datetime.now(timezone.utc) - book.STALE_AFTER - timedelta(seconds=1)
    assert book.delta_for("KC", NOW + timedelta(days=1), NOW + timedelta(days=1)) == 0.0


def test_long_term_window_uses_reported_time() -> None:
    book = _availability()
    fetched = datetime.now(timezone.utc)
    reported = fetched - timedelta(days=20)
    rec = book.team_delta("KC", [_injury("Injured Reserve", reported_at=reported.isoformat())], fetched)
    book.deltas["KC"] = rec
    book.fetched_at = fetched

    assert rec["window_days"] == 28
    assert rec["window_anchor"] == reported.isoformat()
    assert book.delta_for("KC", reported + timedelta(days=27), None) == BETA_QB
    assert book.delta_for("KC", reported + timedelta(days=29), None) == 0.0


class _LLM:
    model = "fake-llm"

    def __init__(self, signals: list[dict]):
        self.signals = signals

    def json_call(self, system: str, user: str, schema: dict, *, name: str, max_tokens: int) -> dict:
        return {"signals": self.signals}


def _signal(player: str, span: str, *, team: str = "Kansas City Chiefs", status: str = "out") -> dict:
    return {"category": "availability", "team": team, "player": player, "status": status,
            "games_affected": 1, "evidence_span": span, "confidence": 0.9}


def _article() -> dict:
    return {"article_id": "story-1", "headline": "Injury update",
            "description": "Patrick Mahomes is out. Joe Burrow is available.",
            "published": NOW.isoformat(), "url": "https://example.test/story"}


def test_news_grounding_deduplication_and_official_disagreement(tmp_path) -> None:
    book = LeagueNews("nfl", tmp_path)
    teams = [{"team_id": "KC", "name": "Kansas City Chiefs", "abbreviation": "KC"},
             {"team_id": "CIN", "name": "Cincinnati Bengals", "abbreviation": "CIN"}]
    signals = [
        _signal("Patrick Mahomes", "Patrick Mahomes is out."),
        _signal("Patrick Mahomes", "Patrick Mahomes is out."),
        _signal("Patrick Mahomes", "Patrick Mahomes will miss the season."),
        _signal("Patrick Mahomes", "Joe Burrow is available."),
        _signal("Joe Burrow", "Joe Burrow is available.", team="Cincinnati Bengals", status="available"),
    ]
    report = {"CIN": [{"name": "Joe Burrow", "status": "Out", "reported_at": NOW.isoformat()}]}

    recs = book.extract(_LLM(signals), _article(), teams, report)

    assert len(recs) == 2
    assert [(r["team_id"], r["player"]) for r in recs] == [("KC", "Patrick Mahomes"), ("CIN", "Joe Burrow")]
    assert recs[0]["disagreement"] is None
    assert recs[1]["disagreement"] == {"official_status": "Out", "official_reported_at": NOW.isoformat(),
                                       "news_status": "available", "note": "sources disagree; uncertainty should rise, not be averaged away"}
    assert all(r["model"] == "fake-llm" for r in recs)


def test_news_rejects_non_verbatim_case_variant(tmp_path) -> None:
    book = LeagueNews("nfl", tmp_path)
    teams = [{"team_id": "KC", "name": "Kansas City Chiefs", "abbreviation": "KC"}]
    recs = book.extract(_LLM([_signal("Patrick Mahomes", "patrick mahomes is out.")]), _article(), teams, None)
    assert recs == []


def _game(game_id: str, home: str, away: str, start: datetime, *, state: str = "pre",
          fetched_at: datetime = NOW, home_score: int = 0, away_score: int = 0) -> GameRecord:
    return GameRecord(
        league="nfl", game_id=game_id, season=2026, season_type=2, start_time=start, state=state,
        status_name={"pre": "STATUS_SCHEDULED", "in": "STATUS_IN_PROGRESS", "post": "STATUS_FINAL"}[state],
        completed=state == "post", period=2 if state == "in" else 0,
        home=TeamLine(team_id=home, name=f"Team {home}", abbreviation=home, score=home_score),
        away=TeamLine(team_id=away, name=f"Team {away}", abbreviation=away, score=away_score),
        fetched_at=fetched_at,
    )


def test_tracker_rejects_older_snapshot_and_calls_on_live_only_for_live_changes(tmp_path) -> None:
    ctx = build_context(Settings(sportsworld_env="test"))
    tracker = LeagueTracker(LEAGUES["nfl"], ctx, tmp_path, now=NOW)
    calls: list[str] = []
    tracker.on_live = calls.append
    start = NOW + timedelta(days=1)
    pre = _game("1", "KC", "BUF", start, fetched_at=NOW)
    tracker.handle(pre, NOW)
    live = _game("1", "KC", "BUF", start, state="in", fetched_at=start + timedelta(minutes=1), home_score=7)
    assert tracker.handle(live, start + timedelta(minutes=1)) is not None
    assert calls == ["nfl"]

    older = _game("1", "KC", "BUF", start, fetched_at=NOW - timedelta(minutes=1), home_score=99)
    before = tracker.games.copy()
    assert tracker.handle(older, start + timedelta(minutes=2)) is None
    assert tracker.games == before
    assert tracker.games[live.event_id] is live
    assert calls == ["nfl"]

    same = live.model_copy(update={"fetched_at": start + timedelta(minutes=3)})
    assert tracker.handle(same, start + timedelta(minutes=3)) is None
    assert calls == ["nfl"]
    changed = _game("1", "KC", "BUF", start, state="in", fetched_at=start + timedelta(minutes=4), home_score=10)
    assert tracker.handle(changed, start + timedelta(minutes=4)) is not None
    assert calls == ["nfl", "nfl"]
    final = _game("1", "KC", "BUF", start, state="post", fetched_at=start + timedelta(hours=3), home_score=10)
    assert tracker.handle(final, start + timedelta(hours=3)) is not None
    assert calls == ["nfl", "nfl"]


def test_season_service_rate_limits_live_bumps(tmp_path, monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr("sportsworld.season.service.time.time", lambda: now[0])
    service = SeasonService(tmp_path, registry=None)
    service.on_live("nfl")
    now[0] += 59
    service.on_live("nfl")
    assert service.state("nfl").global_state_version == 1
    now[0] += 2
    service.on_live("nfl")
    assert service.state("nfl").global_state_version == 2


def test_rating_shift_postseason_window_follows_last_regular_game(tmp_path) -> None:
    first = NOW + timedelta(days=1)
    last = NOW + timedelta(days=7)
    games = [_game("1", "A", "B", first), _game("2", "B", "C", last)]
    write_archive(archive_path(tmp_path, "nfl", 2026), games)
    setup = build_setup("nfl", tmp_path, NOW, season=2026, params=default_params(LEAGUES["nfl"]))
    assert setup.r_start == [first, last]
    team = setup.index()["A"]

    extends = SeasonScenario(rating_shifts=[("A", -4.0, None, last + timedelta(hours=1))])
    expires = SeasonScenario(rating_shifts=[("A", -4.0, None, last - timedelta(hours=1))])
    extended_draws = simulate_regular(setup, 4, np.random.default_rng(1), scenario=extends)
    expired_draws = simulate_regular(setup, 4, np.random.default_rng(1), scenario=expires)

    assert extended_draws.post_shift[team] == -4.0
    assert expired_draws.post_shift[team] == 0.0
