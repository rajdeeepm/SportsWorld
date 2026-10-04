"""Compare independent pregame SportsWorld forecasts with ESPN market odds.

Usage from the repository root::

    PYTHONPATH=backend/src ../env/bin/python scripts/external_consensus.py \
        --leagues nfl nba nhl

Odds are read only by this benchmark. They are never passed to the rating book,
feature builder, or trained SportsWorld model. ESPN's archived odds endpoint does
not guarantee a quote timestamp; this is a retrospective market comparison.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sportsworld.config import get_settings  # noqa: E402
from sportsworld.ingest.espn import GameRecord, drop_exhibitions, read_archive  # noqa: E402
from sportsworld.ingest.features import league_features  # noqa: E402
from sportsworld.ingest.leagues import LEAGUES  # noqa: E402
from sportsworld.ingest.ratings import RatingBook, load_params  # noqa: E402
from sportsworld.models.registry import ModelRegistry  # noqa: E402
from sportsworld.schemas import Sport  # noqa: E402
from sportsworld.sports import BasketballAdapter, FootballAdapter, HockeyAdapter  # noqa: E402

DATA = ROOT / "data" / "real"
REPORTS = ROOT / "data" / "fixtures" / "backtests"
DEFAULT_LEAGUES = ("nfl", "nba", "nhl", "college-football")
ODDS_BASE = "https://sports.core.api.espn.com/v2/sports"
EPS = 1e-12


def american_probability(value: Any) -> float | None:
    """Return the raw implied probability of a nonzero American moneyline."""
    try:
        odds = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(odds) or odds == 0:
        return None
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def market_quote(payload: dict[str, Any]) -> dict[str, Any] | None:
    items = payload.get("items") or []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        home = (item.get("homeTeamOdds") or {}).get("moneyLine")
        away = (item.get("awayTeamOdds") or {}).get("moneyLine")
        raw_home, raw_away = american_probability(home), american_probability(away)
        if raw_home is None or raw_away is None:
            continue
        candidates.append((item, home, away, raw_home, raw_away))
    if not candidates:
        return None
    item, home, away, raw_home, raw_away = next(
        (x for x in candidates if (x[0].get("provider") or {}).get("name", "").upper() == "ESPN BET"),
        candidates[0],
    )
    total = raw_home + raw_away
    return {
        "provider": (item.get("provider") or {}).get("name"),
        "home_moneyline": home,
        "away_moneyline": away,
        "raw_home_probability": raw_home,
        "raw_away_probability": raw_away,
        "home_probability": raw_home / total,
        "overround": total - 1.0,
    }


def cached_odds(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                rows[str(row["game_id"])] = row
    return rows


class OddsFetcher:
    def __init__(self, concurrency: int):
        self.sem = asyncio.Semaphore(concurrency)
        self.rate_lock = asyncio.Lock()
        self.next_request = 0.0
        self.connection_failures = 0
        self.unavailable = False
        self.client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "SportsWorld/1.2 (external consensus research)"},
            limits=httpx.Limits(max_connections=concurrency),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _pace(self) -> None:
        # Across all leagues, start no more than five requests each second.
        async with self.rate_lock:
            now = time.monotonic()
            delay = max(0.0, self.next_request - now)
            if delay:
                await asyncio.sleep(delay)
            self.next_request = time.monotonic() + 0.2

    async def fetch(self, league: str, game_id: str) -> dict[str, Any] | None:
        sport, competition = LEAGUES[league].espn_path.split("/")
        url = f"{ODDS_BASE}/{sport}/leagues/{competition}/events/{game_id}/competitions/{game_id}/odds"
        async with self.sem:
            for attempt in range(4):
                if self.unavailable:
                    return None
                await self._pace()
                try:
                    response = await self.client.get(url)
                    if response.status_code == 404:
                        self.connection_failures = 0
                        return {"status_code": 404, "response": None}
                    if response.status_code == 429 or response.status_code >= 500:
                        raise httpx.HTTPStatusError("retryable ESPN odds response", request=response.request, response=response)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("ESPN odds response is not an object")
                    self.connection_failures = 0
                    return {"status_code": 200, "response": payload}
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    self.connection_failures += 1
                    if self.connection_failures >= 3 and not self.unavailable:
                        self.unavailable = True
                        print(f"ESPN odds feed unavailable: {exc}", file=sys.stderr)
                        return None
                except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                    if attempt == 3:
                        print(f"Odds fetch failed for {league} {game_id}: {exc}", file=sys.stderr)
                        return None
                if attempt < 3:
                    await asyncio.sleep(min(8.0, 0.75 * 2**attempt) + random.random() * 0.25)
        return None


async def odds_for_games(fetcher: OddsFetcher, league: str, games: list[GameRecord]) -> tuple[dict[str, dict], Counter]:
    by_season: dict[int, dict[str, dict]] = {}
    for season in {g.season for g in games}:
        by_season[season] = cached_odds(DATA / "odds" / league / f"{season}.jsonl")
    counts: Counter = Counter()

    async def one(game: GameRecord) -> None:
        cache = by_season[game.season]
        if game.game_id in cache:
            counts["cached"] += 1
            return
        result = await fetcher.fetch(league, game.game_id)
        if result is None:
            counts["fetch_failed"] += 1
            return
        row = {"game_id": game.game_id, "fetched_at": datetime.now(timezone.utc).isoformat(), **result}
        path = DATA / "odds" / league / f"{game.season}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        # This synchronous append contains no await, so it is atomic to these tasks.
        with path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        cache[game.game_id] = row
        counts["fetched"] += 1

    await asyncio.gather(*(one(g) for g in games))
    return {game_id: row for cache in by_season.values() for game_id, row in cache.items()}, counts


def clip(p: float) -> float:
    return min(1.0 - EPS, max(EPS, p))


def losses(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    q = np.clip(p, EPS, 1.0 - EPS)
    return -(y * np.log(q) + (1.0 - y) * np.log1p(-q))


def metrics(p: np.ndarray, y: np.ndarray) -> dict[str, float] | None:
    if len(y) == 0:
        return None
    ece = 0.0
    for b in range(10):
        in_bin = (p >= b / 10) & (p < (b + 1) / 10 if b < 9 else p <= 1.0)
        if in_bin.any():
            ece += float(in_bin.mean()) * abs(float(p[in_bin].mean() - y[in_bin].mean()))
    return {
        "log_loss": float(losses(p, y).mean()),
        "brier": float(np.mean((p - y) ** 2)),
        "ece_10_bins": ece,
        "accuracy": float(np.mean((p >= 0.5) == y)),
    }


def paired_bootstrap(sw: np.ndarray, market: np.ndarray, y: np.ndarray) -> dict[str, Any] | None:
    if len(y) == 0:
        return None
    difference = losses(sw, y) - losses(market, y)
    rng = np.random.default_rng(2406)
    draws = np.empty(2000)
    for i in range(2000):
        draws[i] = difference[rng.integers(0, len(y), len(y))].mean()
    return {
        "direction": "sportsworld_minus_market; negative favors SportsWorld",
        "observed_mean": float(difference.mean()),
        "bootstrap_mean": float(draws.mean()),
        "ci_95": [float(x) for x in np.quantile(draws, [0.025, 0.975])],
        "draws": 2000,
        "seed": 2406,
    }


def research_blend(sw: np.ndarray, market: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    n = len(y)
    result: dict[str, Any] = {
        "label": "A6 research-only blend ablation: NOT production",
        "split": "earlier 50% of games for fitting; later 50% for evaluation",
        "train_games": n // 2,
        "test_games": n - n // 2,
    }
    if n < 10 or len(np.unique(y[: n // 2])) < 2:
        result["status"] = "insufficient training games or outcome classes"
        return result
    logits = lambda p: np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
    x = np.column_stack((np.ones(n), logits(sw), logits(market)))
    split = n // 2
    x_train, y_train = x[:split], y[:split]
    weights = np.zeros(3)
    penalty = np.array([0.0, 1e-6, 1e-6])
    for _ in range(100):
        z = np.clip(x_train @ weights, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        gradient = x_train.T @ (p - y_train) + penalty * weights
        hessian = x_train.T @ (x_train * (p * (1.0 - p))[:, None]) + np.diag(penalty + 1e-9)
        step = np.linalg.solve(hessian, gradient)
        weights -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    z_test = np.clip(x[split:] @ weights, -35.0, 35.0)
    blended = 1.0 / (1.0 + np.exp(-z_test))
    result.update({
        "status": "ok",
        "weights": {"intercept": float(weights[0]), "sportsworld_logit": float(weights[1]), "market_logit": float(weights[2])},
        "out_of_sample_log_loss": float(losses(blended, y[split:]).mean()),
        "sportsworld_out_of_sample_log_loss": float(losses(sw[split:], y[split:]).mean()),
        "market_out_of_sample_log_loss": float(losses(market[split:], y[split:]).mean()),
    })
    return result


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sw = np.array([r["sportsworld_home_probability"] for r in rows], dtype=float)
    market = np.array([r["market_home_probability"] for r in rows], dtype=float)
    y = np.array([r["home_win"] for r in rows], dtype=float)
    disagreement = np.abs(sw - market)
    subset = disagreement > 0.15
    correlation = float(np.corrcoef(sw, market)[0, 1]) if len(rows) > 1 and np.std(sw) > 0 and np.std(market) > 0 else None
    return {
        "sportsworld": metrics(sw, y),
        "market": metrics(market, y),
        "paired_log_loss_difference": paired_bootstrap(sw, market, y),
        "disagreement": {
            "correlation": correlation,
            "mean_absolute_probability_difference": float(disagreement.mean()) if len(rows) else None,
            "threshold": 0.15,
            "games_above_threshold": int(subset.sum()),
            "sportsworld_log_loss_above_threshold": float(losses(sw[subset], y[subset]).mean()) if subset.any() else None,
            "market_log_loss_above_threshold": float(losses(market[subset], y[subset]).mean()) if subset.any() else None,
        },
        "A6_research_only_blend_ablation": research_blend(sw, market, y),
    }


def pregame_features(spec: Any, games: list[GameRecord], selected_ids: set[str]) -> dict[str, dict[str, float]]:
    features: dict[str, dict[str, float]] = {}

    def on_pregame(game: GameRecord, state: dict) -> None:
        if game.game_id in selected_ids:
            features[game.game_id] = league_features({
                **state, "home_score": 0, "away_score": 0,
                "seconds_remaining": spec.regulation_seconds,
            })

    params = load_params(ROOT / "models" / "artifacts" / "ratings" / f"{spec.league_id}.json")
    RatingBook(spec, params).replay(games, on_pregame=on_pregame)
    return features


async def run_league(league: str, seasons: set[int], max_games: int, registry: ModelRegistry, fetcher: OddsFetcher) -> None:
    spec = LEAGUES[league]
    archive = drop_exhibitions(read_archive(DATA, league))
    # An event can appear in more than one season archive; the latest fetched copy wins.
    unique = {game.game_id: game for game in sorted(archive, key=lambda g: g.fetched_at)}
    games = sorted(unique.values(), key=lambda g: (g.start_time, g.game_id))
    eligible = [g for g in games if g.season in seasons and g.season_type in (2, 3) and g.completed and not g.cancelled and g.margin() != 0]
    # Prospective holdout only: games after the model's calibration window ended (never seen in training or calibration).
    _card = registry.league_card(league)
    holdout_start = None
    if _card and _card.calibration_window.get("end"):
        holdout_start = datetime.fromisoformat(str(_card.calibration_window["end"]).replace("Z", "+00:00"))
        eligible = [g for g in eligible if g.start_time > holdout_start]
    selected = eligible[-max_games:]
    if not registry.league_card(league):
        raise RuntimeError(f"No trained league model found for {league}")
    features = pregame_features(spec, games, {g.game_id for g in selected})
    predictions = registry.predict_league_features(league, [features[g.game_id] for g in selected if g.game_id in features])
    pred_ids = [g.game_id for g in selected if g.game_id in features]
    if len(predictions) != len(pred_ids):
        raise RuntimeError(f"Model prediction count mismatch for {league}")
    sportsworld = dict(zip(pred_ids, predictions))
    odds, fetch_counts = await odds_for_games(fetcher, league, selected)
    rows = []
    exclusions: Counter = Counter()
    for game in selected:
        prediction = sportsworld.get(game.game_id)
        cached = odds.get(game.game_id)
        if prediction is None:
            exclusions["missing_pregame_prediction"] += 1
            continue
        if cached is None:
            exclusions["odds_request_failed"] += 1
            continue
        quote = market_quote(cached.get("response") or {})
        if quote is None:
            exclusions["no_two_sided_moneyline"] += 1
            continue
        rows.append({
            "game_id": game.game_id,
            "season": game.season,
            "start_time": game.start_time.isoformat(),
            "home_team": game.home.name,
            "away_team": game.away.name,
            "home_win": int(game.margin() > 0),
            "sportsworld_home_probability": prediction[0],
            "sportsworld_interval_90": [prediction[1], prediction[2]],
            "market_home_probability": quote["home_probability"],
            "market_provider": quote["provider"],
            "home_moneyline": quote["home_moneyline"],
            "away_moneyline": quote["away_moneyline"],
            "overround": quote["overround"],
        })
    card = registry.league_card(league)
    report = {
        "league": league,
        "seasons": sorted(seasons),
        "forecast_horizon": "pregame at kickoff",
        "benchmark": "external market consensus, separate from SportsWorld features and model training",
        "interpretation": "Out-of-sample: only games after the model's calibration window. Archived ESPN odds may lack a verified pre-kickoff quote timestamp (likely closing lines).",
        "holdout_start": holdout_start.isoformat() if holdout_start else None,
        "model_version": card.model_version,
        "model_train_window": card.train_window,
        "eligible_games": len(eligible),
        "selected_games": len(selected),
        "matched_games": len(rows),
        "status": "scored" if rows else "no_paired_games",
        "max_games": max_games,
        "odds_cache": dict(fetch_counts),
        "exclusions": dict(exclusions),
        "metrics": summarize(rows),
        "games": rows,
    }
    path = REPORTS / f"consensus_{league}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    sw = report["metrics"]["sportsworld"]
    market = report["metrics"]["market"]
    if sw and market:
        print(f"{league}: {len(rows)}/{len(selected)} matched | log loss SW {sw['log_loss']:.4f}, market {market['log_loss']:.4f} | Brier SW {sw['brier']:.4f}, market {market['brier']:.4f} | {path}")
    else:
        print(f"{league}: 0/{len(selected)} matched; no paired scores ({dict(exclusions)}) | {path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leagues", nargs="+", choices=DEFAULT_LEAGUES, default=list(DEFAULT_LEAGUES))
    parser.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025])
    parser.add_argument("--max-games", type=int, default=1500, help="maximum eligible games per league, in kickoff order")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if args.max_games < 1 or args.concurrency < 1:
        parser.error("--max-games and --concurrency must be positive")
    adapters = {Sport.FOOTBALL: FootballAdapter(), Sport.BASKETBALL: BasketballAdapter(), Sport.HOCKEY: HockeyAdapter()}
    registry = ModelRegistry(get_settings(), adapters)
    fetcher = OddsFetcher(args.concurrency)
    try:
        for league in args.leagues:
            await run_league(league, set(args.seasons), args.max_games, registry, fetcher)
    finally:
        await fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
