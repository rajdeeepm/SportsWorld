"""Real-data feature schema for tracked leagues.

`league_features` is the single function used both to build training rows from
archived games and to score a live `WorldState`, guaranteeing training/serving
parity.  Names are deliberately distinct from the synthetic v3 schema so the
ContextEngine's profile-derived aggregates can never overwrite them.
"""
from __future__ import annotations

import math
from typing import Any

SCHEMA_VERSION = "league_features_v2_real"
EP_FULL_S = 150.0

PREGAME_FEATURES = ["home_field", "rating_diff", "rating_uncertainty", "prior_season_rating_diff", "form_diff", "rest_diff"]
LIVE_FEATURES = ["score_margin_scaled", "game_elapsed", "margin_time_interaction", "live_margin_z"]
LEAGUE_FEATURES = PREGAME_FEATURES + LIVE_FEATURES
# Football adds the value of the current possession (learned expected points).
FOOTBALL_LEAGUE_FEATURES = LEAGUE_FEATURES + ["possession_ep"]

# Latent-state fields a `team_state` observation may update on a live WorldState.
TEAM_STATE_KEYS = {
    "home_rating", "away_rating", "home_rating_var", "away_rating_var", "home_prior_rating", "away_prior_rating",
    "home_form", "away_form", "home_rest_days", "away_rest_days", "home_strength", "away_strength",
    "hfa", "obs_sd", "home_games_played", "away_games_played",
}

ABLATION_GROUPS = [
    ("A0 home field only", ["home_field"]),
    ("A1 + latent rating state (Kalman mean/var, prior season)", ["home_field", "rating_diff", "rating_uncertainty", "prior_season_rating_diff"]),
    ("A2 + form / rest context", PREGAME_FEATURES),
    ("A3 + live game state", LEAGUE_FEATURES),
]
FOOTBALL_ABLATION_GROUPS = ABLATION_GROUPS[:3] + [
    ("A3 + live score/clock", LEAGUE_FEATURES),
    ("A4 + possession / field position (learned EP)", FOOTBALL_LEAGUE_FEATURES),
]


def ep_design(ytg: float, down: int, distance: float) -> list[float]:
    y = ytg / 100.0
    return [1.0, y, y * y, float(down == 2), float(down == 3), float(down == 4), min(distance, 20.0) / 10.0]


def expected_points(coef: list[float], ytg: float, down: int, distance: float) -> float:
    return float(sum(c * v for c, v in zip(coef, ep_design(ytg, down, distance))))


def possession_value(f: dict[str, Any]) -> float:
    """Signed (home-positive) expected points of the current football possession, 0 if unknown."""
    coef = f.get("ep_coef")
    down = int(f.get("down", 0) or 0)
    if not coef or not 1 <= down <= 4:
        return 0.0
    sign = 1.0 if f.get("possession") == "home" else -1.0 if f.get("possession") == "away" else 0.0
    ytg = 100.0 - float(f.get("yard_line", 75))
    if not sign or not 0 < ytg < 100:
        return 0.0
    return sign * expected_points(coef, ytg, down, float(f.get("distance", 10) or 10))


def is_league_state(f: dict[str, Any]) -> bool:
    return "league" in f and "home_rating" in f


def league_features(f: dict[str, Any]) -> dict[str, float]:
    sd = float(f.get("margin_sd") or 12.0)
    hm, am = float(f.get("home_rating", 0.0)), float(f.get("away_rating", 0.0))
    hv, av = float(f.get("home_rating_var", 100.0)), float(f.get("away_rating_var", 100.0))
    home_field = float(f.get("home_field", 1.0))
    hfa = float(f.get("hfa", 0.0))
    obs_sd = float(f.get("obs_sd", sd))
    reg = max(1.0, float(f.get("regulation_seconds", 3600)))
    remaining = max(0.0, min(reg, float(f.get("seconds_remaining", reg))))
    if float(f.get("completed", 0.0)) >= 1.0:
        remaining = 0.0
    frac = remaining / reg
    elapsed = 1.0 - frac
    score_diff = float(f.get("home_score", 0)) - float(f.get("away_score", 0))
    expected = hfa * home_field + hm - am
    # Remaining-margin distribution: both rating uncertainty and game noise
    # shrink with the share of the game left to play.
    rem_sd = math.sqrt(frac * obs_sd ** 2 + frac * frac * (hv + av)) + 1e-6
    # A possession can only realise its expected points if time remains: scale EP to zero over the
    # final EP_FULL_S seconds (assumption ~ length of a scoring drive; Codex review finding).
    ep = possession_value(f) * min(1.0, remaining / EP_FULL_S) if remaining > 0 else 0.0
    mu = score_diff + expected * frac + ep
    if remaining <= 0.0:
        z = 6.0 if score_diff > 0 else -6.0 if score_diff < 0 else 0.0
    else:
        z = max(-6.0, min(6.0, mu / rem_sd))
    rest = (min(10.0, float(f.get("home_rest_days", 7))) - min(10.0, float(f.get("away_rest_days", 7)))) / 7.0
    return {
        "home_field": home_field,
        "rating_diff": (hm - am) / sd,
        "rating_uncertainty": math.sqrt(hv + av) / sd,
        "prior_season_rating_diff": (float(f.get("home_prior_rating", 0.0)) - float(f.get("away_prior_rating", 0.0))) / sd,
        "form_diff": (float(f.get("home_form", 0.0)) - float(f.get("away_form", 0.0))) / sd,
        "rest_diff": max(-1.0, min(1.0, rest)),
        "score_margin_scaled": score_diff / sd,
        "game_elapsed": elapsed,
        "margin_time_interaction": score_diff / sd * elapsed,
        "live_margin_z": z / 3.0,
        "possession_ep": ep / sd,
    }
