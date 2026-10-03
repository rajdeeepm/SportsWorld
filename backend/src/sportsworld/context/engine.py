from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable
from pathlib import Path

from sportsworld.context.state_space import LatentStateSpaceModel

from sportsworld.schemas import (
    ContextCategory,
    ContextEffect,
    ContextSignal,
    ContextSnapshot,
    EntityMetric,
    EntityProfile,
    EntityType,
    LatentEntityState,
    MatchupEdge,
    Observation,
    SourceType,
    Sport,
    WorldState,
)


COMMON_DIMENSIONS = ("skill", "form", "health", "usage", "experience", "potential", "chemistry")
HALF_LIFE_DAYS = {
    "skill": 365.0,
    "form": 28.0,
    "health": 14.0,
    "usage": 21.0,
    "experience": 730.0,
    "potential": 365.0,
    "chemistry": 90.0,
    "coaching": 180.0,
}

# Each tuple is (label, home/offense dimension, away/defense dimension).  The
# engine evaluates the mirror image too so the final edge is a differential
# matchup rather than a one-sided rating.
MATCHUP_PAIRS: dict[Sport, list[tuple[str, str, str]]] = {
    Sport.FOOTBALL: [
        ("Rushing attack vs run front", "rush_offense", "run_defense"),
        ("Passing attack vs coverage", "pass_offense", "pass_defense"),
        ("Pass protection vs pass rush", "pass_protection", "pass_rush"),
        ("Special teams", "special_teams", "special_teams"),
    ],
    Sport.BASKETBALL: [
        ("Shot creation vs shot defense", "shot_creation", "shot_defense"),
        ("Rim pressure vs rim protection", "rim_pressure", "rim_protection"),
        ("Rebounding", "rebounding", "rebounding"),
        ("Ball security vs pressure", "turnover_control", "turnover_pressure"),
    ],
    Sport.HOCKEY: [
        ("Chance creation vs suppression", "xg_creation", "xg_suppression"),
        ("Power play vs penalty kill", "power_play", "penalty_kill"),
        ("Forecheck vs breakout", "forecheck", "breakout"),
        ("Goal prevention", "goaltending", "finishing"),
    ],
}

HUMAN_CONTEXT_CATEGORIES = {
    ContextCategory.SENTIMENT,
    ContextCategory.NARRATIVE,
    ContextCategory.COACHING,
    ContextCategory.AVAILABILITY,
    ContextCategory.HEALTH,
}
ENVIRONMENT_CATEGORIES = {
    ContextCategory.ENVIRONMENT,
    ContextCategory.WEATHER,
    ContextCategory.REST,
    ContextCategory.TRAVEL,
    ContextCategory.RIVALRY,
    ContextCategory.STAKES,
}


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _decay_weight(age_days: float, half_life_days: float) -> float:
    if age_days <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * age_days / max(half_life_days, 1e-6))


