"""SportsWorld Analyst: turns a sports question into actions on the live SportsWorld engine.

Intents (decided by deterministic rules, never by a language model):
  team status     "How are Michigan doing?"                -> record, playoff / title odds, next game, swing game
  what-if         "What if Michigan's QB misses 3 games?"   -> runs 10,000-season simulations on a private branch
  forced result   "What if Michigan beats Ohio State?"      -> finds the real remaining game, forces it, simulates
  games to watch  "Which games matter tonight?"             -> ranks live / upcoming games by season leverage
  compare         "Should I watch BYU or Texas Tech?"       -> compares two games and recommends one
  matchup         "Who wins Ohio State vs Iowa?"            -> live score + SportsWorld win probability
  outlook         "Who will win the Super Bowl?"            -> title odds with Monte Carlo error
Every number comes from the engine's API; the agent only routes, combines and explains.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

API = os.environ.get("SPORTSWORLD_API", "http://127.0.0.1:8000")
SITE = os.environ.get("SPORTSWORLD_SITE", "https://sportsworld.tech")

LEAGUE_WORDS = {
    "nfl": ["nfl", "super bowl", "afc", "nfc"],
    "college-football": ["college football", "cfb", "cfp", "college football playoff", "fbs", "heisman"],
    "nba": ["nba", "nba finals"],
    "mens-college-basketball": ["college basketball", "cbb", "march madness", "ncaa tournament", "final four"],
    "nhl": ["nhl", "stanley cup", "hockey"],
    "f1": ["f1", "formula 1", "formula one", "grand prix", "constructors"],
}
LEAGUE_NAME = {"nfl": "NFL", "college-football": "College Football", "nba": "NBA", "mens-college-basketball": "College Basketball",
               "nhl": "NHL", "f1": "Formula 1"}
SEARCH_ORDER = ["college-football", "nfl", "nba", "nhl", "mens-college-basketball"]

# common fan names ESPN does not list: alias -> official team name (per league)
ALIASES = {
    "college-football": {"umich": "Michigan Wolverines", "um": "Michigan Wolverines", "the wolverines": "Michigan Wolverines",
                         "bama": "Alabama Crimson Tide", "the tide": "Alabama Crimson Tide", "the u": "Miami Hurricanes",
                         "nd": "Notre Dame Fighting Irish", "the irish": "Notre Dame Fighting Irish", "osu": "Ohio State Buckeyes",
                         "tosu": "Ohio State Buckeyes", "the buckeyes": "Ohio State Buckeyes", "psu": "Penn State Nittany Lions",
                         "uga": "Georgia Bulldogs", "ut": "Texas Longhorns", "a&m": "Texas A&M Aggies", "tamu": "Texas A&M Aggies",
                         "fsu": "Florida State Seminoles", "msu": "Michigan State Spartans", "iu": "Indiana Hoosiers", "usc": "USC Trojans",
                         "ole miss": "Ole Miss Rebels", "byu": "BYU Cougars", "ttu": "Texas Tech Red Raiders", "cal": "California Golden Bears"},
    "mens-college-basketball": {"umich": "Michigan Wolverines", "uconn": "UConn Huskies", "unc": "North Carolina Tar Heels", "uk": "Kentucky Wildcats"},
    "nfl": {"niners": "San Francisco 49ers", "pats": "New England Patriots", "bucs": "Tampa Bay Buccaneers", "jags": "Jacksonville Jaguars",
            "commies": "Washington Commanders", "the birds": "Philadelphia Eagles"},
    "nba": {"sixers": "Philadelphia 76ers", "cavs": "Cleveland Cavaliers", "mavs": "Dallas Mavericks", "wolves": "Minnesota Timberwolves", "blazers": "Portland Trail Blazers"},
    "nhl": {"habs": "Montreal Canadiens", "leafs": "Toronto Maple Leafs", "wings": "Detroit Red Wings", "pens": "Pittsburgh Penguins", "caps": "Washington Capitals"},
}
QUALIFY = {"mens-college-basketball": ("tournament", "NCAA tournament"), "college-football": ("playoffs", "College Football Playoff")}
TITLE = {"nfl": "Super Bowl", "college-football": "national title", "nba": "NBA title", "mens-college-basketball": "national title", "nhl": "Stanley Cup"}


def pct(p: float | None) -> str:
    if p is None:
        return "n/a"
    return "<0.1%" if 0 < p < 0.001 else f"{p * 100:.1f}%" if p < 0.1 else f"{p * 100:.0f}%"


class Engine:
    def __init__(self, base: str = API):
        self.c = httpx.Client(base_url=base, timeout=90)
        self._teams: dict[str, list[dict]] = {}

    def get(self, path: str, **params) -> Any:
        r = self.c.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> Any:
        r = self.c.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def teams(self, league: str) -> list[dict]:
        if league not in self._teams:
            run = self.get(f"/competitions/{league}/seasons/current/season-forecast")
            meta = {}
            try:
                meta = self.get(f"/competitions/{league}/teams/meta")
            except Exception:
                pass
            out = []
            for t in run["teams"]:
                m = meta.get(t["team_id"], {})
                keys = {t["name"].lower(), (m.get("short_name") or "").lower(), (m.get("location") or "").lower(), (m.get("nickname") or "").lower()}
                abbr = (t.get("abbreviation") or m.get("abbreviation") or "").strip()
                # abbreviations only count when written in capitals ("HOW" is Howard, "how" is a word)
                out.append({**t, "short": m.get("short_name") or t["name"], "keys": {k for k in keys if len(k) >= 3}, "abbr": abbr if len(abbr) >= 2 else ""})
            for alias, official in ALIASES.get(league, {}).items():
                for t in out:
                    if t["name"] == official:
                        t["keys"].add(alias)
            self._teams[league] = out
        return self._teams[league]


def find_leagues(text: str) -> list[str]:
    low = text.lower()
    return [lg for lg, words in LEAGUE_WORDS.items() if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)]


def find_teams(eng: Engine, text: str, leagues: list[str]) -> list[tuple[str, dict]]:
    """Teams mentioned in the text: every name/alias match, then the longest non-overlapping spans win
    (so "Ohio State" never resolves to "Ohio"). Searches the named league(s), else in-season leagues in priority order."""
    low = text.lower()  # same length as text, so spans line up
    for lg in leagues or SEARCH_ORDER:
        try:
            ts = eng.teams(lg)
        except Exception:
            continue
        cands = []
        for t in ts:
            for k in t["keys"]:
                for m in re.finditer(rf"\b{re.escape(k)}\b", low):
                    cands.append((m.start(), m.end(), t))
            if t.get("abbr"):
                for m in re.finditer(rf"\b{re.escape(t['abbr'])}\b", text):
                    cands.append((m.start(), m.end(), t))
        chosen: list[tuple[int, int, dict]] = []
        for st, en, t in sorted(cands, key=lambda c: -(c[1] - c[0])):
            if all(en <= a or st >= b for a, b, _ in chosen) and all(t["team_id"] != x["team_id"] for _, _, x in chosen):
                chosen.append((st, en, t))
        if chosen:
            return [(lg, t) for _, _, t in sorted(chosen, key=lambda c: c[0])]
    return []


# ---------------------------------------------------------------- intents

def team_status(eng: Engine, lg: str, t: dict) -> str:
    page = eng.get(f"/entities/team/{lg}/{t['team_id']}")
    st = next((r for r in eng.get(f"/competitions/{lg}/seasons/current/standings")["rows"] if r["team_id"] == t["team_id"]), None)
    tm = page["team"]
    qk, qname = QUALIFY.get(lg, ("playoffs", "playoffs"))
    lines = [f"**{tm['name']}** ({LEAGUE_NAME.get(lg, lg)})"]
    if st:
        lines.append(f"- Record: **{st['wins']}-{st['losses']}** ({st['conf_record']} in conference)")
    lines.append(f"- Expected wins: **{tm['expected_wins']:.1f}** (90% range {tm['wins_p05']:.0f}–{tm['wins_p95']:.0f})")
    lines.append(f"- Make the {qname}: **{pct(tm.get(qk))}** · win the {TITLE.get(lg, 'title')}: **{pct(tm.get('champion'))}**")
    lines.append(f"- Strength: {tm['rating']:+.1f} ± {tm['rating_sd']:.1f} vs an average team")
    live = next((g for g in page["remaining"] if g.get("state") == "in"), None)
    if live:
        mine, theirs = (live.get("home_score"), live.get("away_score")) if live["is_home"] else (live.get("away_score"), live.get("home_score"))
        lines.append(f"- **Live now** vs {live['away'] if live['is_home'] else live['home']}: {mine}–{theirs}, win probability **{pct(live.get('p_win'))}**")
    pre = [g for g in page["remaining"] if g.get("state") == "pre"]
    if pre:
        n = pre[0]
        lines.append(f"- Next: {'vs' if n['is_home'] else 'at'} {n['away'] if n['is_home'] else n['home']} on {n['start_time'][:10]} — **{pct(n.get('p_win'))}** to win")
        lev = lambda g: abs((g.get("leverage_home") if g["is_home"] else g.get("leverage_away")) or 0)  # noqa: E731
        big = max(pre, key=lev)
        if lev(big) >= 0.005:
            lines.append(f"- Biggest remaining game: {'vs' if big['is_home'] else 'at'} {big['away'] if big['is_home'] else big['home']} "
                         f"(win vs loss moves {qname} odds by **{lev(big) * 100:.1f} pts**)")
    lines.append(f"\nSource: SportsWorld season run `{page['season_run_id']}` (10,000 simulated seasons). {SITE}/{lg}/team/{t['team_id']}")
    return "\n".join(lines)


def outlook(eng: Engine, lg: str) -> str:
    if lg == "f1":
        run = eng.get("/competitions/f1/seasons/current/season-forecast")
        ds = sorted(run["drivers"], key=lambda d: -d["title"])[:5]
        body = "\n".join(f"{i + 1}. **{d['name']}** — {pct(d['title'])} (now {d['points_now']:.0f} pts, projected {d['expected_points']:.0f})" for i, d in enumerate(ds))
        return f"**F1 drivers' title** after round {run['standings_round']}:\n{body}\n\n{SITE}/f1"
    run = eng.get(f"/competitions/{lg}/seasons/current/season-forecast")
    ts = run["teams"][:6]
    qk, qname = QUALIFY.get(lg, ("playoffs", "playoffs"))
    body = "\n".join(f"{i + 1}. **{t['name']}** — {pct(t.get('champion'))} ± {pct(1.96 * float(t.get('champion_se') or 0))} · {qname} {pct(t.get(qk))}" for i, t in enumerate(ts))
    return f"**{TITLE.get(lg, 'Title')} favourites** ({run['draws']:,} simulated seasons, state v{run['global_state_version']}):\n{body}\n\n{SITE}/{lg}"


def board(eng: Engine, lg: str) -> list[dict]:
    return eng.get(f"/competitions/{lg}/seasons/current/forecast-board")["events"]


def lev(g: dict) -> float:
    return max(abs(g.get("leverage_home") or 0), abs(g.get("leverage_away") or 0))


def games_to_watch(eng: Engine, leagues: list[str], soon: bool = False) -> str:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=10 if soon else 36)
    out = []
    for lg in leagues or ["college-football", "nfl"]:
        if lg == "f1":
            continue
        gs = [g for g in board(eng, lg) if g["state"] == "in" or datetime.fromisoformat(g["start_time"].replace("Z", "+00:00")) < horizon]
        for g in gs:
            out.append((lg, g))
    if not out:
        return "No live or upcoming games in the next 36 hours for those leagues."
    # season stakes x closeness: a big-leverage game that is still in doubt is the one to watch
    score = lambda g: lev(g) * (1 - abs((g.get("p_home") or 0.5) - 0.5) * 1.4)  # noqa: E731
    top = sorted(out, key=lambda x: -score(x[1]))[:5]
    lines = ["**Games that matter most right now** (season leverage × how close the game is):"]
    for i, (lg, g) in enumerate(top):
        p = g.get("p_home")
        state = f"LIVE {g.get('away_score')}–{g.get('home_score')}" if g["state"] == "in" else g["start_time"][11:16] + " UTC"
        lines.append(f"{i + 1}. **{g['away']} @ {g['home']}** ({LEAGUE_NAME[lg]}, {state}) — home win {pct(p)}, swings playoff odds by up to **{lev(g) * 100:.0f} pts**")
    lines.append(f"\nMy pick: **{top[0][1]['away']} @ {top[0][1]['home']}**. Watch it live: {SITE}/{top[0][0]}/game/{top[0][1]['event_id']}")
    return "\n".join(lines)


def find_game(eng: Engine, lg: str, a: dict, b: dict | None = None) -> dict | None:
    gs = [g for g in board(eng, lg) if a["team_id"] in (g["home_id"], g["away_id"]) and (b is None or b["team_id"] in (g["home_id"], g["away_id"]))]
    return sorted(gs, key=lambda g: (g["state"] != "in", g["start_time"]))[0] if gs else None


def recent_final(eng: Engine, lg: str, a: dict, b: dict) -> str | None:
    page = eng.get(f"/entities/team/{lg}/{a['team_id']}")
    for r in reversed(page.get("recent_results") or []):
        if b["name"] in (r["home"], r["away"]):
            when = r["date"][:10]
            return (f"That game is already final ({when}): **{r['away']} {r['away_score']}, {r['home']} {r['home_score']}**. "
                    f"SportsWorld has already folded the result into both teams' strength and every season forecast. "
                    f"Ask *How are {a['short']} doing?* for the updated outlook.")
    return None


def matchup(eng: Engine, lg: str, a: dict, b: dict | None) -> str:
    g = find_game(eng, lg, a, b)
    if not g:
        fin = recent_final(eng, lg, a, b) if b else None
        return fin or (f"I couldn't find a remaining game for {a['name']}" + (f" against {b['name']}." if b else "."))
    p = g.get("p_home")
    fav, pf = (g["home"], p) if (p or 0) >= 0.5 else (g["away"], 1 - (p or 0))
    head = f"**{g['away']} @ {g['home']}** ({LEAGUE_NAME[lg]})"
    state = f"Live: {g.get('away_score')}–{g.get('home_score')}." if g["state"] == "in" else f"Kickoff {g['start_time'][:16].replace('T', ' ')} UTC."
    return (f"{head}\n{state} SportsWorld favours **{fav}** at **{pct(pf)}**"
            + (f" (pregame {pct(g.get('p_home_pregame'))} home)" if g["state"] == "in" else "")
            + f".\nSeason stakes: the result moves playoff odds by up to **{lev(g) * 100:.0f} pts**.\n{SITE}/{lg}/game/{g['event_id']}")


def compare(eng: Engine, picks: list[tuple[str, dict]]) -> str:
    games = []
    for lg, t in picks[:2]:
        g = find_game(eng, lg, t)
        if g:
            games.append((lg, g))
    if len(games) < 2:
        return "I need two teams with upcoming or live games to compare."
    closeness = lambda g: 1 - abs((g.get("p_home") or 0.5) - 0.5) * 2  # noqa: E731
    rows = [f"- **{g['away']} @ {g['home']}**: stakes {lev(g) * 100:.0f} pts, closeness {closeness(g) * 100:.0f}/100, home win {pct(g.get('p_home'))}" for _, g in games]
    best = max(games, key=lambda x: lev(x[1]) * (0.3 + closeness(x[1])))
    return ("**Head to head:**\n" + "\n".join(rows) + f"\n\nWatch **{best[1]['away']} @ {best[1]['home']}**: "
            f"it moves the race more for the closeness on offer. {SITE}/{best[0]}/game/{best[1]['event_id']}")


def forced_result(eng: Engine, lg: str, winner: dict, loser: dict) -> str | None:
    g = find_game(eng, lg, winner, loser)
    if not g or g["state"] != "pre":
        return recent_final(eng, lg, winner, loser) or (f"{winner['short']} and {loser['short']} have no upcoming game to force." if not g else
                f"{g['away']} @ {g['home']} is already under way; I can only force results of games that haven't started.")
    side = "home" if g["home_id"] == winner["team_id"] else "away"
    r = eng.post(f"/competitions/{lg}/seasons/current/season-simulations",
                 {"label": f"{winner['short']} beat {loser['short']}", "draws": 10000, "forced_results": {g["event_id"]: side}})
    return _scenario_summary(lg, r, [winner["team_id"], loser["team_id"]], f"{winner['short']} beat {loser['short']} ({g['start_time'][:10]})")


def what_if(eng: Engine, lg: str, text: str) -> str:
    r = eng.post(f"/competitions/{lg}/seasons/current/scenario/ask", {"text": text, "draws": 10000})
    if not r.get("base"):
        return ("I can simulate a key player missing games or a team getting stronger / weaker, e.g. "
                "*What if Michigan's starting QB misses 3 games?* " + ("; ".join(r.get("warnings") or [])))
    focus = [a["team_id"] for a in r.get("assumptions") or []]
    how = "; ".join(f"{a['team']}: {a.get('position') or 'strength'} {a['delta_points']:+.1f} pts ({a['delta_source']}) until {str(a['until'])[:10]}" for a in r["assumptions"])
    return _scenario_summary(lg, r, focus, how, parser=r.get("parser"))


def _scenario_summary(lg: str, r: dict, focus: list[str], label: str, parser: str | None = None) -> str:
    qk, qname = QUALIFY.get(lg, ("playoffs", "playoffs"))
    base = {t["team_id"]: t for t in r["base"]["teams"]}
    alt = {t["team_id"]: t for t in r["scenario"]["teams"]}
    ids = list(dict.fromkeys(focus + [d["team_id"] for d in r["deltas"][:4]]))[:5]
    rows = []
    for i in ids:
        b, a = base.get(i), alt.get(i)
        if not b or not a:
            continue
        rows.append(f"- **{a['name']}**: {qname} {pct(b.get(qk))} → **{pct(a.get(qk))}**, {TITLE.get(lg, 'title')} {pct(b.get('champion'))} → **{pct(a.get('champion'))}**, "
                    f"exp. wins {b['expected_wins']:.1f} → {a['expected_wins']:.1f}")
    return (f"**Scenario:** {label}\nRan {r['scenario']['draws']:,} simulated seasons per branch with common random numbers "
            f"(canonical state untouched){f'; parsed by {parser}' if parser else ''}.\n" + "\n".join(rows) + f"\n\nExplore it: {SITE}/{lg}/lab")


HELP = ("I'm **SportsWorld Analyst**: I run the live SportsWorld world model for every NFL, college football, NBA, NHL, college "
        "basketball and F1 season. Try:\n- *How are Michigan doing?*\n- *What if Michigan's starting QB misses 3 games?*\n"
        "- *What if Michigan beats Ohio State?*\n- *Which games matter tonight?*\n- *Should I watch BYU or Texas Tech?*\n"
        "- *Who wins Ohio State vs Iowa?*\n- *Who will win the Super Bowl?*")


def answer(text: str, eng: Engine | None = None) -> str:
    eng = eng or Engine()
    text = re.sub(r"@?agent1[0-9a-z]{20,}", " ", text)  # ASI:One prefixes the agent address
    low = re.sub(r"\s+", " ", text.lower()).strip()
    if not low or low in {"hi", "hello", "help", "hey"} or "what can you do" in low:
        return HELP
    leagues = find_leagues(low)
    try:
        teams = find_teams(eng, re.sub(r"\s+", " ", text).strip(), [lg for lg in leagues if lg != "f1"])
        lg = (leagues[0] if leagues else teams[0][0] if teams else "college-football")
        if lg == "f1" or (leagues and re.search(r"\b(win|favou?rite|odds|who will|chances?)\b", low) and not teams):
            return outlook(eng, lg)
        if re.search(r"\b(watch|matter|biggest|best games?|tonight|today)\b", low) and len(teams) < 2:
            return games_to_watch(eng, leagues, soon=bool(re.search(r"\b(tonight|today|now|right now)\b", low)))
        if re.search(r"\bwhat if\b|\bif\b.*\b(miss|out|injur|without|better|worse|stronger|weaker)", low):
            m = re.search(r"\b(beats?|wins? (?:against|over)|defeats?|upsets?)\b", low)
            if m and len(teams) >= 2:
                w, l_ = (teams[0][1], teams[1][1])
                res = forced_result(eng, teams[0][0], w, l_)
                if res:
                    return res
            m = re.search(r"\b(loses? to|falls? to)\b", low)
            if m and len(teams) >= 2:
                res = forced_result(eng, teams[0][0], teams[1][1], teams[0][1])
                if res:
                    return res
            return what_if(eng, lg, text)
        if re.search(r"\b(beats?|loses? to)\b", low) and len(teams) >= 2:
            res = forced_result(eng, teams[0][0], teams[0][1], teams[1][1]) if re.search(r"\bbeats?\b", low) else forced_result(eng, teams[0][0], teams[1][1], teams[0][1])
            if res:
                return res
        if len(teams) >= 2 and re.search(r"\b(or|versus)\b", low) and re.search(r"\bwatch|which\b", low):
            return compare(eng, teams)
        if len(teams) >= 2 or re.search(r"\b(vs\.?|versus|who wins|beat)\b", low) and teams:
            return matchup(eng, teams[0][0], teams[0][1], teams[1][1] if len(teams) > 1 else None)
        if teams:
            return team_status(eng, teams[0][0], teams[0][1])
        m = re.search(r"\bhow (?:is|are|'s)\s+(?:the\s+)?(.+?)\s+(?:doing|looking|playing)\b", low)
        if m:
            return (f"I couldn't match **{m.group(1)}** to a team. Try the school or team name, e.g. *How are Michigan doing?* "
                    f"or *How are the Detroit Lions doing?*")
        if leagues:
            return outlook(eng, leagues[0])
        return HELP
    except httpx.HTTPError as exc:
        return f"The SportsWorld engine is unreachable right now ({exc.__class__.__name__}). Please try again in a minute."
