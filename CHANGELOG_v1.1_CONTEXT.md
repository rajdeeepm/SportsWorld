# v1.1 — Historical / Contextual Belief-State Extension

This revision implements the requested transition from a live-statistics predictor to a contextual world-state forecasting system.

## Added

- Historical Memory + Context Engine (`backend/src/sportsworld/context/engine.py`).
- Entity contracts for teams, players, drivers, coaches, units, and venues.
- Longitudinal `EntityMetric` records with raw value, normalized value, sample size, provenance, and point-in-time validity.
- Time-decayed latent entity-state estimation for skill, form, health, usage, experience, potential, chemistry, and sport-specific dimensions.
- Opponent-specific historical weighting for matchup history.
- Sport-specific matchup graphs for football, basketball, and hockey; per-driver contextual adjustment for F1.
- Public `ContextSignal` records for availability, coaching, weather, rest, travel, rivalry, stakes, sentiment, narrative, etc.
- Explicit signal effects: forecast mean, forecast variance, or state/display only.
- Versioned `ContextSnapshot` persisted beside each world-state version.
- Context-aware forecast uncertainty using contextual confidence and volatility.
- Context-aware counterfactual proxies that never persist hypothetical evidence.
- Context/entity REST APIs and `context.updated` WebSocket events.
- Memory, Postgres/Neon, and SpacetimeDB context persistence contracts.
- Historical/public context ingestion helpers and transport-agnostic context agent.
- Context-aware sport feature schemas; explicit home-field/home-court/home-ice treatment where appropriate.
- `ContextIntelligencePanel` UI with team/player belief state, raw evidence, matchup graph, public situational context and source confidence.
- Synthetic context fixture with career/season/recent football statistics, opponent-specific rivalry history, home context, rest/stakes/public availability, basketball context, and F1 driver history.
- 22-feature contextual football demo model and A0→A3 contextual ablations.
- Context documentation and data-source policy.
- Context-specific backend tests; suite now passes 20 tests.

## Scientific boundary

The bundled context/training/backtest values are synthetic and exist to verify the architecture. They are not evidence of real-world sports predictive performance. Public “sentiment” or narrative is treated as source-attributed evidence; SportsWorld does not infer private psychological states.
