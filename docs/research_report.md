# SportsWorld: research report

*Persistent, point-in-time probabilistic world models of whole sporting competitions.*
Real data only (ESPN, Jolpica, OpenF1); every number below comes from a chronological held-out window
or a point-in-time historical replay. Generated Oct 3, 2026; reproducible with `scripts/` + `ops/tasks.json`.

## Key findings (one screen)

1. **Correlated futures are necessary for calibrated season odds.** Over 7 replayed seasons, simulating games as
   independent draws gives "90 %" win intervals that cover 52–77 % of outcomes preseason; sampling latent team
   strength once per simulated season gives 91–95 %, and better playoff log loss at almost every checkpoint.
2. **Latent state carries the pregame signal; live state the rest.** Form and rest add ≤ 0.004 log loss.
   The learned outcome layer beats the pure Kalman model in every walk-forward origin in basketball and
   football, and is indistinguishable in hockey (season-to-season spread ≈ 5× the model difference).
3. **Capacity helps only where state is long and data are plentiful.** Football: logistic ≈ MLP ≈ GRU ≈ ESPN's
   published win probability (tied, game-clustered CIs). NBA: a GRU over the possession sequence beats logistic
   in 11/12 walk-forward runs, with the edge growing as history accumulates; with one season of NHL data the
   same models overfit badly, and backfilling NHL play-by-play to 2018 turns that into 24/24 walk-forward wins.
4. **Markets know more pregame.** On true holdout games the de-vigged market beats SportsWorld by ≈ 0.03 log
   loss (≈ 0.01 in hockey); a blend puts ≈ 0 weight on SportsWorld. The edge is information SportsWorld does not
   consume (lineups, injury nuance, money flow). It is the benchmark against which new evidence sources are measured.
5. **Absence of key players is measurable where the data allows** (associational): NFL starting QB −3.0 ± 0.5 pts, FBS starting QB −2.4 ± 0.3,
   NBA top-minutes player −2.5 ± 0.2, NHL starting goalie −0.16 ± 0.06 goals.

Methodological hygiene: whole-game chronological partitions, hyper-parameters fit only on earlier data,
point-in-time replay, game-clustered paired bootstraps, multi-seed and walk-forward replication, zero leakage
violations, and two independent model-assisted code reviews whose critical findings were fixed.

## 1. Questions

1. **Calibration of whole-season forecasts.** Does a season simulator that samples *latent team strength*
   once per simulated season (correlated futures, "DYNAMIC") produce calibrated record / playoff / title
   distributions, compared with treating games as independent draws at the posterior mean ("FAST")?
2. **Where does predictive signal come from?** Rating state vs. form/rest context vs. live state vs.
   possession value vs. player availability.
3. **Does model capacity help in-game?** Logistic vs. gradient-boosted trees vs. MLP vs. a causal GRU over
   the game's play sequence, evaluated with game-clustered paired bootstraps.
4. **How far from an informed external consensus?** ESPN's published in-game win probability and closing
   betting-market prices, kept strictly as benchmarks (never features).

## 2. System in one paragraph

Each competition keeps a Kalman-filtered latent strength per team (two-level driver + car for F1); hyper-
parameters are fit by one-step predictive likelihood through the same result-known queue used in serving.
A calibrated per-league outcome model scores every remaining game; the season engine re-simulates the full
remaining schedule 10,000 times through versioned rules (NFL 7-team bracket, NBA play-in, NHL wildcard,
FBS conference title games + 12-team CFP, NCAA 64-team approximation, F1 sprint/race points with FIA
count-back). Finals, injury reports and verified news propagate: evidence → entity state → every affected
future game → season distribution, each step versioned and visible in a world-update feed.

## 3. Season-level calibration (historical replay)

Replays of 2019–2025 (NFL, NBA, NHL, FBS) rebuild the world state at 0/25/50/75 % of each regular season
using only results known by the cutoff and rating hyper-parameters fit on *earlier* seasons, simulate to the
championship, and score against what happened.

**Preseason 90 % final-wins interval coverage (nominal 0.90)**

| League | seasons | DYNAMIC | FAST |
|---|---:|---:|---:|
| NFL | 7 | 0.94 | 0.77 |
| NBA | 7 | 0.91 | 0.52 |
| NHL | 6 | 0.95 | 0.74 |
| FBS | 7 | 0.94 | 0.77 |
| NCAAM / NCAAW (2024–25) | 2 | 0.91 / 0.88 | 0.61 / 0.56 |

