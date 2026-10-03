"""Cache league structure + official standings for current and historical seasons.

Usage (repo root): PYTHONPATH=backend/src python scripts/fetch_structures.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import httpx  # noqa: E402

from sportsworld.ingest.leagues import LEAGUES, TEAM_LEAGUES  # noqa: E402
from sportsworld.season.structure import fetch_structure, save_structure  # noqa: E402

DATA = ROOT / "data" / "real"


async def main() -> None:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "SportsWorld/1.3"}) as client:
        for league in TEAM_LEAGUES:
            for season in range(2018, 2028):
                try:
                    s = await fetch_structure(LEAGUES[league], season, client)
                except Exception as exc:
                    print(league, season, "ERR", exc)
                    continue
                if not s.teams:
                    continue
                save_structure(DATA, s)
                print(league, season, len(s.teams), "teams", len(s.conferences()), "conf", len(s.divisions()), "div")


if __name__ == "__main__":
    asyncio.run(main())
