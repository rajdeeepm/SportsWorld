# Basketball demo model card

**Version:** `basketball_bootstrap_world_demo_v1`  
**Algorithm:** bootstrap binary logistic ensemble  
**Calibration:** chronological held-out temperature scaling  
**Feature schema:** `basketball_features_v3_world_state`  
**Data mode:** `synthetic_demo`

The model combines learned latent team/player state, matchup/context, live score state, possession, lineup differential, star availability, pace, and home environment. Fifteen bootstrap members provide epistemic disagreement.

Counterfactuals are evaluated with possession-by-possession sequential futures rather than terminal categorical resampling.

The bundled artifact is synthetic and must not be represented as real-world predictive performance.
