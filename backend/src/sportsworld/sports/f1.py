from __future__ import annotations

from datetime import datetime
import math
import numpy as np

from sportsworld.core.math import softmax
from sportsworld.schemas import Observation, WorldState
from sportsworld.sports.base import SportAdapter


class F1Adapter(SportAdapter):
    sport_name = "f1"
    schema_version = "f1_features_v3_learned_world"
    KINDS = {"race_state", "driver_state", "lap", "position_change", "pit_stop", "weather", "safety_car", "penalty", "reliability", "pace", "race_end", "correction"}
    OUTCOME_FEATURES = [
        "position_advantage", "progress_position", "pace_advantage", "reliability_log",
        "wet_interaction", "pit_penalty", "tyre_penalty", "penalty_penalty",
        "context_adjustment", "latent_skill", "latent_form", "latent_health",
        "latent_experience", "latent_potential", "safety_car_position_relief",
    ]
    # Real-data feature set (Jolpica/OpenF1 trained); computed from the per-driver
    # dict so the ContextEngine's profile-derived latent fields never overwrite it.
    REAL_FEATURES = [
        "position_advantage", "progress_position", "driver_rating", "car_rating", "rating_uncertainty",
        "reliability_remaining", "gap_advantage", "progress_gap",
    ]

    def validate_state(self, state: WorldState) -> None:
        if len(state.outcomes) < 2:
            raise ValueError("F1 needs at least two outcomes")
        if int(state.features.get("lap", 0)) < 0:
            raise ValueError("lap cannot be negative")

    def _drivers(self, state: WorldState) -> dict[str, dict]:
        drivers = state.features.setdefault("drivers", {})
        for idx, d in enumerate(state.outcomes, start=1):
            drivers.setdefault(d, {"position": idx, "pace": 0.0, "tyre_age": 0, "compound": "MEDIUM", "reliability": 0.98, "pit_loss": 0.0, "wet_skill": 0.0, "penalty_s": 0.0})
        return drivers

    def apply_observation(self, state: WorldState, observation: Observation) -> WorldState:
        self._check_observation(state, observation)
        s = state.clone()
        f = s.features
        f.setdefault("lap", 0); f.setdefault("total_laps", 57); f.setdefault("rain_probability", 0.0); f.setdefault("safety_car", 0.0); f.setdefault("state_confidence", 0.95)
        drivers = self._drivers(s); p = observation.payload
        if observation.kind in {"race_state", "lap"}:
            if "lap" in p: f["lap"] = int(p["lap"])
            if "total_laps" in p: f["total_laps"] = int(p["total_laps"])
            for d, data in p.get("drivers", {}).items():
                if d in drivers: drivers[d].update(data)
        elif observation.kind == "driver_state":
            for d, data in p.get("drivers", {}).items():
                if d in drivers: drivers[d].update({k: v for k, v in data.items() if k in {"rating_driver", "rating_car", "rating_sd", "reliability", "position", "grid"}})
        elif observation.kind == "position_change":
            d = p["driver"]; drivers.setdefault(d, {}).update({"position": int(p["position"])})
        elif observation.kind == "pit_stop":
            d = p["driver"]; info = drivers.setdefault(d, {})
            info["compound"] = p.get("new_compound", info.get("compound", "MEDIUM")); info["tyre_age"] = 0
            info["pit_loss"] = float(p.get("pit_duration_s", 22.0)) / 25.0
            if "rejoin_position" in p: info["position"] = int(p["rejoin_position"])
            if "lap" in p: f["lap"] = max(int(f.get("lap", 0)), int(p["lap"]))
        elif observation.kind == "weather":
            f["rain_probability"] = min(1.0, max(0.0, float(p.get("rain_probability", p.get("severity", 0.0)))))
        elif observation.kind == "safety_car":
            f["safety_car"] = 1.0 if p.get("active", True) else 0.0
        elif observation.kind == "penalty":
            d = p["driver"]; drivers.setdefault(d, {})["penalty_s"] = float(drivers.get(d, {}).get("penalty_s", 0.0)) + float(p.get("seconds", 5.0))
        elif observation.kind == "reliability":
            d = p["driver"]; drivers.setdefault(d, {})["reliability"] = min(1.0, max(0.0, float(p.get("reliability", 0.5))))
        elif observation.kind == "pace":
            d = p["driver"]; drivers.setdefault(d, {})["pace"] = float(p.get("pace_delta", 0.0))
        elif observation.kind == "race_end":
            f["lap"] = int(f.get("total_laps", f.get("lap", 0))); f["completed"] = 1.0
            if p.get("winner") in drivers: f["winner"] = p["winner"]
            for d, pos in (p.get("classification") or {}).items():
                if d in drivers: drivers[d]["position"] = int(pos)
        elif observation.kind == "correction":
            f.update(p)
        f["drivers"] = drivers
        f["state_confidence"] = min(float(f.get("state_confidence", 1.0)), 0.5 + 0.5 * observation.confidence)
        s.features = f; self.validate_state(s); return s

    def build_outcome_features(self, state: WorldState, prediction_time: datetime) -> dict[str, dict[str, float]]:
        f = state.features; drivers = self._drivers(state.clone())
        lap = float(f.get("lap", 0)); total = max(1.0, float(f.get("total_laps", 57)))
        progress = min(1.0, max(0.0, lap / total)); rain = float(f.get("rain_probability", 0.0)); sc = float(f.get("safety_car", 0.0))
        adjustments = f.get("context_outcome_adjustments", {})
        latent = f.get("latent_outcomes", {})
        out: dict[str, dict[str, float]] = {}
        n = max(2, len(state.outcomes))
        for d in state.outcomes:
            info = drivers[d]; pos = float(info.get("position", n)); pace = float(info.get("pace", 0.0)); rel = float(info.get("reliability", 0.98)); wet = float(info.get("wet_skill", 0.0)); pit = float(info.get("pit_loss", 0.0)); penalty = float(info.get("penalty_s", 0.0)); tyre_age = float(info.get("tyre_age", 0.0)); ls = latent.get(d, {})
            pos_adv = 1.0 - 2.0 * (max(1.0, min(float(n), pos)) - 1.0) / max(1.0, n - 1.0)
            out[d] = {
                "position_advantage": pos_adv,
                "progress_position": progress * pos_adv,
                "pace_advantage": float(np.clip(-pace / 0.75, -1.5, 1.5)),
                "reliability_log": float(np.clip(math.log(max(rel, 1e-4)) + 0.02, -2.0, 0.1)),
                "wet_interaction": rain * float(wet),
                "pit_penalty": -float(pit),
                "tyre_penalty": -max(0.0, tyre_age - 18.0) / 30.0,
                "penalty_penalty": -penalty / 10.0,
                "context_adjustment": float(adjustments.get(d, 0.0)),
                "latent_skill": float(ls.get("skill", 0.0)),
                "latent_form": float(ls.get("form", 0.0)),
                "latent_health": float(ls.get("health", 0.0)),
                "latent_experience": float(ls.get("experience", 0.0)),
                "latent_potential": float(ls.get("potential", 0.0)),
                "safety_car_position_relief": sc * (-pos_adv),
                "driver_rating": float(info.get("rating_driver", 0.0)),
                "car_rating": float(info.get("rating_car", 0.0)),
                "rating_uncertainty": float(info.get("rating_sd", 0.5)),
                "reliability_remaining": (1.0 - progress) * math.log(max(rel, 1e-3)),
                "gap_advantage": -min(float(info.get("gap_to_leader", 0.0)), 120.0) / 20.0,
                "progress_gap": progress * -min(float(info.get("gap_to_leader", 0.0)), 120.0) / 20.0,
            }
        return out

    def build_features(self, state: WorldState, prediction_time: datetime) -> dict[str, float]:
        f = state.features; lap = float(f.get("lap", 0)); total = max(1.0, float(f.get("total_laps", 57)))
        out = {"race_progress": min(1.0, lap / total), "rain_probability": float(f.get("rain_probability", 0.0)), "safety_car": float(f.get("safety_car", 0.0)), "context_volatility": float(f.get("context_volatility", 0.0))}
        for d, feats in self.build_outcome_features(state, prediction_time).items():
            for name, value in feats.items():
                out[f"{d}:{name}"] = float(value)
        return out

    def predict_raw(self, state: WorldState, model=None) -> dict[str, float]:
        # Transparent fallback only.  The final hero path uses the learned shared
        # conditional-softmax ensemble loaded by ModelRegistry.
        outcome_features = self.build_outcome_features(state, state.prediction_cutoff)
        weights = {
            "position_advantage": 1.15, "progress_position": 2.2, "pace_advantage": 0.55,
            "reliability_log": 0.75, "wet_interaction": 0.65, "pit_penalty": 0.65,
            "tyre_penalty": 0.24, "penalty_penalty": 0.9, "context_adjustment": 0.55,
            "latent_skill": 0.45, "latent_form": 0.38, "latent_health": 0.24,
            "latent_experience": 0.16, "latent_potential": 0.12, "safety_car_position_relief": 0.18,
        }
        return {d: sum(weights[k] * feats.get(k, 0.0) for k in weights) for d, feats in outcome_features.items()}

    def simulate_transition(self, state: WorldState, rng: np.random.Generator) -> str:
        labels = list(state.outcomes); scores = self.predict_raw(state, None); probs = softmax([scores[d] for d in labels]); return str(rng.choice(labels, p=probs))

    def supported_observation_kinds(self) -> set[str]:
        return set(self.KINDS)
