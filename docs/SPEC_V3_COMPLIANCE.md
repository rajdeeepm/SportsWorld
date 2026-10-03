# Spec v3.0 — Definition of Done status (Oct 3, 2026)

Legend: ✅ done and exercised on real data · 🟡 partial / documented approximation · ❌ not done

| Area | Status | Where / evidence |
|---|---|---|
| Competition-season is the top-level product | ✅ | `/competition/:cid` season terminal; homepage lists competitions with title favourites; event terminal is the drill-down |
| 100% schedule coverage + audit | ✅ (ESPN source) | full current-season schedules archived (NFL 272, FBS 902, NBA 1,206, NHL 1,336, NCAAM 5,784 …); `GET /competitions/{cid}/seasons/current/coverage` (duplicates, contingent postseason events, forecast coverage) |
| Persistent canonical entities + dated relationships | 🟡 | ESPN team/athlete IDs persist across seasons; F1 driver↔constructor entry list per round; no alias table / dated roster edges yet |
| Evidence with provenance + three timestamps | ✅ | `Observation` (event / known-to-model / ingestion), availability + news records carry source, parser version, `known_to_model_time` |
| Versioned global state reconstructable at any cutoff | ✅ | `build_setup(league, as_of)` rebuilds the competition-season from archived evidence; `global_state_version` per league |
| Learned latent state (posterior mean + variance) | ✅ | Kalman rating book per league (team), two-level driver+car Kalman (F1); hyper-parameters fit by one-step predictive likelihood through the serving replay queue |
| Every future event has a fresh calibrated forecast | ✅ | SeasonService board (`/forecast-board`), freshness + model + state version on every row |
| Live events update without refresh | ✅ | 20 s tracker → observations → WebSocket (`/ws/events/{id}`, `league:{id}`, `season:{id}`) |
| Propagation: finals / availability / live state invalidate affected futures | ✅ | final → ratings → `team_state` to that team's upcoming games → debounced, version-safe season recompute → world-update feed; injury report → learned availability delta → same path; live score changes re-condition the season run on in-progress games (rate-limited 1/min) |
| Standings + tiebreaks, versioned | 🟡 | standings vs ESPN official (0 mismatches on NFL audit); tiebreak chains approximated (win% → div → conf → point diff → coin); NHL regulation-wins and NFL head-to-head not modelled |
| Season simulation ≥ 10,000 full draws | ✅ | `run_season` DYNAMIC + FAST, 10k draws (NFL 0.2 s, NCAA 5–8 s) |
| Contingent postseason from versioned rules | ✅/🟡 | NFL 7-team, NBA play-in, NHL wildcard, CFB conf. title games + 12-team CFP, NCAA 64-team (APPROX: field is now 68/76; auto-bids by regular-season leader). In-progress postseason conditioning ❌ |
| Season outputs (record/rank/seed/qualification/title) | ✅ | per-team win histograms, seed distributions, milestone probabilities with MC standard errors |
| F1 driver + constructor title distributions | ✅ | sprint + race points, current two-seat entry list, reliability DNFs, FIA count-back tiebreak |
| Event + season counterfactuals without canonical mutation | ✅ | `/season-simulations` (typed) + `/scenario/ask` (Llama → typed → learned effect sizes); common random numbers; acceptance test G8 |
| Event + season calibration evaluated chronologically | ✅ | event: per-league held-out tests; season: historical replay at 0/25/50/75 % (`/research/season-summary`) |
| Historical season replay, zero leakage | 🟡 | results, ratings, hyper-parameters, OT rate point-in-time; live inputs (injury report, in-game probabilities) are excluded in replay mode; schedule and conference structure are retrospective snapshots (no historical schedule versions available) — disclosed |
| A0–A5 ablations on real data | 🟡 | A0 venue → A1 latent state → A2 form/rest → A3 live → A4 possession (football); player-availability and verified-context stages are not yet in the ablation table |
| Research UI (metrics, calibration, versions, leakage) | ✅ | Quant / Research page: season replay, bake-offs with game-clustered CIs, player impact, per-league backtests |
| Competition UI (board, standings, outlook, updates) | ✅ | season terminal tabs |
| Team / entity page | ✅ | `/competition/:cid/team/:id`: distribution, trajectory, remaining schedule with forecasts |
| Event UI | ✅ (from v1.2) | event terminal, now aware of real vs replay events |
| Freshness on prominent forecasts | ✅ | board rows + season runs carry as-of, state version, model version, fresh/stale |
| No LLM-authored probabilities | ✅ | Llama only emits schema-constrained structure; effect sizes come from learned models; news signals are state-only and must quote verbatim evidence |
| Offline season-scale replay | ✅ | `AS_OF=… make replay-demo` rebuilds every competition exactly as it stood at that instant from on-disk archives, no network |
| Test suite | ✅ | 52 tests incl. season acceptance (one champion per draw, seed invariants, counterfactual isolation, determinism, point-in-time setup, F1) and live-integrity (stale/empty injury reports, news grounding, out-of-order snapshots, live rate-limit, postseason shift windows) |
| Independent review | ✅ | two read-only reviews by a second model (Codex gpt-6-sol): `ops/codex_review_season.md`, `ops/codex_review2.md`; all critical/high findings fixed or disclosed |
| Real data replaces synthetic for claims | ✅ | all league models trained on real archives; synthetic artifacts remain only for the demo replay events |
| Frontend production build | ✅ | `npm run build` passes |
| Sponsors provisioned | 🟡 | Meta/Llama 3.3 70B self-hosted on a GPU server (vLLM); AWS/Neon/SpacetimeDB/Fetch.ai code paths exist but are not provisioned (need credentials) |
| Judge deployment + submission assets | ❌ | pending |
