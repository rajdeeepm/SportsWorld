# v1.2 — Learned World-State Upgrade

v1.2 completes the three algorithmic upgrades requested after v1.1.

## 1. Learned latent-state estimation

- Added `backend/src/sportsworld/context/state_space.py`.
- Replaced hand-written time-decay aggregation with a trainable linear-Gaussian state-space model.
- Added chronological grid-likelihood parameter fitting for persistence, process variance, and observation variance.
- Added posterior variance and estimator version to `LatentEntityState`.
- Propagated per-outcome latent means/variances into the versioned `WorldState`.
- Added synthetic chronological latent-sequence generator and `latent_state_dynamics_demo_v1` artifact.

## 2. Genuine sequential future simulation

- Added `sportsworld/simulators/`.
- Football now rolls forward drive by drive.
- Basketball now rolls forward possession by possession.
- F1 now rolls forward lap by lap with tyre/strategy/weather/SC/reliability transitions.
- Counterfactual probabilities are empirical terminal frequencies from those state rollouts, not resamples of a static final probability.
- API result now includes simulation method, mean transition count, diagnostics, and representative paths.

## 3. Learned models for all three hero sports

- Football upgraded to `football_bootstrap_world_demo_v3`.
- Basketball added `basketball_bootstrap_world_demo_v1`.
- F1 added `f1_conditional_softmax_world_demo_v1` using a shared per-driver learned scorer.
- All three have separate chronological calibration/backtest reports and bootstrap epistemic uncertainty.
- Research UI now supports all three learned hero reports and multiclass error inspection.

## Validation

- Backend suite expanded from 20 to 25 tests.
- Added tests for learned latent-state posterior variance, all three hero model registry paths, and drive/possession/lap simulators.
- Synthetic training/backtest data remain clearly labeled and are not empirical sports-performance claims.
