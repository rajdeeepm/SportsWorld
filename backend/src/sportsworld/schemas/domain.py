from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


class Sport(str, Enum):
    F1 = "f1"
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    HOCKEY = "hockey"


class SourceType(str, Enum):
    OFFICIAL = "official"
    STATS = "stats"
    WEATHER = "weather"
    NEWS = "news"
    TELEMETRY = "telemetry"
    MANUAL = "manual"
    LLM_EXTRACTED = "llm_extracted"
    REPLAY = "replay"




class EntityType(str, Enum):
    TEAM = "team"
    PLAYER = "player"
    DRIVER = "driver"
    COACH = "coach"
    UNIT = "unit"
    VENUE = "venue"


class ContextCategory(str, Enum):
    HISTORY = "history"
    FORM = "form"
    HEALTH = "health"
    USAGE = "usage"
    EXPERIENCE = "experience"
    POTENTIAL = "potential"
    MATCHUP = "matchup"
    ENVIRONMENT = "environment"
    WEATHER = "weather"
    REST = "rest"
    TRAVEL = "travel"
    RIVALRY = "rivalry"
    STAKES = "stakes"
    COACHING = "coaching"
    AVAILABILITY = "availability"
    SENTIMENT = "sentiment"
    NARRATIVE = "narrative"


class ContextEffect(str, Enum):
    MEAN = "mean"
    VARIANCE = "variance"
    STATE_ONLY = "state_only"


