from __future__ import annotations

import argparse,json
from datetime import datetime
from pathlib import Path
from sportsworld.backtest.runner import run_football_backtest
from sportsworld.backtest.splitter import ChronologicalSplit


def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',default='../data/fixtures/training/football_synthetic_v2_context.jsonl'); p.add_argument('--out',default='../data/fixtures/backtests/football_demo.json'); a=p.parse_args()
    rows=[json.loads(x) for x in Path(a.input).read_text().splitlines() if x.strip()]
    split=ChronologicalSplit(datetime.fromisoformat('2025-12-31T23:59:59+00:00'),datetime.fromisoformat('2026-04-30T23:59:59+00:00'))
    _,_,report=run_football_backtest(rows,split); Path(a.out).write_text(report.model_dump_json(indent=2)); print(Path(a.out).resolve())

if __name__=='__main__': main()
