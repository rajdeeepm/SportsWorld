from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sportsworld.backtest.leakage import assert_point_in_time


def materialize_feature_rows(rows:Iterable[dict], destination:Path)->int:
    rows=list(rows); assert_point_in_time(rows); destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text('\n'.join(json.dumps(r,sort_keys=True,default=str) for r in rows)+'\n'); return len(rows)
