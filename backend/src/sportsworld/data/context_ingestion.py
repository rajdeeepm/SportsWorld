from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sportsworld.schemas import (
    ContextCategory,
    ContextEffect,
    ContextSignal,
    EntityMetric,
    EntityProfile,
    EntityType,
    SourceType,
    Sport,
)


def normalize_entity_profile(
    *, entity_id: str, sport: Sport | str, entity_type: EntityType | str,
    display_name: str, team_id: str | None = None, role: str | None = None,
    capabilities: dict[str, float] | None = None, attributes: dict[str, Any] | None = None,
    importance: float = .5, source_ids: list[str] | None = None,
) -> EntityProfile:
    return EntityProfile(
        entity_id=entity_id, sport=sport, entity_type=entity_type, display_name=display_name,
        team_id=team_id, role=role, capabilities=capabilities or {}, attributes=attributes or {},
        importance=importance, source_ids=source_ids or [],
    )


def normalize_entity_metric(
    *, entity_id: str, sport: Sport | str, metric: str, dimension: str,
    raw_value: float | int | str, normalized_value: float, occurred_at: datetime,
    known_to_model_time: datetime, source_id: str, source_type: SourceType | str = SourceType.STATS,
    unit: str | None = None, sample_size: float = 1.0, confidence: float = 1.0,
    event_id: str | None = None, opponent_id: str | None = None,
    season: str | None = None, competition: str | None = None,
    source_url_or_ref: str | None = None, tags: list[str] | None = None,
) -> EntityMetric:
    return EntityMetric(
        entity_id=entity_id, sport=sport, metric=metric, dimension=dimension,
        raw_value=raw_value, normalized_value=normalized_value, unit=unit,
        sample_size=sample_size, occurred_at=occurred_at,
        known_to_model_time=known_to_model_time, ingestion_time=datetime.now(timezone.utc),
        source_id=source_id, source_type=source_type, source_url_or_ref=source_url_or_ref,
        confidence=confidence, event_id=event_id, opponent_id=opponent_id,
        season=season, competition=competition, tags=tags or [],
    )


def normalize_public_context_signal(
    *, event_id: str, sport: Sport | str, category: ContextCategory | str,
    label: str, summary: str, observed_at: datetime, known_to_model_time: datetime,
    source_id: str, source_type: SourceType | str = SourceType.NEWS,
    effect: ContextEffect | str = ContextEffect.MEAN, target_entity_id: str | None = None,
    direction: float = 0.0, strength: float = .5, volatility: float = 0.0,
    sentiment: str = "neutral", confidence: float = 1.0, verified: bool = True,
    source_url_or_ref: str | None = None, parser_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContextSignal:
    """Normalize a public contextual report without pretending it is private truth.

    The caller is responsible for sport-specific direction/normalization. An LLM
    extractor may populate this structure, but Pydantic validation and the
    ContextEngine still gate whether the signal can influence model state.
    """
    return ContextSignal(
        event_id=event_id, sport=sport, category=category, effect=effect, label=label,
        summary=summary, target_entity_id=target_entity_id, direction=direction,
        strength=strength, volatility=volatility, sentiment=sentiment,
        observed_at=observed_at, known_to_model_time=known_to_model_time,
        source_id=source_id, source_type=source_type, source_url_or_ref=source_url_or_ref,
        confidence=confidence, verified=verified, public_evidence_only=True,
        parser_version=parser_version, metadata=metadata or {},
    )
