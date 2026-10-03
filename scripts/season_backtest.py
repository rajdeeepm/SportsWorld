"""Historical full-season replay backtest (spec §19.3) for every league with complete past seasons.

Usage (repo root): PYTHONPATH=backend/src python scripts/season_backtest.py [--leagues nfl nba nhl] [--draws 5000]
Writes data/fixtures/backtests/season_<league>.json and season_summary.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.season.backtest import evaluate_season, summarize  # noqa: E402

DATA = ROOT / "data" / "real"
OUT = ROOT / "data" / "fixtures" / "backtests"
DEFAULT = {"nfl": [2024, 2025], "nba": [2024, 2025], "nhl": [2024, 2025], "college-football": [2024, 2025],
           "mens-college-basketball": [2024, 2025], "womens-college-basketball": [2024, 2025], "wnba": [2024, 2025]}


def job(args):
    league, season, draws = args
    try:
        return evaluate_season(league, season, DATA, draws=draws)
    except Exception as exc:  # e.g. NHL 2020-21 one-off COVID realignment: rules engine does not model it
        print(f"skip {league} {season}: {type(exc).__name__}: {exc}", flush=True)
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=list(DEFAULT))
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seasons", nargs="*", type=int, help="override evaluated seasons for every league")
    ap.add_argument("--tag", default="", help="suffix for output files (e.g. _ext)")
    a = ap.parse_args()
    jobs = [(lg, s, a.draws) for lg in a.leagues for s in (a.seasons or DEFAULT.get(lg, [2024, 2025]))]
    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        for res in ex.map(job, jobs):
            rows.extend(res)
    OUT.mkdir(parents=True, exist_ok=True)
    for lg in a.leagues:
        sub = [r for r in rows if r["league"] == lg]
        (OUT / f"season_{lg}{a.tag}.json").write_text(json.dumps({"rows": sub, "summary": summarize(sub)}, indent=1))
    summary = summarize(rows)
    path = OUT / f"season_summary{a.tag}.json"
    old = json.loads(path.read_text())["summary"] if path.exists() else []
    keep = [r for r in old if r["league"] not in a.leagues]
    path.write_text(json.dumps({"summary": keep + summary}, indent=1))
    for r in summary:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
