"""Backfill compact football play-by-play states for every archived completed game.

One compact JSONL per league-season:
    data/real/pbp/<league>/<season_start_year>.jsonl
    {"game_id": ..., "plays": [[period, clock_s, home_score, away_score, poss, down, distance, yards_to_endzone, espn_home_wp], ...]}

`poss` is +1 home offense, -1 away offense, 0 unknown.  `espn_home_wp` is ESPN's
own published win probability for that play; it is stored ONLY as an external
consensus comparator and is never a model feature.

Usage (repo root):
    PYTHONPATH=backend/src python scripts/backfill_pbp.py --leagues nfl college-football
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


def clock_seconds(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        if ":" in text:
            m, s = text.split(":", 1)
            return int(m) * 60 + float(s)
        return float(text)
    except ValueError:
        return 0.0


def compact(summary: dict, home_id: str) -> list[list]:
    wp = {str(x.get("playId")): x.get("homeWinPercentage") for x in summary.get("winprobability") or []}
    rows = []
    for drive in (summary.get("drives") or {}).get("previous") or []:
        for p in drive.get("plays") or []:
            start = p.get("start") or {}
            team = str((start.get("team") or {}).get("id") or "")
            poss = 0 if not team else (1 if team == home_id else -1)
            ytg = start.get("yardsToEndzone")
            rows.append([
                int((p.get("period") or {}).get("number") or 0),
                clock_seconds((p.get("clock") or {}).get("displayValue")),
                int(p.get("homeScore") or 0), int(p.get("awayScore") or 0), poss,
                int(start.get("down") or 0), int(start.get("distance") or 0),
                int(ytg) if ytg is not None else -1,
                wp.get(str(p.get("id"))),
            ])
    return rows


async def fetch(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str) -> dict | None:
    async with sem:
        for attempt in range(4):
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return None
            except (httpx.HTTPError, json.JSONDecodeError):
                pass
            await asyncio.sleep(1.5 * (attempt + 1))
    return None


async def run(league: str, concurrency: int) -> None:
    spec = LEAGUES[league]
    games = [g for g in drop_exhibitions(read_archive(DATA, league)) if g.completed and not g.cancelled]
    out_dir = DATA / "pbp" / league
    out_dir.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    for f in out_dir.glob("*.jsonl"):
        done.update(json.loads(x)["game_id"] for x in f.read_text().splitlines() if x.strip())
    todo = [g for g in games if g.game_id not in done]
    print(f"{league}: {len(games)} completed games, {len(todo)} to fetch", flush=True)
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "SportsWorld/1.2 (MHacks research)"}) as client:
        for i in range(0, len(todo), 200):
            batch = todo[i:i + 200]
            results = await asyncio.gather(*(fetch(client, sem, f"{BASE}/{spec.espn_path}/summary?event={g.game_id}") for g in batch))
            by_season: dict[int, list[str]] = {}
            for g, summary in zip(batch, results):
                if not summary:
                    continue
                plays = compact(summary, g.home.team_id)
                if plays:
                    by_season.setdefault(season_start_year(spec, g.start_time), []).append(json.dumps({"game_id": g.game_id, "plays": plays}))
            for season, lines in by_season.items():
                with (out_dir / f"{season}.jsonl").open("a") as fh:
                    fh.write("\n".join(lines) + "\n")
            print(f"{league}: {min(i + 200, len(todo))}/{len(todo)}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=["nfl", "college-football"])
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    for league in args.leagues:
        await run(league, args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
