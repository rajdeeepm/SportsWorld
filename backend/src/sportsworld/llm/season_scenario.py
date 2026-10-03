"""Natural language -> typed season scenario (spec §23.2).

Llama only proposes structure: which team, what kind of change, for how many games.
Team names are resolved deterministically against the season's actual team list; the
size of a player absence comes from the learned player-impact table when available
(models/artifacts/player_impact/<league>.json), otherwise the proposal must carry an
explicit user-stated delta or it is rejected. The LLM never supplies a probability.
"""
from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sportsworld.season.engine import SeasonScenario

from .client import LLMClient, LLMUnavailable

SCHEMA = {
    "type": "object",
    "properties": {
        "operations": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["player_unavailable", "team_strength_shift", "force_result"]},
            "team": {"type": "string"},
            "position": {"type": ["string", "null"]},
            "player": {"type": ["string", "null"]},
            "games": {"type": ["integer", "null"]},
            "weeks": {"type": ["integer", "null"]},
            "delta_points": {"type": ["number", "null"]},
            "opponent": {"type": ["string", "null"]},
        }, "required": ["kind", "team"], "additionalProperties": False}},  # minimal required: forcing every field makes guided decoding emit whitespace until max_tokens
        "unsupported": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["operations", "unsupported"], "additionalProperties": False,
}

SYSTEM = (
    "You convert a sports 'what if' question into typed JSON operations for a season simulator. "
    "Use only the kinds in the schema. player_unavailable = a named player or role (e.g. starting QB) misses games; "
    "team_strength_shift = a team gets better/worse by an explicit number of points the user stated; "
    "force_result = assume team beats opponent in their next meeting. "
    "Copy team names as the user wrote them. Never estimate probabilities or effect sizes the user did not state "
    "(leave delta_points null). Put anything you cannot represent in 'unsupported'."
)


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def load_player_impact(league: str) -> dict:
    p = _repo() / "models" / "artifacts" / "player_impact" / f"{league}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def normalize_role(position: str | None, player: str | None) -> str:
    """Map free-text role descriptions onto the learned impact table's keys."""
    t = f"{position or ''} {player or ''}".lower()
    if "quarterback" in t or "qb" in t.split() or "qb" in t:
        return "QB"
    if "goalie" in t or "goaltender" in t or "netminder" in t:
        return "G"
    return "KEY"


def resolve_team(name: str, teams: list[dict]) -> dict | None:
    low = name.lower().strip()
    for t in teams:
        if low in {t["name"].lower(), str(t.get("abbreviation") or "").lower()}:
            return t
    for t in teams:  # nickname / school name containment
        if low and (low in t["name"].lower() or t["name"].lower().split()[-1] == low):
            return t
    match = difflib.get_close_matches(low, [t["name"].lower() for t in teams], n=1, cutoff=0.6)
    return next((t for t in teams if t["name"].lower() == match[0]), None) if match else None


_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "a couple of": "2", "a few": "3"}


def rules_parse(text: str) -> dict:
    """Deterministic fallback for the common phrasings."""
    low = text.lower()
    for w, n in _NUM.items():
        low = re.sub(rf"\b{w}\b", n, low)
    ops = []
    m = re.search(r"what if (?:the )?(.+?)(?:'s|s')?\s+(starting quarterback|starting qb|quarterback|qb|star|best player|goalie)\s+(?:is |are )?(?:out|misses|miss|injured|unavailable)(?:.*?(\d+)\s+(games|weeks))?", low)
    if m:
        unit = m.group(4)
        ops.append({"kind": "player_unavailable", "team": m.group(1).strip(), "position": "QB" if "q" in m.group(2) else m.group(2),
                    "player": None, "games": int(m.group(3)) if unit == "games" else None, "weeks": int(m.group(3)) if unit == "weeks" else None,
                    "delta_points": None, "opponent": None})
    m = re.search(r"(.+?)\s+(?:gets|get|is|are)\s+(better|worse)\s+by\s+([\d.]+)\s*(?:points|pts)", low)
    if m:
        d = float(m.group(3)) * (1 if m.group(2) == "better" else -1)
        ops.append({"kind": "team_strength_shift", "team": m.group(1).replace("what if", "").strip(), "position": None, "player": None,
                    "games": None, "weeks": None, "delta_points": d, "opponent": None})
    return {"operations": ops, "unsupported": [] if ops else [text]}


def parse_season_scenario(text: str, league: str, teams: list[dict], client: LLMClient | None, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    parser = "deterministic-rules-v1"
    warnings: list[str] = []
    try:
        if client is None or not client.enabled:
            raise LLMUnavailable("LLM disabled")
        raw = client.json_call(SYSTEM, json.dumps({"league": league, "question": text}), SCHEMA, name="season_scenario")
        parser = f"llm:{client.model}"
    except (LLMUnavailable, ValueError, KeyError) as exc:
        raw = rules_parse(text)
        warnings.append(f"LLM unavailable, deterministic parser used ({exc})")
    impact = load_player_impact(league)
    shifts, assumptions = [], []
    for op in raw.get("operations", []):
        team = resolve_team(op.get("team") or "", teams)
        if team is None:
            warnings.append(f"could not resolve team '{op.get('team')}'")
            continue
        weeks = op.get("weeks") or (op.get("games") if league in ("nfl", "college-football") else None)
        days = 7 * weeks if weeks else (2.2 * op["games"] if op.get("games") else None)  # basketball/hockey ≈ 1 game / 2.2 days
        end = now + timedelta(days=days) if days else None
        if op.get("kind") == "player_unavailable":
            pos = normalize_role(op.get("position"), op.get("player"))
            est = impact.get("by_position", {}).get(pos) or impact.get("by_position", {}).get("KEY")
            if op.get("delta_points") is not None:
                delta, source = float(op["delta_points"]), "user-stated"
            elif est:
                delta, source = float(est["points"]), f"learned player-impact ({impact.get('model_version')}, ±{est.get('se', 0):.1f})"
            else:
                warnings.append(f"no learned impact for {pos} in {league}; state a point delta explicitly")
                continue
        elif op.get("kind") == "team_strength_shift":
            if op.get("delta_points") is None:
                warnings.append("team strength change needs an explicit point value")
                continue
            delta, source = float(op["delta_points"]), "user-stated"
        else:
            warnings.append("force_result needs an event id; use the board's typed control")
            continue
        shifts.append((team["team_id"], delta, None, end))
        assumptions.append({"team": team["name"], "team_id": team["team_id"], "kind": op.get("kind"),
                            "position": normalize_role(op.get("position"), op.get("player")) if op.get("kind") == "player_unavailable" else None,
                            "player": op.get("player"), "delta_points": round(delta, 2), "delta_source": source,
                            "until": end.isoformat() if end else "rest of season"})
    for u in raw.get("unsupported", []):
        warnings.append(f"unsupported: {u}")
    return {"text": text, "parser": parser, "assumptions": assumptions, "warnings": warnings, "requires_confirmation": True,
            "scenario": SeasonScenario(rating_shifts=shifts, label=text[:120]) if shifts else None}
