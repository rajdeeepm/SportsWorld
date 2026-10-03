"""Spoken briefings ("SportsWorld Radio") written from the engine's own numbers by fixed templates.

No language model writes these sentences: every figure is read from the live season run, board and feed,
so what the voice says is exactly what the screen shows. ElevenLabs only turns the text into speech.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sportsworld.ingest.leagues import LEAGUES

QUALIFY = {"college-football": ("playoffs", "make the College Football Playoff"),
           "mens-college-basketball": ("tournament", "make the NCAA tournament"),
           "mens-college-hockey": ("tournament", "make the NCAA tournament")}
TITLE = {"nfl": "the Super Bowl", "college-football": "the national title", "nba": "the NBA title",
         "mens-college-basketball": "the national title", "nhl": "the Stanley Cup", "mens-college-hockey": "the national title"}


def _pct(p: float | None) -> str:
    if p is None:
        return "unknown"
    v = p * 100
    if v < 0.1:
        return "less than a tenth of a percent"
    if v < 1:
        return f"{v:.1f} percent"
    return f"{v:.0f} percent"


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return d.strftime("%A, %B ") + str(d.day)


def _qualify(league: str) -> tuple[str, str]:
    return QUALIFY.get(league, ("playoffs", "make the playoffs"))


def team_briefing(league: str, team_page: dict[str, Any], standings_row: dict | None, names: dict[str, str]) -> str:
    t = team_page["team"]
    name = (team_page.get("meta") or {}).get("short_name") or t["name"]
    qk, qtext = _qualify(league)
    parts = []
    if standings_row:
        rec = f"{standings_row['wins']} and {standings_row['losses']}"
        conf = (t.get("conference") or "").replace(" Conference", "")
        parts.append(f"{name} are {rec}" + (f", {standings_row['conf_record'].replace('-', ' and ')} in the {conf}." if conf else "."))
    live = next((g for g in team_page["remaining"] if g.get("state") == "in"), None)
    if live:
        mine, theirs = (live.get("home_score"), live.get("away_score")) if live["is_home"] else (live.get("away_score"), live.get("home_score"))
        opp = names.get(live["away_id"] if live["is_home"] else live["home_id"], "their opponent")
        lead = "lead" if (mine or 0) > (theirs or 0) else "trail" if (mine or 0) < (theirs or 0) else "are level with"
        parts.append(f"Right now they {lead} {opp}, {mine} to {theirs}, and SportsWorld gives them a {_pct(live.get('p_win'))} chance to win.")
    parts.append(f"Across ten thousand simulated seasons they average {t['expected_wins']:.1f} wins, with a {_pct(t.get(qk))} chance to {qtext} "
                 f"and {_pct(t.get('champion'))} to win {TITLE.get(league, 'the title')}.")
    pre = [g for g in team_page["remaining"] if g.get("state") == "pre"]
    if pre:
        nxt = pre[0]
        opp = names.get(nxt["away_id"] if nxt["is_home"] else nxt["home_id"], "their next opponent")
        parts.append(f"Next up: {'home against' if nxt['is_home'] else 'at'} {opp} on {_day(nxt['start_time'])}, where they are {_pct(nxt.get('p_win'))} to win.")
        lev = lambda g: abs((g.get("leverage_home") if g["is_home"] else g.get("leverage_away")) or 0)  # noqa: E731
        big = max(pre, key=lev)
        if lev(big) >= 0.01:
            opp = names.get(big["away_id"] if big["is_home"] else big["home_id"], "that opponent")
            parts.append(f"Their biggest remaining game is {'against' if big['is_home'] else 'at'} {opp}: "
                         f"winning it instead of losing it moves their {qtext.split(' ', 1)[1] if ' ' in qtext else 'playoff'} odds by {lev(big) * 100:.0f} points.")
    return " ".join(parts)


def league_briefing(league: str, run: dict, board: list[dict], feed: list[dict], names: dict[str, str]) -> str:
    spec = LEAGUES[league]
    teams = run.get("teams") or []
    if not teams:
        return f"The {spec.display_name} season has not started yet."
    fav = teams[0]
    parts = [f"This is SportsWorld on the {spec.display_name}.",
             f"{fav['name']} are the favourites for {TITLE.get(league, 'the title')} at {_pct(fav.get('champion'))}"
             + (f", ahead of {teams[1]['name']} at {_pct(teams[1].get('champion'))}." if len(teams) > 1 else ".")]
    live = [g for g in board if g.get("state") == "in"]
    if live:
        parts.append(f"{len(live)} game{'s are' if len(live) != 1 else ' is'} live right now, each one feeding the season simulation.")
    lev = lambda g: max(abs(g.get("leverage_home") or 0), abs(g.get("leverage_away") or 0))  # noqa: E731
    soon = sorted(board, key=lambda g: g["start_time"])[:120]
    if soon:
        big = max(soon, key=lev)
        if lev(big) >= 0.02:
            qtext = _qualify(league)[1]
            parts.append(f"The game that matters most coming up is {big['away']} at {big['home']}: its result swings "
                         f"{'playoff' if 'playoff' in qtext.lower() else 'tournament'} odds by up to {lev(big) * 100:.0f} points.")
    finals = [u for u in feed if str(u.get("reason", "")).lower().startswith("final")]
    if finals:
        parts.append(f"Latest result: {finals[-1]['reason'].replace('Final: ', '')}.")
    return " ".join(parts)


def update_line(update: dict) -> str:
    reason = str(update.get("reason") or "")
    if reason.lower().startswith("final"):
        return f"Final score. {reason.split(':', 1)[-1].strip()}. Every affected forecast and the season have been updated."
    return reason
