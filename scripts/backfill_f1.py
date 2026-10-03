"""Backfill F1 history: Jolpica classified results (every race, every driver) and
OpenF1 lap timing for completed races from 2023 on.

Usage (repo root):
    PYTHONPATH=backend/src python scripts/backfill_f1.py [--from-season 2018] [--laps-from 2023]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.ingest.f1 import JolpicaClient, OpenF1Client, f1_results_path, read_f1_archive, write_f1_season  # noqa: E402

DATA = ROOT / "data" / "real"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-season", type=int, default=2018)
    ap.add_argument("--laps-from", type=int, default=2023)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    jol = JolpicaClient()
    try:
        for season in range(args.from_season, now.year + 1):
            path = f1_results_path(DATA, season)
            if path.exists() and season < now.year and not args.refresh:
                print(f"f1 {season}: cached", flush=True)
                continue
            races = await jol.season_results(season)
            write_f1_season(DATA, season, races)
            print(f"f1 {season}: {len(races)} races, {sum(len(r.results) for r in races)} driver results", flush=True)
            await asyncio.sleep(1.0)
    finally:
        await jol.aclose()

    of1 = OpenF1Client(min_interval=2.2)  # free tier: stay well under 30 req/min
    lap_dir = DATA / "f1" / "laps"
    lap_dir.mkdir(parents=True, exist_ok=True)
    try:
        for race in read_f1_archive(DATA):
            if race.season < args.laps_from or not race.completed or (lap_dir / f"{race.event_id}.json").exists():
                continue
            try:
                session = await of1.race_session(race.season, race.start_time)
                if not session:
                    print(f"{race.event_id}: no OpenF1 race session", flush=True)
                    continue
                key = session["session_key"]
                drivers = await of1.get("drivers", session_key=key)
                laps = await of1.get("laps", session_key=key)
                slim_laps = [{k: l.get(k) for k in ("driver_number", "lap_number", "date_start", "lap_duration", "is_pit_out_lap")} for l in laps]
                slim_drivers = [{k: d.get(k) for k in ("driver_number", "name_acronym", "team_name", "full_name")} for d in drivers]
                (lap_dir / f"{race.event_id}.json").write_text(json.dumps({"session_key": key, "drivers": slim_drivers, "laps": slim_laps}))
                print(f"{race.event_id} {race.race_name}: {len(slim_laps)} laps", flush=True)
            except Exception as exc:
                print(f"{race.event_id}: {type(exc).__name__}: {exc}", flush=True)
    finally:
        await of1.aclose()


if __name__ == "__main__":
    asyncio.run(main())
