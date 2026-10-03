"""Public news -> typed, source-attributed context evidence via Llama (spec §9, §11.1 news/context agent).

Pipeline per article (ESPN news API, polled):
  1. Llama 3.3 70B extracts candidate signals under a strict JSON schema (vLLM guided decoding).
  2. Grounding gate: every signal must quote an `evidence_span` that appears verbatim in the article;
     otherwise it is rejected (no hallucinated facts can enter state).
  3. Entity resolution: team names must resolve to a team in the competition; player names are kept
     as reported.
  4. Signals are stored with effect STATE_ONLY (display + provenance): per spec §9.1 public narrative
     must prove incremental value in the A4 ablation before it may move an authoritative probability.
  5. Source disagreement (spec §9.2): an availability signal is compared with the official injury
     report for that player; conflicts are flagged and surfaced, never silently resolved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from sportsworld.llm.client import LLMClient, LLMUnavailable

from .espn import BASE
from .leagues import LEAGUES

PARSER_VERSION = "news-llama-v1"
SCHEMA = {
    "type": "object",
    "properties": {"signals": {"type": "array", "items": {"type": "object", "properties": {
        "category": {"type": "string", "enum": ["availability", "return_from_injury", "suspension", "coaching_change", "trade_or_signing",
                                                "lineup_or_depth_chart", "weather_or_venue", "other"]},
        "team": {"type": "string"}, "player": {"type": ["string", "null"]},
        "status": {"type": ["string", "null"], "enum": ["out", "doubtful", "questionable", "probable", "available", "returning", "suspended", None]},
        "games_affected": {"type": ["integer", "null"]},
        "evidence_span": {"type": "string"},
        "confidence": {"type": "number"},
    }, "required": ["category", "team", "evidence_span"], "additionalProperties": False}}},
    "required": ["signals"], "additionalProperties": False,
}
SYSTEM = ("You extract structured, verifiable sports context from ONE news item. Only report facts explicitly stated in the text. "
          "evidence_span must be an exact substring copied from the text that supports the signal. confidence in [0,1] reflects how "
          "explicitly the text states it (rumor/speculation < 0.5). Never infer feelings, motivation or private medical details. "
          "If nothing relevant to team strength or availability is stated, return an empty list.")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


class LeagueNews:
    def __init__(self, league: str, data_root: Path):
        self.league = league
        self.path = data_root / "news" / f"{league}.jsonl"
        self.signals: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.signals.append(rec)
                    self.seen.add(rec["article_id"])

    async def fetch(self, client: httpx.AsyncClient, limit: int = 40) -> list[dict]:
        spec = LEAGUES[self.league]
        r = await client.get(f"{BASE}/{spec.espn_path}/news", params={"limit": limit})
        r.raise_for_status()
        out = []
        for a in r.json().get("articles", []):
            aid = str(a.get("id") or a.get("dataSourceIdentifier") or a.get("headline"))
            teams = [c.get("description") for c in a.get("categories", []) if c.get("type") == "team"]
            out.append({"article_id": aid, "headline": a.get("headline") or "", "description": a.get("description") or "",
                        "published": a.get("published"), "url": ((a.get("links") or {}).get("web") or {}).get("href"), "teams": teams})
        return out

    def extract(self, llm: LLMClient, article: dict, teams: list[dict], report: dict[str, list[dict]] | None) -> list[dict]:
        from sportsworld.llm.season_scenario import resolve_team
        text = f"{article['headline']}. {article['description']}".strip()
        raw = llm.json_call(SYSTEM, json.dumps({"league": self.league, "text": text}), SCHEMA, name="news_signals", max_tokens=600)
        now = datetime.now(timezone.utc).isoformat()
        out = []
        seen_keys: set[tuple] = set()
        for sig in raw.get("signals", []):
            if not isinstance(sig, dict) or set(SCHEMA["properties"]["signals"]["items"]["required"]) - set(sig):
                continue  # local schema validation (do not trust the server's guided decoding alone)
            if sig.get("category") not in SCHEMA["properties"]["signals"]["items"]["properties"]["category"]["enum"]:
                continue
            span = sig.get("evidence_span") or ""
            if not span or " ".join(span.split()) not in " ".join(text.split()):
                continue  # grounding gate: verbatim (case-sensitive; whitespace-normalised only)
            player = (sig.get("player") or "").strip()
            if player and _norm(player.split()[-1]) not in _norm(span):
                continue  # the quoted evidence must itself name the player the claim is about
            team = resolve_team(sig.get("team") or "", teams)
            rec = {"article_id": article["article_id"], "league": self.league, "category": sig["category"],
                   "team_id": team["team_id"] if team else None, "team": team["name"] if team else sig.get("team"),
                   "player": sig.get("player"), "status": sig.get("status"), "games_affected": sig.get("games_affected"),
                   "evidence_span": span, "llm_confidence": max(0.0, min(1.0, float(sig.get("confidence", 0.5)))),
                   "headline": article["headline"], "source_url": article.get("url"), "published": article.get("published"),
                   "known_to_model_time": now, "source_id": "espn-news", "parser_version": PARSER_VERSION, "model": llm.model,
                   "effect": "state_only", "disagreement": None}
            if rec["category"] in ("availability", "return_from_injury", "suspension") and rec["player"] and report is not None and team:
                official = next((r for r in report.get(team["team_id"], []) if _norm(r.get("name") or "") == _norm(rec["player"])), None)
                if official is not None and rec["status"]:
                    off = _norm(official.get("status") or "")
                    news_out = rec["status"] in ("out", "suspended", "doubtful")
                    off_out = off.startswith(("out", "injured reserve", "suspension", "doubtful"))
                    if news_out != off_out:
                        rec["disagreement"] = {"official_status": official.get("status"), "official_reported_at": official.get("reported_at"),
                                               "news_status": rec["status"], "note": "sources disagree; uncertainty should rise, not be averaged away"}
            key = (rec["team_id"] or rec["team"], _norm(rec["player"] or ""), rec["category"], rec["status"])
            if key in seen_keys:
                continue  # same claim restated within one article
            seen_keys.add(key)
            out.append(rec)
        return out

    def append(self, recs: list[dict], article_id: str) -> None:
        self.seen.add(article_id)
        self.signals.extend(recs)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
            if not recs:
                fh.write(json.dumps({"article_id": article_id, "league": self.league, "category": "none", "known_to_model_time": datetime.now(timezone.utc).isoformat()}) + "\n")


class NewsService:
    def __init__(self, leagues: list[str], data_root: Path, llm: LLMClient, teams_for, report_for=None, on_signal=None):
        self.books = {lg: LeagueNews(lg, data_root) for lg in leagues if lg in LEAGUES and LEAGUES[lg].espn_path}
        self.llm = llm
        self.teams_for = teams_for          # league -> [{"team_id","name","abbreviation"}]
        self.report_for = report_for        # league -> {team_id: injury rows} | None
        self.on_signal = on_signal
        self.error: str | None = None
        self.processed = 0

    async def refresh(self) -> None:
        if not self.llm.enabled:
            self.error = "LLM not configured"
            return
        import asyncio
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "SportsWorld/1.3"}) as client:
            for lg, book in self.books.items():
                try:
                    arts = await book.fetch(client)
                except Exception as exc:
                    self.error = f"{lg}: {exc}"
                    continue
                for art in arts:
                    if art["article_id"] in book.seen:
                        continue
                    if "fantasy" in art["headline"].lower():  # ranking/advice pieces: no first-hand availability facts
                        book.append([], art["article_id"])
                        continue
                    try:
                        recs = await asyncio.get_running_loop().run_in_executor(None, book.extract, self.llm, art, self.teams_for(lg), self.report_for(lg) if self.report_for else None)
                    except (LLMUnavailable, ValueError, KeyError) as exc:
                        self.error = f"extract: {exc}"
                        return
                    book.append(recs, art["article_id"])
                    self.processed += 1
                    if recs and self.on_signal:
                        self.on_signal(lg, recs)

    def status(self) -> dict:
        return {"processed_articles": self.processed, "error": self.error, "llm": self.llm.model,
                "signals": {lg: sum(1 for s in b.signals if s.get("category") != "none") for lg, b in self.books.items()}}
