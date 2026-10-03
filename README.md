# SportsWorld — MHacks 2026

SportsWorld is a real-time, cross-sport forecasting platform that combines longitudinal historical memory, estimated player/driver/team state, matchup interactions, public contextual evidence, environment, and live observations into a versioned belief state. It produces calibrated probabilistic forecasts with uncertainty, records forecast revisions, supports counterfactual simulation, and exposes a quant/research backtesting surface.

This repository is the implementation package for the SportsWorld MHacks 2026 master build specification.

## v3.0 — competition-season world models on real data

SportsWorld models **entire competitions**: every team, every scheduled game, every live state, simulated to
the championship. NFL, FBS, NBA, WNBA, NCAA men's/women's basketball, NHL, NCAA hockey (ESPN) and Formula 1
(Jolpica + OpenF1), ~60,000 real games of history.

* **Season terminal** (`/competition/:cid`): calibrated forecast for every remaining game, standings audited
  against ESPN, 10,000-season Monte Carlo through versioned playoff rules (NFL, NBA play-in, NHL wildcard,
  CFP 12-team, NCAA, F1 driver + constructor titles), world-update feed, team pages, season what-ifs.
* **Propagation**: finals and live injury reports → latent team state → every affected future game →
  season distribution, each step versioned. Games in progress condition the season run on their live state.
* **Learned components**: Kalman latent strength (team; driver + car for F1), calibrated per-league outcome
  models with calibration-window model selection, learned football expected points, learned player-
  availability effects.
* **Llama 3.3 70B** (self-hosted, vLLM): natural-language season scenarios → typed operations; ESPN news →
  grounded, source-attributed evidence with disagreement flags. It never produces a probability.
* **Research**: historical season replay (2019–25) shows independent-game simulation is badly overconfident
  while correlated latent-state simulation is near-nominally calibrated; in-game bake-off with game-clustered
  paired bootstraps; external market consensus benchmark. Write-up: [`docs/research_report.md`](docs/research_report.md).

```bash
make real-data && make train-real          # backfill + train (one-off)
make live                                  # API: tracker + season engine + availability + news
make frontend                              # http://localhost:5173  (Seasons · Live games · Quant / Research)
```
Status against the spec: [`docs/SPEC_V3_COMPLIANCE.md`](docs/SPEC_V3_COMPLIANCE.md). Data feeds: [`docs/real_data.md`](docs/real_data.md),
[`docs/overnight_plan.md`](docs/overnight_plan.md). Compute orchestration across GPU hosts: [`ops/orchestrator.py`](ops/orchestrator.py).

## What is implemented

- Shared normalized `Observation`, `WorldState`, `Forecast`, `ForecastDriver`, counterfactual, model-card, and backtest contracts.
- First-class **Historical Memory + Entity State + Context Engine** with `EntityProfile`, `EntityMetric`, `ContextSignal`, `LatentEntityState`, `MatchupEdge`, and versioned `ContextSnapshot` contracts.
- **Learned linear-Gaussian latent-state estimation** for skill, form, health, usage, experience, potential, chemistry, and coaching. Persistence/process/observation noise are fit from chronological sequences; every entity state exposes posterior means, posterior variances, estimator version, raw evidence, and provenance.
- Player/driver/unit state rolls into team/field belief state, while sport-specific matchup graphs model interactions such as rush offense vs run defense instead of collapsing every participant to a single scalar.
- Public human/situational context supports mean, variance-only, or display-only effects so verified context can be modeled without turning narrative into an arbitrary directional feature or inferring private mental states.
- Independent `event_time`, `known_to_model_time`, and `ingestion_time`; stale evidence is rejected in the live path and leakage is audited in historical feature rows.
- Immutable observation log and versioned state snapshots.
- Functional sport adapters for Formula 1, American football, basketball, and a hockey extension adapter.
- Learned **football** hero model: 22-feature contextual bootstrap logistic ensemble (`football_bootstrap_world_demo_v3`) with held-out temperature scaling and ensemble epistemic uncertainty.
- Learned **basketball** hero model: contextual bootstrap logistic ensemble (`basketball_bootstrap_world_demo_v1`) over latent state, matchup/context, lineup, pace, possession, and live score state.
- Learned **F1** hero model: shared conditional-softmax bootstrap ensemble (`f1_conditional_softmax_world_demo_v1`) that scores a variable driver field using grid/position, pace, reliability, tyres/penalties, weather, contextual adjustment, and latent driver state.
- Hockey remains the documented extension adapter; the three MHacks hero sports all use learned model artifacts.
- Sequential forecast updates and non-causal replay-delta attribution.
- Reproducible **sequential** 10,000-draw counterfactual simulation without canonical-state mutation: drive-by-drive football, possession-by-possession basketball, and lap-by-lap F1 with strategy/weather/reliability transitions.
- Chronological backtesting, Brier score, log loss, accuracy, ECE, 90% interval coverage/width, reliability data, rolling performance, calibrated feature-group ablations, research slices, PSI drift diagnostics, confident-error exploration, baseline comparison, and a zero-leakage audit.
- Deterministic replay engine with reset, step, play, pause, and seek controls.
- FastAPI REST API and WebSocket event stream with missed-message history.
- React + TypeScript terminal with overview, hero live/replay event screen, **Context Intelligence** panel, research terminal, provenance screen, probability timelines, event feed, forecast drivers, matchup graph, entity belief state, public-context evidence, and scenario console.
- Optional Fetch.ai uAgents bridge, current SpacetimeDB 2.0 TypeScript module, Neon/Postgres schema/store, AWS artifact/deployment infrastructure, bounded Llama-compatible scenario parser, and ElevenLabs TTS adapter.
- Docker, CI, reproducible demo-data generator, model-training script, tests, and offline fallback fixtures.

