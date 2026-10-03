from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sportsworld.schemas import ContextSignal, EntityMetric, EntityProfile, EventCreate, Observation, Sport

UTC = timezone.utc


def test_context_snapshot_has_history_people_and_matchup(ctx):
    t = datetime(2025, 12, 1, tzinfo=UTC)
    ctx.store.upsert_entity_profile(EntityProfile(
        entity_id="team:home", sport="football", entity_type="team", display_name="Home",
        capabilities={"skill": .4, "rush_offense": .6, "run_defense": .2}, importance=1,
    ))
    ctx.store.upsert_entity_profile(EntityProfile(
        entity_id="team:away", sport="football", entity_type="team", display_name="Away",
        capabilities={"skill": .2, "rush_offense": .1, "run_defense": .3}, importance=1,
    ))
    ctx.store.upsert_entity_profile(EntityProfile(
        entity_id="player:home-rb", sport="football", entity_type="player", display_name="Home RB",
        team_id="team:home", role="rb1", capabilities={"skill": .5, "form": .2, "health": .8}, importance=.9,
    ))
    ctx.store.append_entity_metric(EntityMetric(
        entity_id="player:home-rb", sport="football", metric="recent_rushing", dimension="form",
        raw_value=112, normalized_value=.6, unit="yd/game", sample_size=5,
        occurred_at=t, known_to_model_time=t + timedelta(hours=1), source_id="stats",
    ))
    # Future information must not be visible at the event cutoff.
    ctx.store.append_entity_metric(EntityMetric(
        entity_id="player:home-rb", sport="football", metric="future_metric", dimension="form",
        raw_value=999, normalized_value=-1,
        occurred_at=datetime(2026, 2, 1, tzinfo=UTC), known_to_model_time=datetime(2026, 2, 1, tzinfo=UTC),
        source_id="future",
    ))
    ctx.store.append_context_signal(ContextSignal(
        event_id="context-game", sport="football", category="rivalry", effect="variance",
        label="Rivalry", summary="Public rivalry context", strength=.8, volatility=.5,
        observed_at=t, known_to_model_time=t + timedelta(hours=1), source_id="official",
    ))
    req = EventCreate(
        event_id="context-game", sport=Sport.FOOTBALL, competition="test", season="2026",
        outcomes=["home", "away"], start_time=datetime(2026, 1, 1, tzinfo=UTC), participants=["Home", "Away"],
        initial_features={}, metadata={"outcome_entity_ids": {"home": "team:home", "away": "team:away"}},
    )
    state = ctx.engine.create_event(req)
    snap = ctx.store.get_context_snapshot("context-game")
    assert len(snap.entity_states) == 3
    assert snap.matchup_edges
    assert snap.aggregate_features["historical_strength_diff"] > 0
    rb = next(e for e in snap.entity_states if e.entity_id == "player:home-rb")
    assert rb.dimensions["form"] > 0
    assert all(ev["metric"] != "future_metric" for ev in rb.recent_evidence)
    assert state.features["context_volatility"] > 0


def test_runtime_context_signal_updates_forecast_and_state(ctx):
    base = ctx.store.get_state("test-game")
    base.metadata["outcome_entity_ids"] = {"home": "team:test-home", "away": "team:test-away"}
    ctx.store.upsert_entity_profile(EntityProfile(
        entity_id="team:test-home", sport="football", entity_type="team", display_name="Home", capabilities={"skill": .2},
    ))
    ctx.store.upsert_entity_profile(EntityProfile(
        entity_id="team:test-away", sport="football", entity_type="team", display_name="Away", capabilities={"skill": .1},
    ))
    base, _ = ctx.context_engine.enrich_state(base, persist_snapshot=False)
    ctx.store.save_state(base)
    # Recompute rather than use the forecast cached before the profiles were injected.
    before = ctx.engine.forecast_state(base)

    t = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    obs = Observation(
        event_id="test-game", sport="football", kind="context_signal",
        payload={
            "category": "coaching", "effect": "mean", "label": "Verified public coaching update",
            "summary": "Public pregame update", "target_entity_id": "team:test-home",
            "direction": .8, "strength": .9, "sentiment": "positive",
        },
        source_id="official", source_type="official", known_to_model_time=t,
        ingestion_time=t + timedelta(seconds=1), sequence_no=1, verified=True,
    )
    after = ctx.engine.ingest(obs)
    state = ctx.store.get_state("test-game")
    snap = ctx.store.get_context_snapshot("test-game")
    assert state.state_version == 1
    assert snap.aggregate_features["context_mean_shift"] > 0
    assert after.probabilities["home"] != before.probabilities["home"]
    assert after.drivers[0].explanation and "not a causal" in after.drivers[0].explanation


