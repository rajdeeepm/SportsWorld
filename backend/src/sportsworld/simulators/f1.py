from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from sportsworld.schemas import WorldState
from sportsworld.simulators.base import SequentialSimulationResult


COMPOUND_PACE={"SOFT":-0.16,"MEDIUM":0.0,"HARD":0.10,"INTERMEDIATE":0.20,"WET":0.34}
COMPOUND_DEG={"SOFT":0.030,"MEDIUM":0.018,"HARD":0.010,"INTERMEDIATE":0.016,"WET":0.013}


@dataclass(slots=True)
class F1SequentialSimulator:
    adapter: object
    transition_kind: str = "lap_by_lap"

    def _one_path(self,state:WorldState,rng:np.random.Generator)->tuple[str,int,list[dict]]:
        f=state.features; drivers=self.adapter._drivers(state.clone()); labels=list(state.outcomes); lap=int(f.get("lap",0));total=int(f.get("total_laps",57));rain_p=float(f.get("rain_probability",0));vol=float(f.get("context_volatility",0));path=[]
        time={d:max(0,float(drivers[d].get("position",1))-1)*1.25 for d in labels};active={d:True for d in labels};tyre={d:float(drivers[d].get("tyre_age",0)) for d in labels};comp={d:str(drivers[d].get("compound","MEDIUM")).upper() for d in labels}
        for L in range(lap+1,total+1):
            rain=bool(rng.random()<rain_p); safety=bool(rng.random() < (.012+.010*vol))
            if safety:
                lead=min(time[d] for d in labels if active[d]);
                for d in labels:
                    if active[d]:time[d]=lead+(time[d]-lead)*.28
            events=[]
            for d in labels:
                if not active[d]:continue
                info=drivers[d];rel=float(info.get("reliability",.98));hazard=.00015+max(0,1-rel)*.025
                if rng.random()<hazard:
                    active[d]=False;time[d]=1e9;events.append(f"{d} DNF");continue
                tyre[d]+=1; c=comp[d]; base=float(info.get("pace",0)); deg=COMPOUND_DEG.get(c,.018)*max(0,tyre[d]-10); wet=float(info.get("wet_skill",0)); weather=( -.32*wet if rain else 0.0 ) + (.65 if rain and c not in {"INTERMEDIATE","WET"} else 0.0) + (.22 if (not rain and c in {"INTERMEDIATE","WET"}) else 0.0)
                noise=float(rng.normal(0,.20 if not safety else .08));time[d]+=90.0+base+COMPOUND_PACE.get(c,0)+deg+weather+noise
                # Strategy is intentionally simple but stateful: old dry tyres or
                # a rain-regime mismatch can trigger a pit and compound switch.
                need_dry=tyre[d]>(25 if c=="HARD" else 20 if c=="MEDIUM" else 14)
                mismatch=(rain and c not in {"INTERMEDIATE","WET"}) or ((not rain) and c in {"INTERMEDIATE","WET"})
                if L<total-3 and (mismatch or (need_dry and rng.random()<.32)):
                    time[d]+=22.0+float(rng.normal(0,.7));tyre[d]=0;comp[d]="INTERMEDIATE" if rain else ("HARD" if total-L>18 else "MEDIUM");events.append(f"{d} pit->{comp[d]}")
            if len(path)<4 or L>total-4 or events:path.append({"lap":L,"rain":rain,"safety_car":safety,"events":events,"order":[d for d in sorted(labels,key=lambda x:time[x]) if active[d]]})
        penalties={d:float(drivers[d].get("penalty_s",0)) for d in labels}
        for d in labels:time[d]+=penalties[d]
        alive=[d for d in labels if active[d]];winner=min(alive,key=lambda d:time[d]) if alive else labels[0]
        return winner,max(0,total-lap),path[-14:]

    def simulate(self,state:WorldState,draws:int,seed:int,*,capture_paths:int=3)->SequentialSimulationResult:
        rng=np.random.default_rng(seed);f=state.features;drivers=self.adapter._drivers(state.clone());labels=list(state.outcomes);k=len(labels);lap=int(f.get("lap",0));total=int(f.get("total_laps",57));remaining=max(0,total-lap);rain_p=float(f.get("rain_probability",0));vol=float(f.get("context_volatility",0))
        pos=np.asarray([float(drivers[d].get("position",i+1)) for i,d in enumerate(labels)]);times=np.tile((pos-1)*1.25,(draws,1)).astype(float);active=np.ones((draws,k),dtype=bool);tyre=np.tile(np.asarray([float(drivers[d].get("tyre_age",0)) for d in labels]),(draws,1));comp=np.tile(np.asarray([str(drivers[d].get("compound","MEDIUM")).upper() for d in labels],dtype=object),(draws,1));pace=np.asarray([float(drivers[d].get("pace",0)) for d in labels]);rel=np.asarray([float(drivers[d].get("reliability",.98)) for d in labels]);wet=np.asarray([float(drivers[d].get("wet_skill",0)) for d in labels]);pitted=np.zeros((draws,k),dtype=int);dnf=np.zeros((draws,k),dtype=bool);safety_count=np.zeros(draws,dtype=int)
        for step in range(remaining):
            rain=rng.random(draws)<rain_p;safety=rng.random(draws)<(.012+.010*vol);safety_count+=safety.astype(int)
            if np.any(safety):
                idx=np.flatnonzero(safety);masked=np.where(active[idx],times[idx],np.inf);lead=np.min(masked,axis=1)
                times[idx]=np.where(active[idx],lead[:,None]+(times[idx]-lead[:,None])*.28,times[idx])
            for j,d in enumerate(labels):
                act=active[:,j];hazard=.00015+max(0,1-rel[j])*.025;fail=act&(rng.random(draws)<hazard);active[fail,j]=False;dnf[fail,j]=True;times[fail,j]=1e9;act=active[:,j]
                tyre[act,j]+=1
                # Object-array compound masks are cheap at this small driver count.
                cp=comp[:,j];base_comp=np.vectorize(lambda x:COMPOUND_PACE.get(str(x),0.0))(cp).astype(float);deg_rate=np.vectorize(lambda x:COMPOUND_DEG.get(str(x),.018))(cp).astype(float);deg=deg_rate*np.maximum(0,tyre[:,j]-10)
                wet_ok=np.isin(cp,["INTERMEDIATE","WET"]);weather=(-.32*wet[j]*rain.astype(float)) + (.65*(rain & ~wet_ok)) + (.22*((~rain)&wet_ok));noise=rng.normal(0,.20,size=draws);noise[safety]=rng.normal(0,.08,size=int(np.sum(safety)))
                times[act,j]+=90.0+pace[j]+base_comp[act]+deg[act]+weather[act]+noise[act]
                laps_left=remaining-step-1;need=tyre[:,j]>np.where(cp=="HARD",25,np.where(cp=="MEDIUM",20,14));mismatch=(rain&~wet_ok)|((~rain)&wet_ok);pit=act&(laps_left>3)&(mismatch|(need&(rng.random(draws)<.32)))
                times[pit,j]+=22.0+rng.normal(0,.7,size=int(np.sum(pit)));tyre[pit,j]=0;pitted[pit,j]+=1
                # Assign compounds draw-by-draw based on current regime.
                comp[pit & rain,j]="INTERMEDIATE";comp[pit & (~rain) & (laps_left>18),j]="HARD";comp[pit & (~rain) & (laps_left<=18),j]="MEDIUM"
        penalties=np.asarray([float(drivers[d].get("penalty_s",0)) for d in labels]);times+=penalties[None,:]
        winner_idx=np.argmin(times,axis=1);outcomes=[labels[i] for i in winner_idx.tolist()];steps=np.full(draws,remaining,dtype=np.int16);paths=[]
        for i in range(min(capture_paths,draws)):
            _,_,p=self._one_path(state,np.random.default_rng(seed+30_000+i));paths.append(p)
        dnf_rate={d:float(np.mean(dnf[:,j])) for j,d in enumerate(labels)};pit_mean={d:float(np.mean(pitted[:,j])) for j,d in enumerate(labels)}
        return SequentialSimulationResult.from_outcomes(outcomes,labels,draws,steps=steps,transition_kind=self.transition_kind,representative_paths=paths,diagnostics={"dnf_rate":dnf_rate,"mean_pit_stops":pit_mean,"safety_car_rate":float(np.mean(safety_count>0)),"remaining_laps":remaining})
