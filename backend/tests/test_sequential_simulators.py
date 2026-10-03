from __future__ import annotations

from datetime import datetime,timezone

from sportsworld.schemas import EventCreate,CounterfactualRequest,ScenarioOperation

UTC=timezone.utc


def test_football_counterfactual_is_drive_by_drive(ctx):
    base=ctx.store.get_state('test-game')
    req=CounterfactualRequest(base_event_id=base.event_id,overrides=[ScenarioOperation(kind='weather',payload={'severity':.8})],draws=500,seed=101)
    result=ctx.simulator.run(base,req)
    assert result.simulation_method=='drive_by_drive'
    assert result.scenario_mean_steps>1
    assert result.representative_paths and result.representative_paths[0]
    assert sum(result.simulation_counts.values())==500


def test_basketball_counterfactual_is_possession_by_possession(ctx):
    t=datetime(2026,1,1,tzinfo=UTC)
    state=ctx.engine.create_event(EventCreate(event_id='bb-sim',sport='basketball',competition='x',season='2026',outcomes=['home','away'],start_time=t,initial_features={'seconds_remaining':600,'home_score':90,'away_score':88,'pace':100}))
    req=CounterfactualRequest(base_event_id='bb-sim',overrides=[ScenarioOperation(kind='availability',payload={'team':'home','status':'out','impact':-.15})],draws=400,seed=102)
    result=ctx.simulator.run(state,req)
    assert result.simulation_method=='possession_by_possession'
    assert result.scenario_mean_steps>10
    assert sum(result.scenario_probabilities.values())==1


def test_f1_counterfactual_is_lap_by_lap(ctx):
    t=datetime(2026,1,1,tzinfo=UTC)
    state=ctx.engine.create_event(EventCreate(event_id='f1-sim',sport='f1',competition='x',season='2026',outcomes=['Norris','Verstappen','Leclerc','Other'],start_time=t,initial_features={'lap':40,'total_laps':50,'rain_probability':.2,'drivers':{'Norris':{'position':1,'pace':-.05,'reliability':.98,'wet_skill':.2},'Verstappen':{'position':2,'pace':-.08,'reliability':.99,'wet_skill':.5},'Leclerc':{'position':3,'pace':.01,'reliability':.97,'wet_skill':.15},'Other':{'position':4,'pace':.1,'reliability':.96,'wet_skill':.05}}}))
    req=CounterfactualRequest(base_event_id='f1-sim',overrides=[ScenarioOperation(kind='weather',payload={'rain_probability':.9})],draws=300,seed=103)
    result=ctx.simulator.run(state,req)
    assert result.simulation_method=='lap_by_lap'
    assert result.scenario_mean_steps==10
    assert 'dnf_rate' in result.simulation_diagnostics['scenario']
    assert sum(result.simulation_counts.values())==300