## Scientific-integrity note

The repository ships **synthetic deterministic demo events**, synthetic point-in-time-valid training sets for **football, basketball, and F1**, and synthetic longitudinal sequences used to fit the latent-state dynamics artifact. This allows the complete model/calibration/uncertainty/backtest/leakage/simulation/UI path to run without a paid sports-data provider. The UI/API labels those values as `synthetic_demo`. They must not be presented as empirical real-world sports performance.

Before final judging, replace or supplement the generated dataset with an actual historical source whose information-availability timestamps are defensible, rerun `scripts/train_demo.py` or a production training job, and preserve the resulting model/data versions. No code path requires fabricated metrics.

## Architecture

```text
HISTORICAL DATA          PUBLIC CONTEXT          LIVE DATA
career / season /        reports / lineup /      play-by-play / timing /
recent form / usage      weather / rest / stakes telemetry / injuries
       |                       |                         |
       v                       v                         v
EntityProfile +         ContextSignal              Observation
EntityMetric                   |                         |
       \                       |                         |
        +-------> Historical Memory + Context Engine <---+
                         |
                         +--> latent entity states
                         +--> matchup graph
                         +--> context mean / volatility
                         +--> provenance / confidence
                         |
                         v
                    ContextSnapshot
                         |
                         v
                 versioned WorldState
                         |
                  sport-specific model
                         |
                calibration + uncertainty
                         |
                  Forecast + Drivers
                    /             \
                   v               v
           forecast history   counterfactual branch
                                   |
                              Monte Carlo

SpacetimeDB  <--- live/event/context path ---> WebSocket UI
Neon/Postgres <--- historical/context/backtest/model metadata
S3/AWS       <--- versioned binary artifacts
```

The full belief-state contract is documented in [`docs/context_belief_layer.md`](docs/context_belief_layer.md).

## Fast start

### 1. Regenerate fixtures and model artifact

The generated repository already includes these outputs, but this proves they are reproducible:

```bash
python scripts/generate_demo_data.py
PYTHONPATH=backend/src python scripts/train_demo.py
```

### 2. Run backend tests

```bash
cd backend
PYTHONPATH=src pytest
```

Expected result for this package: **25 passed**.

### 3. Start the API

From the repository root:

```bash
./scripts/run_demo.sh
```

API: `http://localhost:8000`
OpenAPI: `http://localhost:8000/docs`

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

UI: `http://localhost:5173`

### 5. One-command smoke test

```bash
PYTHONPATH=backend/src SPORTSWORLD_ENV=demo python scripts/smoke_test.py
```

## Demo events

| Event ID | Sport | Purpose |
|---|---|---|
| `mich-osu-2026-demo` | football | learned model, score/possession/weather/injury revisions, QB counterfactual |
| `basketball-2026-demo` | basketball | learned model, lineup/pace/availability state changes, possession-by-possession futures |
| `demo-gp-2026` | F1 | learned multiclass forecast, rain, pit stops, safety car, reliability, lap-by-lap futures |

All are clearly marked synthetic replay fixtures.

## Five-minute judging flow

