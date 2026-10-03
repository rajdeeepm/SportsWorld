# Latent-state dynamics demo model card

**Version:** `latent_state_dynamics_demo_v1`  
**Algorithm:** independent linear-Gaussian state-space filters with learned dynamics  
**Data mode:** `synthetic_demo`

For each latent capability dimension the trainer fits persistence (`phi`), process variance, and observation variance by chronological likelihood over synthetic longitudinal sequences. Serving performs point-in-time Kalman filtering and returns posterior mean and variance.

The model is used for skill, form, health, usage, experience, potential, chemistry, coaching, and any sport-specific dimension that falls back to the generic learned/default dynamics contract.

The bundled parameters exist to verify training/serving parity. They must be refit on real longitudinal sports evidence before empirical claims.