def test_time_decay_prefers_recent_form(ctx):
    profile = EntityProfile(
        entity_id="player:decay", sport="football", entity_type="player", display_name="Decay Player",
        capabilities={"form": 0},
    )
    ctx.store.upsert_entity_profile(profile)
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    ctx.store.append_entity_metric(EntityMetric(
        entity_id="player:decay", sport="football", metric="old", dimension="form",
        raw_value=1, normalized_value=1, occurred_at=as_of - timedelta(days=180),
        known_to_model_time=as_of - timedelta(days=179), source_id="stats",
    ))
    ctx.store.append_entity_metric(EntityMetric(
        entity_id="player:decay", sport="football", metric="recent", dimension="form",
        raw_value=-1, normalized_value=-1, occurred_at=as_of - timedelta(days=1),
        known_to_model_time=as_of - timedelta(hours=12), source_id="stats",
    ))
    state = ctx.context_engine.estimate_entity_state(profile, as_of)
    assert state.dimensions["form"] < 0

def test_matching_opponent_history_gets_contextual_weight(ctx):
    profile = EntityProfile(
        entity_id="team:matchup-aware", sport="football", entity_type="team",
        display_name="Matchup Aware", capabilities={"form": 0.0},
    )
    ctx.store.upsert_entity_profile(profile)
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    # Same age/confidence/sample size, opposite evidence. The exact-opponent
    # record should receive more weight for this matchup than the unrelated one.
    ctx.store.append_entity_metric(EntityMetric(
        entity_id=profile.entity_id, sport="football", metric="vs_target", dimension="form",
        raw_value=1, normalized_value=.8, occurred_at=as_of-timedelta(days=14),
        known_to_model_time=as_of-timedelta(days=13), source_id="stats",
        opponent_id="team:target",
    ))
    ctx.store.append_entity_metric(EntityMetric(
        entity_id=profile.entity_id, sport="football", metric="vs_other", dimension="form",
        raw_value=-1, normalized_value=-.8, occurred_at=as_of-timedelta(days=14),
        known_to_model_time=as_of-timedelta(days=13), source_id="stats",
        opponent_id="team:other",
    ))
    versus_target = ctx.context_engine.estimate_entity_state(profile, as_of, opponent_id="team:target")
    versus_other = ctx.context_engine.estimate_entity_state(profile, as_of, opponent_id="team:other")
    assert versus_target.dimensions["form"] > 0
    assert versus_other.dimensions["form"] < 0


def test_latent_state_uses_learned_state_space_and_exposes_variance(ctx):
    profile = EntityProfile(
        entity_id="player:ssm", sport="football", entity_type="player", display_name="State Player",
        capabilities={"form": .1, "health": .5},
    )
    ctx.store.upsert_entity_profile(profile)
    as_of=datetime(2026,1,1,tzinfo=UTC)
    for days,val in [(60,-.2),(21,.1),(7,.55),(1,.72)]:
        ctx.store.append_entity_metric(EntityMetric(
            entity_id=profile.entity_id,sport="football",metric=f"form_{days}",dimension="form",
            raw_value=val,normalized_value=val,occurred_at=as_of-timedelta(days=days),
            known_to_model_time=as_of-timedelta(days=days)+timedelta(hours=1),source_id="stats",sample_size=5,
        ))
    state=ctx.context_engine.estimate_entity_state(profile,as_of)
    assert state.estimator_version.startswith("latent_state_")
    assert state.dimension_variance["form"] > 0
    assert state.dimensions["form"] > 0
    assert 0 < state.confidence <= 1
