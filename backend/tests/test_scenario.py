def test_rule_scenario_parser(ctx):
    s=ctx.store.get_state('test-game');r=ctx.scenario_parser.parse('What if the quarterback gets injured and is out?',s)
    assert r.operations and r.operations[0].kind=='injury_status'
