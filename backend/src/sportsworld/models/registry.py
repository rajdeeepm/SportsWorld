from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sportsworld.config import Settings
from sportsworld.core.calibration import IdentityCalibrator, TemperatureScaler
from sportsworld.core.math import softmax
from sportsworld.models.linear import BootstrapBinaryEnsemble, BootstrapConditionalSoftmaxEnsemble
from sportsworld.schemas import ModelCard, Sport, WorldState


@dataclass(slots=True)
class PredictionBundle:
    probabilities: dict[str, float]
    intervals_90: dict[str, tuple[float, float]]
    epistemic: float | None
    model_version: str
    calibration_version: str
    raw_scores: dict[str, float] | None = None
    method: str = "adapter_baseline"


class ModelRegistry:
    """Versioned learned-model registry for all hero sports.

    Football and basketball use contextual bootstrap binary logistic ensembles.
    F1 uses a shared conditional-softmax ensemble that scores each driver with
    the same learned feature function, allowing a variable outcome set.  Every
    learned path carries a separately fit chronological temperature calibrator.
    """

    def __init__(self, settings: Settings, adapters: dict[Sport, Any]):
        self.settings=settings; self.adapters=adapters; self._models={}; self._cards={}; self._calibrators={}; self.reload()

    def reload(self) -> None:
        repo=Path(__file__).resolve().parents[4]
        root=Path(self.settings.model_dir); root=(repo/'models'/'artifacts') if not root.is_absolute() else root
        manifests=Path(self.settings.manifest_dir); manifests=(repo/'models'/'manifests') if not manifests.is_absolute() else manifests
        self._models.clear(); self._cards.clear(); self._calibrators.clear()
        if not manifests.exists(): return
        for manifest in manifests.glob('*.json'):
            try: card=ModelCard.model_validate_json(manifest.read_text())
            except Exception: continue
            art=root/Path(card.artifact_uri).name
            if not art.exists(): continue
            try: payload=json.loads(art.read_text())
            except Exception: continue
            try:
                if card.algorithm=='kalman_analytic': model='kalman_analytic'
                elif card.algorithm=='bootstrap_logistic': model=BootstrapBinaryEnsemble.from_dict(payload['model'])
                elif card.algorithm=='bootstrap_conditional_softmax': model=BootstrapConditionalSoftmaxEnsemble.from_dict(payload['model'])
                else: continue
                key=f'league:{card.competition}' if card.competition else card.sport
                self._models[key]=model; self._cards[key]=card
                self._calibrators[key]=TemperatureScaler.from_dict(payload.get('calibrator',{'temperature':1.0,'version':card.calibration_version}))
            except Exception:
                continue

    def card(self,sport:Sport)->ModelCard|None:return self._cards.get(sport)

    def league_card(self,league:str)->ModelCard|None:return self._cards.get(f'league:{league}')

    def leagues(self)->list[str]:return sorted(k.removeprefix('league:') for k in self._cards if isinstance(k,str) and k.startswith('league:'))

    def predict_league_features(self,league:str,rows:list[dict[str,float]])->list[tuple[float,float,float]]:
        """Calibrated P(home) with 90% ensemble interval for many feature rows (all-event forecast board)."""
        key=f'league:{league}';model=self._models.get(key);cal=self._calibrators.get(key,IdentityCalibrator())
        if model=='kalman_analytic':
            from math import erf,sqrt
            out=[]
            for f in rows:
                p=min(1-1e-4,max(1e-4,0.5*(1+erf(float(f.get('live_margin_z',0.0))*3.0/sqrt(2)))));w=min(0.25,0.15*float(f.get('rating_uncertainty',0.0))*p*(1-p)*4)
                out.append((p,max(0.0,p-w),min(1.0,p+w)))
            return out
        if not isinstance(model,BootstrapBinaryEnsemble): return []
        out=[]
        for f in rows:
            mh=model.member_probabilities(f);cm=np.asarray([cal.transform_probabilities({'home':x,'away':1-x})['home'] for x in mh])
            out.append((float(cm.mean()),float(np.quantile(cm,.05)),float(np.quantile(cm,.95))))
        return out

    def _key(self,state:WorldState):
        # League-specific models live in their own namespace so a league id can
        # never shadow a sport-level model (e.g. league "f1" vs Sport.F1).
        key=f'league:{state.competition}'
        return key if key in self._models else state.sport

    @staticmethod
    def _calibrate_members(labels:list[str], matrix:np.ndarray, calibrator:Any)->tuple[dict[str,float],dict[str,tuple[float,float]],float]:
        calibrated=[]
        for row in matrix:
            d=calibrator.transform_probabilities(dict(zip(labels,row.tolist())))
            calibrated.append([d[k] for k in labels])
        arr=np.asarray(calibrated,dtype=float); mean=np.mean(arr,axis=0);lo=np.quantile(arr,.05,axis=0);hi=np.quantile(arr,.95,axis=0)
        return dict(zip(labels,mean.tolist())),{k:(float(max(0,lo[i])),float(min(1,hi[i]))) for i,k in enumerate(labels)},float(np.mean(np.std(arr,axis=0)))

    def _terminal(self,state:WorldState)->PredictionBundle|None:
        """A decided two-sided game is not a forecast any more: report the realized outcome."""
        f=state.features
        if float(f.get('completed',0.0))<1.0: return None
        if len(state.outcomes)>2:
            w=f.get('winner')
            if w not in state.outcomes: return None
            probs={k:(1.0 if k==w else 0.0) for k in state.outcomes};card=self._cards.get(self._key(state))
            return PredictionBundle(probabilities=probs,intervals_90={k:(v,v) for k,v in probs.items()},epistemic=0.0,model_version=card.model_version if card else 'terminal',calibration_version='terminal',method='terminal_outcome')
        if len(state.outcomes)!=2: return None
        hs,as_=float(f.get('home_score',0)),float(f.get('away_score',0))
        if hs==as_: return None
        winner=state.outcomes[0] if hs>as_ else state.outcomes[1]
        probs={k:(1.0 if k==winner else 0.0) for k in state.outcomes}
        card=self._cards.get(self._key(state))
        return PredictionBundle(probabilities=probs,intervals_90={k:(v,v) for k,v in probs.items()},epistemic=0.0,model_version=card.model_version if card else 'terminal',calibration_version='terminal',method='terminal_outcome')

    def predict(self,state:WorldState)->PredictionBundle:
        terminal=self._terminal(state)
        if terminal: return terminal
        sport=state.sport;adapter=self.adapters[sport];key=self._key(state);model=self._models.get(key);card=self._cards.get(key);cal=self._calibrators.get(key,IdentityCalibrator())
        if model=='kalman_analytic' and len(state.outcomes)==2:
            from math import erf,sqrt
            x=adapter.build_features(state,state.prediction_cutoff);z=float(x.get('live_margin_z',0.0))*3.0
            p=min(1-1e-4,max(1e-4,0.5*(1+erf(z/sqrt(2)))));sd=float(x.get('rating_uncertainty',0.0))
            probs=dict(zip(state.outcomes,[p,1-p]));w=min(0.25,0.15*sd*p*(1-p)*4)
            return PredictionBundle(probabilities=probs,intervals_90={state.outcomes[0]:(max(0,p-w),min(1,p+w)),state.outcomes[1]:(max(0,1-p-w),min(1,1-p+w))},epistemic=w/1.645,model_version=card.model_version,calibration_version='analytic',method='kalman_analytic')
        if isinstance(model,BootstrapBinaryEnsemble) and len(state.outcomes)==2:
            features=adapter.build_features(state,state.prediction_cutoff); labels=list(state.outcomes)
            # Ensemble labels are semantic home/away by default; remap to event labels by order.
            member_home=model.member_probabilities(features); matrix=np.column_stack([member_home,1-member_home])
            probs,intervals,epi=self._calibrate_members(labels,matrix,cal)
            return PredictionBundle(probabilities=probs,intervals_90=intervals,epistemic=epi,model_version=card.model_version,calibration_version=getattr(cal,'version','identity-v1'),method='bootstrap_logistic')
        if isinstance(model,BootstrapConditionalSoftmaxEnsemble) and sport==Sport.F1:
            outcome_features=adapter.build_outcome_features(state,state.prediction_cutoff); labels,matrix=model.member_probabilities(outcome_features)
            probs,intervals,epi=self._calibrate_members(labels,matrix,cal)
            return PredictionBundle(probabilities=probs,intervals_90=intervals,epistemic=epi,model_version=card.model_version,calibration_version=getattr(cal,'version','identity-v1'),method='bootstrap_conditional_softmax')

        scores=adapter.predict_raw(state,None);labels=list(state.outcomes);raw=[float(scores.get(k,0.0)) for k in labels];p=softmax(raw);probs=dict(zip(labels,p.tolist()));state_conf=float(state.features.get('state_confidence',.9));width=.03+(1-state_conf)*.12;intervals={k:(max(0,v-width),min(1,v+width)) for k,v in probs.items()}
        return PredictionBundle(probabilities=probs,intervals_90=intervals,epistemic=None,model_version=f'{sport.value}_adapter_baseline_v1',calibration_version='identity-v1',raw_scores=dict(zip(labels,raw)),method='adapter_baseline')
