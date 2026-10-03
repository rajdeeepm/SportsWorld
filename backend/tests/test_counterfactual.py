from sportsworld.schemas import CounterfactualRequest,ScenarioOperation

def test_counterfactual_does_not_mutate_canonical(ctx):
    base=ctx.store.get_state('test-game');before=base.model_dump()
    req=CounterfactualRequest(base_event_id='test-game',base_state_version=0,overrides=[ScenarioOperation(kind='injury_status',payload={'team':'home','role':'starting_qb','status':'out','impact':-.2})],draws=2000,seed=9)
    result=ctx.simulator.run(base,req)
    assert ctx.store.get_state('test-game',0).model_dump()==before
    assert result.current_probabilities!=result.scenario_probabilities
    assert sum(result.simulation_counts.values())==2000
    assert all(0<=x<=1 for interval in result.scenario_intervals_90.values() for x in interval)

def test_counterfactual_injury_updates_latent_context_without_persisting(ctx):
    base = ctx.store.get_state('test-game')
    before_signals = list(ctx.store.list_context_signals('test-game'))
    before_state = base.model_dump()
    req = CounterfactualRequest(
        base_event_id='test-game',
        base_state_version=base.state_version,
        overrides=[ScenarioOperation(
            kind='injury_status',
            payload={'team':'home','role':'starting_qb','status':'out','impact':-.35},
        )],
        draws=1000,
        seed=17,
    )
    branch = ctx.simulator.apply_operation(base.clone(), req.overrides[0], 1)
    assert branch.features.get('health_diff', 0.0) < base.features.get('health_diff', 0.0)
    assert branch.features.get('context_volatility', 0.0) >= base.features.get('context_volatility', 0.0)
    ctx.simulator.run(base, req)
    assert ctx.store.get_state('test-game').model_dump() == before_state
    assert ctx.store.list_context_signals('test-game') == before_signals
