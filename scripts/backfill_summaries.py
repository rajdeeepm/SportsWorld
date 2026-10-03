"""Backfill per-game ESPN summaries: player participation (all leagues) + basketball/hockey play-by-play.

Participation is point-in-time truth (who actually played, how much) and is the training
signal for player-availability impact. The summary's `injuries` block is NOT used: ESPN
serves the *current* injury list for historical games, which would leak future information.

Output (one JSONL per league-season, run on the training hosts where storage lives):
  data/real/summaries/<league>/<season>.jsonl
  {"game_id", "players": [[team_id, athlete_id, name, pos, starter, usage]], "plays": [[period, clock_s, hs, as, side, type_id, scoring]]}
usage = minutes (basketball), TOI minutes (hockey), pass attempts / carries / targets (football, max over groups).

Usage: PYTHONPATH=backend/src python scripts/backfill_summaries.py --leagues nba wnba [--seasons 2023 2024 2025]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.ingest.espn import BASE, drop_exhibitions, read_archive, season_start_year  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402

DATA = ROOT / "data" / "real"


def _clock(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        if ":" in text:
            m, s = text.split(":", 1)
            return int(m) * 60 + float(s)
        return float(text)
    except ValueError:
        return 0.0


def _num(x: str) -> float:
    try:
        if "/" in x:  # C/ATT
            return float(x.split("/")[1])
        if ":" in x:  # TOI mm:ss
            m, s = x.split(":")
            return int(m) + int(s) / 60
        return float(x)
    except (ValueError, IndexError):
        return 0.0


def players(summary: dict, sport: str) -> list[list]:
    out: dict[tuple[str, str], list] = {}
    for team in summary.get("boxscore", {}).get("players", []):
        tid = str(team.get("team", {}).get("id"))
        for group in team.get("statistics", []):
            labels = group.get("labels") or []
            key = {"basketball": "MIN", "hockey": "TOI"}.get(sport)
            for a in group.get("athletes", []):
                ath = a.get("athlete", {})
                stats = a.get("stats") or []
                usage = 0.0
                if key and key in labels and len(stats) > labels.index(key):
                    usage = _num(stats[labels.index(key)])
                elif sport == "football" and stats:
                    usage = _num(stats[0])  # C/ATT, CAR, REC ...
                if a.get("didNotPlay"):
                    usage = 0.0
                k = (tid, str(ath.get("id")))
                row = out.get(k)
                if row is None:
                    out[k] = [tid, str(ath.get("id")), ath.get("displayName"), (ath.get("position") or {}).get("abbreviation"),
                              bool(a.get("starter")), usage, group.get("name")]
                else:
                    row[5] = max(row[5], usage)
                    row[4] = row[4] or bool(a.get("starter"))
    return list(out.values())


def plays(summary: dict, home_id: str) -> list[list]:
    out = []
    for p in summary.get("plays") or []:
        team = str((p.get("team") or {}).get("id") or "")
        side = 0 if not team else (1 if team == home_id else -1)
        out.append([int((p.get("period") or {}).get("number") or 0), _clock((p.get("clock") or {}).get("displayValue")),
                    int(p.get("homeScore") or 0), int(p.get("awayScore") or 0), side, str((p.get("type") or {}).get("id") or ""),
                    int(bool(p.get("scoringPlay")))])
    return out


async def run(league: str, seasons: list[int] | None, concurrency: int) -> None:
    spec = LEAGUES[league]
    sport = spec.sport.value
    games = [g for g in drop_exhibitions(read_archive(DATA, league)) if g.completed and not g.cancelled]
    if seasons:
        games = [g for g in games if season_start_year(spec, g.start_time) in seasons]
    out_dir = DATA / "summaries" / league
    out_dir.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    for f in out_dir.glob("*.jsonl"):
        done.update(json.loads(x)["game_id"] for x in f.read_text().splitlines() if x.strip())
    todo = [g for g in games if g.game_id not in done]
    print(f"{league}: {len(games)} games, {len(todo)} to fetch", flush=True)
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "SportsWorld/1.3 (research)"}) as client:
        async def fetch(g):
            async with sem:
                for attempt in range(4):
                    try:
                        r = await client.get(f"{BASE}/{spec.espn_path}/summary", params={"event": g.game_id})
                        if r.status_code == 200:
                            return r.json()
                        if r.status_code == 404:
                            return None
                    except (httpx.HTTPError, json.JSONDecodeError):
                        pass
                    await asyncio.sleep(1.5 * (attempt + 1))
            return None
        for i in range(0, len(todo), 250):
            batch = todo[i:i + 250]
            res = await asyncio.gather(*(fetch(g) for g in batch))
            by_season: dict[int, list[str]] = {}
            for g, s in zip(batch, res):
                if not s:
                    continue
                rec = {"game_id": g.game_id, "players": players(s, sport)}
                if sport in ("basketball", "hockey"):
                    rec["plays"] = plays(s, g.home.team_id)
                by_season.setdefault(season_start_year(spec, g.start_time), []).append(json.dumps(rec, separators=(",", ":")))
            for season, lines in by_season.items():
                with (out_dir / f"{season}.jsonl").open("a") as fh:
                    fh.write("\n".join(lines) + "\n")
            print(f"{league}: {min(i + 250, len(todo))}/{len(todo)}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="+", required=True)
    ap.add_argument("--seasons", nargs="*", type=int)
    ap.add_argument("--concurrency", type=int, default=10)
    a = ap.parse_args()
    for lg in a.leagues:
        await run(lg, a.seasons, a.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