class EntityProfile(BaseModel):
    """Slow-moving identity and capability prior for a real-world entity.

    Capability values are normalized to [-1, 1].  They are priors, not claims
    about an entity's exact current state; the ContextEngine updates them using
    point-in-time historical evidence.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    sport: Sport
    entity_type: EntityType
    display_name: str
    team_id: str | None = None
    role: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, float] = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("valid_from", "valid_to", "updated_at")
    @classmethod
    def validate_profile_tz(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: dict[str, float]) -> dict[str, float]:
        for key, score in value.items():
            if not -1.0 <= float(score) <= 1.0:
                raise ValueError(f"capability {key!r} must be normalized to [-1,1]")
        return {k: float(v) for k, v in value.items()}


class EntityMetric(BaseModel):
    """A point-in-time historical/current measurement for one entity.

    `raw_value` is what should be shown to a user (yards, touchdowns, EPA,
    rating, etc.). `normalized_value` is the sport-specific model feature in
    [-1, 1]. Keeping both prevents the UI from turning interpretable statistics
    into opaque normalized numbers.
    """

    model_config = ConfigDict(extra="forbid")

    metric_id: UUID = Field(default_factory=uuid4)
    entity_id: str
    sport: Sport
    metric: str
    dimension: str
    raw_value: float | int | str
    normalized_value: float = Field(ge=-1.0, le=1.0)
    unit: str | None = None
    sample_size: float = Field(default=1.0, ge=0.0)
    occurred_at: datetime
    known_to_model_time: datetime
    ingestion_time: datetime = Field(default_factory=utc_now)
    source_id: str
    source_type: SourceType = SourceType.STATS
    source_url_or_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    event_id: str | None = None
    opponent_id: str | None = None
    season: str | None = None
    competition: str | None = None
    tags: list[str] = Field(default_factory=list)
    dedupe_key: str | None = None

    @field_validator("occurred_at", "known_to_model_time", "ingestion_time")
    @classmethod
    def validate_metric_tz(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def compute_metric_dedupe(self) -> "EntityMetric":
        if self.dedupe_key is None:
            payload = {
                "entity_id": self.entity_id, "metric": self.metric,
                "occurred_at": self.occurred_at.isoformat(),
                "known_to_model_time": self.known_to_model_time.isoformat(),
                "source_id": self.source_id, "raw_value": self.raw_value,
            }
            self.dedupe_key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return self


class ContextSignal(BaseModel):
    """Public contextual evidence that may shift mean beliefs or uncertainty.

    A signal is intentionally not called a psychological state.  SportsWorld
    records what was publicly observed/reported, its provenance and confidence,
    and lets the quantitative layer learn/use only the validated signal.
    """

    model_config = ConfigDict(extra="forbid")

    signal_id: UUID = Field(default_factory=uuid4)
    event_id: str
    sport: Sport
    category: ContextCategory
    effect: ContextEffect = ContextEffect.MEAN
    label: str
    summary: str
    target_entity_id: str | None = None
    direction: float = Field(default=0.0, ge=-1.0, le=1.0)
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    volatility: float = Field(default=0.0, ge=0.0, le=1.0)
    sentiment: Literal["positive", "neutral", "cautious", "negative", "mixed"] = "neutral"
    observed_at: datetime
    known_to_model_time: datetime
    ingestion_time: datetime = Field(default_factory=utc_now)
    source_id: str
    source_type: SourceType = SourceType.NEWS
    source_url_or_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified: bool = True
    public_evidence_only: bool = True
    parser_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str | None = None

    @field_validator("observed_at", "known_to_model_time", "ingestion_time")
    @classmethod
    def validate_signal_tz(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def compute_signal_dedupe(self) -> "ContextSignal":
        if self.dedupe_key is None:
            payload = {
                "event_id": self.event_id, "category": self.category.value, "effect": self.effect.value,
                "label": self.label, "target_entity_id": self.target_entity_id,
                "known_to_model_time": self.known_to_model_time.isoformat(), "source_id": self.source_id,
            }
            self.dedupe_key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return self


class LatentEntityState(BaseModel):
    entity_id: str
    display_name: str
    entity_type: EntityType
    team_id: str | None = None
    role: str | None = None
    as_of: datetime
    dimensions: dict[str, float] = Field(default_factory=dict)
    dimension_variance: dict[str, float] = Field(default_factory=dict)
    uncertainty: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)
    estimator_version: str = "latent_state_default_v1"
    recent_evidence: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_latent_tz(cls, value: datetime) -> datetime:
        return _utc(value)


class MatchupEdge(BaseModel):
    source_entity_id: str
    target_entity_id: str
    label: str
    source_dimension: str
    target_dimension: str
    advantage: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str


class ContextSnapshot(BaseModel):
    """Auditable event-specific belief/context state at a prediction cutoff."""

    event_id: str
    sport: Sport
    state_version: int
    as_of: datetime
    entity_states: list[LatentEntityState] = Field(default_factory=list)
    matchup_edges: list[MatchupEdge] = Field(default_factory=list)
    signals: list[ContextSignal] = Field(default_factory=list)
    aggregate_features: dict[str, float] = Field(default_factory=dict)
    outcome_adjustments: dict[str, float] = Field(default_factory=dict)
    provenance_summary: dict[str, int] = Field(default_factory=dict)
    data_quality: dict[str, float | int | str] = Field(default_factory=dict)

    @field_validator("as_of")
    @classmethod
    def validate_context_tz(cls, value: datetime) -> datetime:
        return _utc(value)


class DriverMethod(str, Enum):
    REPLAY_DELTA = "replay_delta"
    SHAP = "shap"
    PERMUTATION = "permutation"
    LEAVE_ONE_EVENT_OUT = "leave_one_event_out"
    SCENARIO_DELTA = "scenario_delta"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID = Field(default_factory=uuid4)
    event_id: str
    sport: Sport
    kind: str
    payload: dict[str, Any]
    source_id: str
    source_type: SourceType = SourceType.STATS
    source_url_or_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    event_time: datetime | None = None
    known_to_model_time: datetime
    ingestion_time: datetime = Field(default_factory=utc_now)
    sequence_no: int = Field(default=0, ge=0)
    dedupe_key: str | None = None
    parser_version: str | None = None
    raw_record_ref: str | None = None
    verified: bool = True

    @field_validator("event_time", "known_to_model_time", "ingestion_time")
    @classmethod
    def validate_tz(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def compute_dedupe(self) -> "Observation":
        if self.dedupe_key is None:
            payload = {
                "event_id": self.event_id,
                "sport": self.sport.value,
                "kind": self.kind,
                "payload": self.payload,
                "source_id": self.source_id,
                "event_time": self.event_time.isoformat() if self.event_time else None,
                "known_to_model_time": self.known_to_model_time.isoformat(),
            }
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            self.dedupe_key = digest[:24]
        return self


class WorldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    sport: Sport
    competition: str
    season: str
    outcomes: list[str]
    features: dict[str, Any] = Field(default_factory=dict)
    state_version: int = 0
    observation_cursor: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    prediction_cutoff: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at", "prediction_cutoff")
    @classmethod
    def validate_state_tz(cls, value: datetime) -> datetime:
        return _utc(value)

    def clone(self) -> "WorldState":
        return self.model_copy(deep=True)


class UncertaintySummary(BaseModel):
    total: float = Field(ge=0.0, le=1.0)
    predictive_entropy: float | None = Field(default=None, ge=0.0, le=1.0)
    epistemic: float | None = Field(default=None, ge=0.0)
    aleatoric: float | None = Field(default=None, ge=0.0)
    state: float | None = Field(default=None, ge=0.0, le=1.0)
    method: str = "entropy"


class ForecastDriver(BaseModel):
    label: str
    target_outcome: str
    probability_delta: float
    score_delta: float | None = None
    method: DriverMethod = DriverMethod.REPLAY_DELTA
    source_id: str | None = None
    observation_id: UUID | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    explanation: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_driver_tz(cls, value: datetime) -> datetime:
        return _utc(value)


class Forecast(BaseModel):
    forecast_id: UUID = Field(default_factory=uuid4)
    event_id: str
    sport: Sport
    as_of: datetime
    state_version: int
    model_version: str
    calibration_version: str
    probabilities: dict[str, float]
    intervals_90: dict[str, tuple[float, float]]
    uncertainty: UncertaintySummary
    drivers: list[ForecastDriver] = Field(default_factory=list)
    simulation_summary: dict[str, Any] | None = None
    data_cutoff: datetime

    @field_validator("as_of", "data_cutoff")
    @classmethod
    def validate_forecast_tz(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def probabilities_valid(self) -> "Forecast":
        if not self.probabilities:
            raise ValueError("forecast requires outcomes")
        if any(p < -1e-9 or p > 1 + 1e-9 for p in self.probabilities.values()):
            raise ValueError("probabilities must be in [0,1]")
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > 1e-5:
            raise ValueError(f"probabilities must sum to 1, got {total}")
        for outcome, bounds in self.intervals_90.items():
            lo, hi = bounds
            if outcome not in self.probabilities or not (0 <= lo <= hi <= 1):
                raise ValueError("invalid probability interval")
        return self

    @property
    def leader(self) -> str:
        return max(self.probabilities, key=self.probabilities.get)


class EventCreate(BaseModel):
    event_id: str
    sport: Sport
    competition: str
    season: str
    outcomes: list[str]
    start_time: datetime
    participants: list[str] = Field(default_factory=list)
    venue: str | None = None
    initial_features: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Prediction cutoff of the initial state.  Defaults to start_time (replays);
    # live trackers pass "now" so pre-game evidence can be ingested before kickoff.
    as_of: datetime | None = None

    @field_validator("start_time", "as_of")
    @classmethod
    def validate_event_tz(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class EventRecord(BaseModel):
    event_id: str
    sport: Sport
    competition: str
    season: str
    outcomes: list[str]
    participants: list[str]
    venue: str | None
    start_time: datetime
    status: Literal["upcoming", "live", "completed", "replay"] = "replay"
    current_state_version: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioOperation(BaseModel):
    kind: str
    payload: dict[str, Any]
    effective_time: datetime | None = None
    effective_lap: int | None = None

    @field_validator("effective_time")
    @classmethod
    def validate_scenario_tz(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class CounterfactualRequest(BaseModel):
    base_event_id: str
    base_state_version: int | None = None
    overrides: list[ScenarioOperation]
    draws: int = Field(default=10_000, ge=100, le=100_000)
    seed: int | None = None
    label: str | None = None


class CounterfactualResult(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    event_id: str
    base_state_version: int
    label: str | None = None
    assumptions: list[ScenarioOperation]
    draws: int
    seed: int
    current_probabilities: dict[str, float]
    scenario_probabilities: dict[str, float]
    probability_delta_pp: dict[str, float]
    current_intervals_90: dict[str, tuple[float, float]]
    scenario_intervals_90: dict[str, tuple[float, float]]
    simulation_counts: dict[str, int]
    standard_error: dict[str, float]
    simulation_method: str = "sequential"
    current_mean_steps: float = 0.0
    scenario_mean_steps: float = 0.0
    representative_paths: list[list[dict[str, Any]]] = Field(default_factory=list)
    simulation_diagnostics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ScenarioParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ScenarioParseResult(BaseModel):
    text: str
    operations: list[ScenarioOperation]
    parser: str
    requires_confirmation: bool = True
    warnings: list[str] = Field(default_factory=list)


class BacktestRun(BaseModel):
    run_id: str
    sport: Sport
    competition: str
    model_version: str
    feature_schema_version: str
    train_window: dict[str, str]
    calibration_window: dict[str, str]
    test_window: dict[str, str]
    split_method: Literal["walk_forward", "rolling_origin", "chronological_holdout"]
    prediction_horizons: list[str]
    sample_counts: dict[str, int]
    metrics: dict[str, float]
    baselines: dict[str, dict[str, float]] = Field(default_factory=dict)
    ablations: list[dict[str, Any]] = Field(default_factory=list)
    slices: list[dict[str, Any]] = Field(default_factory=list)
    leakage_violations: int = 0
    reliability: list[dict[str, float | int]] = Field(default_factory=list)
    rolling: list[dict[str, Any]] = Field(default_factory=list)
    drift: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    data_mode: str = "historical"
    created_at: datetime = Field(default_factory=utc_now)
    git_commit: str = "unknown"
    data_snapshot_hash: str = "unknown"


class ModelCard(BaseModel):
    model_version: str
    sport: Sport
    # League-specific models (e.g. "nfl", "nba") take precedence over the sport-level model.
    competition: str | None = None
    algorithm: str
    feature_schema_version: str
    features: list[str]
    train_window: dict[str, str]
    calibration_window: dict[str, str]
    test_window: dict[str, str]
    artifact_uri: str
    calibration_version: str
    metrics: dict[str, float] = Field(default_factory=dict)
    data_mode: str = "historical"
    notes: list[str] = Field(default_factory=list)


class WSMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    type: str
    event_id: str
    sequence: int
    state_version: int | None = None
    sent_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
