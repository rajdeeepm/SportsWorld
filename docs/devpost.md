# SportsWorld: Devpost submission

**Name:** SportsWorld

**Tagline (≤ 200 chars):** A live, calibrated world model of entire sports seasons: every team and every game in 7 leagues, and how each result moves the playoff race and the title.

**Links**
- Live: https://worldofsports.tech
- Code: https://github.com/rajdeeepm/SportsWorld
- Fetch.ai agent: `sportsworld-analyst` · `agent1qwh0gtgvn9j8cv8dzsa6jjz7tan0xr0yazds2vymxlvhyq8ehzevja34v5w` (ASI:One / Agentverse)
- Video: *(add YouTube link)*

---

## Inspiration

Every sports app tells you who's *probably* going to win tonight. None of them tells you what tonight actually
*means*: if Michigan loses, how far do their playoff odds fall? Does an injury to the Bills' quarterback change who
wins the AFC? What changed since yesterday, and why?

Those are world-model questions, not single-game ones. A season is a correlated system: one latent strength per
team drives every one of its games, results feed back into that strength, and the rules (tiebreaks, conference
title games, a 12-team playoff, play-ins, FIA points) turn thousands of games into a handful of outcomes that
people care about. We wanted to build that system properly (persistent, calibrated, auditable) and make it
something you can watch move in real time.

## What it does

SportsWorld keeps **one persistent probabilistic belief about each entire competition** (the NFL, college
football, NBA, NHL, men's and women's college basketball, college hockey and Formula 1) and updates it as
evidence arrives.

- **Every team, with uncertainty.** A Kalman-filtered latent strength (mean ± sd) for every team; F1 tracks driver
  skill and car pace separately.
- **Every game, forecast.** A calibrated model scores every remaining game before and during play (552 remaining
  FBS games right now).
- **Whole seasons, simulated.** 10,000 full seasons per league through versioned rules: the NFL's 7-team brackets,
  FBS conference title games and the 12-team CFP, the NBA play-in, NHL wildcards, the NCAA tournament, F1 sprint +
  race points with FIA count-back.
- **Propagation you can see.** A final score → both teams' strength → every affected future game → the season →
  playoff and title odds. Each step creates a new versioned world state, pushed instantly to every open browser
  and logged in a live feed with what changed and by how much.
- **Season leverage.** For every game: how much the result moves each team's playoff odds (win vs loss). The
  homepage ranks tonight's games by what they mean for the season, not by TV slot.
- **Counterfactual lab.** "What if Michigan's starting QB misses 3 games?" or "What if Michigan beats Ohio
  State?" runs on a private branch with common random numbers, so every difference is the scenario's effect.
  Absences use effects *learned from data* (an NFL starting QB is worth −3.0 ± 0.5 points). Every listed player
  is pooled by the share of the team's carries, catches or tackles they account for; in college football ball
  carriers are significant (a lead back ≈ −0.9 pts) and are applied. Effects that are not significant are shown
  with their estimate and never applied; offensive linemen leave no box-score trace and are labelled unmeasurable.
- **Live games with real positions.** Ball spot and drives (football), shot charts (basketball), shot/goal/hit
  maps (hockey), every F1 car on its real track position, live box scores and season player stats.
- **Live commentary and radio (ElevenLabs).** Turn on commentary for any game and it calls every play
  ("Touchdown! … two-point try … it's good! SportsWorld now has Cal at 50 percent"), plus a radio mode that calls
  every final and big swing across the league.
- **An agent you can talk to (Fetch.ai).** SportsWorld Analyst lives on ASI:One and inside the site. It turns
  questions into actions on the engine: reads the live run, builds and runs what-if scenarios (10,000 seasons per
  branch), ranks games to watch, explains matchups. A self-hosted Llama 3.3 70B rewrites answers conversationally
  and a checker rejects any rewrite whose numbers aren't in the engine's answer.
- **A daily scorecard.** Every day it grades its own kickoff forecasts against what happened, side by side with
  ESPN's model and the betting market.

## How we built it

**Data (all real, nothing synthetic).** 101,061 archived games across 8 leagues from ESPN's scoreboards (2018 →
today), play-by-play for 9,829 football games plus NBA/NHL event streams, 8,343 box-score summaries, live injury
reports, Jolpica F1 results and OpenF1 car telemetry. Market lines (8,877 games) are used *only* as a benchmark,
never as a feature. Every observation carries both its event time and the time the model knew it, so any
competition can be rebuilt exactly as it stood at any past instant.

**Engine (Python, FastAPI, NumPy).**
- Kalman rating book per league; hyper-parameters (home field, observation/process noise, season carry-over) fit
  by one-step predictive likelihood.
- Event models: bootstrap-ensemble logistic on strength gap, uncertainty, home field, rest, and live state
  (margin, clock, possession, down/distance → *learned* expected points), temperature-calibrated; a per-league
  choice between the learned model and the analytic Kalman model, made on a calibration window.
- Season Monte Carlo with two modes: DYNAMIC samples each team's latent strength once per simulated season (so
  futures are correlated, like a portfolio with parameter uncertainty), FAST treats games independently. Leverage
  comes from FAST; odds from DYNAMIC.
