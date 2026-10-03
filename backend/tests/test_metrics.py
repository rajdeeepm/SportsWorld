import numpy as np
from sportsworld.backtest.metrics import multiclass_brier,log_loss,accuracy,top_label_ece

def test_metrics_are_finite():
    p=np.array([[.8,.2],[.3,.7],[.55,.45]]);y=np.array([0,1,1])
    assert 0<=multiclass_brier(p,y)<=2
    assert log_loss(p,y)>0
    assert 0<=accuracy(p,y)<=1
    ece,bins=top_label_ece(p,y);assert 0<=ece<=1 and len(bins)==10


def test_bundled_backtest_has_research_surfaces():
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    d=json.loads((root/'data'/'fixtures'/'backtests'/'football_demo.json').read_text())
    for key in ('brier','log_loss','ece','accuracy','interval_coverage','interval_width'):
        assert key in d['metrics']
    assert d['leakage_violations']==0
    assert len(d['reliability'])==10
    assert d['rolling'] and d['ablations'] and d['slices'] and d['drift']
    assert all('count' in s for s in d['slices'])
