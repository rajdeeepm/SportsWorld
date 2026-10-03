from datetime import datetime,timezone
import pytest
from sportsworld.schemas import Observation,Sport

def test_observation_dedupe_and_timezone():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    a=Observation(event_id='x',sport=Sport.FOOTBALL,kind='weather',payload={'severity':.2},source_id='s',known_to_model_time=t)
    b=Observation(event_id='x',sport=Sport.FOOTBALL,kind='weather',payload={'severity':.2},source_id='s',known_to_model_time=t)
    assert a.dedupe_key==b.dedupe_key

def test_naive_timestamp_rejected():
    with pytest.raises(ValueError): Observation(event_id='x',sport='football',kind='weather',payload={},source_id='s',known_to_model_time=datetime(2026,1,1))
