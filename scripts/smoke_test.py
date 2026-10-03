from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'/'src'))
from fastapi.testclient import TestClient
from sportsworld.api.main import app

with TestClient(app) as c:
    assert c.get('/health').status_code==200
    events=c.get('/events').json(); assert len(events)>=3
    eid='mich-osu-2026-demo'; assert c.get(f'/events/{eid}/forecast').status_code==200
    context=c.get(f'/events/{eid}/context'); assert context.status_code==200; assert len(context.json()['entity_states'])>=4; assert context.json()['matchup_edges']
    r=c.post(f'/demo/{eid}/replay',json={'action':'step','count':2}); assert r.status_code==200
    parsed=c.post(f'/events/{eid}/scenario/parse',json={'text':'What if the Michigan quarterback leaves the game?'}).json(); assert parsed['operations']
    req={'base_event_id':eid,'overrides':parsed['operations'],'draws':1000,'seed':7}; res=c.post(f'/events/{eid}/counterfactuals',json=req); assert res.status_code==200
print('SportsWorld smoke test passed')
