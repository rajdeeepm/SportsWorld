from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sportsworld.schemas import Observation, SourceType, Sport


@dataclass
class PublicContextAgent:
    """Transport-agnostic adapter for verified contextual sources.

    It emits normal SportsWorld observations (`context_signal` or `entity_metric`)
    rather than directly touching forecasts. Fetch.ai/uAgents, RSS/news polling,
    team press feeds, or a human demo source can all wrap this object.
    """

    source_id: str
    source_type: SourceType = SourceType.NEWS
    parser_version: str = "context-agent-v1"

    def context_signal(
        self, *, event_id: str, sport: Sport, known_to_model_time: datetime,
        payload: dict[str, Any], sequence_no: int, event_time: datetime | None = None,
        confidence: float = .8, source_url_or_ref: str | None = None, verified: bool = True,
    ) -> Observation:
        return Observation(
            event_id=event_id, sport=sport, kind="context_signal", payload=payload,
            source_id=self.source_id, source_type=self.source_type,
            source_url_or_ref=source_url_or_ref, confidence=confidence,
            event_time=event_time, known_to_model_time=known_to_model_time,
            sequence_no=sequence_no, parser_version=self.parser_version, verified=verified,
        )

    def entity_metric(
        self, *, event_id: str, sport: Sport, known_to_model_time: datetime,
        payload: dict[str, Any], sequence_no: int, event_time: datetime | None = None,
        confidence: float = .9, source_url_or_ref: str | None = None, verified: bool = True,
    ) -> Observation:
        return Observation(
            event_id=event_id, sport=sport, kind="entity_metric", payload=payload,
            source_id=self.source_id, source_type=self.source_type,
            source_url_or_ref=source_url_or_ref, confidence=confidence,
            event_time=event_time, known_to_model_time=known_to_model_time,
            sequence_no=sequence_no, parser_version=self.parser_version, verified=verified,
        )
