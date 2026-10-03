# Historical Memory, Entity State, and Context Belief Layer

SportsWorld does not treat a live scoreboard as the complete state of a sporting event. The observable game/race state is only one stream of evidence. The forecasting state also incorporates point-in-time-valid historical memory, current form, player/driver availability, matchup interactions, environment, public human/context signals, and uncertainty about those signals.

The resulting hierarchy is:

```text
historical memory
      +
recent/current form
      +
player / driver / unit state
      +
matchup interactions
      +
environment and situational context
      +
verified public human/context signals
      +
live observations
      |
      v
latent/context belief snapshot
      |
      v
sport-specific forecast model
      |
      +--> calibrated probability distribution
      +--> uncertainty
      +--> forecast revision attribution
      +--> counterfactual simulation
```

## 1. Point-in-time rule

Every historical metric and context signal carries `known_to_model_time`. A forecast at time `T` may consume an item only when:

```text
known_to_model_time <= T
```

This applies equally to career/season data, injury reports, press-conference statements, lineup announcements, weather, and live observations. Retrospectively known information is not allowed to leak into an earlier forecast.

## 2. Entity profiles

`EntityProfile` stores slow-moving priors and identity relationships for:

- teams;
- players;
- drivers;
- coaches;
- units such as offensive line, defensive front, bench, special teams, or pit crew;
- venues.

Profiles can contain normalized capability priors such as `skill`, `form`, `health`, `experience`, `potential`, `chemistry`, plus sport-specific dimensions such as `rush_offense`, `run_defense`, `pass_rush`, `shot_creation`, `rim_protection`, `goaltending`, or `wet_weather`.

The profile is a prior, not a claim that the entity has a fixed true rating.

## 3. Historical and recent metrics

`EntityMetric` stores raw human-readable values together with a model-normalized value and provenance. Examples include career touchdowns, season rushing yards, EPA/play, pressure rate, player usage, lineup net rating, driver pace, tyre degradation, and reliability history.

These measurements are not simply averaged. They are treated as noisy observations of a latent capability that evolves through time. Each observation retains its time, source confidence, sample size, opponent-specific relevance, and information-availability cutoff.

## 4. Learned latent entity state

`ContextEngine.estimate_entity_state` now delegates to `LatentStateSpaceModel`, a learned linear-Gaussian state-space estimator. For a capability dimension `z_t` and noisy observation `y_t`, the serving model is conceptually:

```text
z_t = A(dt) z_(t-1) + process noise
y_t = z_t + observation noise
```

The transition persistence `phi`, process variance `q`, and observation variance `r` are fit from chronological sequences rather than fixed as hand-written half-lives. Irregular time gaps are handled explicitly. At serving time, each public/historical measurement is assimilated with a Kalman update whose effective observation noise depends on source confidence, sample size, and matchup relevance.

The posterior therefore carries both:

```text
posterior mean      -> best current estimate
posterior variance  -> how uncertain that estimate remains
```

`LatentEntityState` exposes:

```text
LatentEntityState
  entity_id
  dimensions                  # posterior means
  dimension_variance          # posterior variances
  confidence
  uncertainty
  evidence_count
  estimator_version
  recent_evidence[]
```

The bundled artifact `latent_state_dynamics_demo_v1` is fit from synthetic chronological sequences only to verify the full learning/training/serving path. A real deployment should refit the same estimator on point-in-time-valid longitudinal sports evidence.

Opponent-specific historical evidence is not treated as magic. A matching opponent changes measurement relevance/precision while general history remains in the posterior. Player/unit states are then aggregated into team state with role importance, preserving uncertainty.

## 5. Matchup graph

Sports are interactions, not scalar rankings. The context layer therefore creates explicit matchup edges.

Football currently models:

- rushing attack vs run front;
- passing attack vs coverage;
- pass protection vs pass rush;
- special teams.

Basketball currently models:

- shot creation vs shot defense;
- rim pressure vs rim protection;
- rebounding;
- ball security vs turnover pressure.

Hockey currently models:

- chance creation vs chance suppression;
- power play vs penalty kill;
- forecheck vs breakout;
- goaltending/finishing interactions.

F1 uses per-driver latent state and outcome-specific adjustments rather than forcing a binary matchup abstraction.

Each `MatchupEdge` contains the two entities/dimensions, a signed advantage, confidence, and an auditable rationale.

