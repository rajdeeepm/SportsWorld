"""News from several outlets (RSS), for the News tab and for availability extraction.

ESPN's own news API stays the primary feed (it carries ESPN's team tags). This adds public RSS feeds:
  * Yahoo Sports and CBS Sports league headlines,
  * On3's league feed and, for college football, On3's per-team feeds, which publish the conference
    availability reports (e.g. the Big Ten's four weekly reports) as articles with the full text.
Team feeds are polled in rotation, a slice per cycle, so 130+ teams cost a few requests a minute.
Only injury-related articles are passed on for extraction; everything is kept for display.
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

def _gn(q: str) -> str:
    from urllib.parse import quote_plus
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"


# Google News aggregates hundreds of outlets (each item names its outlet); Barstool has no RSS of its own, so it
# comes in through a Google News site search. Reddit is a fan community: shown on the News tab, never extracted.
EXTRA_FEEDS: dict[str, list[tuple[str, str]]] = {
    "college-football": [("Google News", _gn("college football when:2d")), ("Google News", _gn('college football (injury OR "availability report" OR "ruled out") when:2d')),
                         ("Barstool Sports", _gn("site:barstoolsports.com college football when:7d")), ("Reddit r/CFB", "https://www.reddit.com/r/CFB/new/.rss")],
    "nfl": [("Google News", _gn("NFL when:2d")), ("Google News", _gn('NFL injury report (out OR doubtful OR questionable) when:2d')),
            ("Barstool Sports", _gn("site:barstoolsports.com NFL when:7d")), ("Reddit r/nfl", "https://www.reddit.com/r/nfl/new/.rss")],
    "nba": [("Google News", _gn("NBA when:2d")), ("Google News", _gn("NBA injury when:2d")), ("Reddit r/nba", "https://www.reddit.com/r/nba/new/.rss")],
    "nhl": [("Google News", _gn("NHL when:2d")), ("Google News", _gn("NHL injury when:2d")), ("Reddit r/hockey", "https://www.reddit.com/r/hockey/new/.rss")],
    "mens-college-basketball": [("Google News", _gn("college basketball when:2d"))],
}
LEAGUE_WORDS = {"college-football": r"college football|\bCFB\b|Heisman|\bCFP\b|bowl game", "nfl": r"\bNFL\b|Super Bowl", "nba": r"\bNBA\b",
                "nhl": r"\bNHL\b|Stanley Cup", "mens-college-basketball": r"college basketball|March Madness"}
MERCH = re.compile(r"\b(Tee|Hoodie|Crewneck|Quarter Zip|Hat|Polo)\b|Blogs & Videos|^[^ ]+( [^ ]+)? - barstoolsports\.com$", re.I)


def relevant(a: dict, league: str, team_words: re.Pattern | None) -> bool:
    """Broad sources (Barstool, Reddit) only count when the item is about this league."""
    t = a["headline"]
    if a["source"] == "Barstool Sports":
        t = re.sub(r"\s*-\s*barstoolsports\.com$", "", t)
        a["headline"] = t
        if MERCH.search(a["headline"] + " - barstoolsports.com") or len(t.split()) < 4:
            return False
        return bool(re.search(LEAGUE_WORDS.get(league, "$^"), t, re.I) or (team_words and team_words.search(t)))
    if a["source"].startswith("Reddit"):
        return not re.match(r"\[(Game Thread|Postgame Thread|Pregame Thread)\]", t)
    return True


NO_EXTRACT = {"Reddit r/CFB", "Reddit r/nfl", "Reddit r/nba", "Reddit r/hockey"}

LEAGUE_FEEDS: dict[str, list[tuple[str, str]]] = {
    "college-football": [("Yahoo Sports", "https://sports.yahoo.com/college-football/rss.xml"),
                         ("CBS Sports", "https://www.cbssports.com/rss/headlines/college-football/"),
                         ("On3", "https://www.on3.com/feed/")],
    "nfl": [("Yahoo Sports", "https://sports.yahoo.com/nfl/rss.xml"), ("CBS Sports", "https://www.cbssports.com/rss/headlines/nfl/")],
    "nba": [("Yahoo Sports", "https://sports.yahoo.com/nba/rss.xml"), ("CBS Sports", "https://www.cbssports.com/rss/headlines/nba/")],
    "nhl": [("Yahoo Sports", "https://sports.yahoo.com/nhl/rss.xml"), ("CBS Sports", "https://www.cbssports.com/rss/headlines/nhl/")],
    "mens-college-basketball": [("Yahoo Sports", "https://sports.yahoo.com/college-basketball/rss.xml"),
                                ("CBS Sports", "https://www.cbssports.com/rss/headlines/college-basketball/")],
}
TEAM_FEED_LEAGUES = {"college-football"}  # On3 team feeds
INJURY = re.compile(r"injur|availability|ruled out|\bout for\b|questionable|doubtful|game-time decision|suspend|return(s|ing)? from|sidelined|\bwon't play\b|will miss", re.I)
TEAMS_PER_CYCLE = 24


def _clean(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def _tag(item: str, name: str) -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", item, re.S)
    return _clean(m.group(1)) if m else ""


def parse_rss(xml: str, source: str, team_id: str | None = None) -> list[dict[str, Any]]:
    out = []
    atom = "<entry" in xml and "<item" not in xml
    for item in re.findall(r"<entry\b[^>]*>(.*?)</entry>" if atom else r"<item\b[^>]*>(.*?)</item>", xml, re.S):
        if atom:  # Atom (Reddit): <link href>, <updated>, <content>
            lm = re.search(r'<link[^>]*href="([^"]+)"', item)
            item = item.replace("<updated>", "<pubDate>").replace("</updated>", "</pubDate>").replace("<content", "<content:encoded").replace("</content>", "</content:encoded>")
            link = html.unescape(lm.group(1)) if lm else ""
        else:
            link = _tag(item, "link") or _tag(item, "guid")
        title = _tag(item, "title")
        outlet = _tag(item, "source")  # Google News names the original outlet
        src = f"{outlet} via Google News" if source == "Google News" and outlet else source
        if source == "Google News" and outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3]
        if not title or not link:
            continue
        try:
            raw = _tag(item, "pubDate")
            published = (datetime.fromisoformat(raw.replace("Z", "+00:00")) if atom else parsedate_to_datetime(raw)).astimezone(timezone.utc).isoformat()
        except Exception:
            published = None
        body = _tag(item, "content:encoded")
        desc = _tag(item, "description")
        img = re.search(r'<media:(?:content|thumbnail)[^>]*url="([^"]+)"', item) or re.search(r'<enclosure[^>]*url="([^"]+)"', item)
        out.append({"article_id": "rss-" + hashlib.blake2b(link.encode(), digest_size=8).hexdigest(), "source": src,
                    "headline": title, "description": desc[:400], "body": body[:6000] if len(body) > len(desc) else "",
                    "published": published, "url": link, "image": img.group(1) if img else None,
                    "team_ids": [team_id] if team_id else [], "tagged_by": "feed" if team_id else None})
    return out


def on3_slug(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", "").replace("(", "").replace(")", "").replace(".", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


class FeedHub:
    """Keeps the latest articles per league from every outlet; the news service reads from here."""

    def __init__(self) -> None:
        self.articles: dict[str, dict[str, dict]] = {}
        self.cursor: dict[str, int] = {}
        self.bad_slugs: set[str] = set()
        self.errors: dict[str, str] = {}

    async def refresh(self, client: httpx.AsyncClient, league: str, teams: list[dict]) -> list[dict]:
        got: list[dict] = []
        for source, url in LEAGUE_FEEDS.get(league, []) + EXTRA_FEEDS.get(league, []):
            try:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (SportsWorld news reader)"}, follow_redirects=True)
                r.raise_for_status()
                got += parse_rss(r.text, source)
            except Exception as exc:
                self.errors[f"{league}:{source}"] = str(exc)[:120]
        if league in TEAM_FEED_LEAGUES and teams:
            first = league not in self.cursor  # first cycle: every team once, then a rotating slice
            i = self.cursor.get(league, 0)
            batch = teams if first else [teams[(i + k) % len(teams)] for k in range(min(TEAMS_PER_CYCLE, len(teams)))]
            self.cursor[league] = 0 if first else (i + len(batch)) % len(teams)
            for t in batch:
                slug = on3_slug(t["name"])
                if slug in self.bad_slugs:
                    continue
                try:
                    r = await client.get(f"https://www.on3.com/teams/{slug}/feed/", headers={"User-Agent": "Mozilla/5.0 (SportsWorld news reader)"}, follow_redirects=True)
                    if r.status_code == 404:
                        self.bad_slugs.add(slug)
                        continue
                    r.raise_for_status()
                    got += parse_rss(r.text, "On3", team_id=t["team_id"])
                except Exception as exc:
                    self.errors[f"{league}:on3:{slug}"] = str(exc)[:120]
        words = [re.escape(t["name"].rsplit(" ", 1)[0]) for t in teams if len(t["name"].rsplit(" ", 1)[0]) > 3]
        team_words = re.compile(r"\b(" + "|".join(sorted(words, key=len, reverse=True)) + r")\b") if words else None
        got = [a for a in got if relevant(a, league, team_words)]
        book = self.articles.setdefault(league, {})
        cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        for a in got:
            if a["published"] and a["published"] < cutoff:
                continue
            prev = book.get(a["article_id"])
            if prev and prev["team_ids"] and not a["team_ids"]:
                continue  # keep the team-feed copy (it carries the team tag)
            book[a["article_id"]] = a
        if len(book) > 1500:
            for k in sorted(book, key=lambda k: book[k]["published"] or "")[: len(book) - 1500]:
                book.pop(k, None)
        return got

    def latest(self, league: str, limit: int = 60) -> list[dict]:
        return sorted(self.articles.get(league, {}).values(), key=lambda a: a["published"] or "", reverse=True)[:limit]

    @staticmethod
    def injury_related(a: dict) -> bool:
        if a["source"] in NO_EXTRACT:
            return False
        return bool(INJURY.search(a["headline"]) or INJURY.search(a.get("description") or ""))
