from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ChronologicalSplit:
    train_end: datetime
    calibration_end: datetime
    test_end: datetime | None = None

    def split(self, rows:list[dict]) -> tuple[list[dict],list[dict],list[dict]]:
        train=[]; cal=[]; test=[]
        # Partition by `split_time` (game kickoff) when present so every row of a game lands in one
        # partition; otherwise by prediction time.
        for r in sorted(rows,key=lambda x:x['prediction_time']):
            key=r.get('split_time') or r['prediction_time']
            t=key if isinstance(key,datetime) else datetime.fromisoformat(str(key).replace('Z','+00:00'))
            if t<=self.train_end: train.append(r)
            elif t<=self.calibration_end: cal.append(r)
            elif self.test_end is None or t<=self.test_end: test.append(r)
        if not train or not cal or not test: raise ValueError("chronological split requires non-empty train/calibration/test")
        return train,cal,test
