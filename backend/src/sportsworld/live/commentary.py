"""Live play-by-play commentary for one game, voiced by ElevenLabs.

Every line is built from the real ESPN play text and SportsWorld's own live win probability by fixed rules:
no language model writes or embellishes the call. Key moments (scores, turnovers, big probability swings) get
a broadcast-style lead-in; routine plays are kept short.
"""
from __future__ import annotations

import re
from typing import Any

# last probability / score we voiced per game, so lines can say "up 9" and score changes are never missed
_last_p: dict[str, float] = {}
_last_score: dict[str, tuple[int, int]] = {}


def _seq(pid: str) -> int:
    try:
        return int(pid)
    except (TypeError, ValueError):
        return -1

SKIP_TYPES = {"End Period", "End of Half", "End Game", "Timeout", "Official Timeout", "Two-minute warning", "Two-Minute Warning",
              "Coin Toss", "End of Game", "Period Start", "Period End", "Game Start", "Stoppage", "Jump Ball"}


def _clean(text: str) -> str:
    t = re.sub(r"^\(\s*\d{1,2}:\d{2}\s*-?\s*\d?\w*\)\s*", "", text)          # "(11:51) " clock prefix
    t = re.sub(r"\b(Shotgun|No Huddle-Shotgun|No Huddle|Under Center)\b\s*", "", t)
    t = re.sub(r"#\d+\s+", "", t)                                           # jersey numbers
    t = re.sub(r"(?<!the )\b([A-Z]{2,5})(\d{1,2})\b", r"the \1 \2", t)     # "MINN48" -> "the MINN 48"
    t = re.sub(r"\b([A-Z]{2,5})(\d{1,2})\b", r"\1 \2", t)                  # "the OSU42" -> "the OSU 42"
    t = re.sub(r"\b1ST DOWN\b", "first down", t)
    t = re.sub(r"\s+,", ",", t)
    conv = ""
    for m in re.finditer(r"\(([^()]*(?:two-point|2pt|2-pt|conversion|kick|pat|extra point)[^()]*)\)", t, flags=re.I):
        inner = m.group(1)
        if re.search(r"two-point|2pt|2-pt|conversion", inner, re.I):
            ok = not re.search(r"fail|no good|incomplete|failed", inner, re.I)
            who = re.sub(r"#\d+\s*", "", inner)
            who = re.sub(r"\s*(for (a )?)?two-point conversion.*$|\s*2pt.*$|\s*conversion.*$", "", who, flags=re.I).strip(" ,.")
            conv = f" Two-point try: {who}... " + ("it's good!" if ok else "no good.")
        elif re.search(r"kick|pat|extra point", inner, re.I):
            conv = " The extra point is good." if not re.search(r"blocked|no good|missed", inner, re.I) else " The extra point is no good!"
    t = re.sub(r"\(([^)]*)\)", "", t)                                       # tackler lists etc.
    t = re.sub(r"\s{2,}", " ", t).strip(" .,")
    return (t + "." if t else "") + conv


def _lead(sport: str, play: dict) -> str:
    typ, text = play.get("type", ""), (play.get("text") or "").lower()
    if sport == "football":
        if "touchdown" in typ.lower() or "touchdown" in text:
            return "Touchdown!"
        if "interception" in typ.lower():
            return "Picked off!"
        if "fumble" in typ.lower() and play.get("turnover"):
            return "Fumble, and it's a turnover!"
        if "field goal good" in typ.lower():
            return "The kick is good."
        if "missed field goal" in typ.lower() or "field goal missed" in typ.lower():
            return "No good!"
        if "sack" in typ.lower():
            return "Sacked!"
        if "safety" in typ.lower():
            return "Safety!"
    if sport == "basketball" and play.get("scoring"):
        if "three point" in text:
            return "From downtown!"
        if "dunk" in text:
            return "Slam!"
    if sport == "hockey":
        if typ == "Goal":
            return "Goal!"
        if "penalty" in typ.lower():
            return "Penalty."
    return ""


