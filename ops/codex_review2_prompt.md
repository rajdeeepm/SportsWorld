READ-ONLY review (do not modify files) of SportsWorld code added since the last review, for a D. E. Shaw-grade audience.
Focus files:
- backend/src/sportsworld/ingest/availability.py (live injury report -> learned player-impact -> team strength delta), and how it is applied in backend/src/sportsworld/season/service.py (_availability_scenario, compute) and backend/src/sportsworld/ingest/tracker.py (_team_fields, refresh_availability).
- backend/src/sportsworld/ingest/news.py (ESPN news -> Llama structured extraction -> grounding gate -> disagreement flags) and backend/src/sportsworld/llm/client.py, llm/season_scenario.py.
- backend/src/sportsworld/season/engine.py live_probs conditioning of in-progress games, and the SeasonScenario path (rating_shifts windows, common random numbers).
- backend/src/sportsworld/models/registry.py 'kalman_analytic' path and predict_league_features; scripts/train_real.py M4 model selection on the calibration window.
- backend/src/sportsworld/ingest/features.py EP time-conditioning (EP_FULL_S).
Look for: double counting (e.g. availability delta applied both in tracker team_state and season scenario), stale/cached state bugs, point-in-time leakage, prompt-injection or hallucination paths where untrusted news text could change quantitative state, incorrect probability math, race conditions between async loops, and anything that would embarrass the project in front of quant researchers.
Output: markdown table of findings (file:line, severity, failure scenario, minimal fix), then top 5 recommended changes. Terse.
