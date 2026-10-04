"""Live player availability -> team strength deltas (spec §9.1 availability/health, §15.3 entity-availability recompute).

Evidence: ESPN league injury report (`/apis/site/v2/sports/<path>/injuries`), polled live.
Impact: learned per-absence effect from player participation (models/artifacts/player_impact/<league>.json),
applied only to each team's *established key players* (starting QB, top-minutes players, starting goalie).

    delta_team = sum_key_players beta_pos * (1 - P(plays | report status))

STATUS_P_PLAY is an explicit, documented prior mapping (report status -> probability of playing);
it is not yet calibrated against outcomes and is labelled as such in every evidence record.
Historical ESPN summaries expose only *current* injury lists, so no historical injury feature is
ever used in training (that would leak); the learned beta comes from ex-post participation.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from .espn import BASE
from .leagues import LEAGUES

STATUS_P_PLAY = {  # prior; labelled "uncalibrated_prior_v1"
    "out": 0.0, "injured reserve": 0.0, "suspension": 0.0, "physically unable to perform": 0.0, "non-football injury": 0.0,
    "doubtful": 0.25, "questionable": 0.5, "day-to-day": 0.6, "game-time decision": 0.5, "probable": 0.85, "active": 1.0,
}
LONG_TERM = {"injured reserve", "physically unable to perform", "suspension", "non-football injury"}


def p_play(status: str) -> float:
    s = (status or "").lower().strip()
    for k, v in STATUS_P_PLAY.items():
        if s.startswith(k):
            return v
    return 1.0


def name_key(name: str) -> str:
    """Comparable player name: lower case, no punctuation or generational suffix ('Alex Afari Jr.' == 'Alex Afari')."""
    s = re.sub(r"[.,']", "", (name or "").lower())
    s = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", " ".join(s.split()))
    return s


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


class LeagueAvailability:
    def __init__(self, league: str):
        self.league = league
        p = _repo() / "models" / "artifacts" / "player_impact" / f"{league}.json"
        self.impact = json.loads(p.read_text()) if p.exists() else {}
        self.keys: dict[str, dict[str, list[dict]]] = self.impact.get("current_key_players", {})
        self.report: dict[str, list[dict]] = {}
        # grounded availability from other outlets (conference availability reports via On3, etc.): {team_id: {player_norm: row}}
        self.news_rows: dict[str, dict[str, dict]] = {}
        self.deltas: dict[str, dict[str, Any]] = {}
        self.fetched_at: datetime | None = None
        self.error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.impact.get("by_position")) and bool(self.keys)

    async def refresh(self, client: httpx.AsyncClient) -> dict[str, dict]:
        """Fetch the league injury report; return {team_id: new_delta_record} for teams whose delta changed."""
        spec = LEAGUES[self.league]
        r = await client.get(f"{BASE}/{spec.espn_path}/injuries")
        r.raise_for_status()
        data = r.json()
        now = datetime.now(timezone.utc)
        if not data.get("injuries"):
            raise ValueError("empty injury report; keeping previous state (not treated as 'everyone healthy')")
        report: dict[str, list[dict]] = {}
        for team in data.get("injuries", []):
            tid = str(team.get("id") or "")
            rows = []
            for i in team.get("injuries", []):
                a = i.get("athlete", {})
                rows.append({"athlete_id": str(a.get("id") or (a.get("links") or [{}])[0].get("href", "").split("/id/")[-1].split("/")[0]),
                             "name": a.get("displayName"), "position": (a.get("position") or {}).get("abbreviation"),
                             "status": i.get("status"), "reported_at": i.get("date"), "detail": (i.get("details") or {}).get("type")})
            report[tid] = rows
        self.report, self.fetched_at, self.error = report, now, None
        return self.recompute(now)

    def rows_for(self, team_id: str) -> list[dict]:
        """Official report rows first; a news-reported player is added only when the official report does not list them."""
        rows = list(self.report.get(team_id, []))
        have = {name_key(r.get("name") or "") for r in rows}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        for k, r in self.news_rows.get(team_id, {}).items():
            if k not in have and (r.get("reported_at") or "") >= cutoff:
                rows.append(r)
        return rows

    def add_news(self, sig: dict) -> bool:
        """Record one grounded news signal about a player's status; True if it changed what we hold."""
        if sig.get("category") not in ("availability", "return_from_injury", "suspension") or not sig.get("team_id") or not sig.get("player") or not sig.get("status"):
            return False
        status = {"available": "active", "returning": "active", "suspended": "suspension"}.get(sig["status"], sig["status"])
        key = name_key(sig["player"])
        team_rows = self.news_rows.setdefault(sig["team_id"], {})
        if " " not in key:  # surname only ("Heintschel"): attach to the full name we already hold
            key = next((k for k in team_rows if k.endswith(" " + key)), key)
        else:
            team_rows.pop(key.split()[-1], None)
        when = sig.get("published") or sig.get("known_to_model_time")
        old = team_rows.get(key)
        if old and (old.get("reported_at") or "") > (when or ""):
            return False
        self.news_rows[sig["team_id"]][key] = {"athlete_id": "", "name": sig["player"], "position": None, "status": status.capitalize(),
                                               "reported_at": when, "detail": None, "source_id": sig.get("source_id") or "news",
                                               "source": sig.get("source") or ("ESPN news" if sig.get("source_id") == "espn-news" else "News"), "source_url": sig.get("source_url"),
                                               "evidence_span": sig.get("evidence_span"), "headline": sig.get("headline")}
        return True

    def recompute(self, now: datetime | None = None) -> dict[str, dict]:
        now = now or datetime.now(timezone.utc)
        if self.fetched_at is None:
            self.fetched_at = now  # news-only leagues (thin official report) still count as fresh
        changed = {}
        for tid, keys in self.keys.items():
            rec = self.team_delta(tid, self.rows_for(tid), now)
            old = self.deltas.get(tid)
            if (old or {}).get("delta_points", 0.0) != rec["delta_points"] or (old is None and rec["absences"]):
                changed[tid] = rec
            self.deltas[tid] = rec
        return changed

    def team_delta(self, team_id: str, rows: list[dict], now: datetime) -> dict[str, Any]:
        by_pos = self.impact.get("by_position", {})
        by_id = {r["athlete_id"]: r for r in rows}
        by_name = {name_key(r["name"] or ""): r for r in rows}
        absences, total, long_term = [], 0.0, False
        for pos, players in self.keys.get(team_id, {}).items():
            est = by_pos.get(pos, {})
            beta = est.get("points")
            if beta is None or est.get("significant") is False:  # unproven roles never move a forecast
                continue
            for pl in players:
                r = by_id.get(pl["athlete_id"]) or by_name.get(name_key(pl["name"] or ""))
                if not r:
                    continue
                pp = p_play(r["status"])
                if pp >= 1.0:
                    continue
                d = beta * (1.0 - pp)
                total += d
                long_term |= (r["status"] or "").lower() in LONG_TERM
                absences.append({"player": pl["name"], "athlete_id": pl["athlete_id"], "role": pos, "status": r["status"], "p_play": pp,
                                 "beta": beta, "delta_points": round(d, 3), "reported_at": r.get("reported_at"),
                                 "source_id": r.get("source_id") or "espn-injuries", "source_url": r.get("source_url"),
                                 "status_mapping": "uncalibrated_prior_v1"})
        reported = [a["reported_at"] for a in absences if a.get("reported_at")]
        return {"team_id": team_id, "delta_points": round(total, 3), "absences": absences, "known_to_model_time": now.isoformat(),
                "window_days": 28 if long_term else None, "window_anchor": min(reported) if reported else now.isoformat(),
                "impact_model": self.impact.get("model_version")}

    STALE_AFTER = timedelta(hours=3)

    def is_stale(self) -> bool:
        return self.fetched_at is None or datetime.now(timezone.utc) - self.fetched_at > self.STALE_AFTER

    def delta_for(self, team_id: str, start: datetime, next_game: datetime | None) -> float:
        """Delta applying to a game at `start`: next game only, or 28 days from the report for long-term absences.
        A stale report (no successful fetch for 3 h) contributes nothing rather than freezing old absences."""
        rec = self.deltas.get(team_id)
        if not rec or not rec["delta_points"] or self.is_stale():
            return 0.0
        if rec.get("window_days"):
            anchor = datetime.fromisoformat(str(rec.get("window_anchor") or self.fetched_at.isoformat()).replace("Z", "+00:00"))
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=timezone.utc)
            return rec["delta_points"] if start <= anchor + timedelta(days=rec["window_days"]) else 0.0
        return rec["delta_points"] if next_game is not None and start <= next_game else 0.0