## 6. Context signals

`ContextSignal` captures public, source-attributed information that is not naturally represented as a box-score metric. Categories include:

- health and availability;
- coaching;
- environment and weather;
- rest and travel;
- rivalry;
- stakes;
- public sentiment;
- public narrative.

A signal has an explicit effect type:

- `mean`: allowed to alter the directional forecast context;
- `variance`: increases/decreases uncertainty without asserting which participant benefits;
- `state_only`: displayed for situational awareness but does not change the forecast mean.

This prevents narrative text from silently acquiring arbitrary directional meaning.

## 7. Human/context evidence boundary

SportsWorld can ingest *public evidence* such as official press conferences, team announcements, verified beat reporting, or public sentiment aggregates. It does **not** infer private mental-health states, private personal-life facts, or hidden emotions.

Examples of valid structured evidence:

```text
"Coach says starting QB remained limited in practice"
  -> availability/health context signal
  -> source + timestamp + confidence retained

"Three verified reports expect reduced RB workload"
  -> usage/availability signal
  -> consensus/provenance retained
```

The system may display a human/context panel and model whether such public signals historically add predictive value, but it never labels a player's private “morale” with fake precision.

## 8. Aggregate model features

For binary team sports, the context snapshot exports:

- `historical_strength_diff`
- `recent_form_diff`
- `health_diff`
- `usage_stability_diff`
- `experience_diff`
- `potential_diff`
- `chemistry_diff`
- `matchup_advantage`
- `context_mean_shift`
- `human_context_diff`
- `environment_context_diff`
- `context_volatility`
- `context_confidence`

F1 additionally exports per-outcome context adjustments derived from driver latent state and public context.

These features become part of the same versioned `WorldState` used by the forecast registry, so historical training and live serving can share definitions.

## 9. Runtime behavior

The context engine is called at event creation and after every accepted observation:

```text
Observation
   |
   +--> immutable observation log
   +--> sport reducer (when sport-state event)
   +--> ContextEngine memory update
             |
             +--> historical/current entity state
             +--> public context signals
             +--> matchup graph
             +--> aggregate context features
   |
   v
new WorldState version
   |
   v
Forecast
```

Context-only observations (`entity_profile`, `entity_metric`, `context_signal`) are first-class events. They can change the forecast even when score/clock/position does not change.

## 10. Counterfactuals

Counterfactual context operations modify a cloned branch only. A hypothetical QB injury, weather shift, or contextual signal affects the scenario's latent/context features without writing fake evidence into canonical history.

This is covered by tests that assert:

- the scenario forecast changes;
- contextual health/volatility features change;
- canonical world state does not change;
- canonical context-signal storage does not change.

## 11. Persistence

The context layer is supported in all store contracts. Durable schema adds:

- `entity_profiles`
- `entity_metrics`
- `context_signals`
- `context_snapshots`

The in-memory store supports deterministic offline demo/replay. The Postgres/Neon schema supports durable historical research. The SpacetimeDB module contains the equivalent live/subscription tables and reducer boundary.

## 12. UI

The event terminal includes a **Context Intelligence** panel that exposes:

- historical strength;
- recent form;
- health/availability;
- matchup advantage;
- public context;
- contextual volatility;
- team belief state;
- key player/unit belief states;
- recent raw evidence with provenance;
- matchup graph;
- public human/situational context signals.

The UI states that the layer estimates state from public evidence and does not infer private mental states.

## 13. Synthetic demo fixture

`data/fixtures/context/context_demo.json` contains synthetic contextual evidence for the three MHacks hero environments, including:

- Michigan/Ohio State team, player, and unit priors;
- raw career/season/recent football metrics such as career TD and rushing-yard examples;
- home/rivalry/rest/stakes context;
- verified-public-style practice/availability evidence;
- basketball player/team context;
- F1 driver historical/recent-form and rain-risk context.

These records exist to exercise the architecture. They are **not real empirical claims** and are labeled synthetic demo data.

## 14. Real-data replacement contract

A production historical/live provider only needs to normalize its information into:

- `EntityProfile` for slow priors/identity;
- `EntityMetric` for historical/current numeric evidence;
- `ContextSignal` for public contextual evidence;
- `Observation` for live state events.

No forecast-core redesign is required when changing providers.