class ContextEngine:
    """Historical memory + latent entity state + event context compiler.

    SportsWorld's live scoreboard state is observable; this layer estimates the
    slower and partially observed state underneath it.  Historical metrics are
    filtered through a learned state-space estimator; player/driver states are aggregated into team/field beliefs,
    public contextual evidence is provenance-preserving, and sport-specific
    capability interactions become explicit matchup edges.

    Crucially, the engine never consumes evidence whose `known_to_model_time` is
    later than the prediction cutoff.  It also never treats public-language
    sentiment as a private psychological diagnosis: it stores the public signal
    exactly as evidence with confidence and provenance.
    """

    SHARED_OBSERVATION_KINDS = {"entity_metric", "context_signal", "entity_profile"}

    def __init__(self, store, latent_model: LatentStateSpaceModel | None = None):
        self.store = store
        if latent_model is not None:
            self.latent_model = latent_model
        else:
            # <repo>/backend/src/sportsworld/context/engine.py -> <repo>
            repo = Path(__file__).resolve().parents[4]
            artifact = repo / "models" / "artifacts" / "latent_state_dynamics_demo_v1.json"
            try:
                self.latent_model = LatentStateSpaceModel.load(artifact) if artifact.exists() else LatentStateSpaceModel()
            except Exception:
                # The system remains runnable even if a model artifact is damaged;
                # provenance exposes the fallback version instead of silently
                # pretending the learned estimator loaded successfully.
                self.latent_model = LatentStateSpaceModel(version="latent_state_fallback_v1", data_mode="fallback")

    def handles(self, kind: str) -> bool:
        return kind in self.SHARED_OBSERVATION_KINDS

    # ------------------------------------------------------------------
    # Entity-state estimation
    # ------------------------------------------------------------------
    def estimate_entity_state(self, profile: EntityProfile, as_of: datetime, opponent_id: str | None = None) -> LatentEntityState:
        """Estimate a posterior over the entity's current latent capabilities.

        Unlike the v1.1 weighted average, each dimension is now a learned
        linear-Gaussian state process.  Older evidence affects the prior through
        the transition model; recent measurements update that prior with a Kalman
        gain determined by learned process/observation noise and source quality.
        The posterior variance is preserved and later propagated into event-level
        context uncertainty.
        """
        metrics = [m for m in self.store.list_entity_metrics(profile.entity_id) if m.known_to_model_time <= as_of]
        by_dimension: dict[str, list[EntityMetric]] = defaultdict(list)
        for metric in metrics:
            by_dimension[metric.dimension].append(metric)

        dimensions = set(profile.capabilities) | set(by_dimension) | set(COMMON_DIMENSIONS)
        values: dict[str, float] = {}
        variances: dict[str, float] = {}
        evidence_weight = 0.0
        recent_evidence: list[dict] = []

        posterior_by_dim = {}
        for dimension in sorted(dimensions):
            observations = []
            for metric in by_dimension.get(dimension, []):
                relevance = 1.0
                if metric.opponent_id:
                    relevance = 1.30 if opponent_id and metric.opponent_id == opponent_id else 0.65
                observations.append({
                    "time": metric.occurred_at,
                    "value": float(metric.normalized_value),
                    "confidence": float(metric.confidence),
                    "sample_size": float(metric.sample_size),
                    "relevance": relevance,
                })
            posterior = self.latent_model.filter(
                dimension=dimension,
                prior_mean=float(profile.capabilities.get(dimension, 0.0)),
                observations=observations,
                as_of=as_of,
            )
            posterior_by_dim[dimension] = posterior
            values[dimension] = _clip(posterior.mean)
            variances[dimension] = float(posterior.variance)
            evidence_weight += posterior.evidence_weight

        for metric in sorted(metrics, key=lambda m: m.known_to_model_time, reverse=True)[:6]:
            post = posterior_by_dim.get(metric.dimension)
            recent_evidence.append(
                {
                    "metric": metric.metric,
                    "dimension": metric.dimension,
                    "raw_value": metric.raw_value,
                    "unit": metric.unit,
                    "normalized_value": metric.normalized_value,
                    "source_id": metric.source_id,
                    "known_to_model_time": metric.known_to_model_time.isoformat(),
                    "confidence": metric.confidence,
                    "opponent_id": metric.opponent_id,
                    "matchup_specific": bool(metric.opponent_id and opponent_id and metric.opponent_id == opponent_id),
                    "posterior_variance": float(post.variance) if post else None,
                }
            )

        # Map posterior variance to [0,1].  Sparse dimensions remain uncertain
        # even when a capability prior exists; repeated consistent observations
        # shrink the posterior naturally.
        vars_for_conf = [variances[d] for d in dimensions if d in variances]
        mean_var = float(sum(vars_for_conf) / max(len(vars_for_conf), 1)) if vars_for_conf else 0.35
        variance_conf = 1.0 / (1.0 + 3.5 * math.sqrt(max(mean_var, 0.0)))
        coverage_conf = min(1.0, math.log1p(max(evidence_weight, 0.0)) / 3.5)
        confidence = min(0.99, max(0.05, 0.25 + 0.55 * variance_conf + 0.20 * coverage_conf))
        return LatentEntityState(
            entity_id=profile.entity_id,
            display_name=profile.display_name,
            entity_type=profile.entity_type,
            team_id=profile.team_id,
            role=profile.role,
            as_of=as_of,
            dimensions=values,
            dimension_variance=variances,
            uncertainty=max(0.01, 1.0 - confidence),
            confidence=confidence,
            evidence_count=len(metrics),
            estimator_version=self.latent_model.version,
            recent_evidence=recent_evidence,
        )

    # ------------------------------------------------------------------
    # Event topology
    # ------------------------------------------------------------------
    def _outcome_entity_ids(self, state: WorldState) -> dict[str, str]:
        explicit = state.metadata.get("outcome_entity_ids") or state.metadata.get("participant_entity_ids") or {}
        if explicit:
            return {str(k): str(v) for k, v in explicit.items()}
        participants = list(state.metadata.get("participants") or [])
        if len(participants) == len(state.outcomes):
            return {outcome: f"{state.sport.value}:{participant.lower().replace(' ', '-')}" for outcome, participant in zip(state.outcomes, participants)}
        return {}

    def _profile_index(self, sport: Sport) -> dict[str, EntityProfile]:
        return {p.entity_id: p for p in self.store.list_entity_profiles(sport=sport)}

    def _members_for(self, team_id: str, profiles: Iterable[EntityProfile]) -> list[EntityProfile]:
        return [p for p in profiles if p.team_id == team_id and p.entity_type in {EntityType.PLAYER, EntityType.DRIVER, EntityType.UNIT, EntityType.COACH}]

    @staticmethod
    def _aggregate_dimension(team: LatentEntityState | None, members: list[tuple[EntityProfile, LatentEntityState]], dimension: str) -> float:
        team_value = float(team.dimensions.get(dimension, 0.0)) if team else 0.0
        weighted = [(max(0.05, p.importance), float(s.dimensions.get(dimension, 0.0))) for p, s in members]
        if not weighted:
            return team_value
        member_value = sum(w * v for w, v in weighted) / sum(w for w, _ in weighted)
        # Player/driver state matters most for health/usage; team priors matter
        # more for persistent system properties such as skill and chemistry.
        member_share = 0.65 if dimension in {"health", "usage", "form"} else 0.35
        return _clip((1.0 - member_share) * team_value + member_share * member_value)

    def _binary_matchups(
        self,
        state: WorldState,
        outcome_entities: dict[str, str],
        profiles: dict[str, EntityProfile],
        states: dict[str, LatentEntityState],
    ) -> list[MatchupEdge]:
        pairs = MATCHUP_PAIRS.get(state.sport, [])
        if len(state.outcomes) != 2 or not pairs:
            return []
        home_key, away_key = state.outcomes[0], state.outcomes[1]
        home_id, away_id = outcome_entities.get(home_key), outcome_entities.get(away_key)
        if not home_id or not away_id or home_id not in states or away_id not in states:
            return []
        home_state, away_state = states[home_id], states[away_id]
        edges: list[MatchupEdge] = []
        for label, offense_dim, defense_dim in pairs:
            home_attack = home_state.dimensions.get(offense_dim, profiles.get(home_id, EntityProfile(entity_id=home_id,sport=state.sport,entity_type=EntityType.TEAM,display_name=home_id)).capabilities.get(offense_dim, 0.0))
            away_defense = away_state.dimensions.get(defense_dim, profiles.get(away_id, EntityProfile(entity_id=away_id,sport=state.sport,entity_type=EntityType.TEAM,display_name=away_id)).capabilities.get(defense_dim, 0.0))
            away_attack = away_state.dimensions.get(offense_dim, profiles.get(away_id, EntityProfile(entity_id=away_id,sport=state.sport,entity_type=EntityType.TEAM,display_name=away_id)).capabilities.get(offense_dim, 0.0))
            home_defense = home_state.dimensions.get(defense_dim, profiles.get(home_id, EntityProfile(entity_id=home_id,sport=state.sport,entity_type=EntityType.TEAM,display_name=home_id)).capabilities.get(defense_dim, 0.0))
            advantage = _clip(((home_attack - away_defense) - (away_attack - home_defense)) / 2.0)
            confidence = min(home_state.confidence, away_state.confidence)
            edges.append(
                MatchupEdge(
                    source_entity_id=home_id,
                    target_entity_id=away_id,
                    label=label,
                    source_dimension=offense_dim,
                    target_dimension=defense_dim,
                    advantage=advantage,
                    confidence=confidence,
                    rationale=f"Differential {offense_dim} vs {defense_dim}; positive favors {home_state.display_name}.",
                )
            )
        return edges

    # ------------------------------------------------------------------
    # Signal interpretation
    # ------------------------------------------------------------------
    def _entity_side(self, entity_id: str | None, outcome_entities: dict[str, str], profiles: dict[str, EntityProfile]) -> str | None:
        if not entity_id:
            return None
        for outcome, root_id in outcome_entities.items():
            if entity_id == root_id:
                return outcome
            p = profiles.get(entity_id)
            if p and p.team_id == root_id:
                return outcome
        return None

    def _signal_features(self, state: WorldState, signals: list[ContextSignal], outcome_entities: dict[str, str], profiles: dict[str, EntityProfile]) -> tuple[dict[str, float], dict[str, float]]:
        if not state.outcomes:
            return {}, {}
        per_outcome = {o: 0.0 for o in state.outcomes}
        per_weight = {o: 0.0 for o in state.outcomes}
        human = {o: 0.0 for o in state.outcomes}
        human_w = {o: 0.0 for o in state.outcomes}
        env = {o: 0.0 for o in state.outcomes}
        env_w = {o: 0.0 for o in state.outcomes}
        variance_terms: list[float] = []

        for signal in signals:
            weight = signal.strength * signal.confidence * (1.0 if signal.verified else 0.25)
            if signal.effect == ContextEffect.VARIANCE:
                variance_terms.append(max(signal.volatility, signal.strength) * signal.confidence)
                continue
            side = self._entity_side(signal.target_entity_id, outcome_entities, profiles)
            if side in per_outcome and signal.effect == ContextEffect.MEAN:
                per_outcome[side] += weight * signal.direction
                per_weight[side] += weight
                if signal.category in HUMAN_CONTEXT_CATEGORIES:
                    human[side] += weight * signal.direction
                    human_w[side] += weight
                if signal.category in ENVIRONMENT_CATEGORIES:
                    env[side] += weight * signal.direction
                    env_w[side] += weight
            elif signal.target_entity_id is None and signal.effect == ContextEffect.MEAN:
                # Untargeted mean signals are displayed but not silently assigned
                # to a team/driver.  This prevents narrative text from acquiring
                # arbitrary directional meaning.
                pass
            variance_terms.append(signal.volatility * signal.confidence)

        outcome_adjustments = {
            o: _clip(per_outcome[o] / per_weight[o]) if per_weight[o] else 0.0
            for o in state.outcomes
        }
        if len(state.outcomes) == 2:
            h, a = state.outcomes[:2]
            features = {
                "context_mean_shift": _clip((outcome_adjustments[h] - outcome_adjustments[a]) / 2.0),
                "human_context_diff": _clip(((human[h] / human_w[h]) if human_w[h] else 0.0) - ((human[a] / human_w[a]) if human_w[a] else 0.0)) / 2.0,
                "environment_context_diff": _clip(((env[h] / env_w[h]) if env_w[h] else 0.0) - ((env[a] / env_w[a]) if env_w[a] else 0.0)) / 2.0,
                "context_volatility": min(1.0, sum(variance_terms) / max(1, len(variance_terms))),
            }
        else:
            features = {"context_volatility": min(1.0, sum(variance_terms) / max(1, len(variance_terms)))}
        return features, outcome_adjustments

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compile_snapshot(self, state: WorldState, as_of: datetime | None = None) -> ContextSnapshot:
        as_of = as_of or state.prediction_cutoff
        profiles_list = self.store.list_entity_profiles(sport=state.sport)
        profiles = {p.entity_id: p for p in profiles_list}
        outcome_entities = self._outcome_entity_ids(state)

        relevant_ids = set(outcome_entities.values())
        for root in list(relevant_ids):
            relevant_ids.update(p.entity_id for p in self._members_for(root, profiles_list))
        # F1 outcomes usually are the driver entities themselves.
        relevant_ids.update(v for v in outcome_entities.values() if v in profiles)

        entity_states: dict[str, LatentEntityState] = {}
        binary_opponents: dict[str, str] = {}
        if len(state.outcomes) == 2:
            left = outcome_entities.get(state.outcomes[0]); right = outcome_entities.get(state.outcomes[1])
            if left and right:
                binary_opponents[left] = right
                binary_opponents[right] = left
        for entity_id in relevant_ids:
            profile = profiles.get(entity_id)
            if profile and (profile.valid_from is None or profile.valid_from <= as_of) and (profile.valid_to is None or as_of <= profile.valid_to):
                root_id = profile.team_id or profile.entity_id
                entity_states[entity_id] = self.estimate_entity_state(profile, as_of, opponent_id=binary_opponents.get(root_id))

        # Fold player/unit state into each team root while preserving every
        # individual entity state for the UI and audit trail.
        for outcome, root_id in outcome_entities.items():
            root_profile = profiles.get(root_id)
            root_state = entity_states.get(root_id)
            if not root_profile or not root_state or root_profile.entity_type == EntityType.DRIVER:
                continue
            members = [(p, entity_states[p.entity_id]) for p in self._members_for(root_id, profiles_list) if p.entity_id in entity_states]
            for dimension in set(root_state.dimensions) | set(COMMON_DIMENSIONS):
                root_state.dimensions[dimension] = self._aggregate_dimension(root_state, members, dimension)
                member_vars = [(max(0.05, p.importance), float(es.dimension_variance.get(dimension, 0.25))) for p, es in members]
                if member_vars:
                    member_var = sum(w*w*v for w, v in member_vars) / max(sum(w for w, _ in member_vars) ** 2, 1e-9)
                    root_state.dimension_variance[dimension] = 0.55 * float(root_state.dimension_variance.get(dimension, 0.25)) + 0.45 * member_var
            if members:
                root_state.confidence = _clip(0.65 * root_state.confidence + 0.35 * sum(s.confidence * p.importance for p, s in members) / max(sum(p.importance for p, _ in members), 1e-9), 0.0, 1.0)
                root_state.uncertainty = 1.0 - root_state.confidence
                root_state.evidence_count += sum(s.evidence_count for _, s in members)

        matchup_edges = self._binary_matchups(state, outcome_entities, profiles, entity_states)
        signals = [s for s in self.store.list_context_signals(state.event_id) if s.known_to_model_time <= as_of]
        signal_features, outcome_adjustments = self._signal_features(state, signals, outcome_entities, profiles)

        aggregate: dict[str, float] = dict(signal_features)
        if len(state.outcomes) == 2:
            home_key, away_key = state.outcomes[0], state.outcomes[1]
            hs = entity_states.get(outcome_entities.get(home_key, ""))
            as_ = entity_states.get(outcome_entities.get(away_key, ""))
            def diff(dim: str) -> float:
                return _clip(((hs.dimensions.get(dim, 0.0) if hs else 0.0) - (as_.dimensions.get(dim, 0.0) if as_ else 0.0)) / 2.0)
            aggregate.update(
                {
                    "historical_strength_diff": diff("skill"),
                    "recent_form_diff": diff("form"),
                    "health_diff": diff("health"),
                    "usage_stability_diff": diff("usage"),
                    "experience_diff": diff("experience"),
                    "potential_diff": diff("potential"),
                    "chemistry_diff": diff("chemistry"),
                    "matchup_advantage": _clip(sum(e.advantage * e.confidence for e in matchup_edges) / max(sum(e.confidence for e in matchup_edges), 1e-9)) if matchup_edges else 0.0,
                }
            )
        else:
            # Multiclass sports use a per-outcome adjustment.  Add latent driver
            # ability/form/reliability so F1 can consume history without forcing
            # it into a fake home-away differential.
            for outcome, entity_id in outcome_entities.items():
                es = entity_states.get(entity_id)
                if es:
                    latent = 0.32 * es.dimensions.get("skill", 0.0) + 0.28 * es.dimensions.get("form", 0.0) + 0.16 * es.dimensions.get("health", 0.0) + 0.12 * es.dimensions.get("experience", 0.0) + 0.12 * es.dimensions.get("potential", 0.0)
                    outcome_adjustments[outcome] = _clip(0.65 * latent + 0.35 * outcome_adjustments.get(outcome, 0.0))

        confidences = [s.confidence for s in entity_states.values()] + [s.confidence for s in signals if s.verified]
        aggregate["context_confidence"] = float(sum(confidences) / len(confidences)) if confidences else 0.5

        provenance: dict[str, int] = defaultdict(int)
        for es in entity_states.values():
            for ev in es.recent_evidence:
                provenance[str(ev.get("source_id", "unknown"))] += 1
        for signal in signals:
            provenance[signal.source_id] += 1

        return ContextSnapshot(
            event_id=state.event_id,
            sport=state.sport,
            state_version=state.state_version,
            as_of=as_of,
            entity_states=sorted(entity_states.values(), key=lambda x: (x.entity_type.value, x.display_name)),
            matchup_edges=matchup_edges,
            signals=sorted(signals, key=lambda s: s.known_to_model_time, reverse=True),
            aggregate_features={k: float(v) for k, v in aggregate.items()},
            outcome_adjustments={k: float(v) for k, v in outcome_adjustments.items()},
            provenance_summary=dict(provenance),
            data_quality={
                "profile_count": len(entity_states),
                "signal_count": len(signals),
                "matchup_count": len(matchup_edges),
                "context_confidence": round(float(aggregate.get("context_confidence", 0.5)), 4),
                "latent_estimator": self.latent_model.version,
                "latent_data_mode": self.latent_model.data_mode,
                "time_valid": "yes",
            },
        )

    def enrich_state(self, state: WorldState, *, persist_snapshot: bool = False) -> tuple[WorldState, ContextSnapshot]:
        enriched = state.clone()
        snapshot = self.compile_snapshot(enriched, enriched.prediction_cutoff)
        enriched.features.update(snapshot.aggregate_features)
        enriched.features["context_outcome_adjustments"] = snapshot.outcome_adjustments
        # Preserve per-outcome latent posterior means/variances for multiclass
        # sport models (especially F1) without requiring them to reach back into
        # the context store at prediction time.
        outcome_entities = self._outcome_entity_ids(enriched)
        state_index = {es.entity_id: es for es in snapshot.entity_states}
        enriched.features["latent_outcomes"] = {
            outcome: dict(state_index[entity_id].dimensions)
            for outcome, entity_id in outcome_entities.items() if entity_id in state_index
        }
        enriched.features["latent_outcome_variance"] = {
            outcome: dict(state_index[entity_id].dimension_variance)
            for outcome, entity_id in outcome_entities.items() if entity_id in state_index
        }
        enriched.metadata["context"] = {
            "snapshot_version": snapshot.state_version,
            "as_of": snapshot.as_of.isoformat(),
            "entity_count": len(snapshot.entity_states),
            "signal_count": len(snapshot.signals),
            "matchup_count": len(snapshot.matchup_edges),
            "context_confidence": snapshot.aggregate_features.get("context_confidence", 0.5),
        }
        if persist_snapshot:
            self.store.save_context_snapshot(snapshot)
        return enriched, snapshot

    def ingest_observation(self, obs: Observation, state: WorldState) -> None:
        """Update memory/context stores from a normalized observation.

        Shared context kinds are full first-class ingestion records.  Selected
        sport observations also emit conservative derived context evidence so a
        live injury/weather/pace update changes both the scoreboard state and the
        latent/context layer.
        """
        p = obs.payload
        if obs.kind == "entity_profile":
            profile = EntityProfile.model_validate({**p, "sport": p.get("sport", obs.sport)})
            self.store.upsert_entity_profile(profile)
            return
        if obs.kind == "entity_metric":
            occurred = p.get("occurred_at") or obs.event_time or obs.known_to_model_time
            metric = EntityMetric(
                entity_id=str(p["entity_id"]), sport=obs.sport, metric=str(p["metric"]), dimension=str(p.get("dimension", p["metric"])),
                raw_value=p.get("raw_value", p.get("value", 0.0)), normalized_value=float(p.get("normalized_value", p.get("value", 0.0))),
                unit=p.get("unit"), sample_size=float(p.get("sample_size", 1.0)), occurred_at=occurred,
                known_to_model_time=obs.known_to_model_time, ingestion_time=obs.ingestion_time, source_id=obs.source_id,
                source_type=obs.source_type, source_url_or_ref=obs.source_url_or_ref, confidence=obs.confidence,
                event_id=obs.event_id, opponent_id=p.get("opponent_id"), season=p.get("season"), competition=p.get("competition"),
                tags=list(p.get("tags", [])) + ["runtime"],
            )
            self.store.append_entity_metric(metric)
            return
        if obs.kind == "context_signal":
            signal = ContextSignal(
                event_id=obs.event_id, sport=obs.sport, category=p.get("category", "narrative"), effect=p.get("effect", "mean"),
                label=str(p.get("label", "Context update")), summary=str(p.get("summary", p.get("label", "Context update"))),
                target_entity_id=p.get("target_entity_id"), direction=float(p.get("direction", 0.0)), strength=float(p.get("strength", 0.5)),
                volatility=float(p.get("volatility", 0.0)), sentiment=p.get("sentiment", "neutral"), observed_at=obs.event_time or obs.known_to_model_time,
                known_to_model_time=obs.known_to_model_time, ingestion_time=obs.ingestion_time, source_id=obs.source_id, source_type=obs.source_type,
                source_url_or_ref=obs.source_url_or_ref, confidence=obs.confidence, verified=obs.verified, parser_version=obs.parser_version,
                metadata={**dict(p.get("metadata", {})), "runtime": True},
            )
            self.store.append_context_signal(signal)
            return

        outcome_entities = self._outcome_entity_ids(state)
        target_entity: str | None = None
        team = p.get("team")
        if team in outcome_entities:
            target_entity = outcome_entities[str(team)]
            role = str(p.get("role", "")).lower()
            if role:
                candidates = [
                    prof for prof in self.store.list_entity_profiles(sport=state.sport, team_id=target_entity)
                    if str(prof.role or "").lower() == role
                    or (role == "qb" and str(prof.role or "").lower() == "starting_qb")
                ]
                if candidates:
                    target_entity = max(candidates, key=lambda prof: prof.importance).entity_id
        if p.get("entity_id"):
            target_entity = str(p["entity_id"])

        if obs.kind in {"injury_status", "availability"}:
            status = str(p.get("status", "available")).lower()
            direction = -0.95 if status in {"out", "unavailable", "injured"} else -0.45 if status in {"questionable", "limited"} else 0.25
            self.store.append_context_signal(
                ContextSignal(
                    event_id=obs.event_id, sport=obs.sport, category=ContextCategory.HEALTH, effect=ContextEffect.MEAN,
                    label=f"Availability: {p.get('role') or p.get('player') or 'participant'} {status}",
                    summary=f"Verified availability update ({status}); treated as public evidence, not a private health inference.",
                    target_entity_id=target_entity, direction=direction, strength=min(1.0, 0.45 + abs(float(p.get("impact", 0.0))) * 2.0),
                    volatility=0.15 if status in {"questionable", "limited"} else 0.05, sentiment="cautious" if direction < 0 else "positive",
                    observed_at=obs.event_time or obs.known_to_model_time, known_to_model_time=obs.known_to_model_time, ingestion_time=obs.ingestion_time,
                    source_id=obs.source_id, source_type=obs.source_type, source_url_or_ref=obs.source_url_or_ref, confidence=obs.confidence,
                    verified=obs.verified, parser_version=obs.parser_version, metadata={"runtime": True, "derived_from_observation": str(obs.observation_id)},
                )
            )
        elif obs.kind == "weather":
            severity = float(p.get("severity", p.get("rain_probability", 0.0)))
            self.store.append_context_signal(
                ContextSignal(
                    event_id=obs.event_id, sport=obs.sport, category=ContextCategory.WEATHER, effect=ContextEffect.VARIANCE,
                    label="Live weather regime", summary=f"Weather severity/rain signal updated to {severity:.2f}.", target_entity_id=None,
                    direction=0.0, strength=min(1.0, severity), volatility=min(1.0, 0.2 + 0.65 * severity), sentiment="neutral",
                    observed_at=obs.event_time or obs.known_to_model_time, known_to_model_time=obs.known_to_model_time, ingestion_time=obs.ingestion_time,
                    source_id=obs.source_id, source_type=obs.source_type, source_url_or_ref=obs.source_url_or_ref, confidence=obs.confidence,
                    verified=obs.verified, metadata={"runtime": True, "derived_from_observation": str(obs.observation_id)},
                )
            )
        elif obs.kind == "pace" and obs.sport == Sport.F1 and p.get("driver"):
            driver_id = outcome_entities.get(str(p["driver"]))
            if driver_id:
                # Lower pace_delta is faster; normalize conservatively around a
                # roughly +/-0.5 second demo operating range.
                pace_delta = float(p.get("pace_delta", 0.0))
                self.store.append_entity_metric(
                    EntityMetric(
                        entity_id=driver_id, sport=obs.sport, metric="live_pace_delta", dimension="form", raw_value=pace_delta,
                        normalized_value=_clip(-pace_delta / 0.5), unit="s/lap vs reference", sample_size=1.0,
                        occurred_at=obs.event_time or obs.known_to_model_time, known_to_model_time=obs.known_to_model_time,
                        ingestion_time=obs.ingestion_time, source_id=obs.source_id, source_type=obs.source_type,
                        source_url_or_ref=obs.source_url_or_ref, confidence=obs.confidence, event_id=obs.event_id, tags=["runtime", "live"],
                    )
                )


    def apply_scenario_proxy(self, state: WorldState, kind: str, payload: dict) -> WorldState:
        """Pure context adjustment for a hypothetical branch.

        Counterfactuals must never persist fake evidence. This method mirrors the
        conservative direction of common context updates directly on a cloned
        state's aggregate features so the simulator can reason about latent-state
        consequences without writing ContextSignal/EntityMetric rows.
        """
        s = state.clone()
        if len(s.outcomes) == 2:
            side = str(payload.get("team", "home"))
            sign = 1.0 if side == s.outcomes[0] or side == "home" else -1.0
            if kind in {"injury_status", "availability"}:
                status = str(payload.get("status", "available")).lower()
                severity = 0.75 if status in {"out", "unavailable", "injured"} else 0.35 if status in {"questionable", "limited"} else -0.15
                # If home is hurt, health_diff must move negative; away hurt moves positive.
                delta = -sign * severity * 0.35
                s.features["health_diff"] = _clip(float(s.features.get("health_diff", 0.0)) + delta)
                s.features["context_mean_shift"] = _clip(float(s.features.get("context_mean_shift", 0.0)) + delta * 0.55)
                s.features["context_volatility"] = min(1.0, float(s.features.get("context_volatility", 0.0)) + severity * 0.12)
            elif kind == "context_signal":
                direction = float(payload.get("direction", 0.0)); strength = float(payload.get("strength", 0.5))
                effect = str(payload.get("effect", "mean"))
                if effect == "mean":
                    s.features["context_mean_shift"] = _clip(float(s.features.get("context_mean_shift", 0.0)) + sign * direction * strength * 0.5)
                volatility = float(payload.get("volatility", 0.0))
                s.features["context_volatility"] = min(1.0, float(s.features.get("context_volatility", 0.0)) + volatility * strength)
        if kind == "weather":
            severity = float(payload.get("severity", payload.get("rain_probability", 0.0)))
            s.features["context_volatility"] = max(float(s.features.get("context_volatility", 0.0)), min(1.0, 0.2 + 0.65 * severity))
        return s

    def seed(self, profiles: list[EntityProfile], metrics: list[EntityMetric], signals: list[ContextSignal]) -> None:
        for profile in profiles:
            self.store.upsert_entity_profile(profile)
        for metric in metrics:
            self.store.append_entity_metric(metric)
        for signal in signals:
            self.store.append_context_signal(signal)
