# Demo failure drill and judging path

## Hero judging path

1. Start on Overview and enter `mich-osu-2026-demo`.
2. Before advancing the replay, open the **Context Intelligence** section. Show that the pregame forecast is not a scoreboard guess: it already includes historical team priors, career/recent player evidence, current availability, explicit matchup edges, home environment, rivalry/stakes variance, and public context with source/timestamp/confidence.
3. Point at one raw evidence item (for example synthetic career TD/rushing history) and one opponent-specific historical item. Explain that raw values remain displayable while normalized values feed the model.
4. Step/play the replay. Live score, possession, weather, injury and F1 timing observations update the same versioned belief state; the context panel and forecast refresh through WebSocket events.
5. Run the QB-out counterfactual. The scenario modifies a cloned branch's live + context state and rolls 10,000 drive-by-drive futures to completion without persisting hypothetical evidence. Expand a representative simulated path to show that the probability comes from evolving futures, not a terminal categorical resample.
6. Switch to F1 to demonstrate per-driver posterior state, a learned conditional-softmax multiclass model, and lap-by-lap futures with tyres, weather, safety-car compression, pits, and reliability. Basketball uses the same architecture with a learned contextual model and possession-by-possession rollouts.
7. Open Quant / Research and show chronological splits, calibration, proper scoring rules, contextual feature ablations, drift, error slices, model/data hashes, and leakage violations = 0.

All bundled event/context/model performance data are synthetic demo fixtures. Never present them as real-world empirical performance.

## Failure drill

- Live API unavailable: use bundled replay files and show the REPLAY badge.
- Historical/context provider unavailable: use bundled point-in-time synthetic `EntityProfile` / `EntityMetric` / `ContextSignal` fixture and label it DEMO.
- LLM unavailable: deterministic scenario parser handles the hero scenarios; context extraction can use pre-normalized verified records.
- ElevenLabs unavailable: typed scenario flow remains complete.
- Neon unavailable: bundled computed backtest JSON powers Research; `MemoryStore` retains demo context/state.
- SpacetimeDB unavailable: `MemoryStore` runs the identical store interface.
- Internet unavailable: backend, context fixture, model artifact, replay packs, and backtest assets are local.
- Learned artifact missing: registry falls back to the explicit sport adapter baseline and exposes that model version.

Never hide a fallback. The UI should say LIVE / REPLAY / DEMO and expose model/source health.