- Versioned rule sets per league and season; scenario branches share random numbers with the baseline.
- Bake-offs on GPUs: logistic vs LightGBM vs MLP vs GRU over play sequences, walk-forward, multi-seed, with
  game-clustered bootstrap CIs.

**Real-time and storage.**
- **SpacetimeDB on Maincloud** is the live world state: competitions, ~975 teams' odds, ~14,000 games with live
  score / probability / leverage, the update feed, win-probability history and viewer presence. The engine is the
  only writer (owner-only reducers); every browser subscribes and receives changes the moment they commit.
- **Neon Postgres** is the durable history: every season run, every live win-probability point, every world
  update, plus point-in-time replays that draw each team's "odds over the season" chart.

**Frontend.** React + TypeScript + Vite, recharts, official team colours and logos, designed for dark ground and
phone widths.

**AI.** Llama 3.3 70B self-hosted with vLLM: only for structuring questions and news into schema-checked JSON and
for rewriting answers with every number verified. It never produces a probability. ElevenLabs voices briefings,
radio and commentary from fixed templates over real play text. The Fetch.ai uAgent speaks the Agent Chat Protocol
via an Agentverse mailbox.

**Hosting.** worldofsports.tech (.Tech) through a Cloudflare Tunnel to the engine.

## Why we trust it (evidence)

- **Calibration at season scale.** Over seven replayed seasons, the preseason 90 % win-total interval covers the
  truth 91–95 % of the time (NFL 0.94, NBA 0.91, NHL 0.95, FBS 0.94). Treating games as independent, as most
  simulators do, gives only 52–77 %. Correlated futures are the whole point.
- **Walk-forward.** The learned model beats the Kalman-only model at every rolling origin in the NBA, FBS and NFL;
  in hockey they're tied, so the data picks the simpler one.
- **Bake-offs.** A GRU over NBA possessions beats logistic in 11/12 runs; in hockey neural models win 24/24 once
  play-by-play is backfilled to 2018; in football logistic ≈ MLP ≈ GRU ≈ ESPN's own win probability.
- **Honest benchmark.** On holdout games the de-vigged betting market beats our pregame forecasts by ≈ 0.03 log
  loss. We say so on the product.
- **Saturday's slate.** On all 47 completed FBS games of Oct 3, graded from point-in-time kickoff forecasts:
  SportsWorld log loss 0.497, ESPN's model 0.452, market 0.439. ESPN and the market were better that day; one day
  is a small sample, and the seven-season replay is the real evidence. The scorecard publishes this every day, good or bad.
- 58 tests including season acceptance (exactly one champion per simulated season, seed invariance,
  counterfactual isolation), zero leakage violations.

## Challenges we ran into

- **Our own simulator was overconfident** until we sampled latent strength per simulated season, and then our
  leverage numbers were *inflated*, because the dynamic run conflates a result with the team being better. We
  compute leverage from the independent-game run and odds from the dynamic one.
- **Late-game football was wrong** in obvious ways (down 2 at the opponent's 19 with 0:38 left showed 29 %). A
  time-conditioned learned expected-points model fixed it (67 %).
- **Live commentary missed scores** because play-by-play arrives out of order and conversions are separate plays;
  we made the scoreboard the source of truth for scores and resume the play stream by sequence.
- **Agent plumbing:** browsers block the Agentverse inspector from reaching localhost, so we registered the
  mailbox programmatically by signing the ownership challenge with the agent's key.
- **Restraint:** we estimated more player roles than we ship. Effects that aren't significant are shown, labelled,
  and never applied.

## Accomplishments that we're proud of

- One engine and one architecture for seven very different competitions, from a 12-team CFP to FIA count-back.
- Season-scale calibration that actually holds up on history, and saying out loud where the market is better.
- Watching a final score land and the whole season redraw itself across every open browser within seconds.
- An agent that *does* things (runs 10,000-season counterfactuals) rather than chatting about sports.

## What we learned

Uncertainty about the *state* matters more than precision about any single game. Most of the value of a world
model is in the correlations: the same latent strength drives fifteen games, and ignoring that makes every
probability look sharper than it is. We also learned that model capacity only pays when the state is long and
data-rich (NBA possessions, a backfilled hockey archive), and that the honest answer is often "logistic is tied."

## What's next

- Lineup and depth-chart evidence (the main thing the market knows that we don't), with the market as the
  yardstick for each new source.
- Conditioning simulations on postseasons already in progress; exact standings tiebreaks for every league.
- Per-player effects beyond the starting quarterback, as soon as they become statistically distinguishable.
- Push alerts when a game you care about swings your team's odds.

## Built with

python · fastapi · numpy · pytorch · lightgbm · react · typescript · vite · recharts ·
spacetimedb · neon · postgresql · elevenlabs · fetch.ai · uagents · agentverse · asi-one · llama · vllm ·
cloudflare · espn-api · openf1 · jolpica

## Prize tracks to select

- SpacetimeDB (Maincloud live world state)
- Fetch.ai (SportsWorld Analyst on ASI:One / Agentverse)
- ElevenLabs (commentary, radio, briefings)
- Best Use of .Tech domain: worldofsports.tech
- Neon (if offered)
- Overall / data & ML tracks as applicable
