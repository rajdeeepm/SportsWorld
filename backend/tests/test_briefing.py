from sportsworld.live.briefing import league_briefing, team_briefing


def _team_page():
    return {
        "team": {"name": "Michigan Wolverines", "conference": "Big Ten Conference", "expected_wins": 6.27, "playoffs": 0.0079, "champion": 0.0005},
        "meta": {"short_name": "Michigan"},
        "remaining": [{"state": "pre", "is_home": True, "home_id": "130", "away_id": "213", "start_time": "2026-10-17T16:00:00+00:00",
                       "p_win": 0.56, "leverage_home": 0.004, "leverage_away": 0.1}],
    }


def test_team_briefing_reads_engine_numbers_verbatim():
    text = team_briefing("college-football", _team_page(), {"wins": 3, "losses": 2, "conf_record": "0-2"}, {"213": "Penn State Nittany Lions"})
    assert "Michigan are 3 and 2, 0 and 2 in the Big Ten." in text
    assert "6.3 wins" in text and "0.8 percent chance to make the College Football Playoff" in text
    assert "Penn State Nittany Lions" in text and "56 percent to win" in text


def test_league_briefing_names_favourite_and_live_games():
    run = {"teams": [{"name": "Alabama Crimson Tide", "champion": 0.16}, {"name": "Utah Utes", "champion": 0.13}]}
    board = [{"state": "in", "start_time": "2026-10-03T20:00:00+00:00", "away": "A", "home": "B", "leverage_home": 0.3, "leverage_away": 0.1}]
    text = league_briefing("college-football", run, board, [], {})
    assert "Alabama Crimson Tide are the favourites for the national title at 16 percent" in text
    assert "1 game is live right now" in text and "up to 30 points" in text
