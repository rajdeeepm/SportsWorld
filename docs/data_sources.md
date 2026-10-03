# Data-source and provenance policy

SportsWorld intentionally combines **historical**, **contextual**, and **live** information. Raw play-by-play alone is insufficient to represent the current competitive state.

## Source families

### Historical/statistical memory

Use official/public historical statistics or defensible archival datasets for:

- team and opponent-adjusted performance;
- player/driver career and season statistics;
- recent form windows;
- usage/snap/minutes history;
- lineup/unit performance;
- matchup history;
- coaching/system history;
- F1 driver/circuit/team/reliability history.

Numeric evidence is normalized to `EntityMetric` while preserving the raw human-readable value, unit, sample size, source, and `known_to_model_time`.

### Live structured state

Use official/public play-by-play, box score, timing, telemetry, lineup, roster, and weather feeds for scores, clocks, possessions, field position, player participation, race order, gaps, pit/tyre state, etc. These become normalized `Observation` records.

### Public contextual evidence

Use official team/league statements, press conferences, verified reporting, lineup/availability announcements, public weather/environment reports, and other source-attributed public context. These become `ContextSignal` records or, when numerical, `EntityMetric` records.

An LLM may extract a **candidate** structured signal from unstructured text, but source allowlisting/verification, schema validation, timestamping, and confidence are required before it affects state.

## Human/context boundary

Public context can include reported availability, coach statements, usage expectations, public sentiment aggregates, rivalry/stakes/rest/travel context, and verified reporting. SportsWorld does not infer or store private psychological/medical facts. “Sentiment” refers to observable public-language/context signals, not a diagnosis of a participant's mental state.

A signal explicitly declares whether it affects:

- forecast mean;
- forecast variance/uncertainty only; or
- display/state only.

Untargeted narrative cannot silently become a directional team advantage.

## Time validity

Every normalized observation, historical metric, and context signal carries source attribution and availability time. Historical feature generation rebuilds state from only evidence satisfying:

```text
known_to_model_time <= prediction_time
```

Missing data stays missing or receives a training-only imputation strategy; it is never filled from future records.

## Provider independence

The core does not depend on one sports-data vendor. Source-specific collectors normalize into these contracts:

```text
identity / slow priors        -> EntityProfile
historical numeric evidence   -> EntityMetric
public contextual evidence    -> ContextSignal
live sport-state evidence     -> Observation
```

This permits swapping an ESPN-style public feed, league/official source, F1 timing provider, weather API, news source, or paid historical vendor without rewriting the forecasting engine.

## Rumor and social media

Social/rumor data is excluded by default. If a research experiment explicitly enables it, it must retain its own `source_type`, verification state, confidence, and ablation slice so its incremental value can be evaluated separately rather than silently contaminating the primary model.