**Finding 1.** Independent-game simulation (FAST) is systematically overconfident about season outcomes
(preseason intervals cover only 52–77 % of outcomes) because it ignores uncertainty in the latent state that
every game shares. Sampling that state once per rollout (DYNAMIC) restores near-nominal coverage at every
checkpoint, and improves playoff-qualification log loss at almost every checkpoint (7 seasons, preseason:
NBA 0.588 vs 0.660, NHL 0.574 vs 0.630, NFL 0.643 vs 0.677; base rate ≈ 0.69). Expected-wins MAE beats a
"current pace" extrapolation at every checkpoint in every league (e.g. NHL preseason 5.5 vs 6.8 wins).

| League | checkpoint | coverage DYN / FAST | playoff log loss DYN / FAST (base ≈ 0.69) |
|---|---|---|---|
| NBA | 0 / 25 / 50 / 75 % | 0.91/0.52 · 0.89/0.68 · 0.86/0.76 · 0.89/0.86 | 0.588/0.660 · 0.417/0.472 · 0.335/0.365 · 0.244/0.250 |
| NHL | 0 / 25 / 50 / 75 % | 0.95/0.74 · 0.94/0.83 · 0.94/0.90 · 0.95/0.94 | 0.574/0.630 · 0.425/0.456 · 0.289/0.287 · 0.218/0.219 |
| NFL | 0 / 25 / 50 / 75 % | 0.94/0.77 · 0.93/0.85 · 0.91/0.87 · 0.95/0.93 | 0.643/0.677 · 0.475/0.480 · 0.394/0.407 · 0.301/0.304 | This is the season-scale analogue of ignoring parameter uncertainty in a
portfolio simulation.

Caveats: title probabilities are evaluated on few seasons (one champion per season) and are noisy;
historical schedules and conference structures are retrospective snapshots (results, ratings and
hyper-parameters are point-in-time); seasons whose postseason lies outside the archive window (2019–20
bubble) are excluded from playoff/title scoring.

## 4. Event-level forecasts (chronological held-out windows)

Whole games are assigned to train (60 %) / calibration (20 %) / test (20 %) by kickoff; temperature scaling is
fit on the calibration window only. Rows: kickoff state plus in-game states (every 3rd snap in football,
period ends elsewhere). Log loss (lower is better):

| League | learned model | Kalman-only analytic | test rows |
|---|---:|---:|---:|
| NFL (2018–26) | **0.467** | 0.486 | 136k |
| FBS | **0.339** | 0.352 | 460k |
| NBA | **0.506** | 0.524 | 40k |
| WNBA | **0.482** | 0.492 | 4.7k |
| NCAAM / NCAAW | 0.476 / 0.373 | 0.480 / 0.374 | 50k / 95k |
| NHL | 0.5745 | **0.5735** | 31k |
| F1 (race winner, 21 test races) | **0.917** | 1.110 (grid-slot base rate) | 105 |

**Finding 2 (null result).** In hockey the learned layer does not beat the analytic state-space model, so
model choice is made per league on the calibration window (spec "M4") rather than assumed.

