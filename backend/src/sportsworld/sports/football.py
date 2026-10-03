from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from sportsworld.core.math import sigmoid
from sportsworld.ingest.features import TEAM_STATE_KEYS, is_league_state, league_features
from sportsworld.schemas import Observation, WorldState
from sportsworld.sports.base import SportAdapter


class FootballAdapter(SportAdapter):
    sport_name = "football"
    schema_version = "football_features_v3_world_state"

    KINDS = {
        "score_state", "score", "possession", "turnover", "injury_status",
        "weather", "timeout", "penalty", "availability", "drive_state",
        "correction", "game_end", "team_state"
    }

    DEFAULTS = {
        "home_score": 0, "away_score": 0, "quarter": 1, "seconds_remaining": 3600,
        "possession": "home", "down": 1, "distance": 10, "yard_line": 25,
        "home_timeouts": 3, "away_timeouts": 3, "home_strength": 0.0,
        "away_strength": 0.0, "home_qb_available": 1.0, "away_qb_available": 1.0,
        "weather_severity": 0.0, "home_field": 1.0, "state_confidence": 0.95,
        "completed": 0.0,
    }

    def validate_state(self, state: WorldState) -> None:
        if len(state.outcomes) != 2:
            raise ValueError("football requires two outcomes")
        if float(state.features.get("seconds_remaining", 0)) < 0:
            raise ValueError("seconds_remaining cannot be negative")

    def apply_observation(self, state: WorldState, observation: Observation) -> WorldState:
        self._check_observation(state, observation)
        s = state.clone()
        f = {**self.DEFAULTS, **s.features}
        p = observation.payload
        if observation.kind in {"score_state", "drive_state"}:
            for key in ("home_score", "away_score", "quarter", "seconds_remaining", "possession", "down", "distance", "yard_line", "home_timeouts", "away_timeouts"):
                if key in p:
                    f[key] = p[key]
        elif observation.kind == "score":
            team = p.get("team", "home")
            points = int(p.get("points", 0))
            f[f"{team}_score"] = int(f[f"{team}_score"]) + points
            if "seconds_remaining" in p: f["seconds_remaining"] = p["seconds_remaining"]
            if "possession" in p: f["possession"] = p["possession"]
        elif observation.kind in {"possession", "turnover"}:
            f["possession"] = p.get("possession", "away" if f["possession"] == "home" else "home")
            for key in ("down", "distance", "yard_line", "seconds_remaining"):
                if key in p: f[key] = p[key]
        elif observation.kind in {"injury_status", "availability"}:
            role = str(p.get("role", ""))
            team = str(p.get("team", "home"))
            status = str(p.get("status", "available")).lower()
            value = 0.0 if status in {"out", "unavailable", "injured"} else 0.5 if status in {"questionable", "limited"} else 1.0
            if role in {"qb", "starting_qb"}:
                f[f"{team}_qb_available"] = value
            impact = float(p.get("impact", 0.0))
            f[f"{team}_strength"] = float(f[f"{team}_strength"]) + impact
        elif observation.kind == "weather":
            if "severity" in p:
                f["weather_severity"] = min(1.0, max(0.0, float(p["severity"])))
            elif "rain_probability" in p:
                f["weather_severity"] = min(1.0, max(0.0, float(p["rain_probability"])))
        elif observation.kind == "timeout":
            team = p.get("team", "home")
            f[f"{team}_timeouts"] = max(0, int(f[f"{team}_timeouts"]) - 1)
        elif observation.kind == "game_end":
            f["seconds_remaining"] = 0
            f["completed"] = 1.0
        elif observation.kind == "correction":
            f.update(p)
        elif observation.kind == "team_state":
            f.update({k: v for k, v in p.items() if k in TEAM_STATE_KEYS})
        # Confidence compounds conservatively but never collapses to zero because
        # one low-confidence contextual item appeared.
        f["state_confidence"] = min(float(f.get("state_confidence", 1.0)), 0.5 + 0.5 * observation.confidence)
        s.features = f
        self.validate_state(s)
        return s

    def build_features(self, state: WorldState, prediction_time: datetime) -> dict[str, float]:
        f = {**self.DEFAULTS, **state.features}
        score_diff = float(f["home_score"]) - float(f["away_score"])
        seconds = max(0.0, float(f["seconds_remaining"]))
        time_frac = seconds / 3600.0
        yard = float(f.get("yard_line", 50))
        possession_home = 1.0 if f.get("possession") == "home" else -1.0
        out = {
            "strength_diff": float(f["home_strength"]) - float(f["away_strength"]),
            "historical_strength_diff": float(f.get("historical_strength_diff", 0.0)),
            "recent_form_diff": float(f.get("recent_form_diff", 0.0)),
            "health_diff": float(f.get("health_diff", 0.0)),
            "usage_stability_diff": float(f.get("usage_stability_diff", 0.0)),
            "experience_diff": float(f.get("experience_diff", 0.0)),
            "potential_diff": float(f.get("potential_diff", 0.0)),
            "chemistry_diff": float(f.get("chemistry_diff", 0.0)),
            "matchup_advantage": float(f.get("matchup_advantage", 0.0)),
            "context_mean_shift": float(f.get("context_mean_shift", 0.0)),
            "human_context_diff": float(f.get("human_context_diff", 0.0)),
            "environment_context_diff": float(f.get("environment_context_diff", 0.0)),
            "context_volatility": float(f.get("context_volatility", 0.0)),
            "score_diff_scaled": score_diff / 14.0,
            "time_elapsed": 1.0 - min(1.0, time_frac),
            "score_time_interaction": (score_diff / 14.0) * (1.0 - min(1.0, time_frac)),
            "possession_home": possession_home,
            "field_position_home": (yard - 50.0) / 50.0 * (1.0 if f.get("possession") == "home" else -1.0),
            "home_qb_available": float(f["home_qb_available"]),
            "away_qb_available": float(f["away_qb_available"]),
            "weather_severity": float(f["weather_severity"]),
            "home_field": float(f["home_field"]),
        }
        if is_league_state(f):
            out.update(league_features(f))
        return out

    def predict_raw(self, state: WorldState, model=None) -> dict[str, float]:
        x = self.build_features(state, state.prediction_cutoff)
        # Transparent statistical baseline. The production demo football path can
        # replace this with the learned bootstrap ensemble from ModelRegistry.
        z = (
            0.48 * x["strength_diff"]
            + 0.38 * x["historical_strength_diff"]
            + 0.32 * x["recent_form_diff"]
            + 0.26 * x["health_diff"]
            + 0.10 * x["usage_stability_diff"]
            + 0.12 * x["experience_diff"]
            + 0.10 * x["potential_diff"]
            + 0.12 * x["chemistry_diff"]
            + 0.34 * x["matchup_advantage"]
            + 0.24 * x["context_mean_shift"]
            + 0.12 * x["human_context_diff"]
            + 0.10 * x["environment_context_diff"]
            + 1.35 * x["score_diff_scaled"]
            + 1.55 * x["score_time_interaction"] + 0.20 * x["possession_home"]
            + 0.12 * x["field_position_home"] + 0.85 * (x["home_qb_available"] - x["away_qb_available"])
            - 0.08 * x["weather_severity"] + 0.18 * x["home_field"]
        )
        labels = state.outcomes
        return {labels[0]: z / 2.0, labels[1]: -z / 2.0}

    def simulate_transition(self, state: WorldState, rng: np.random.Generator) -> str:
        scores = self.predict_raw(state, None)
        labels = state.outcomes
        z = scores[labels[0]] - scores[labels[1]]
        p = float(sigmoid(z))
        return labels[0] if rng.random() < p else labels[1]

    def supported_observation_kinds(self) -> set[str]:
        return set(self.KINDS)
