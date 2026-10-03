from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from sportsworld.schemas import WorldState
from sportsworld.simulators.base import SequentialSimulationResult


@dataclass(slots=True)
class BasketballSequentialSimulator:
    adapter: object
    transition_kind: str = "possession_by_possession"

    def _advantage(self,state:WorldState)->float:
        x=self.adapter.build_features(state,state.prediction_cutoff)
        return float(.34*x.get("strength_diff",0)+.26*x.get("historical_strength_diff",0)+.24*x.get("recent_form_diff",0)+.18*x.get("health_diff",0)+.25*x.get("matchup_advantage",0)+.16*x.get("context_mean_shift",0)+.25*x.get("lineup_diff",0)+.46*x.get("star_availability_diff",0)+.10*x.get("home_field",1))

    @staticmethod
    def _point_probs(adv:np.ndarray|float,foul_pressure:np.ndarray|float=0.0):
        edge=np.tanh(adv)
        p3=np.clip(.105+.025*edge,.06,.17)
        p2=np.clip(.315+.050*edge,.21,.42)
        p1=np.clip(.055+.030*np.asarray(foul_pressure),.03,.13)
        p0=np.maximum(.20,1.0-p3-p2-p1)
        total=p0+p1+p2+p3
        return p0/total,p1/total,p2/total,p3/total

    def _one_path(self,state:WorldState,rng:np.random.Generator)->tuple[str,int,list[dict]]:
        f=state.features; hs=int(f.get("home_score",0)); aas=int(f.get("away_score",0)); sec=float(f.get("seconds_remaining",2880)); poss=str(f.get("possession","home")); pace=float(f.get("pace",100)); base=self._advantage(state); path=[]; steps=0
        sec_per=max(8.0,2880.0/max(80.0,2.0*pace))
        while sec>0 and steps<260:
            steps+=1; side=1 if poss=="home" else -1; adv=base*side
            trailing=(hs<aas) if side==1 else (aas<hs); foul_pressure=1.0 if sec<90 and trailing else 0.0
            p0,p1,p2,p3=self._point_probs(adv,foul_pressure); u=rng.random(); pts=0 if u<p0 else 1 if u<p0+p1 else 2 if u<p0+p1+p2 else 3
            if side==1: hs+=pts
            else: aas+=pts
            duration=float(np.clip(rng.normal(sec_per,3.5),4.0,30.0)); sec=max(0.0,sec-duration)
            if len(path)<8 or sec<150: path.append({"possession":steps,"seconds_remaining":round(sec,1),"team":poss,"points":pts,"home_score":hs,"away_score":aas})
            poss="away" if poss=="home" else "home"
        ot=0
        while hs==aas and ot<4:
            ot+=1
            for _ in range(max(12,int(round(pace*5/48))*2)):
                side=1 if poss=="home" else -1; p0,p1,p2,p3=self._point_probs(base*side,0);u=rng.random();pts=0 if u<p0 else 1 if u<p0+p1 else 2 if u<p0+p1+p2 else 3
                if side==1:hs+=pts
                else:aas+=pts
                poss="away" if poss=="home" else "home";steps+=1
            path.append({"period":f"OT{ot}","home_score":hs,"away_score":aas})
        winner=state.outcomes[0] if hs>=aas else state.outcomes[1]
        return winner,steps,path[-18:]

    def simulate(self,state:WorldState,draws:int,seed:int,*,capture_paths:int=3)->SequentialSimulationResult:
        rng=np.random.default_rng(seed); f=state.features; labels=list(state.outcomes)
        hs=np.full(draws,int(f.get("home_score",0)),dtype=np.int16); aas=np.full(draws,int(f.get("away_score",0)),dtype=np.int16)
        pace=float(f.get("pace",100)); sec=float(f.get("seconds_remaining",2880)); base=self._advantage(state); poss=1 if str(f.get("possession","home"))=="home" else -1
        sec_per=max(8.0,2880.0/max(80.0,2.0*pace)); remaining=max(0,int(math.ceil(sec/sec_per))); steps=np.full(draws,remaining,dtype=np.int16)
        # Use a fixed possession count for vectorized speed; stochastic possession
        # duration is represented by a small count jitter per draw.
        jitter=rng.integers(-2,3,size=draws); target=np.maximum(0,remaining+jitter)
        for j in range(max(0,int(np.max(target)))):
            active=target>j
            if not np.any(active):break
            side=poss if j%2==0 else -poss; idx=np.flatnonzero(active); n=len(idx)
            adv=np.full(n,base*side,dtype=float)
            # Approximate end-game intentional fouling for trailing offense.
            frac=(j+1)/max(1,remaining); trailing=(hs[idx]<aas[idx]) if side==1 else (aas[idx]<hs[idx]); fp=(trailing & (frac>.94)).astype(float)
            p0,p1,p2,p3=self._point_probs(adv,fp); u=rng.random(n); pts=np.where(u<p0,0,np.where(u<p0+p1,1,np.where(u<p0+p1+p2,2,3))).astype(np.int16)
            if side==1: hs[idx]+=pts
            else: aas[idx]+=pts
        tied=hs==aas; ot=0
        ot_pos=max(12,int(round(pace*5/48))*2)
        while np.any(tied) and ot<5:
            ot+=1; idx=np.flatnonzero(tied)
            for j in range(ot_pos):
                side=1 if j%2==0 else -1; p0,p1,p2,p3=self._point_probs(base*side,0);u=rng.random(len(idx));pts=np.where(u<p0,0,np.where(u<p0+p1,1,np.where(u<p0+p1+p2,2,3))).astype(np.int16)
                if side==1:hs[idx]+=pts
                else:aas[idx]+=pts
            steps[idx]+=ot_pos;tied=hs==aas
        idx=np.flatnonzero(hs==aas)
        if len(idx):
            p=1/(1+math.exp(-base));home=rng.random(len(idx))<p;hs[idx[home]]+=1;aas[idx[~home]]+=1
        outcomes=np.where(hs>=aas,labels[0],labels[1]).tolist();paths=[]
        for i in range(min(capture_paths,draws)):
            _,_,p=self._one_path(state,np.random.default_rng(seed+20_000+i));paths.append(p)
        return SequentialSimulationResult.from_outcomes(outcomes,labels,draws,steps=steps,transition_kind=self.transition_kind,representative_paths=paths,diagnostics={"mean_final_home_score":float(np.mean(hs)),"mean_final_away_score":float(np.mean(aas)),"mean_remaining_possessions":float(np.mean(target))})
