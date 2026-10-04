# SportsWorld v1.2: Learned State + Sequential Futures + Three Hero Models

This build completes the three algorithmic upgrades identified after the contextual-belief layer.

## 1. Learned latent-state estimation

The v1.1 context engine used explicit time-decay weights. v1.2 replaces that rule with a trainable linear-Gaussian state-space model. Each capability dimension has learned persistence, process variance, and observation variance. Point-in-time-valid measurements are assimilated chronologically with Kalman updates, producing a posterior mean and posterior variance rather than a single weighted score.

The bundled artifact is `models/artifacts/latent_state_dynamics_demo_v1.json`. It is trained by `scripts/train_demo.py` from `data/fixtures/training/latent_state_sequences_demo.jsonl` and is intentionally marked `synthetic_demo`.

## 2. Genuine sequential sport simulators

Counterfactual probabilities now come from explicit rollouts of sport state rather than categorical resampling of a terminal model distribution.

- **Football:** drive-by-drive scoring, turnovers/punts, clock consumption, possession changes, late-game urgency, and overtime.
- **Basketball:** possession-by-possession scoring, pace-derived possession count, lineup/star advantage, end-game foul pressure, and overtime.
- **Formula 1:** lap-by-lap pace, tyre age/degradation, compound choice, pit stops, rain regime, safety-car compression, reliability/DNF hazard, penalties, and final race time.

The API returns the transition method, mean number of simulated steps, Monte Carlo standard errors, Wilson intervals, diagnostics, and representative trajectories.

## 3. Learned models for all hero sports

### Football
`football_bootstrap_world_demo_v3`, bootstrap binary logistic ensemble with 22 contextual/live features.

### Basketball
`basketball_bootstrap_world_demo_v1`, bootstrap binary logistic ensemble over latent team/player state, matchup/context, lineup, star availability, pace, possession, and live score state.

### Formula 1
`f1_conditional_softmax_world_demo_v1`, bootstrap conditional-softmax ensemble. The same learned scoring function is applied to every driver, so the model can handle a variable field while producing one race-level probability distribution.

All three use held-out chronological temperature scaling and bootstrap disagreement for epistemic uncertainty.

## Research boundary

All bundled training sets, model artifacts, backtests, and learned latent-state dynamics are synthetic demo artifacts. They validate the architecture and execution path, not real-world predictive quality. Replace them with defensible point-in-time historical data before making empirical performance claims.
