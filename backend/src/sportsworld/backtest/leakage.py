from __future__ import annotations

from datetime import datetime
from typing import Iterable


def audit_rows(rows: Iterable[dict]) -> list[dict]:
    violations=[]
    for i,row in enumerate(rows):
        pred=_dt(row["prediction_time"])
        known=_dt(row.get("max_known_to_model_time") or row["prediction_time"])
        if known>pred:
            violations.append({"index":i,"event_id":row.get("event_id"),"prediction_time":pred.isoformat(),"known_to_model_time":known.isoformat()})
    return violations


def assert_point_in_time(rows: Iterable[dict]) -> None:
    violations=audit_rows(rows)
    if violations: raise ValueError(f"point-in-time leakage violations: {violations[:3]}")


def _dt(value):
    if isinstance(value,datetime): return value
    return datetime.fromisoformat(str(value).replace('Z','+00:00'))
