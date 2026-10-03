from sportsworld.config import Settings
from sportsworld.api.context import build_context
from sportsworld.schemas import EventCreate,Sport
from datetime import datetime,timezone


def test_all_three_hero_learned_models_loaded():
    c=build_context(Settings(sportsworld_env='test',store_backend='memory'))
    expected={
        Sport.FOOTBALL:('bootstrap_logistic','football_bootstrap_world_demo_v3'),
        Sport.BASKETBALL:('bootstrap_logistic','basketball_bootstrap_world_demo_v1'),
        Sport.F1:('bootstrap_conditional_softmax','f1_conditional_softmax_world_demo_v1'),
    }
    for sport,(algorithm,version) in expected.items():
        card=c.registry.card(sport)
        assert card is not None
        assert card.algorithm==algorithm
        assert card.data_mode=='synthetic_demo'
        assert card.model_version==version

    c.engine.create_event(EventCreate(event_id='m',sport='football',competition='x',season='2026',outcomes=['home','away'],start_time=datetime(2026,1,1,tzinfo=timezone.utc),initial_features={}))
    f=c.engine.latest_forecast('m')
    assert f.model_version=='football_bootstrap_world_demo_v3'
    assert f.uncertainty.epistemic is not None


def test_basketball_and_f1_forecasts_use_learned_models():
    c=build_context(Settings(sportsworld_env='test',store_backend='memory'))
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    c.engine.create_event(EventCreate(event_id='b',sport='basketball',competition='x',season='2026',outcomes=['home','away'],start_time=t,initial_features={}))
    fb=c.engine.latest_forecast('b')
    assert fb.model_version=='basketball_bootstrap_world_demo_v1'
    assert fb.uncertainty.epistemic is not None
    c.engine.create_event(EventCreate(event_id='r',sport='f1',competition='x',season='2026',outcomes=['Norris','Verstappen','Leclerc','Other'],start_time=t,initial_features={'drivers':{'Norris':{'position':1},'Verstappen':{'position':2},'Leclerc':{'position':3},'Other':{'position':4}}}))
    ff=c.engine.latest_forecast('r')
    assert ff.model_version=='f1_conditional_softmax_world_demo_v1'
    assert ff.uncertainty.epistemic is not None
    assert abs(sum(ff.probabilities.values())-1)<1e-8