1. Open **Overview** and point out that all three hero sports use one domain/forecast contract but separate reducers/features.
2. Open `mich-osu-2026-demo`; inspect **Context Intelligence** first: historical/team priors, recent form, player/unit state, matchup edges, rivalry/rest/home context, raw evidence and provenance. Then reset and step/play the replay so live evidence updates that belief state and the forecast without refresh.
3. Enter “What if the starting QB leaves the game?” in the scenario console. Parse it into a typed operation, inspect the assumptions, then run 10,000 **drive-by-drive** futures and open one representative simulated path.
4. Open `demo-gp-2026` and step through rain/pit/reliability events. The learned shared driver scorer produces a calibrated multiclass distribution; a scenario rolls the race forward lap by lap.
5. Open **Quant / Research**. Show the chronological train/calibration/test split, Brier/log loss/ECE, reliability diagram, baseline comparison, model/data hash, and leakage violations = 0. Make clear the bundled dataset is synthetic demo data unless it has been replaced before judging.
6. Open **Provenance** to show the active model card, source registry, dependency health, and timestamp invariant.

## API matrix

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | service/integration health |
| GET | `/sports` | supported adapters and event kinds |
| GET | `/sources` | provenance registry |
| GET/POST | `/events` | list/create events |
| GET | `/events/{id}` | event + state + forecast |
| POST | `/events/{id}/observations` | idempotent normalized ingest |
| POST | `/events/{id}/observations/batch` | batch ingest |
| GET | `/events/{id}/observations` | immutable audit stream |
| GET | `/events/{id}/forecast` | latest forecast |
| GET | `/events/{id}/forecasts` | forecast time series |
| GET | `/events/{id}/context` | latest historical/entity/matchup/context belief snapshot |
| GET | `/events/{id}/context/history` | versioned context-snapshot history |
| GET | `/events/{id}/context/signals` | public contextual evidence for the event |
| GET/POST | `/entities` | list/create team/player/driver/coach/unit priors |
| GET | `/entities/{entity_id}` | entity profile + estimated state + evidence |
| POST | `/entities/{entity_id}/metrics` | append point-in-time historical/current metric |
| POST | `/events/{id}/scenario/parse` | text -> typed scenario proposal |
| POST | `/events/{id}/counterfactuals` | scenario branch + Monte Carlo |
| GET | `/events/{id}/explanation` | bounded deterministic explanation |
| GET | `/backtests/{sport}` | approved/bundled research report |
| GET | `/models/{sport}/active` | active model card |
| POST | `/demo/{id}/replay` | replay control |
| WS | `/ws/events/{id}` | state/forecast/observation/replay stream |
| POST | `/voice/narrate` | ElevenLabs TTS when configured |

## Time validity

Every live observation, historical metric, and context signal is point-in-time valid. Live observations expose three different temporal meanings:

- `event_time`: when the real-world event happened.
- `known_to_model_time`: earliest time the model was permitted to know it.
- `ingestion_time`: when SportsWorld actually received it.

Historical rows are legal only when:

```text
max_known_to_model_time <= prediction_time
```

The Postgres schema enforces this for feature snapshots, the Python leakage auditor tests it, and the UI exposes the audit result.

## Model hierarchy

The hero path is now learned end-to-end at all three required modeling layers:

1. **Latent entity state** — `LatentStateSpaceModel` uses a learned linear-Gaussian state process for each capability dimension. Historical/current measurements are assimilated chronologically with a Kalman update, and posterior variance is propagated into context confidence. The bundled `latent_state_dynamics_demo_v1` parameters are fit from synthetic sequences solely to verify training/serving parity.
2. **Outcome models** — football and basketball use calibrated bootstrap binary logistic ensembles; F1 uses a calibrated bootstrap conditional-softmax ensemble with a shared driver scorer. All three are selected through the same `ModelRegistry` and carry model cards/data hashes.
3. **Sequential futures** — counterfactuals do not resample the terminal model distribution. Football advances drive by drive, basketball advances possession by possession, and F1 advances lap by lap with stochastic scoring/pace, clock, strategy, weather, safety-car, tyre and reliability dynamics as appropriate.

The transparent sport-adapter equations remain only as emergency fallbacks and debugging baselines. Hockey is the non-hero extension path.

Active artifacts:

- `models/artifacts/latent_state_dynamics_demo_v1.json`
- `models/artifacts/football_bootstrap_world_demo_v3.json`
- `models/artifacts/basketball_bootstrap_world_demo_v1.json`
- `models/artifacts/f1_conditional_softmax_world_demo_v1.json`

