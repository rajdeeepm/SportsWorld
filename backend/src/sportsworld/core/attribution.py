from __future__ import annotations

from sportsworld.schemas import DriverMethod, ForecastDriver, Observation


def transition_driver(before: dict[str,float], after: dict[str,float], obs: Observation) -> ForecastDriver:
    target=max(after,key=after.get)
    return ForecastDriver(
        label=human_label(obs), target_outcome=target,
        probability_delta=float(after.get(target,0)-before.get(target,0)),
        method=DriverMethod.REPLAY_DELTA, source_id=obs.source_id,
        observation_id=obs.observation_id, timestamp=obs.known_to_model_time,
        explanation="Change in the model forecast after this observation was incorporated; not a causal effect."
    )


def human_label(obs: Observation) -> str:
    p=obs.payload
    if obs.kind in {"injury_status","availability"}: return f"{p.get('team','')} {p.get('role',p.get('participant_id','participant'))} {p.get('status','update')}".strip()
    if obs.kind=="weather": return f"Weather update: severity {p.get('severity',p.get('rain_probability','changed'))}"
    if obs.kind=="pit_stop": return f"{p.get('driver','Driver')} pit stop on lap {p.get('lap','?')}"
    if obs.kind=="turnover": return "Possession turnover"
    if obs.kind=="score": return f"{p.get('team','Team')} scored {p.get('points','')}"
    if obs.kind in {"lineup","substitution"}: return f"{p.get('team','Team')} lineup update"
    return obs.kind.replace('_',' ').title()
