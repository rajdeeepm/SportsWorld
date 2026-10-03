from fastapi.testclient import TestClient
from sportsworld.api.main import app

def test_demo_api_end_to_end():
    with TestClient(app) as c:
        assert c.get('/health').status_code==200
        events=c.get('/events').json();assert len(events)>=3
        eid='mich-osu-2026-demo';before=c.get(f'/events/{eid}/forecast').json();r=c.post(f'/demo/{eid}/replay',json={'action':'step','count':1});assert r.status_code==200
        after=c.get(f'/events/{eid}/forecast').json();assert after['state_version']>=before['state_version']
        parsed=c.post(f'/events/{eid}/scenario/parse',json={'text':'What if the quarterback leaves the game?'}).json();assert parsed['operations']
        cf=c.post(f'/events/{eid}/counterfactuals',json={'base_event_id':eid,'overrides':parsed['operations'],'draws':500,'seed':7});assert cf.status_code==200
        bt=c.get('/backtests/football');assert bt.status_code==200 and bt.json()['leakage_violations']==0
        context=c.get(f'/events/{eid}/context');assert context.status_code==200;payload=context.json();assert payload['entity_states'] and 'historical_strength_diff' in payload['aggregate_features']


def test_observation_idempotency_header():
    from datetime import datetime, timezone, timedelta
    with TestClient(app) as c:
        event_id='idempotency-test-football'
        now=datetime.now(timezone.utc)
        created=c.post('/events',json={
            'event_id':event_id,'sport':'football','competition':'demo','season':'2026',
            'outcomes':['home','away'],'start_time':now.isoformat(),'participants':['A','B'],
            'initial_features':{'home_score':0,'away_score':0,'quarter':1,'seconds_remaining':900,'possession':'home','home_strength':0.1,'away_strength':0.0}
        })
        assert created.status_code==200
        obs={
            'event_id':event_id,'sport':'football','kind':'score_state','payload':{'home_score':7,'away_score':0,'quarter':1,'seconds_remaining':700,'possession':'away'},
            'source_id':'test','source_type':'stats','confidence':1.0,
            'known_to_model_time':(now+timedelta(minutes=2)).isoformat(),'ingestion_time':(now+timedelta(minutes=2)).isoformat(),'sequence_no':1,'verified':True
        }
        headers={'Idempotency-Key':'same-write'}
        r1=c.post(f'/events/{event_id}/observations',json=obs,headers=headers); assert r1.status_code==200
        v1=r1.json()['state_version']
        r2=c.post(f'/events/{event_id}/observations',json=obs,headers=headers); assert r2.status_code==200
        assert r2.json()['state_version']==v1
