# Football demo model card

**Version:** `football_bootstrap_world_demo_v3`  
**Algorithm:** bootstrap binary logistic ensemble  
**Calibration:** chronological held-out temperature scaling  
**Feature schema:** `football_features_v3_world_state`  
**Data mode:** `synthetic_demo`

The model consumes raw team strength, learned latent-state aggregates (historical strength, current form, health, usage, experience, potential, chemistry), matchup and contextual features, plus live score/clock/possession/field position/QB availability/weather/home-field state.

Fifteen bootstrap members provide an empirical epistemic-disagreement signal. The associated research report is generated chronologically and includes calibration, proper scoring rules, ablations, drift, error slices, and a point-in-time leakage audit.

The bundled artifact is synthetic and must not be represented as real-world predictive performance.
