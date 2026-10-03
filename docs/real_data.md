# Real data: every team, every game, every season

SportsWorld now tracks complete leagues concurrently rather than a single demo event per sport.
Every scheduled and live game in every tracked league is a first-class event with the same
point-in-time state, forecast history, drivers and WebSocket stream as the demo replays.

## Coverage

| League | Source | History archived | Teams/drivers rated |
|---|---|---|---|
| NFL | ESPN scoreboard + ESPN play-by-play | 2023 → today (904 games, every snap) | 32 |
| College football (FBS + FCS opponents) | ESPN scoreboard + ESPN play-by-play | 2023 → today (3,223 games, every snap) | ~250 |
| NBA | ESPN scoreboard | 2023-24 → today | 30 (+ exhibition opponents) |
| WNBA | ESPN scoreboard | 2023 → today | 15 |
| Men's college basketball (D-I) | ESPN scoreboard | 2022-23 → 2025-26 (25,057 games) | ~1,000 |
| Women's college basketball (D-I) | ESPN scoreboard | 2022-23 → 2025-26 (23,712 games) | ~900 |
| Formula 1 | Jolpica (results) + OpenF1 (lap timing) | results 2018 → today, lap timing 2023 → today | every driver + every car |

Observed ESPN limits (probed 2026-10-02): one day per request, `limit` ≤ 500, `groups=80` (FBS) / `groups=50` (D-I).
ESPN's API is unofficial: it can change without notice. The tracker records fetch errors per league
(`GET /leagues`) and keeps serving the last state when a fetch fails.

## Pipeline

```text
ESPN scoreboard / summary        Jolpica + OpenF1
        │                              │
        ▼                              ▼
data/real/games/<league>/<season>.jsonl     data/real/f1/{results,laps}/
data/real/pbp/<league>/<season>.jsonl
        │
        ├─ RatingBook (Kalman latent team strength, hyper-parameters fit on the train window)
        ├─ learned expected points (football, from play-by-play)
        ├─ point-in-time feature rows (pregame + every 3rd snap / period ends / lap checkpoints)
        ▼
bootstrap logistic (team sports) · masked conditional-softmax (F1)
        → temperature calibration on a later window → untouched chronological test window
        → models/artifacts/*_real_v1.json + models/manifests/<league>_active.json
        ▼
TrackerService (TRACKER_ENABLED=true)
  schedule loop (10 min): every game yesterday … +8 days (football) / +2 days (basketball) / next race (F1)
  live loop (20 s): one scoreboard request per league-day covers every live game
  → Observation(score_state | game_end | team_state | race_state | driver_state | race_end)
  → ForecastEngine.ingest → forecast history + WebSocket (`/ws/events/<id>`, `/ws/events/league:<league>`)
```

### Latent team state (`ingest/ratings.py`)

`margin_home = hfa·(1−neutral) + r_home − r_away + ε`, with each `r` a Gaussian state that drifts between
games and regresses between seasons. Hyper-parameters (hfa, observation noise, drift, season regression,
season variance, newcomer prior) are chosen by one-step-ahead predictive log-likelihood on the training
window only. Results are applied only once they were knowable (kickoff + 4 h for football, + 3 h for
basketball), so a 1 pm result never leaks into a 4:25 pm prior.

When a result moves a team's rating, every not-yet-started game involving that team receives a
`team_state` observation, so its pregame forecast is revised with provenance.

### Football possession value (`ingest/football_ep.py`)

Expected points are fit by least squares on next-score-in-half outcomes from real snaps
(own 25, 1st & 10 ≈ +0.9; opponent 10, 1st & 10 ≈ +4.8 on the NFL fit). The live margin distribution
adds the signed EP of the current possession, so "down 2, ball at the opponent 19, 38 s left" is
scored as a likely field goal, not as a team trailing.

### F1 (`ingest/f1.py`, `ingest/f1_tracker.py`)

Two-level Kalman rating (driver + car) on a normalized finishing score, a decayed classified-finish rate
per car for reliability, and a shared conditional-softmax scorer trained with masks so the field size can
vary race to race. Live timing comes from OpenF1; real-time access during a session may need
`OPENF1_TOKEN`. Without it the tracker still forecasts from the grid and settles from Jolpica results.

## Held-out results (real games, chronological test windows)

Test rows mix pregame and in-game states. "Kalman only" is the analytic `P(margin > 0)` from the
state-space model with no learned outcome layer. Leakage violations: 0 for every league.

| League | Test rows | Log loss | Brier | ECE | Accuracy | Kalman only (log loss) |
|---|---:|---:|---:|---:|---:|---:|
| NFL | 11,319 | 0.500 | 0.338 | 0.017 | 74.1% | 0.511 |
| College football | 39,365 | 0.314 | 0.201 | 0.009 | 85.6% | 0.326 |
| NBA | 3,174 | 0.475 | 0.316 | 0.032 | 76.8% | 0.487 |
| WNBA | 943 | 0.479 | 0.320 | 0.023 | 75.2% | 0.488 |
| Men's college basketball | 10,040 | 0.473 | 0.318 | 0.021 | 75.4% | 0.477 |
| Women's college basketball | 18,999 | 0.372 | 0.244 | 0.013 | 81.6% | 0.374 |

**Formula 1** (winner of a ~20-car field; 21 test races Oct 2025 → Sep 2026, 105 rows): log loss 0.917,
Brier 0.459, ECE 0.071, top-pick accuracy 67.6%, vs an empirical win-rate-by-grid-slot baseline at 1.110.
By horizon: pre-race 1.44, 25% distance 1.25, 50% 1.17, 75% 0.55, 90% 0.19. Ablation: grid/position
0.966 → + driver & car latent state 0.958 → + reliability 0.940 → + live gaps 0.912. The sample is small;
treat these as indicative.

Ablation (log loss): every league follows the same shape. Home field alone ≈ 0.63–0.69; adding the
latent rating state gives the large pregame gain (e.g. NBA 0.687 → 0.583, CFB 0.633 → 0.451);
form and rest add little (≤ 0.004); live state gives the rest.

**External consensus (football, same plays, never used as a feature):** ESPN's published win
probability scores 0.494 (NFL) / 0.295 (CFB) vs SportsWorld 0.498 / 0.312. ESPN's model uses
betting-market priors; SportsWorld does not, by design, so the gap is a measurement of what that
information is worth.

Known gaps: basketball in-game rows are period-end snapshots (no possession/lineup history yet);
injuries/availability, weather and news context are not yet collected for real games.

## Running it

```bash
make real-data      # backfill ESPN games, football play-by-play, F1 results + lap timing (~15 min)
make train-real     # fit ratings, EP, models, calibrators, backtests for every league (~6 min)
make live           # API with TRACKER_ENABLED=true; then `make frontend` → http://localhost:5173/leagues
```

API: `GET /leagues`, `GET /leagues/{league}/board`, `GET /leagues/{league}/teams`,
`GET /leagues/{league}/backtest`, `GET /leagues/{league}/model`, `POST /leagues/sync`,
`GET /events?competition=nfl&status=live`, WebSocket `/ws/events/league:{league}`.
