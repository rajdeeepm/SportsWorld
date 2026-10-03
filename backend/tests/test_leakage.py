from sportsworld.backtest.leakage import audit_rows,assert_point_in_time
import pytest

def test_leakage_audit():
    rows=[{'event_id':'x','prediction_time':'2026-01-01T00:00:00+00:00','max_known_to_model_time':'2026-01-01T00:00:01+00:00'}]
    assert len(audit_rows(rows))==1
    with pytest.raises(ValueError):assert_point_in_time(rows)