**Ablation (every league, same split).** Home field alone ≈ 0.63–0.69 → + latent rating state gives the
large pregame gain (e.g. NBA 0.687 → 0.583) → form / rest add ≤ 0.004 → live state provides the rest; in
football a learned expected-points possession value adds a further small gain and fixes late-game errors
(ball at the opponent's 19, down 2, 0:38 → 29 % before vs 67 % after).

## 5. Model capacity in-game (bake-off with game-clustered paired bootstraps)

Same rows, split and calibration for logistic / LightGBM / MLP / GRU-over-play-sequence; 95 % CIs resample
whole games (plays within a game are strongly correlated; a play-level test would overstate significance).

* NFL, 454 test games: MLP − ESPN published WP = +0.0006 log loss, 95 % CI [−0.015, +0.016]: **statistically
  tied with ESPN's own model.** An earlier, naive comparison suggested the MLP "beat" ESPN; the clustered
  bootstrap shows that was noise.
* FBS, 1,539 test games: every SportsWorld model trails ESPN by ≈ 0.009–0.011 with CIs excluding zero; ESPN's
  college model uses market priors that SportsWorld deliberately excludes.
* LightGBM is significantly *worse* than the logistic model (overfits game-level structure with ~1k games).
* Football MLP / GRU vs logistic: differences within ±0.002 and not significant (NFL 454 games, FBS 1,539).
* **Dense play-by-play in basketball / hockey is different** (same protocol, every 4th event, game-clustered CIs):

| League | test games | GRU − logistic | MLP − logistic |
|---|---:|---|---|
| NBA | 2,011 | **−0.0053 [−0.0085, −0.0020]** | +0.0008 [−0.0053, +0.0077] |
| NHL | 837 | −0.0050 [−0.0118, +0.0016] | **−0.0059 [−0.0113, −0.0008]** |
| NCAAM | 2,474 | +0.0003 [−0.0037, +0.0045] | −0.0039 [−0.0081, +0.0003] |
| NCAAW | 2,354 | −0.0016 [−0.0038, +0.0007] | −0.0016 [−0.0045, +0.0013] |
| WNBA | 235 | +0.0080 [−0.0054, +0.0211] | +0.0035 [−0.0098, +0.0164] |

  **Finding 3.** Capacity helps where in-game state is long and information-rich (the NBA possession
  sequence; NHL event flow) and does not where a compact, well-specified state already exists (football's
  down-distance-field position summarised by learned EP). Production keeps logistic until multi-seed
  replication confirms the gains and stateful sequence serving is implemented.

  *Multi-seed replication (same data fingerprint, 5 seeds).* NBA: GRU test log loss 0.4472–0.4501 (mean 0.4487)
  and MLP 0.4485–0.4501 (mean 0.4493) vs logistic 0.4516: **every seed beats logistic** (mean gain ≈ 0.003;
  the single v3 MLP run was the outlier). NCAAW: seeds straddle logistic (0.3400–0.3441 vs 0.3411), no
  consistent gain. NHL: GRU beats logistic in 5/5 seeds (mean −0.0045; CI excludes 0 in 2/5), MLP in 5/5 (mean
  −0.0039). NCAAM: GRU beats logistic in 5/5 seeds (−0.0037 to −0.0047; CI excludes 0 in 3/5).

  *Walk-forward (NBA, train ≤ O−2 / calibrate O−1 / test O, 3 seeds per origin, ~1,320 test games each).*
  GRU − logistic: O = 2022: −0.0009 · −0.0012 · +0.0004; 2023: −0.0040 · −0.0027 · −0.0047; 2024: −0.0031 ·
  −0.0049 · −0.0006; 2025: −0.0055 · −0.0059 · −0.0055. The GRU wins 11 of 12 runs and its edge grows with the
  amount of training history: the signature of a real, data-limited effect rather than noise. MLP is mixed
  (wins 2023–25, loses 2022). An NHL walk-forward with only ONE season of training play-by-play (test 2025) first diverged numerically
  (near-constant feature standardised by ≈ 0; fixed with a variance floor) and, once fixed, still shows both
  neural models far worse than logistic (+0.03 to +0.17 log loss, CIs excluding 0). They overfit a single
  season, while logistic is robust. **Backfilling NHL play-by-play to 2018 and rerunning the same
  walk-forward reverses the result:** GRU − logistic by origin (3 seeds, ~1,400 test games each):
  2022: −0.0024 · −0.0065 · −0.0025; 2023: −0.0075 · −0.0098 · −0.0102; 2024: −0.0031 · −0.0018 · −0.0073;
  2025: −0.0082 · −0.0073 · −0.0070. MLP: −0.0025 to −0.0097. **Both neural models beat logistic in 24 of 24
  runs** (GRU CI excludes 0 in 8/12). The sequence models are **data-hungry**: harmful with one season of
  play-by-play, consistently better with four or more.

## 6. Player availability

Residual of actual margin against the point-in-time Kalman expectation, regressed on established key-player
absences from ex-post participation (summaries, NFL and FBS backfilled to 2018). Pooled rows: regulars (≥ 3 earlier games, ≥ 8 % average share) who appear nowhere in the box score; offensive line is not measurable from box scores:

| League | absence | effect | ±SE | t | games |
|---|---|---:|---:|---:|---:|
| NFL | starting QB | -2.96 pts | 0.54 | -5.51 | 1,988 |
| NFL | lead RB / top WR / top tackler | -0.99 / -0.97 / -0.97 pts | 0.68 / 0.79 / 0.75 | not significant | 1,988 |
| NFL | per 100 % of carries / catches / tackles missing (pooled) | -1.52 / -1.50 / -3.78 pts | 1.07 / 1.59 / 4.07 | not significant | 1,844 |
| FBS | starting QB | -2.39 pts | 0.35 | -6.92 | 6,141 |
| FBS | lead RB / top WR / top tackler | -0.95 / -1.06 / -0.50 pts | 0.55 / 0.62 / 1.02 | not significant | 6,141 |
| FBS | per 100 % of carries missing (pooled) | **-2.21 pts** | 0.93 | -2.38 | 4,817 |
| FBS | per 100 % of catches / tackles missing (pooled) | -1.94 / -5.44 pts | 1.05 / 7.68 | -1.84 / -0.71 | 4,817 |
| NBA | per top-2-minutes player | -2.47 pts | 0.20 | -12.4 | 9,456 |
| WNBA | per top-2-minutes player | -3.73 pts | 0.80 | -4.68 | 1,056 |
| NCAAM | per top-2-minutes player | -0.89 pts | 0.31 | -2.86 | 10,643 |
| NCAAW | per top-2-minutes player | -2.49 pts | 0.38 | -6.62 | 10,132 |
| NHL | starting goalie | -0.16 goals | 0.06 | -2.72 | 4,027 |
| NHL | per top-2-minutes player | -0.14 goals | 0.10 | -1.45 | 4,027 |

These are **associations**, not causal effects: participation is ex-post and correlated with in-game injury,
rotation and trades. Live serving maps official injury-report status to P(plays) with an explicit,
uncalibrated prior and applies effect × (1 − P(plays)) to every affected future game and the season run.

## 7. External consensus (pregame, true holdout)

Market moneylines (ESPN core API, de-vigged; likely closing lines) vs SportsWorld's independent pregame
probability on identical games played **after each model's calibration window** (never seen in training):

| League | games | SportsWorld LL | market LL | Δ (SW − market), 95 % CI | corr |
|---|---:|---:|---:|---|---:|
| NFL | 453 | 0.631 | 0.597 | +0.035 [+0.017, +0.052] | 0.86 |
| NBA | 1,500 | 0.608 | 0.574 | +0.034 [+0.023, +0.045] | 0.88 |
| FBS | 1,320 | 0.526 | 0.493 | +0.033 [+0.021, +0.045] | 0.91 |
| NHL | 1,500 | 0.687 | 0.677 | +0.010 [+0.005, +0.015] | 0.81 |

**Finding 4.** Markets are better pregame, everywhere (≈ 0.03 log loss; ≈ 0.01 in hockey). A research-only
logistic blend fit on the earlier half never beats the market on the later half (NBA 0.549 vs 0.546; FBS 0.465
vs 0.464), and the fitted weight on SportsWorld is ≈ 0 or negative: **pregame, the market subsumes the
information SportsWorld uses** (results-based latent strength). The market's edge is information SportsWorld
deliberately does not consume (lineups, injury nuance, money flow). SportsWorld's contribution is therefore
not single-game edge; it is an auditable, point-in-time world model whose season-scale distributions are
calibrated (§3) and whose every revision is attributable, and a clean benchmark for measuring how much each
additional information source (availability, news) closes that 0.03 gap.

## 7b. Rolling-origin (walk-forward) evaluation

Train ≤ O−2, calibrate O−1, test O for O = 2022–2025 (whole games, zero leakage violations):

| League | origins | learned LL mean ± sd | Kalman-only LL | learned − Kalman by origin |
|---|---|---|---|---|
| NBA | 2022–25 | 0.517 ± 0.018 | 0.533 | −0.016 · −0.016 · −0.018 · −0.015 |
| FBS | 2022–25 | 0.365 ± 0.020 | 0.377 | −0.011 · −0.006 · −0.017 · −0.013 |
| NFL | 2022–25 | 0.490 ± 0.038 | 0.516 | −0.058 · −0.007 · −0.009 · −0.029 |
| NCAAM | 2024–25 | 0.442 ± 0.005 | 0.448 | −0.008 · −0.004 |
| NHL | 2022–25 | 0.568 ± 0.011 | 0.568 | +0.004 · −0.002 · −0.002 · +0.002 |

**Finding 5.** The learned outcome layer's gain over the pure state-space model is consistent in sign across
every walk-forward origin in basketball and football, and absent in hockey, where the season-to-season
spread of log loss (sd 0.011) is ~5× any model difference, so single-split hockey comparisons are noise.

## 8. Threats to validity / what I would do next

* Schedules and conference structures are not historically versioned (retrospective snapshots).
* Tiebreak chains and NCAA selection are approximations; postseason-in-progress conditioning is not implemented.
* Player effects are associational; next step is a pregame-availability design with team/opponent fixed effects.
* Expected points are time-conditioned near the end of halves; finer clock / timeout modelling would sharpen late-game estimates further.
* Rolling-origin evaluation is done (§7b); nested model selection would tighten the per-league choices further.
