Create ONE new script: scripts/external_consensus.py (do not modify any existing file). It implements spec §24 / Appendix D "external consensus comparison" for SportsWorld.

Goal: compare SportsWorld's independent PREGAME home-win probability with the betting-market implied probability on the same completed games, as a SEPARATE benchmark (market data must never become a model feature).

Data you can use (read the code to learn the APIs):
- Archived games: sportsworld.ingest.espn.read_archive(Path("data/real"), league), drop_exhibitions; GameRecord has game_id, start_time, completed, home/away TeamLine scores, season_type.
- Ratings: sportsworld.ingest.ratings.RatingBook(spec, load_params(models/artifacts/ratings/<league>.json)).replay(games, on_pregame=cb) calls cb(game, state) with a point-in-time pregame state dict.
- Features + model: sportsworld.ingest.features.league_features(state | {"home_score":0,"away_score":0,"seconds_remaining":spec.regulation_seconds}); the trained calibrated league model via sportsworld.models.registry.ModelRegistry(get_settings(), adapters).predict_league_features(league, [features...]) -> list of (p_home, lo, hi). Build adapters like backend/src/sportsworld/api/context.py does.
- Market odds: ESPN core API https://sports.core.api.espn.com/v2/sports/<sport>/leagues/<league>/events/<game_id>/competitions/<game_id>/odds -> items[] with provider.name, homeTeamOdds.moneyLine, awayTeamOdds.moneyLine (American odds). Prefer provider "ESPN BET" else the first item with both moneylines. sport path = LEAGUES[league].espn_path.split("/")[0]; league path = espn_path.split("/")[1].
Method:
- Leagues: nfl, nba, nhl, college-football (CLI --leagues, --seasons default 2024 2025, --max-games per league default 1500, --concurrency 8 with httpx.AsyncClient + retries + polite rate).
- Implied probabilities: convert American odds to raw probabilities, remove the vig proportionally (p_home = r_h/(r_h+r_a)). Record overround.
- For each completed regular/post-season game with market odds and a non-tie result: our p_home (from the replay at kickoff), market p_home, outcome.
- Metrics on the identical game set: log loss, Brier, ECE (10 bins), accuracy for SportsWorld and market; paired difference of log loss with a bootstrap over games (2000 draws) giving mean and 95% CI; disagreement analysis: correlation, mean |p_sw - p_mkt|, and log loss of each model on the subset where they disagree by > 0.15; a research-only blend ablation (A6): logistic regression of outcome on logit(p_sw) and logit(p_mkt) fit on the earlier half of games, evaluated on the later half (report weights and out-of-sample log loss) — label clearly as research ablation, NOT production.
- Write data/fixtures/backtests/consensus_<league>.json and print a concise summary. Cache raw odds responses to data/real/odds/<league>/<season>.jsonl so reruns do not refetch.
Run it: `PYTHONPATH=backend/src ../env/bin/python scripts/external_consensus.py --leagues nfl nba nhl` from the repo root and iterate until it completes. Report the summary numbers in your final message.
