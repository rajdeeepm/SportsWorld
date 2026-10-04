# SportsWorld: 5-minute judge demo (v3)

**Setup (before judging):** `make live` (or `make replay-demo` if the venue network is unreliable) and
`make frontend`; open `http://localhost:5173`. Optional: the Llama tunnel to the GPU server for natural-language
scenarios and news extraction (`ssh -N -L 8001:127.0.0.1:8001 <gpu-host>`).

**0:00 · The thesis (Home).** "SportsWorld doesn't predict a game; it maintains a calibrated belief about an
entire competition." Point at the competition cards: Super Bowl / CFP / Stanley Cup / F1 title favourites, each
with a global-state version and 10,000 simulated seasons.

**0:30 · Season terminal (NFL).** Season outlook: every team's latent strength ± σ, expected wins with a 90 %
band, playoff / division / bye / conference / Super Bowl probabilities with Monte-Carlo standard errors. Click a
team: final-record distribution, seed distribution. Open *All games*: a fresh calibrated forecast for every
remaining game, each stamped with model and state version.

**1:15 · The research punchline (FAST vs DYNAMIC column).** "If you simulate games as independent coin flips you
are wildly overconfident. We replayed 2019–2025 point-in-time: independent-game simulation's 90 % intervals
covered only 52–77 % of outcomes preseason; sampling latent strength once per simulated season brings coverage to
91–95 %." Show *Quant / Research → Historical season replay*.

**2:00 · Propagation (World updates).** Show tonight's real feed: a final score → both teams' Kalman ratings →
every future game for both teams reforecast → season re-simulated (new global-state version). Then the live
availability panel: ESPN injury report → learned player-impact (e.g. starting QB out = -3.0 ± 0.5 pts, t = -5.5)
→ affected games + season odds.

**2:45 · Ask a what-if (Scenario tab).** Type: "What if the Bills' starting quarterback misses the next three
games?" Llama 3.3 70B (self-hosted) only *structures* the question; the effect size comes from the learned model,
the window is exact, and both branches share random numbers so deltas are pure scenario effect. Canonical state
is untouched.

**3:30 · F1 title race.** Antonelli vs Russell: driver and constructor championship probabilities from 8 remaining
GPs + a sprint, current two-seat entry list, reliability DNFs, FIA count-back. Insight: Antonelli's 66-point lead is
mostly Russell's two DNFs; the model attributes that to car reliability + luck, not pace.

**4:00 · Honesty slide (Quant / Research).** Bake-off with game-clustered paired bootstraps: our NFL in-game
model is statistically tied with ESPN's own win probability; ESPN wins in college (it uses market priors we
exclude by design); LightGBM is significantly worse than logistic; in hockey the simple state-space model beats
the learned layer, so model choice is made per league on a calibration window. Market-consensus benchmark on
out-of-sample games. Leakage audits are zero; every forecast is versioned.

**4:40 · Close.** "Every probability on screen is point-in-time, versioned, calibrated and backtested, from the
next possession to the championship."

### Backup paths
* Network down: `AS_OF=2025-12-01T00:00:00Z make replay-demo` rebuilds every competition exactly as it stood then
  (shows Seattle at 10.8 % for the Super Bowl on Dec 1; they won it).
* LLM down: the scenario box falls back to the deterministic parser (labelled in the UI).
