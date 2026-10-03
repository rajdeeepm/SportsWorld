"""Backfill every game of every team for the tracked ESPN leagues.

Usage (repo root):
    PYTHONPATH=backend/src python scripts/backfill_espn.py                      # all leagues, last 3 seasons + current
    PYTHONPATH=backend/src python scripts/backfill_espn.py --leagues nfl nba --seasons 2023 2024 2025 2026

Completed seasons are cached in data/real/games/<league>/<season_start_year>.jsonl
and skipped on re-runs unless --refresh is given.  The in-progress season is
always re-fetched from (today - 3 days) onward and merged.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.ingest.espn import ESPNClient, GameRecord, archive_path, season_days, write_archive  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES, TEAM_LEAGUES  # noqa: E402

DATA = ROOT / "data" / "real"


def current_start_year(spec, today: date) -> int:
    # The season that contains `today`, or the most recent one that started.
    y = today.year
    days = season_days(spec, y)
    return y if today >= days[0] else y - 1


async def backfill_league(client: ESPNClient, league: str, seasons: list[int], refresh: bool, full_schedule: bool = True) -> None:
    spec = LEAGUES[league]
    today = datetime.now(timezone.utc).date()
    for season in seasons:
        days = season_days(spec, season)
        if days[0] > today + timedelta(days=60):  # upcoming seasons within 60 days are initialized (spec 2.2 preseason)
            continue
        path = archive_path(DATA, league, season)
        finished = days[-1] < today - timedelta(days=3)
        existing: list[GameRecord] = []
        if path.exists():
            existing = [GameRecord.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]
            if finished and not refresh:
                print(f"{league} {season}: cached ({len(existing)} games)")
                continue
            # In-progress season: only re-pull the recent/future window.
            days = [d for d in days if d >= today - timedelta(days=3)] if not refresh else days
        if not full_schedule:
            days = [d for d in days if d <= today + timedelta(days=14)]
        results = await asyncio.gather(*(client.scoreboard(spec, d) for d in days), return_exceptions=True)
        games = list(existing)
        failures = 0
        for r in results:
            if isinstance(r, Exception):
                failures += 1
                continue
            games.extend(r)
        # A scoreboard day can include adjacent-season games; keep only this season's.
        season_years = {g.season for g in games}
        write_archive(path, games)
        completed = sum(1 for g in games if g.completed)
        print(f"{league} {season}: {len({g.game_id for g in games})} games ({completed} completed rows), espn season ids {sorted(season_years)}, {failures} failed days")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=TEAM_LEAGUES)
    ap.add_argument("--seasons", nargs="*", type=int)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--window-only", action="store_true", help="only fetch up to today+14 instead of the full remaining schedule")
    args = ap.parse_args()
    client = ESPNClient(concurrency=args.concurrency)
    today = datetime.now(timezone.utc).date()
    try:
        for league in args.leagues:
            spec = LEAGUES[league]
            seasons = args.seasons or list(range(current_start_year(spec, today) - 3, current_start_year(spec, today) + 2))
            await backfill_league(client, league, seasons, args.refresh, full_schedule=not args.window_only)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
