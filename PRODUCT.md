# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary: MHacks 2026 judges during a live 3–5 minute walkthrough on a laptop or projector, including technically
sophisticated sponsor judges (D. E. Shaw quant researchers, AWS, Meta, SpaceX). They must grasp the product in
seconds and be able to drill into technical depth on request. Secondary: the project doubles as a portfolio piece
for quant-research internship applications, read later by recruiters and engineers.

## Product Purpose
SportsWorld maintains a continuously updating, calibrated probabilistic model of entire sporting competitions:
every team and every game/race of a season, from latent team strength through each event forecast to playoff and
championship probabilities. New evidence (finals, live scores, injury reports, verified news) propagates through
the whole season. Success: a judge sees one piece of information move a team's championship odds, and trusts that
the numbers are real, point-in-time, and backtested.

## Positioning
Not a game predictor: a persistent world model of a whole season. Whole-season Monte Carlo with correlated futures
(latent strength sampled once per simulated season) that is shown to be calibrated over 7 replayed seasons;
counterfactual branches without touching canonical state; an LLM that only structures questions and never emits
probabilities.

## Operating Context
Demo runs locally (`make live` / `make replay-demo`, Vite frontend on :5173, FastAPI on :8000). Venue network may be
unreliable; an offline replay at a fixed as-of date must render identically. A self-hosted Llama 3.3 70B is reachable
only through an SSH tunnel and may be down; the deterministic parser is the fallback.

## Capabilities and Constraints
- Stack: existing React + Vite + TypeScript frontend (`frontend/`), FastAPI backend.
- Leagues in the UI: exactly F1, NFL, College Football (CFB), NBA, College Basketball (CBB, men's), NHL, College
  Hockey (men's). WNBA and women's college basketball stay in the backend but are not shown.
- Real data available per league: team list with ESPN ids/logos, records, standings, latent strength ± sd, full
  remaining schedule with win probabilities (live and pregame), season distributions (expected wins + band, win
  histograms, seed distributions, playoff/division/conference/title probabilities with MC standard errors), FAST vs
  DYNAMIC season runs, world-update feed (finals, availability changes, season recomputes), live injury report with
  learned availability deltas, grounded news signals, typed and natural-language season counterfactuals, F1 driver
  and constructor title odds with entry list, research results (season replay, bake-offs, consensus, rolling).
- Not available and must not be shown as data: coaches, venues/capacity, player photos and player ratings,
  position-group/unit breakdowns, matchup factors, betting spreads/totals, TV networks, weather, recruiting,
  transfers, rankings polls, curated storylines.

## Brand Commitments
Name "SportsWorld", subtitle "Season Intelligence Engine". Page names "<Team> — Season World", "<League> — <Season>
Season World", "<League> — Season Simulation Lab". Real ESPN team logos and league colours. The user's reference
renderings (dark navy broadcast-terminal dashboards, top league tab bar, left sidebar, dense multi-panel layouts) are
the binding visual reference.

## Evidence on Hand
All numbers come from the live API and `data/fixtures/backtests/*`. Research findings are in
`docs/research_report.md`. No fabricated statistics, testimonials, accuracy claims or "model grade" scores; model
health panels must show real backtest metrics (log loss, Brier, ECE, interval coverage).

## Product Principles
1. Every number on screen is real, point-in-time, versioned and traceable to the engine.
2. Story first, depth on demand: a judge understands a panel in five seconds; the research layer is one click away.
3. Propagation is the hero: show evidence moving games, then seasons, then titles.
4. Honest uncertainty: show bands, standard errors and limitations instead of false precision.
5. Bulletproof demo: every screen works offline in replay mode and degrades gracefully.