class AvailabilityService:
    def __init__(self, leagues: list[str], on_change: Callable[[str, dict[str, dict]], None] | None = None):
        self.books = {lg: LeagueAvailability(lg) for lg in leagues if lg in LEAGUES and LEAGUES[lg].espn_path}
        self.books = {k: v for k, v in self.books.items() if v.enabled}
        self.on_change = on_change

    async def refresh_all(self) -> None:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "SportsWorld/1.3"}) as client:
            for lg, book in self.books.items():
                try:
                    changed = await book.refresh(client)
                except Exception as exc:
                    book.error = f"{type(exc).__name__}: {exc}"
                    continue
                if changed and self.on_change:
                    self.on_change(lg, changed)

    def full_report(self, league: str, names: dict[str, str]) -> list[dict]:
        """Every listed player for every team, each marked with whether (and why) it moves the forecast."""
        b = self.books.get(league)
        if not b:
            return []
        by_pos = b.impact.get("by_position", {})
        out = []
        for tid in sorted(set(b.report) | set(b.news_rows)):
            key_of = {}
            for pos, players in b.keys.get(tid, {}).items():
                for pl in players:
                    key_of[name_key(pl["name"] or "")] = pos
            priced = {name_key(a["player"] or ""): a for a in b.deltas.get(tid, {}).get("absences", [])}
            rows = []
            for r in b.rows_for(tid):
                k = name_key(r.get("name") or "")
                pos = key_of.get(k)
                est = by_pos.get(pos or "", {})
                a = priced.get(k)
                if p_play(r.get("status")) >= 1.0:
                    effect, why = 0.0, "available"
                elif a:
                    effect, why = a["delta_points"], f"established {pos}: learned effect {est.get('points', 0):+.1f} ± {est.get('se', 0):.1f} pts, weighted by P(plays)"
                elif pos and est.get("significant") is False:
                    effect, why = 0.0, f"established {pos}, but that role's effect is not statistically significant"
                elif pos and p_play(r.get("status")) >= 1.0:
                    effect, why = 0.0, "available"
                else:
                    effect, why = 0.0, "not priced: role has no measured effect"
                rows.append({**{k2: r.get(k2) for k2 in ("name", "position", "status", "reported_at", "detail", "source_url", "evidence_span", "headline")},
                             "source": r.get("source") or "ESPN injury report", "role": pos, "effect_points": effect, "why": why})
            if rows:
                rows.sort(key=lambda x: (x["effect_points"] == 0, p_play(x["status"]), x["name"] or ""))
                out.append({"team_id": tid, "team": names.get(tid, tid), "delta_points": b.deltas.get(tid, {}).get("delta_points", 0.0), "players": rows})
        out.sort(key=lambda t: (t["delta_points"], -len(t["players"])))
        return out

    def status(self) -> dict:
        return {lg: {"teams_with_absences": sum(1 for d in b.deltas.values() if d["absences"]), "fetched_at": b.fetched_at.isoformat() if b.fetched_at else None,
                     "impact_model": b.impact.get("model_version"), "error": b.error} for lg, b in self.books.items()}
