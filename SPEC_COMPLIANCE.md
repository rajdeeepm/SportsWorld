# Master specification implementation map — v1.2 learned world-state build

This file maps the master specification plus the historical/contextual and world-model upgrades to concrete source files. It separates executable implementation from external data/deployment steps that require real providers or credentials.

| Requirement | Status | Implementation |
|---|---|---|
| Three hero environments | Implemented | F1, football, basketball adapters + deterministic demo fixtures/replays |
| Cross-sport shared contract | Implemented | `schemas/domain.py`, `sports/base.py`, `core/engine.py` |
| Historical memory contracts | Implemented | `EntityProfile`, `EntityMetric`, source/provenance/timestamp fields |
| Learned latent/current entity state | Implemented | `context/state_space.py`: learned linear-Gaussian dynamics + Kalman filtering; `LatentEntityState` exposes posterior mean/variance and estimator version |
| Learned latent dynamics artifact | Implemented | `latent_state_dynamics_demo_v1.json`, fit from chronological synthetic sequences by `scripts/train_demo.py` |
| Matchup interaction graph | Implemented | football, basketball, hockey interaction edges; F1 per-driver latent/outcome context |
| Public human/context evidence | Implemented | `ContextSignal` mean/variance/state-only effects with confidence, verification, provenance; no private mental-state inference |
| Versioned context snapshots | Implemented | `ContextSnapshot` store/API/UI history tied to state version and prediction cutoff |
| Per-outcome latent state | Implemented | context enrichment writes `latent_outcomes` and posterior variances into versioned world state for multiclass models |
| Dual/tri timestamp validity | Implemented | `event_time`, `known_to_model_time`, `ingestion_time`; live filtering + historical leakage audit + SQL checks |
| Immutable event stream/versioned state | Implemented | Store interfaces + Memory/Postgres/SpacetimeDB tables |
| Learned football model | Implemented | `football_bootstrap_world_demo_v3`, bootstrap logistic ensemble, 22 features |
| Learned basketball model | Implemented | `basketball_bootstrap_world_demo_v1`, bootstrap logistic ensemble, 18 features |
| Learned F1 model | Implemented | `f1_conditional_softmax_world_demo_v1`, shared conditional-softmax bootstrap ensemble |
| Variable F1 outcome set | Implemented | shared learned per-driver scorer + race-level softmax rather than fixed class-specific weights |
| Calibration | Implemented | held-out chronological temperature scaling for all three hero models |
| Predictive/state/epistemic/context uncertainty | Implemented | entropy + context posterior/state uncertainty + bootstrap disagreement |
| 90% intervals | Implemented | calibrated bootstrap-member quantiles for learned models; Wilson intervals for sequential simulation outcomes |
| Forecast attribution | Implemented | replay-delta attribution with source/method/non-causal wording |
| Typed counterfactual branch | Implemented | `core/simulation.py`; branch never mutates canonical state/context |
| Football sequential simulator | Implemented | `simulators/football.py`: drive-by-drive clock, possessions, scores, turnovers/punts, late-game urgency, OT |
| Basketball sequential simulator | Implemented | `simulators/basketball.py`: possession-by-possession scoring, pace, lineup/star state, late-game fouling, OT |
| F1 sequential simulator | Implemented | `simulators/f1.py`: lap pace, tyre age/degradation, compounds, pit strategy, weather, SC, reliability/DNF, penalties |
| 10,000 sequential draws | Implemented | counterfactual default/full mode; deterministic seed; method/step count/paths/diagnostics returned |
| Representative simulated trajectory | Implemented | API returns representative drive/possession/lap path for audit/demo |
| Chronological backtests | Implemented | separate bundled reports for football, basketball, and F1 |
| Brier/log loss/ECE/accuracy/reliability | Implemented | `backtest/metrics.py`, `backtest/runner.py`, Research UI |
| Feature-group ablations | Implemented | A0 basic prior → A1 latent state → A2 context/matchup → A3 live/full world state for all hero sports |
| Baseline comparison | Implemented | empirical base-rate/winner-frequency baselines |
| Leakage audit | Implemented | zero violations in all bundled generated datasets |
| Rolling/drift/error view | Implemented | rolling Brier/log loss, PSI drift, confident-error explorer, sample-counted slices |
| REST API | Implemented | FastAPI endpoints from spec + context/entity routes |
| WebSocket live updates | Implemented | reconnectable history + `context.updated` |
| Cross-sport overview | Implemented | React page |
| Hero Event Terminal | Implemented | forecast/timeline/drivers/state/feed/context/scenario/replay controls |
| Context Intelligence UI | Implemented | posterior dimensions/variance, raw evidence, people/units, matchup graph, public context |
| Sequential scenario UI | Implemented | simulation method, mean steps, probability shift, representative future |
| Quant / Research | Implemented | sport selector now has bundled learned reports for football, basketball, F1 |
| Provenance/model card | Implemented | React page + endpoints + three hero manifests + latent-state manifest |
| Deterministic replay | Implemented | replay manager and JSONL packs |
| Natural-language scenario parsing | Implemented | deterministic parser + optional bounded Llama-compatible endpoint |
| No LLM probabilities | Enforced architecturally | LLM output is typed operations/extractions only |
| ElevenLabs | Implemented optional adapter | requires API key/voice ID |
| Fetch.ai uAgents | Implemented optional bridge | requires `uagents` install and Agentverse/network configuration |
| SpacetimeDB | Implemented module + store boundary | TypeScript live/context tables/reducers included; publish/bind requires credentials |
| Neon | Implemented Postgres schema/store | historical/context tables included; requires `DATABASE_URL` + migration |
| AWS | Implemented deployment artifacts | Docker + Terraform for S3/ECR/logs; actual deployment requires AWS credentials |
| Admin/CORS/secrets/idempotency/rate limit | Implemented | environment token, origin restriction, `.env` ignored, idempotent writes, expensive-endpoint limiter |
| Unit/property/integration/API tests | Implemented | **25-test** backend suite including learned latent state and all three sequential simulators |
| Offline operation | Implemented | memory store + synthetic history/context + learned local artifacts + deterministic replay |
| Hockey extension | Implemented functional adapter | non-hero extension; no learned hockey artifact bundled |
| Seven-competition family coverage | Architecture implemented | NFL/college football; NBA/college basketball; NHL/college hockey; F1 |

## Intentional truthfulness boundary

The repository now contains complete execution paths for learned latent-state estimation, three learned hero-sport forecasters, sequential counterfactual futures, context/provenance, and research evaluation. The bundled training data, latent dynamics, model metrics, and backtests are **synthetic demo artifacts**. Real predictive claims still require real point-in-time historical/context/live data, retraining, recalibration, and external-service deployment. That is a data/operations step rather than an architectural redesign.
