# SportsWorld quantitative review

**The historical season replay is not fully point-in-time.** It gates game *results* by cutoff, but uses retrospectively fetched schedules and structures. The most consequential simulation errors are the NCAA field size and the missing postseason forecast once playoffs begin.

## Findings

### 1. Whole-season engine and brackets

| Severity | File:line | Concrete failure scenario | Minimal fix |
|---|---|---|---|
| **High** | [rules.py:252](backend/src/sportsworld/season/rules.py:252) | Both NCAA tournaments are hard-coded to 64 teams. The 2024–26 fields had 68; the announced 2027 fields have 76. Teams in the preliminary round have zero simulated qualification probability. The code also awards automatic bids to regular-season leaders rather than conference-tournament winners. [NCAA field announcement](https://www.ncaa.org/news/media-center-ncaa-reveals-new-76-team-bracket-for-di-mens-and-womens-basketball-championships/) | Version field size and preliminary-round format by season; model conference tournaments before assigning automatic bids. |
| **High** | [engine.py:136](backend/src/sportsworld/season/engine.py:136), [engine.py:447](backend/src/sportsworld/season/engine.py:447) | After the first postseason result is known, `run_season` returns no playoff, seed, or champion probabilities at all. | Condition the bracket on completed postseason games and simulate only unresolved games. |
| **Medium** | [engine.py:184](backend/src/sportsworld/season/engine.py:184), [engine.py:288](backend/src/sportsworld/season/engine.py:288) | A game currently in progress remains “remaining” and receives a fresh pregame draw. A late lead therefore has no effect on season odds until the result is final. | Condition that game on its live score, clock, and possession, or explicitly exclude in-progress forecasts. |
| **Medium** | [engine.py:390](backend/src/sportsworld/season/engine.py:390) | NHL ties in standings points are resolved with division and conference win rates before regulation wins. This can change wildcard selection and home ice; the NHL’s first substantive tiebreak is regulation wins. [NHL tiebreak procedure](https://www.nhl.com/info/standings-info/tie-breaking-procedure) | Track regulation wins and implement league-specific lexicographic tiebreak keys. |
| **Medium** | [rules.py:222](backend/src/sportsworld/season/rules.py:222) | A simulated conference-title result affects the CFP proxy only through a fixed `0.04` champion bonus; the title-game win/loss never enters the record used for ranking. A title-game loser can retain an overstated résumé. | Add title-game outcomes to the ranking inputs before selecting the field. |
| **Low** | [engine.py:475](backend/src/sportsworld/season/engine.py:475) | The numeric `seed` array enters the generic milestone branch, producing a mean seed labeled `seed` and a meaningless Bernoulli `seed_se`. | Handle `seed` separately; report qualification probability and conditional seed distribution. |

The NFL wildcard pairings and divisional reseeding, NBA play-in pairings, NHL wildcard pairings, and CFP first-round array indices appear internally consistent. I found no confirmed off-by-one error in those paths.

### 2. Historical season replay

| Severity | File:line | Concrete failure scenario | Minimal fix |
|---|---|---|---|
| **Critical** | [backtest.py:77](backend/src/sportsworld/season/backtest.py:77), [engine.py:124](backend/src/sportsworld/season/engine.py:124) | A 2024 preseason replay sees the final 2024 schedule, including later postponements and replacements. The archive retains one latest record per game; sampled 2024 NFL records were fetched in October 2026. Result gating does not make the schedule point-in-time. | Retain timestamped schedule snapshots and load the latest snapshot available at each checkpoint. |
| **High** | [engine.py:127](backend/src/sportsworld/season/engine.py:127) | Conference/division membership comes from a structure file fetched after the historical cutoff; sampled 2024 structure files were fetched in 2026. This can reveal realignment or membership changes early. | Store effective-date, fetched-at structure snapshots and select by cutoff. |
| **Medium** | [engine.py:191](backend/src/sportsworld/season/engine.py:191) | NHL overtime frequency is estimated from *all* completed archived regular-season games, including seasons after the checkpoint, and enters simulated standings points. | Restrict the estimate to results known by `as_of`; preferably estimate it in the prior training window. |
| **Medium** | [backtest.py:106](backend/src/sportsworld/season/backtest.py:106), [backtest.py:128](backend/src/sportsworld/season/backtest.py:128) | For leagues outside `PLAYOFF_SCORED`, playoff Brier and log loss are reported as `0.0` because the accumulator is divided by the team count despite no playoff observations being scored. | Use a separate playoff observation count and emit `null` when it is zero. |
| **Medium** | [backtest.py:58](backend/src/sportsworld/season/backtest.py:58), [engine.py:341](backend/src/sportsworld/season/engine.py:341) | NFL ties count as half a win in backtest truth, while forecast `expected_wins` excludes ties. Win MAE and interval coverage then compare different quantities. | Define one wins metric on both sides, or compare forecast `wins + 0.5 × ties` with truth. |

The season replay does fit rating hyperparameters using pre-season games only. That part is temporally separated; the schedule, structure, and overtime estimate are not.

### 3. Ratings, features, EP, and training

| Severity | File:line | Concrete failure scenario | Minimal fix |
|---|---|---|---|
| **High** | [train_real.py:150](scripts/train_real.py:150), [splitter.py:15](backend/src/sportsworld/backtest/splitter.py:15) | Cutoffs are selected by game start, but rows are split by prediction time. If a game starts at the cutoff, its pregame row can train the model while its later play rows enter calibration, or calibration while later rows enter test. All rows share the final-result label. | Assign each entire game to one partition by kickoff, with a time gap around boundaries. |
| **Medium** | [ratings.py:236](backend/src/sportsworld/ingest/ratings.py:236) | Hyperparameter fitting applies each game’s final immediately in start-time order. An early game can inform the fitted one-step likelihood for a later kickoff before its result would have been known; this differs from the serving replay’s result-known queue. | Score candidate parameters through the same queued chronological replay used for prediction. |
| **Medium** | [train_real.py:82](scripts/train_real.py:82), [train_real.py:87](scripts/train_real.py:87) | Pregame rows are timestamped five minutes before kickoff, but features are generated from the rating state at kickoff. A result becoming known in those five minutes can enter the feature; `latest_known(pre_t)` then masks that timestamp in the audit field. | Generate the state at the actual prediction time and record the true latest applied result time. |
| **Medium** | [features.py:83](backend/src/sportsworld/ingest/features.py:83), [features.py:85](backend/src/sportsworld/ingest/features.py:85) | `live_margin_z` adds full possession EP to the remaining final margin regardless of time left. At a game’s final seconds, a normal EP estimate can dominate a one-point lead even though there is insufficient time for a normal drive. | Estimate time-conditioned possession value, including score and clock, or suppress EP as remaining time approaches zero. |

I found no direct future-score use in `football_ep.py` at feature construction: its future next-score target is used to fit EP on the training window. The concern is the EP model’s simplified state and its use in late-game features.

### 4. Player impact and WP bakeoff

| Severity | File:line | Concrete failure scenario | Minimal fix |
|---|---|---|---|
| **High** | [player_impact.py:111](scripts/player_impact.py:111), [player_impact.py:144](scripts/player_impact.py:144) | The OLS coefficient is presented as points *caused* by absence, but participation is ex-post and correlated with trades, rotation, opponent, health, and in-game injury. A QB who begins the game but is replaced can be coded “absent” because another passer led attempts. The coefficient does not identify a counterfactual absence effect. | Use pregame availability and roster status, adjust for team/opponent/time effects, and validate a causal design on held-out games; label the current estimate as an association. |
| **Medium** | [wp_bakeoff.py:243](scripts/wp_bakeoff.py:243), [wp_bakeoff.py:253](scripts/wp_bakeoff.py:253) | ESPN comparisons sample every test game, then discard games lacking ESPN WP, yet report the count of *all* test games. With sparse ESPN coverage, a bootstrap replicate can contain no eligible plays and yield `NaN` confidence bounds. | Build each comparison’s eligible game set first, resample that set, and report its size. |
| **Medium** | [wp_bakeoff.py:251](scripts/wp_bakeoff.py:251) | `p_a_better` is the fraction of bootstrap estimates below zero. It is neither a calibrated probability of model superiority nor a null-hypothesis p-value, especially after selecting candidates on the same test set. | Report the paired effect and confidence interval; use a fresh outer holdout for model selection. |

### 5. F1 season

| Severity | File:line | Concrete failure scenario | Minimal fix |
|---|---|---|---|
| **High** | [f1_season.py:43](backend/src/sportsworld/season/f1_season.py:43), [f1_season.py:81](backend/src/sportsworld/season/f1_season.py:81) | The simulator treats every driver in season standings as an entrant in every future race. The cached 2026 state has **23 drivers for 22 cars**, including three attributed to Red Bull, so it simulates a third Red Bull entry and allocates its points to the constructor. FIA rules permit two cars per team. [FIA regulations](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_02_-_2026-02-27.pdf) | Build a round-specific two-seat entry list; keep replaced drivers’ banked points but remove them from future grids. |
| **Medium** | [f1_season.py:137](backend/src/sportsworld/season/f1_season.py:137), [f1_season.py:146](backend/src/sportsworld/season/f1_season.py:146) | Driver ties use wins then random; constructor ties are entirely random. Equal-point contenders with different second-place counts—or constructors with different win counts—can receive the wrong title. FIA countback proceeds through first places, second places, and so on. [FIA regulations](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_02_-_2026-02-27.pdf) | Track finishing-position counts for drivers and constructors and compare them lexicographically. |

The standard race and sprint points tables in lines 25–26 match the published 2026 full-distance tables. The principal F1 points failure is awarding future points to drivers who are no longer entered.

## Five highest-value next improvements

1. **Create immutable, timestamped input snapshots** for schedules, structures, rosters, availability, and model artifacts; replay each cutoff exclusively from available versions.
2. **Build an exact bracket validation suite** with synthetic standings and historical seed lists, including NCAA preliminary rounds, active-postseason conditioning, ties, home court, and invariant checks such as one champion per draw.
3. **Use rolling-origin evaluation with game-level partitions** and nested model selection; report calibration and paired loss differences by league, season, and forecast horizon.
4. **Make live game state part of season simulation**, replacing pregame redraws with conditional win probabilities for games in progress and reconciling FAST board probabilities with scenario shifts.
5. **Separate predictive associations from causal availability effects**; establish a pregame treatment definition and evaluate injury/lineup effects with an explicit identification strategy.

This was a read-only review; no files were changed.