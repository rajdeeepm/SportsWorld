"""Backfill this season's odds trajectory into Neon with point-in-time replays.

For each day since the season's first game, rebuild the competition exactly as it stood at that moment from
archived evidence only (results known by then, ratings and hyper-parameters fitted on earlier data), simulate the
rest of the season, and archive the run as `pit-<league>-<date>`. These are what SportsWorld *would have* said that
day; the UI labels them as replays, distinct from runs archived live.

Usage: PYTHONPATH=backend/src python scripts/backfill_history.py [--leagues college-football nfl] [--draws 4000]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.config import get_settings  # noqa: E402
from sportsworld.ingest.espn import drop_exhibitions, read_archive, season_start_year  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.live.neon_archive import CONF, DDL, QUALIFY  # noqa: E402
from sportsworld.season.engine import build_setup, run_season  # noqa: E402

DATA = ROOT / "data" / "real"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=["college-football", "nfl", "nba", "mens-college-basketball", "nhl"])
    ap.add_argument("--draws", type=int, default=4000)
    a = ap.parse_args()
    import psycopg
    url = get_settings().database_url
    if not url:
        sys.exit("DATABASE_URL not set")
    now = datetime.now(timezone.utc)
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(DDL)
        for league in a.leagues:
            spec = LEAGUES[league]
            games = drop_exhibitions(read_archive(DATA, league))
            season = max(season_start_year(spec, g.start_time) for g in games if g.start_time <= now)
            first = min(g.start_time for g in games if season_start_year(spec, g.start_time) == season)
            day = datetime.combine(first.date(), time(9, 0), tzinfo=timezone.utc)
            n = 0
            while day < now:
                rid = f"pit-{league}-{day.date().isoformat()}"
                if c.execute("select 1 from season_run where run_id = %s", (rid,)).fetchone():
                    day += timedelta(days=1)
                    continue
                try:
                    setup = build_setup(league, DATA, day, games=games)
                    run = run_season(setup, draws=a.draws, mode="dynamic")
                except Exception as exc:  # e.g. no remaining schedule yet
                    print(league, day.date(), "skipped:", exc)
                    day += timedelta(days=1)
                    continue
                q = QUALIFY.get(league, "playoffs")
                teams = [{"id": t["team_id"], "r": round(float(t["rating"]), 2), "sd": round(float(t["rating_sd"]), 2), "ew": round(float(t["expected_wins"]), 2),
                          "q": round(float(t.get(q) or 0), 4), "c": round(float(next((t[k] for k in CONF if k in t), 0) or 0), 4), "t": round(float(t.get("champion") or 0), 4)}
                         for t in run["teams"]]
                c.execute("insert into season_run (run_id, league, state_version, as_of, draws, teams, diagnostics) values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
                          (rid, league, 0, day, a.draws, json.dumps(teams), json.dumps({**run["diagnostics"], "point_in_time_replay": True})))
                n += 1
                day += timedelta(days=1)
            print(league, "season", season, "archived", n, "point-in-time runs", flush=True)


if __name__ == "__main__":
    main()
