from __future__ import annotations

from sportsworld.schemas import Forecast,WorldState


def deterministic_explanation(state:WorldState,forecast:Forecast)->str:
    leader=max(forecast.probabilities,key=forecast.probabilities.get); p=forecast.probabilities[leader]*100
    driver='; '.join(f'{d.label} ({d.probability_delta*100:+.1f} pp)' for d in forecast.drivers[:3]) or 'no recent material observation'
    return f'{leader} leads the current model distribution at {p:.1f}%. Recent forecast revisions: {driver}. This is a model forecast, not a causal claim.'
