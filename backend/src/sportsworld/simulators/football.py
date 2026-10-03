from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from sportsworld.schemas import WorldState
from sportsworld.simulators.base import SequentialSimulationResult


def _clip(x, lo, hi):
    return np.minimum(hi, np.maximum(lo, x))


@dataclass(slots=True)
class FootballSequentialSimulator:
    adapter: object
    transition_kind: str = "drive_by_drive"

    def _base_advantage(self, state: WorldState) -> float:
        x = self.adapter.build_features(state, state.prediction_cutoff)
        return float(
            0.36*x.get("strength_diff",0) + 0.30*x.get("historical_strength_diff",0)
            + 0.25*x.get("recent_form_diff",0) + 0.22*x.get("health_diff",0)
            + 0.26*x.get("matchup_advantage",0) + 0.18*x.get("context_mean_shift",0)
            + 0.55*(x.get("home_qb_available",1)-x.get("away_qb_available",1))
            + 0.12*x.get("home_field",1)
        )

    def _simulate_one_path(self, state: WorldState, rng: np.random.Generator) -> tuple[str, int, list[dict]]:
        f = state.features
        hs, aas = int(f.get("home_score",0)), int(f.get("away_score",0))
        seconds = float(f.get("seconds_remaining",3600)); poss = str(f.get("possession","home"))
        weather = float(f.get("weather_severity",0)); base = self._base_advantage(state)
        path=[]; steps=0
        while seconds > 0 and steps < 40:
            steps += 1
            adv = base if poss == "home" else -base
            urgency = 1.0 if seconds > 360 else 0.75
            td = float(np.clip(0.205 + 0.090*np.tanh(adv) - 0.035*weather, 0.06, 0.42))
            fg = float(np.clip(0.145 + 0.030*np.tanh(adv) - 0.015*weather, 0.06, 0.23))
            turnover = float(np.clip(0.105 - 0.025*np.tanh(adv) + 0.025*weather, 0.05, 0.19))
            no_score = max(0.01, 1.0-td-fg-turnover)
            probs=np.asarray([td,fg,turnover,no_score],dtype=float); probs/=probs.sum()
            outcome=str(rng.choice(["TD","FG","TURNOVER","PUNT"],p=probs))
            # Drives become faster late in the game, especially for trailing teams.
            trailing = (hs<aas) if poss=="home" else (aas<hs)
            mean_duration = 155.0 * urgency * (0.78 if trailing and seconds<600 else 1.0)
            duration=float(np.clip(rng.gamma(shape=3.0,scale=max(12.0,mean_duration/3.0)),18.0,min(320.0,seconds)))
            seconds=max(0.0,seconds-duration)
            points=7 if outcome=="TD" else 3 if outcome=="FG" else 0
            if poss=="home": hs+=points
            else: aas+=points
            path.append({"step":steps,"seconds_remaining":round(seconds,1),"possession":poss,"drive_outcome":outcome,"home_score":hs,"away_score":aas})
            poss="away" if poss=="home" else "home"

        # Simple untimed overtime if regulation is tied.  Each side receives a
        # possession; repeat until the scores differ.
        ot=0
        while hs==aas and ot<6:
            ot+=1
            for team in ("home","away"):
                adv = base if team=="home" else -base
                p_td=float(np.clip(.22+.08*np.tanh(adv),.08,.42)); p_fg=.16
                r=rng.random(); pts=7 if r<p_td else 3 if r<p_td+p_fg else 0
                if team=="home": hs+=pts
                else: aas+=pts
                path.append({"step":steps+ot,"period":"OT","possession":team,"points":pts,"home_score":hs,"away_score":aas})
            if hs!=aas: break
        winner=state.outcomes[0] if hs>=aas else state.outcomes[1]
        return winner,steps+ot,path

    def simulate(self, state: WorldState, draws: int, seed: int, *, capture_paths: int = 3) -> SequentialSimulationResult:
        rng=np.random.default_rng(seed)
        f=state.features
        hs=np.full(draws,int(f.get("home_score",0)),dtype=np.int16)
        aas=np.full(draws,int(f.get("away_score",0)),dtype=np.int16)
        sec=np.full(draws,float(f.get("seconds_remaining",3600)),dtype=float)
        poss=np.full(draws,1 if str(f.get("possession","home"))=="home" else -1,dtype=np.int8)
        steps=np.zeros(draws,dtype=np.int16)
        base=self._base_advantage(state); weather=float(f.get("weather_severity",0))
        active=sec>0
        while np.any(active) and int(np.max(steps))<40:
            idx=np.flatnonzero(active); n=len(idx); side=poss[idx]
            adv=base*side
            td=_clip(.205+.090*np.tanh(adv)-.035*weather,.06,.42)
            fg=_clip(.145+.030*np.tanh(adv)-.015*weather,.06,.23)
            turnover=_clip(.105-.025*np.tanh(adv)+.025*weather,.05,.19)
            u=rng.random(n)
            pts=np.where(u<td,7,np.where(u<td+fg,3,0)).astype(np.int16)
            home_mask=side==1
            hs[idx[home_mask]]+=pts[home_mask]; aas[idx[~home_mask]]+=pts[~home_mask]
            trailing=np.where(side==1,hs[idx]<aas[idx],aas[idx]<hs[idx])
            urgency=np.where(sec[idx]>360,1.0,.75)
            mean=155.0*urgency*np.where(trailing & (sec[idx]<600),.78,1.0)
            duration=np.clip(rng.gamma(3.0,np.maximum(12.0,mean/3.0)),18.0,np.minimum(320.0,sec[idx]))
            sec[idx]=np.maximum(0.0,sec[idx]-duration); poss[idx]*=-1; steps[idx]+=1
            active=sec>0

        # Overtime vectorized in paired possessions.
        tied=hs==aas; rounds=0
        while np.any(tied) and rounds<8:
            rounds+=1; idx=np.flatnonzero(tied)
            for side in (1,-1):
                adv=base*side; ptd=float(np.clip(.22+.08*np.tanh(adv),.08,.42)); pfg=.16
                u=rng.random(len(idx)); pts=np.where(u<ptd,7,np.where(u<ptd+pfg,3,0)).astype(np.int16)
                if side==1: hs[idx]+=pts
                else: aas[idx]+=pts
            steps[idx]+=1; tied=hs==aas
        # Resolve extremely rare persistent tie with a coin weighted by base edge.
        idx=np.flatnonzero(hs==aas)
        if len(idx):
            p_home=1/(1+math.exp(-base)); home=rng.random(len(idx))<p_home; hs[idx[home]]+=1; aas[idx[~home]]+=1

        labels=list(state.outcomes); outcome_arr=np.where(hs>=aas,labels[0],labels[1]); outcomes=outcome_arr.tolist()
        paths=[]
        for i in range(min(capture_paths,draws)):
            w,_,path=self._simulate_one_path(state,np.random.default_rng(seed+10_000+i)); paths.append(path)
        return SequentialSimulationResult.from_outcomes(outcomes,labels,draws,steps=steps,transition_kind=self.transition_kind,representative_paths=paths,diagnostics={"mean_final_home_score":float(np.mean(hs)),"mean_final_away_score":float(np.mean(aas)),"overtime_rate":float(np.mean(steps>np.median(steps)+4))})
