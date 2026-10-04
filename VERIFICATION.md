# SportsWorld v1.2 verification: learned world-state build

Verification was rerun on the final v1.2 source tree after the learned-state, sequential-simulation, and three-hero-model upgrades.

## Executed checks

- Demo/historical synthetic fixture regeneration: **PASS** (`python scripts/generate_demo_data.py`).
- Latent dynamics + football + basketball + F1 training pipeline: **PASS** (`PYTHONPATH=backend/src python scripts/train_demo.py`).
- Backend unit/property/integration/API suite: **25 passed**.
- Offline end-to-end API smoke test: **PASS**.
- Python `compileall` over `backend/src` and `scripts`: **PASS**.
- TypeScript/TSX syntax transpilation: **PASS, 19 files** across frontend and SpacetimeDB source.
- Point-in-time leakage audit in all bundled hero-sport reports: **0 violations**.
- Counterfactual branches remain isolated from canonical state/context: covered by tests.
- Model registry resolves learned artifacts for **football, basketball, and Formula 1**.
- Context engine resolves the learned latent-state dynamics artifact and exposes posterior variance.

## 10,000-future sequential-simulation benchmark

Measured locally on the bundled deterministic demo states after retraining. These are engineering runtime measurements, not predictive-performance claims.

| Event | Active model | Transition model | Draws | Runtime | Mean simulated transitions |
|---|---|---|---:|---:|---:|
| `mich-osu-2026-demo` | `football_bootstrap_world_demo_v3` | drive by drive | 10,000 | ~0.029 s | 25.54 |
| `basketball-2026-demo` | `basketball_bootstrap_world_demo_v1` | possession by possession | 10,000 | ~0.067 s | 200.58 |
| `demo-gp-2026` | `f1_conditional_softmax_world_demo_v1` | lap by lap | 10,000 | ~0.767 s | 57.00 |

Each benchmark produced exactly 10,000 terminal outcomes. Runtime is hardware/environment dependent.

## Algorithmic implementation verification

### 1. Learned latent-state estimation

`backend/src/sportsworld/context/state_space.py` implements a trainable linear-Gaussian state-space estimator. Parameters are fit from chronological sequences, and serving uses Kalman prediction/update steps. Entity state now carries posterior mean and posterior variance rather than only a hand-weighted score. `known_to_model_time` remains the hard evidence cutoff.

### 2. Sequential future simulation

`backend/src/sportsworld/simulators/` contains explicit sport transition models:

- football: drive-by-drive clock, score, turnover/punt, possession and overtime evolution;
- basketball: possession-by-possession scoring, pace, lineups/star state, late-game fouling and overtime;
- F1: lap-by-lap pace, tyre age/degradation, compounds, pits, rain, safety car, penalties and reliability/DNF.

`core/simulation.py` computes counterfactual probabilities from empirical terminal frequencies of these complete rollouts. It does not resample a static final probability for supported hero sports.

### 3. Learned hero-sport models

Active bundled learned artifacts:

- `football_bootstrap_world_demo_v3`
- `basketball_bootstrap_world_demo_v1`
- `f1_conditional_softmax_world_demo_v1`

All three are chronologically trained/calibrated in the demo pipeline, expose ensemble-derived epistemic uncertainty, and have separate research/backtest reports. F1 uses a shared learned per-driver scorer followed by race-level softmax so the outcome set can vary.

## Frontend build boundary

The TypeScript/TSX source was syntax-transpiled successfully. A dependency-resolved `npm install && npm run build` was not executed in this environment because `frontend/node_modules` is not present and package installation requires registry access. CI is configured to execute the complete frontend install/build on a networked runner.

## Data truthfulness boundary

The bundled longitudinal sequences, historical/context data, training rows, learned parameters, model artifacts, and backtest metrics are **synthetic demo data**. They prove the full algorithmic and software execution path. They are not evidence of real-world sports predictive performance. Before making empirical performance claims, replace/supplement the synthetic providers with real point-in-time historical/context/live feeds, retrain, recalibrate, and preserve the resulting model/data lineage.
