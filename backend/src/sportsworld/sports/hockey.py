from __future__ import annotations

from datetime import datetime
import numpy as np
from sportsworld.core.math import sigmoid
from sportsworld.schemas import Observation, WorldState
from sportsworld.sports.base import SportAdapter
from sportsworld.ingest.features import TEAM_STATE_KEYS, is_league_state, league_features


class HockeyAdapter(SportAdapter):
    """Functional extension adapter; MHacks hero demo remains F1/football/basketball."""
    sport_name="hockey"; schema_version="hockey_features_v2_context"
    KINDS={"score_state","goal","penalty","goalie","empty_net","injury_status","game_end","correction","team_state"}
    def validate_state(self,state:WorldState)->None:
        if len(state.outcomes)!=2: raise ValueError("hockey requires two outcomes")
    def apply_observation(self,state:WorldState,observation:Observation)->WorldState:
        self._check_observation(state,observation); s=state.clone(); f={"home_score":0,"away_score":0,"seconds_remaining":3600,"home_strength":0.0,"away_strength":0.0,"home_goalie":0.0,"away_goalie":0.0,"manpower":0.0,"home_field":1.0,"state_confidence":0.95,**s.features}; p=observation.payload
        if observation.kind=="score_state":
            for k in ("home_score","away_score","seconds_remaining","manpower"):
                if k in p: f[k]=p[k]
        elif observation.kind=="goal": f[f"{p.get('team','home')}_score"]+=1
        elif observation.kind=="penalty": f["manpower"]=float(p.get("manpower",0.0))
        elif observation.kind=="goalie": f[f"{p.get('team','home')}_goalie"]=float(p.get("rating",0.0))
        elif observation.kind=="game_end": f["seconds_remaining"]=0; f["completed"]=1.0
        elif observation.kind=="team_state": f.update({k:v for k,v in p.items() if k in TEAM_STATE_KEYS})
        elif observation.kind=="correction": f.update(p)
        f["state_confidence"]=min(float(f.get("state_confidence",1)),0.5+0.5*observation.confidence); s.features=f; return s
    def build_features(self,state:WorldState,prediction_time:datetime)->dict[str,float]:
        f=state.features; diff=float(f.get("home_score",0))-float(f.get("away_score",0)); elapsed=1-min(1,max(0,float(f.get("seconds_remaining",3600)))/3600); return {"strength_diff":float(f.get("home_strength",0))-float(f.get("away_strength",0)),"historical_strength_diff":float(f.get("historical_strength_diff",0)),"recent_form_diff":float(f.get("recent_form_diff",0)),"health_diff":float(f.get("health_diff",0)),"matchup_advantage":float(f.get("matchup_advantage",0)),"context_mean_shift":float(f.get("context_mean_shift",0)),"environment_context_diff":float(f.get("environment_context_diff",0)),"home_field":float(f.get("home_field",1.0)),"score_time":diff*(0.4+1.4*elapsed),"goalie_diff":float(f.get("home_goalie",0))-float(f.get("away_goalie",0)),"manpower":float(f.get("manpower",0)),**(league_features(f) if is_league_state(f) else {})}
    def predict_raw(self,state:WorldState,model=None)->dict[str,float]:
        x=self.build_features(state,state.prediction_cutoff); z=.45*x["strength_diff"]+.32*x["historical_strength_diff"]+.28*x["recent_form_diff"]+.20*x["health_diff"]+.30*x["matchup_advantage"]+.18*x["context_mean_shift"]+.08*x["environment_context_diff"]+.12*x["home_field"]+.75*x["score_time"]+.4*x["goalie_diff"]+.25*x["manpower"]; return {state.outcomes[0]:z/2,state.outcomes[1]:-z/2}
    def simulate_transition(self,state:WorldState,rng:np.random.Generator)->str:
        s=self.predict_raw(state,None); p=float(sigmoid(s[state.outcomes[0]]-s[state.outcomes[1]])); return state.outcomes[0] if rng.random()<p else state.outcomes[1]
    def supported_observation_kinds(self)->set[str]: return set(self.KINDS)
