from __future__ import annotations

from datetime import datetime
import numpy as np

from sportsworld.core.math import sigmoid
from sportsworld.ingest.features import TEAM_STATE_KEYS, is_league_state, league_features
from sportsworld.schemas import Observation, WorldState
from sportsworld.sports.base import SportAdapter


class BasketballAdapter(SportAdapter):
    sport_name = "basketball"
    schema_version = "basketball_features_v3_world_state"
    KINDS = {"score_state", "score", "possession", "lineup", "substitution", "foul", "injury_status", "availability", "pace", "timeout", "game_end", "correction", "team_state"}
    DEFAULTS = {
        "home_score": 0, "away_score": 0, "seconds_remaining": 2880, "possession": "home",
        "home_strength": 0.0, "away_strength": 0.0, "home_star_available": 1.0,
        "away_star_available": 1.0, "home_lineup_rating": 0.0, "away_lineup_rating": 0.0,
        "pace": 100.0, "home_fouls": 0, "away_fouls": 0, "home_field": 1.0, "state_confidence": 0.95,
        "completed": 0.0,
    }

    def validate_state(self, state: WorldState) -> None:
        if len(state.outcomes) != 2: raise ValueError("basketball requires two outcomes")
        if float(state.features.get("seconds_remaining", 0)) < 0: raise ValueError("seconds_remaining cannot be negative")

    def apply_observation(self, state: WorldState, observation: Observation) -> WorldState:
        self._check_observation(state, observation)
        s = state.clone(); f = {**self.DEFAULTS, **s.features}; p = observation.payload
        if observation.kind == "score_state":
            for k in ("home_score", "away_score", "seconds_remaining", "possession", "pace", "home_fouls", "away_fouls"):
                if k in p: f[k] = p[k]
        elif observation.kind == "score":
            team = p.get("team", "home"); f[f"{team}_score"] = int(f[f"{team}_score"]) + int(p.get("points", 0))
            if "seconds_remaining" in p: f["seconds_remaining"] = p["seconds_remaining"]
        elif observation.kind == "possession": f["possession"] = p.get("possession", f["possession"])
        elif observation.kind in {"lineup", "substitution"}:
            team = p.get("team", "home"); f[f"{team}_lineup_rating"] = float(p.get("lineup_rating", f[f"{team}_lineup_rating"]))
        elif observation.kind in {"injury_status", "availability"}:
            team = p.get("team", "home"); status = str(p.get("status", "available")).lower()
            f[f"{team}_star_available"] = 0.0 if status in {"out", "unavailable", "injured"} else 0.5 if status in {"questionable", "limited"} else 1.0
            f[f"{team}_strength"] = float(f[f"{team}_strength"]) + float(p.get("impact", 0.0))
        elif observation.kind == "foul":
            team = p.get("team", "home"); f[f"{team}_fouls"] = int(f[f"{team}_fouls"]) + 1
        elif observation.kind == "pace": f["pace"] = float(p.get("pace", f["pace"]))
        elif observation.kind == "game_end": f["seconds_remaining"] = 0; f["completed"] = 1.0
        elif observation.kind == "correction": f.update(p)
        elif observation.kind == "team_state": f.update({k: v for k, v in p.items() if k in TEAM_STATE_KEYS})
        f["state_confidence"] = min(float(f.get("state_confidence", 1.0)), 0.5 + 0.5 * observation.confidence)
        s.features = f; self.validate_state(s); return s

    def build_features(self, state: WorldState, prediction_time: datetime) -> dict[str, float]:
        f = {**self.DEFAULTS, **state.features}; score_diff = float(f["home_score"]) - float(f["away_score"])
        reg = max(1.0, float(f.get("regulation_seconds", 2880)))
        elapsed = 1.0 - min(1.0, max(0.0, float(f["seconds_remaining"])) / reg)
        out = {
            "strength_diff": float(f["home_strength"]) - float(f["away_strength"]),
            "historical_strength_diff": float(f.get("historical_strength_diff", 0.0)),
            "recent_form_diff": float(f.get("recent_form_diff", 0.0)),
            "health_diff": float(f.get("health_diff", 0.0)),
            "experience_diff": float(f.get("experience_diff", 0.0)),
            "chemistry_diff": float(f.get("chemistry_diff", 0.0)),
            "matchup_advantage": float(f.get("matchup_advantage", 0.0)),
            "context_mean_shift": float(f.get("context_mean_shift", 0.0)),
            "human_context_diff": float(f.get("human_context_diff", 0.0)),
            "environment_context_diff": float(f.get("environment_context_diff", 0.0)),
            "context_volatility": float(f.get("context_volatility", 0.0)),
            "score_diff_scaled": score_diff / 10.0,
            "score_time_interaction": (score_diff / 10.0) * elapsed,
            "possession_home": 1.0 if f["possession"] == "home" else -1.0,
            "lineup_diff": (float(f["home_lineup_rating"]) - float(f["away_lineup_rating"])) / 10.0,
            "star_availability_diff": float(f["home_star_available"]) - float(f["away_star_available"]),
            "pace_scaled": (float(f["pace"]) - 100.0) / 15.0,
            "home_field": float(f.get("home_field", 1.0)),
        }
        if is_league_state(f):
            out.update(league_features(f))
        return out

    def predict_raw(self, state: WorldState, model=None) -> dict[str, float]:
        x = self.build_features(state, state.prediction_cutoff)
        z = 0.50*x["strength_diff"] + 0.35*x["historical_strength_diff"] + 0.34*x["recent_form_diff"] + 0.24*x["health_diff"] + 0.12*x["experience_diff"] + 0.18*x["chemistry_diff"] + 0.30*x["matchup_advantage"] + 0.22*x["context_mean_shift"] + 0.10*x["human_context_diff"] + 0.08*x["environment_context_diff"] + 1.0*x["score_diff_scaled"] + 1.65*x["score_time_interaction"] + 0.10*x["possession_home"] + 0.35*x["lineup_diff"] + 0.65*x["star_availability_diff"] + 0.04*x["pace_scaled"] + 0.14*x["home_field"]
        return {state.outcomes[0]: z/2, state.outcomes[1]: -z/2}

    def simulate_transition(self, state: WorldState, rng: np.random.Generator) -> str:
        s = self.predict_raw(state, None); z=s[state.outcomes[0]]-s[state.outcomes[1]]; p=float(sigmoid(z)); return state.outcomes[0] if rng.random()<p else state.outcomes[1]

    def supported_observation_kinds(self) -> set[str]: return set(self.KINDS)
