from datetime import datetime,timedelta,timezone
import pytest
from sportsworld.schemas import Observation

def obs(seq=1,t=None,kind='score_state',payload=None):
    t=t or datetime(2026,1,1,0,5,tzinfo=timezone.utc)
    return Observation(event_id='test-game',sport='football',kind=kind,payload=payload or {'home_score':7,'away_score':0,'seconds_remaining':3300,'possession':'away'},source_id='test',known_to_model_time=t,ingestion_time=t+timedelta(seconds=1),sequence_no=seq)

def test_forecast_sums_to_one(ctx):
    f=ctx.engine.latest_forecast('test-game');assert abs(sum(f.probabilities.values())-1)<1e-9

def test_ingest_versions_state_and_forecast(ctx):
    before=ctx.engine.latest_forecast('test-game');after=ctx.engine.ingest(obs());state=ctx.store.get_state('test-game')
    assert state.state_version==1 and state.features['home_score']==7
    assert after.state_version==1 and after.probabilities!=before.probabilities
    assert after.drivers and after.drivers[0].method.value=='replay_delta'

def test_dedupe_is_idempotent(ctx):
    o=obs();a=ctx.engine.ingest(o);b=ctx.engine.ingest(o);assert b.state_version==a.state_version

def test_stale_observation_rejected(ctx):
    ctx.engine.ingest(obs())
    with pytest.raises(ValueError):ctx.engine.ingest(obs(seq=2,t=datetime(2026,1,1,0,4,tzinfo=timezone.utc)))