Every bundled artifact/report is labeled `synthetic_demo`; none of its metric values should be described as real-world predictive performance.

## Sponsor integrations

### Fetch.ai

`backend/src/sportsworld/agents/fetch_uagent.py` provides a real optional `uagents` bridge, and `backend/src/sportsworld/agents/context_agent.py` normalizes historical/public context into entity metrics and context signals. Agent transport can never inject an authoritative probability.

### SpacetimeDB

`infra/spacetimedb/src/index.ts` is a SpacetimeDB TypeScript module defining public event, observation, state-snapshot, forecast, entity-profile, historical-metric, context-signal, and context-snapshot tables plus reducers. The Python store adapter is isolated behind `Store` so generated bindings/gateway code can be swapped without changing forecasting logic.

### Neon

`infra/sql/001_init.sql` defines the complete durable Postgres research schema. `PostgresStore` uses `DATABASE_URL`; Neon works as a standard Postgres provider.

### AWS

`infra/aws/main.tf` provisions a versioned artifact bucket, CloudWatch log group, and ECR repository. Dockerfiles are included for backend/frontend. A deployment is not claimed until the team actually publishes the image/endpoint.

### Meta / Llama

The scenario parser can call an OpenAI-compatible endpoint hosting Llama when `LLM_PROVIDER`, `LLM_BASE_URL`, and `LLM_API_KEY` are configured. Its output is typed JSON only and must pass schema/domain validation before simulation. The model never supplies a probability.

### ElevenLabs

`backend/src/sportsworld/voice.py` calls the ElevenLabs text-to-speech endpoint only when credentials/voice ID exist. Voice is presentation-only; typed UI remains canonical.

### D. E. Shaw

No fake API integration. The relevant artifact is the Quant / Research terminal: point-in-time validation, proper scoring rules, calibration, uncertainty, backtesting, model lineage, drift-ready rolling diagnostics, baseline comparison, and counterfactual analysis.

## Persistence modes

`STORE_BACKEND=memory` is the zero-dependency demo/replay mode.

`STORE_BACKEND=postgres` uses Neon/Postgres and `DATABASE_URL`; install `sportsworld[postgres]` and apply `infra/sql/001_init.sql`.

`STORE_BACKEND=spacetimedb` uses the adapter/gateway path and the included SpacetimeDB module.

## Security

- Mutation/replay endpoints can be protected with `ADMIN_API_TOKEN`.
- Secrets live only in environment variables; `.env` is ignored.
- CORS is restricted to `FRONTEND_ORIGIN` plus local dev.
- Payloads are Pydantic-validated.
- Observation writes accept `Idempotency-Key`; canonical payload deduplication also remains active.
- Counterfactual, scenario-parsing, and voice endpoints have an in-process per-client rate limiter suitable for the single-instance hackathon deployment.
- LLM text never executes code or directly mutates state.
- Sponsor/provider calls have bounded timeouts.
- Replay fallback avoids dependence on internet availability during judging.

## Repository layout

```text
backend/             FastAPI, forecasting core, sport adapters, stores, agents, tests, requirements.lock
frontend/            React/TypeScript quant terminal (direct dependencies pinned exactly)
data/replays/         deterministic offline judge replays
data/fixtures/        demo events, context-memory fixture, generated contextual training rows, backtest report
models/artifacts/     versioned learned model/calibrator artifact
models/manifests/     model card metadata
scripts/              generate/train/smoke/run helpers
infra/docker/         local/prod containers
infra/sql/            Neon/Postgres schema
infra/spacetimedb/    SpacetimeDB 2.0 module
infra/aws/            Terraform starter for artifacts/logging/ECR
docs/                 architecture, context-belief layer, data policy, model card, demo guide, master specification
```

## Final pre-submission replacement checklist

The software package is complete enough to run end-to-end now. Before presenting **real predictive performance**, the team should still do the external-data/deployment work that cannot be truthfully pre-baked into a source archive:

1. Acquire the chosen real historical, contextual, roster/news/weather, and live feeds and record defensible `known_to_model_time` values for every evidence class.
2. Materialize real point-in-time longitudinal sequences and feature rows; refit the latent-state dynamics plus all three hero outcome models/calibrators; replace the synthetic model cards/backtests.
3. Add real sponsor credentials, publish the SpacetimeDB module/Fetch agents if those prize tracks are pursued, and deploy the chosen AWS/Neon services.
4. Run the full test suite, internet-off replay drill, projector QA, and record the final demo video.

No architecture changes are required for those substitutions.
