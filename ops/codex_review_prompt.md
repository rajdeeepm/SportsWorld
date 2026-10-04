You are a senior quantitative researcher reviewing SportsWorld (MHacks 2026, target audience: D. E. Shaw quant researchers).
Repository root is the current directory. READ-ONLY review: do not modify files.

Review these for correctness bugs, statistical errors, and point-in-time leakage, in priority order:
1. backend/src/sportsworld/season/engine.py and season/rules.py, whole-season Monte Carlo (DYNAMIC vs FAST), standings key, NFL/NBA/NHL/CFB/NCAA postseason brackets (seeding, reseeding, play-in, wildcard pairing, CFP 12-team bracket). Check vectorized indexing bugs, off-by-one seeds, wrong home/away, constraint violations.
2. backend/src/sportsworld/season/backtest.py and scripts/season_backtest.py, is the historical season replay truly point-in-time (hyper-parameters, ratings, played games, structures)? Are metrics/baselines computed correctly?
3. backend/src/sportsworld/ingest/ratings.py (Kalman rating book), ingest/features.py (league_features incl. live_margin_z and EP), ingest/football_ep.py, scripts/train_real.py (row construction, chronological split, calibration), leakage, train/serve skew, math errors.
4. scripts/player_impact.py and scripts/wp_bakeoff.py (incl. the game-clustered paired bootstrap), identification problems, selection bias, leakage.
5. backend/src/sportsworld/season/f1_season.py, points, sprints, DNFs, constructor points, tie-breaks.

Output a markdown report: for each finding give file:line, severity (critical/high/medium/low), the concrete failure scenario, and a minimal fix. Then list the 5 highest-value improvements a D. E. Shaw researcher would ask for next. Be specific and terse; no praise.
