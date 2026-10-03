# Formula 1 demo model card

**Version:** `f1_conditional_softmax_world_demo_v1`  
**Algorithm:** bootstrap conditional-softmax ensemble  
**Calibration:** chronological held-out temperature scaling  
**Feature schema:** `f1_features_v3_learned_world`  
**Data mode:** `synthetic_demo`

The F1 model learns one shared driver-scoring function instead of hard-coding a fixed class head. Each driver is represented with position/progress, pace, reliability, wet-weather interaction, pit/tyre/penalty state, contextual adjustment, and learned latent skill/form/health/experience/potential. Scores are normalized jointly through a race-level softmax.

This lets the same artifact score a variable outcome set. Counterfactuals use lap-by-lap rollouts with tyre degradation, strategy, rain, safety cars, reliability/DNF and penalties.

The bundled artifact is synthetic and must not be represented as real-world predictive performance.
