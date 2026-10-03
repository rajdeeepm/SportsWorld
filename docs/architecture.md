# Architecture invariants

1. Every source normalizes into a typed SportsWorld contract before forecasting: live events become `Observation`; slow identity priors become `EntityProfile`; longitudinal numeric evidence becomes `EntityMetric`; public situational evidence becomes `ContextSignal`.
2. `known_to_model_time`, not `event_time`, gates information availability across **both live and historical/context evidence**.
3. Canonical live state is versioned and reproducible from an immutable event stream.
4. Historical memory is explicit. Player/driver/team/unit priors and chronological evidence are filtered by a learned linear-Gaussian latent-state model into a versioned `ContextSnapshot`; context is not hidden in one opaque feature table.
5. Current latent entity state is an estimate with uncertainty, never a claim to observe a person's private “true state.” Public human/context evidence retains provenance and confidence.
6. Sports are modeled as interactions. Sport-specific matchup graphs represent player/unit/team capability interactions rather than reducing every participant to one scalar rating.
7. Sport adapters own live state semantics and final sport-specific features; the shared core owns orchestration, context compilation, model/calibration contracts, simulation, persistence, and transport.
8. Counterfactuals clone state and context features and never mutate canonical event history or persist hypothetical evidence.
9. LLM text becomes a typed proposal or source-attributed extraction and cannot set an authoritative probability.
10. Every forecast records model version, calibration version, state version, as-of time, and data cutoff.
11. Attribution is described as forecast/model revision, not real-world causality.
12. Replay and live ingestion share the same observation/context schemas.
13. Historical training and live serving consume the same context-feature definitions wherever possible to prevent train/serve skew.
14. Research metrics are stored with split/data/model versions and sample counts.

## Belief-state flow

```text
HISTORICAL MEMORY                     PUBLIC CONTEXT
career/season/recent metrics          reports / lineups / weather / rest / rivalry
        |                                      |
        v                                      v
EntityProfile + EntityMetric  --->  ContextSignal
        \                                      /
         \                                    /
          +------> ContextEngine <------------+
                    |
                    +--> latent entity states
                    +--> matchup graph
                    +--> contextual mean/variance
                    +--> provenance/confidence
                    |
                    v
              ContextSnapshot
                    |
                    +---------------------------+
                                                |
LIVE / REPLAY Observation --> sport reducer --> versioned WorldState
                                                |
                                                v
                                      context-enriched features
                                                |
                                                v
                                         model registry
                                                |
                                 calibration + uncertainty
                                                |
                                                v
                                             Forecast
                                      /                    \
                                     v                      v
                              attribution             scenario branch
                                                        + sequential futures
                                          (drives / possessions / laps)
```

See `docs/context_belief_layer.md` for the complete data and modeling contract.