def _worth_calling(sport: str, play: dict) -> bool:
    if not play.get("text") or play.get("type") in SKIP_TYPES:
        return False
    if sport == "football":
        return True
    if sport == "basketball":
        return bool(play.get("scoring") or play.get("turnover") or "turnover" in (play.get("type") or "").lower())
    if sport == "hockey":
        return play.get("type") in ("Goal", "Penalty", "Shot") or "penalty" in (play.get("type") or "").lower()
    return True


def _prob_line(event_id: str, p_home: float | None, teams: dict, force: bool) -> str:
    if p_home is None:
        return ""
    prev = _last_p.get(event_id)
    delta = None if prev is None else p_home - prev
    if not force and delta is not None and abs(delta) < 0.02:
        return ""
    _last_p[event_id] = p_home
    home, away = teams.get("home", {}).get("name", "the home side"), teams.get("away", {}).get("name", "the visitors")
    fav, pf, dfav = (home, p_home, delta) if p_home >= 0.5 else (away, 1 - p_home, -delta if delta is not None else None)
    move = ""
    if dfav is not None and abs(dfav) >= 0.02:
        move = f", {'up' if dfav > 0 else 'down'} {abs(dfav) * 100:.0f}"
    return f"SportsWorld now has {fav} at {pf * 100:.0f} percent{move}."


def commentary(event_id: str, sport: str, stream: dict, p_home: float | None, after: str | None, max_lines: int = 3,
               live_score: tuple[int, int] | None = None) -> dict[str, Any]:
    plays = sorted(stream["plays"], key=lambda p: _seq(p["id"]))
    teams = stream["teams"]
    last_id = plays[-1]["id"] if plays else after
    an, hn = teams.get("away", {}).get("name"), teams.get("home", {}).get("name")
    if after is None:
        h, a = teams.get("home", {}), teams.get("away", {})
        last = next((p for p in reversed(plays) if p.get("home_score") is not None), None)
        hs, as_ = (last or {}).get("home_score", 0), (last or {}).get("away_score", 0)
        _last_p.pop(event_id, None)
        if live_score:
            _last_score[event_id] = live_score
        intro = (f"We're live with {a.get('name')} at {h.get('name')}. {a.get('name')} {as_}, {h.get('name')} {hs}, "
                 f"{stream.get('detail') or ''}.").replace(" ,", ",")
        prob = _prob_line(event_id, p_home, teams, force=True)
        return {"lines": [{"id": last_id, "text": f"{intro} {prob}".strip()}], "last_id": last_id}
    cut = _seq(after)
    new = [p for p in plays if _seq(p["id"]) > cut and _worth_calling(sport, p)]  # by sequence: re-numbered drives never skip plays
    lines = []
    for p in new[-max_lines:]:
        lead = _lead(sport, p)
        body = _clean(p["text"])
        if p.get("scoring") and p.get("home_score") is not None:
            body += f" That makes it {teams.get('away', {}).get('name')} {p.get('away_score')}, {teams.get('home', {}).get('name')} {p.get('home_score')}."
        lines.append({"id": p["id"], "text": f"{lead} {body}".strip(), "key": bool(lead or p.get("scoring") or p.get("turnover"))})
    # scoring plays seen in the play-by-play bring the announced score up to date
    for p in new:
        if p.get("scoring") and p.get("home_score") is not None:
            _last_score[event_id] = (int(p.get("away_score") or 0), int(p.get("home_score") or 0))
    # the scoreboard moves before the play-by-play: announce the new score at once, details follow
    if live_score and _last_score.get(event_id) not in (None, live_score):
        a0, h0 = _last_score[event_id]
        scorer = an if live_score[0] > a0 else hn if live_score[1] > h0 else None
        lead = f"Points for {scorer}!" if scorer else "Score update."
        lines.append({"id": last_id or "", "text": f"{lead} It's {an} {live_score[0]}, {hn} {live_score[1]}. The full play is coming in.", "key": True})
        _last_score[event_id] = live_score
    if lines:
        prob = _prob_line(event_id, p_home, teams, force=any(x.get("key") for x in lines))
        if prob and lines:
            lines[-1]["text"] += f" {prob}"
    if not new and stream.get("state") == "post":
        return {"lines": [], "last_id": last_id, "final": True}
    return {"lines": lines, "last_id": last_id}
