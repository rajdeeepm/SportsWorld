from __future__ import annotations

from datetime import datetime, timezone

from sportsworld.config import Settings
from sportsworld.llm import client as llm_client
from sportsworld.llm.scenario import ScenarioParser
from sportsworld.schemas import Sport, WorldState


def _state() -> WorldState:
    return WorldState(event_id="e", sport=Sport.FOOTBALL, competition="x", season="2026", outcomes=["home", "away"],
                      features={}, metadata={"display_outcomes": {"home": "Michigan", "away": "Ohio State"}},
                      created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def _settings() -> Settings:
    return Settings(llm_provider="openai_compatible", llm_base_url="http://127.0.0.1:9/v1", llm_api_key="none")


def test_rules_first_when_rules_recognise_the_scenario(monkeypatch):
    monkeypatch.setattr(llm_client.LLMClient, "json_call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    r = ScenarioParser(_settings()).parse("What if the Michigan quarterback leaves the game?", _state())
    assert r.parser.startswith("deterministic") and r.operations[0].kind == "injury_status"


def test_llm_output_restricted_to_supported_kinds(monkeypatch):
    monkeypatch.setattr(llm_client.LLMClient, "json_call", lambda *a, **k: {"operations": [
        {"kind": "injury", "team": "away", "role": "qb", "status": "out", "effective_lap": None},          # invented kind
        {"kind": "timeout", "team": "home", "role": None, "status": None, "effective_lap": None}]})       # valid kind
    r = ScenarioParser(_settings()).parse("Something the rules do not understand", _state())
    assert [o.kind for o in r.operations] == ["timeout"]


def test_llm_failure_falls_back_to_rules(monkeypatch):
    def boom(*a, **k):
        raise llm_client.LLMUnavailable("down")
    monkeypatch.setattr(llm_client.LLMClient, "json_call", boom)
    r = ScenarioParser(_settings()).parse("Something the rules do not understand", _state())
    assert r.operations == [] and any("deterministic parser used" in w for w in r.warnings)


def test_role_normalisation_and_number_words():
    from sportsworld.llm.season_scenario import normalize_role, rules_parse
    assert normalize_role("starting QB", None) == "QB"
    assert normalize_role(None, "starting quarterback") == "QB"
    assert normalize_role("goaltender", None) == "G"
    assert normalize_role("star", None) == "KEY"
    ops = rules_parse("What if the Bills starting quarterback misses the next three games?")["operations"]
    assert ops and ops[0]["games"] == 3 and ops[0]["position"] == "QB"
