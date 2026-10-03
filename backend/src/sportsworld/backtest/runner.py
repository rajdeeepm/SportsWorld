from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Any

import numpy as np

from sportsworld.backtest.leakage import audit_rows, assert_point_in_time
from sportsworld.backtest.metrics import accuracy, binary_reliability, log_loss, multiclass_brier, top_label_ece
from sportsworld.backtest.splitter import ChronologicalSplit
from sportsworld.core.calibration import TemperatureScaler
from sportsworld.models.linear import BootstrapBinaryEnsemble, BootstrapConditionalSoftmaxEnsemble
from sportsworld.schemas import BacktestRun, Sport


FOOTBALL_FEATURES=["strength_diff","historical_strength_diff","recent_form_diff","health_diff","usage_stability_diff","experience_diff","potential_diff","chemistry_diff","matchup_advantage","context_mean_shift","human_context_diff","environment_context_diff","context_volatility","score_diff_scaled","time_elapsed","score_time_interaction","possession_home","field_position_home","home_qb_available","away_qb_available","weather_severity","home_field"]
BASKETBALL_FEATURES=["strength_diff","historical_strength_diff","recent_form_diff","health_diff","experience_diff","chemistry_diff","matchup_advantage","context_mean_shift","human_context_diff","environment_context_diff","context_volatility","score_diff_scaled","score_time_interaction","possession_home","lineup_diff","star_availability_diff","pace_scaled","home_field"]
F1_OUTCOME_FEATURES=["position_advantage","progress_position","pace_advantage","reliability_log","wet_interaction","pit_penalty","tyre_penalty","penalty_penalty","context_adjustment","latent_skill","latent_form","latent_health","latent_experience","latent_potential","safety_car_position_relief"]
# Backward compatibility for callers/tests from v1.1.
FEATURES=FOOTBALL_FEATURES


def _digest(rows:list[dict])->str:
    return hashlib.sha256('\n'.join(json.dumps(r,sort_keys=True,default=str) for r in rows).encode()).hexdigest()[:16]


def psi(train:np.ndarray,test:np.ndarray,bins:int=8)->float:
    train=np.asarray(train,dtype=float);test=np.asarray(test,dtype=float)
    if len(train)<3 or len(test)<3:return 0.0
    qs=np.unique(np.quantile(train,np.linspace(0,1,bins+1)))
    if len(qs)<3:return 0.0
    qs[0]=-np.inf;qs[-1]=np.inf
    tr=np.histogram(train,bins=qs)[0]/len(train);te=np.histogram(test,bins=qs)[0]/len(test)
    tr=np.clip(tr,1e-6,None);te=np.clip(te,1e-6,None)
    return float(np.sum((te-tr)*np.log(te/tr)))


def _binary_xy(rows:list[dict],features:list[str]):
    X=np.asarray([[float(r['features'].get(k,0.0)) for k in features] for r in rows],dtype=float)
    y=np.asarray([int(r['target_home_win']) for r in rows],dtype=int)
    return X,y


def rows_to_xy(rows:list[dict], features:list[str]=FOOTBALL_FEATURES):
    return _binary_xy(rows,features)


def probs_from_ensemble(model:BootstrapBinaryEnsemble,rows:list[dict])->np.ndarray:
    p=np.asarray([model.predict(r['features'])[0]['home'] for r in rows],dtype=float)
    return np.column_stack([p,1-p])


def _binary_member_matrix(model:BootstrapBinaryEnsemble,row:dict)->np.ndarray:
    p=model.member_probabilities(row['features']);return np.column_stack([p,1-p])


def _binary_calibrated_predictions(model:BootstrapBinaryEnsemble,cal:list[dict],test:list[dict],version:str):
    cal_probs=probs_from_ensemble(model,cal);cal_logits=np.log(np.clip(cal_probs,1e-9,1));_,ycal=_binary_xy(cal,model.members[0].features);class_cal=np.where(ycal==1,0,1)
    scaler=TemperatureScaler(version=version).fit(cal_logits,class_cal)
    raw=probs_from_ensemble(model,test)
    calibrated=np.vstack([[d['home'],d['away']] for d in (scaler.transform_probabilities({'home':r[0],'away':r[1]}) for r in raw)])
    return scaler,calibrated


def _metric_dict(probs:np.ndarray,y_class:np.ndarray)->dict[str,float]:
    ece,_=top_label_ece(probs,y_class)
    return {'brier':multiclass_brier(probs,y_class),'log_loss':log_loss(probs,y_class),'ece':ece,'accuracy':accuracy(probs,y_class)}


def metric_dict(probs:np.ndarray,y_binary:np.ndarray)->dict[str,float]:
    return _metric_dict(probs,np.where(y_binary==1,0,1))


def _top_reliability(probs:np.ndarray,y_class:np.ndarray,bins:int=10)->list[dict[str,float|int]]:
    pred=np.argmax(probs,axis=1);conf=np.max(probs,axis=1);correct=(pred==y_class).astype(float);edges=np.linspace(0,1,bins+1);rows=[]
    for i in range(bins):
        mask=(conf>=edges[i])&(conf<(edges[i+1]) if i<bins-1 else conf<=edges[i+1]);n=int(mask.sum())
        rows.append({'bin_low':float(edges[i]),'bin_high':float(edges[i+1]),'count':n,'mean_prediction':float(conf[mask].mean()) if n else 0.0,'observed_frequency':float(correct[mask].mean()) if n else 0.0})
    return rows


def run_binary_backtest(
    rows:list[dict],split:ChronologicalSplit,*,sport:Sport,features:list[str],model_version:str,schema_version:str,
    competition:str,seed:int=7,data_mode:str='synthetic_demo',ablation_groups:list[tuple[str,list[str]]]|None=None,
    slice_specs:list[tuple[str,Callable[[dict],bool]]]|None=None,
):
    assert_point_in_time(rows);train,cal,test=split.split(rows);Xtr,ytr=_binary_xy(train,features)
    model=BootstrapBinaryEnsemble.fit_bootstrap(Xtr,ytr,features,n_members=15,seed=seed)
    scaler,calibrated=_binary_calibrated_predictions(model,cal,test,f'{model_version}_temperature_v1');_,ytest=_binary_xy(test,features);classes=np.where(ytest==1,0,1)
    met=_metric_dict(calibrated,classes);reliability=binary_reliability(calibrated[:,0],ytest)
    covered=[];widths=[]
    for r in test:
        mat=_binary_member_matrix(model,r);cal_members=np.asarray([[scaler.transform_probabilities({'home':x[0],'away':x[1]})['home'],scaler.transform_probabilities({'home':x[0],'away':x[1]})['away']] for x in mat])
        lo,hi=np.quantile(cal_members[:,0],[.05,.95]);widths.append(float(hi-lo))
        if 'true_home_probability'in r:covered.append(float(lo<=float(r['true_home_probability'])<=hi))
    met['interval_coverage']=float(np.mean(covered)) if covered else float('nan');met['interval_width']=float(np.mean(widths)) if widths else float('nan')
    base_rate=float(np.mean([r['target_home_win'] for r in train]));base=np.tile([base_rate,1-base_rate],(len(test),1));baselines={'empirical_base_rate':_metric_dict(base,classes)}
    groups=ablation_groups or [('A0 raw strength + venue',[features[0],features[-1]]),('A1 historical/current',features[:min(8,len(features))]),('A2 context + matchup',features[:min(13,len(features))]),('A3 full live world state',features)]
    ablations=[]
    for idx,(label,feat) in enumerate(groups):
        X,y=_binary_xy(train,feat);m=BootstrapBinaryEnsemble.fit_bootstrap(X,y,feat,n_members=7,seed=seed+20+idx);_,p=_binary_calibrated_predictions(m,cal,test,f'{model_version}-ablation-{idx}');a=_metric_dict(p,classes);ablations.append({'stage':f'A{idx}','label':label,'feature_count':len(feat),**a})
    slices=[]
    for name,pred in (slice_specs or []):
        mask=np.asarray([bool(pred(r)) for r in test]);n=int(mask.sum())
        slices.append({'name':name,'count':n,**(_metric_dict(calibrated[mask],classes[mask]) if n>=3 else {'status':'insufficient sample'})})
    rolling=[];by_month={}
    for r,p,c in zip(test,calibrated,classes):by_month.setdefault(str(r['prediction_time'])[:7],[]).append((p,c))
    for month,items in sorted(by_month.items()):
        pp=np.asarray([x[0] for x in items]);yy=np.asarray([x[1] for x in items]);rolling.append({'period':month,'count':len(items),'brier':multiclass_brier(pp,yy),'log_loss':log_loss(pp,yy)})
    Xte=np.asarray([[float(r['features'].get(k,0.0)) for k in features] for r in test]);drift=sorted([{'feature':name,'psi':(v:=psi(Xtr[:,i],Xte[:,i])),'level':'high' if v>.25 else 'moderate' if v>.1 else 'low'} for i,name in enumerate(features)],key=lambda x:x['psi'],reverse=True)
    errors=[]
    for r,p,y in zip(test,calibrated,ytest):
        pred=int(p[0]>=.5);conf=float(max(p))
        if pred!=int(y):errors.append({'event_id':r['event_id'],'prediction_time':r['prediction_time'],'home_probability':float(p[0]),'target_home_win':int(y),'confidence':conf,'weather_severity':float(r['features'].get('weather_severity',0)),'strength_diff':float(r['features'].get('strength_diff',0)),'predicted':'home' if pred else 'away','actual':'home' if y else 'away'})
    errors=sorted(errors,key=lambda x:x['confidence'],reverse=True)[:12];digest=_digest(rows)
    report=BacktestRun(run_id=f'{sport.value}-{model_version}-{digest[:8]}',sport=sport,competition=competition,model_version=model_version,feature_schema_version=schema_version,train_window={'start':str(train[0]['prediction_time']),'end':str(train[-1]['prediction_time'])},calibration_window={'start':str(cal[0]['prediction_time']),'end':str(cal[-1]['prediction_time'])},test_window={'start':str(test[0]['prediction_time']),'end':str(test[-1]['prediction_time'])},split_method='chronological_holdout',prediction_horizons=['pregame','in_game'],sample_counts={'train':len(train),'calibration':len(cal),'test':len(test)},metrics=met,baselines=baselines,ablations=ablations,slices=slices,leakage_violations=len(audit_rows(rows)),reliability=reliability,rolling=rolling,drift=drift,errors=errors,data_mode=data_mode,created_at=datetime.now(timezone.utc),data_snapshot_hash=digest)
    return model,scaler,report


def run_football_backtest(rows:list[dict],split:ChronologicalSplit,*,model_version:str='football_bootstrap_world_demo_v3',seed:int=7,data_mode:str='synthetic_demo'):
    groups=[('A0 raw strength + venue',["strength_diff","home_field"]),('A1 + learned latent state',["strength_diff","home_field","historical_strength_diff","recent_form_diff","health_diff","experience_diff","potential_diff","chemistry_diff"]),('A2 + matchup/context',["strength_diff","home_field","historical_strength_diff","recent_form_diff","health_diff","experience_diff","potential_diff","chemistry_diff","matchup_advantage","context_mean_shift","human_context_diff","environment_context_diff","context_volatility"]),('A3 + live game state',FOOTBALL_FEATURES)]
    slices=[('high_weather',lambda r:float(r['features']['weather_severity'])>=.55),('qb_availability_change',lambda r:abs(float(r['features']['home_qb_available'])-float(r['features']['away_qb_available']))>.1),('home_underdog',lambda r:float(r['features']['strength_diff'])<-.35)]
    return run_binary_backtest(rows,split,sport=Sport.FOOTBALL,features=FOOTBALL_FEATURES,model_version=model_version,schema_version='football_features_v3_world_state',competition='demo-football',seed=seed,data_mode=data_mode,ablation_groups=groups,slice_specs=slices)


def run_basketball_backtest(rows:list[dict],split:ChronologicalSplit,*,model_version:str='basketball_bootstrap_world_demo_v1',seed:int=11,data_mode:str='synthetic_demo'):
    groups=[('A0 raw strength + venue',["strength_diff","home_field"]),('A1 + learned latent state',["strength_diff","home_field","historical_strength_diff","recent_form_diff","health_diff","experience_diff","chemistry_diff"]),('A2 + matchup/context',["strength_diff","home_field","historical_strength_diff","recent_form_diff","health_diff","experience_diff","chemistry_diff","matchup_advantage","context_mean_shift","human_context_diff","environment_context_diff","context_volatility"]),('A3 + live possessions/lineups',BASKETBALL_FEATURES)]
    slices=[('star_availability_change',lambda r:abs(float(r['features']['star_availability_diff']))>.1),('high_pace',lambda r:float(r['features']['pace_scaled'])>.35),('late_game',lambda r:abs(float(r['features']['score_time_interaction']))>.35)]
    return run_binary_backtest(rows,split,sport=Sport.BASKETBALL,features=BASKETBALL_FEATURES,model_version=model_version,schema_version='basketball_features_v3_world_state',competition='demo-basketball',seed=seed,data_mode=data_mode,ablation_groups=groups,slice_specs=slices)


def _f1_tensor(rows:list[dict],features:list[str]):
    labels=list(rows[0]['outcome_features'])
    X=np.asarray([[[float(r['outcome_features'][label].get(k,0.0)) for k in features] for label in labels] for r in rows],dtype=float)
    y=np.asarray([labels.index(str(r['target_winner'])) for r in rows],dtype=int)
    return labels,X,y


def _f1_raw_probs(model:BootstrapConditionalSoftmaxEnsemble,rows:list[dict])->np.ndarray:
    labels=list(rows[0]['outcome_features']);arr=[]
    for r in rows:
        p=model.predict(r['outcome_features'])[0];arr.append([p[x] for x in labels])
    return np.asarray(arr,dtype=float)


def _fit_f1_calibrator(model,cal,version):
    labels,_,y=_f1_tensor(cal,model.members[0].features);raw=_f1_raw_probs(model,cal);return TemperatureScaler(version=version).fit(np.log(np.clip(raw,1e-9,1)),y)


def _calibrate_matrix(raw:np.ndarray,labels:list[str],scaler:TemperatureScaler)->np.ndarray:
    return np.asarray([[scaler.transform_probabilities(dict(zip(labels,row.tolist())))[k] for k in labels] for row in raw],dtype=float)


def run_f1_backtest(rows:list[dict],split:ChronologicalSplit,*,model_version:str='f1_conditional_softmax_world_demo_v1',seed:int=13,data_mode:str='synthetic_demo'):
    assert_point_in_time(rows);train,cal,test=split.split(rows);labels,Xtr,ytr=_f1_tensor(train,F1_OUTCOME_FEATURES)
    model=BootstrapConditionalSoftmaxEnsemble.fit_bootstrap(Xtr,ytr,F1_OUTCOME_FEATURES,n_members=15,seed=seed);scaler=_fit_f1_calibrator(model,cal,f'{model_version}_temperature_v1');_,_,ytest=_f1_tensor(test,F1_OUTCOME_FEATURES);raw=_f1_raw_probs(model,test);probs=_calibrate_matrix(raw,labels,scaler);met=_metric_dict(probs,ytest);ece,_=top_label_ece(probs,ytest);met['ece']=ece
    cover=[];widths=[]
    for r in test:
        labs,matrix=model.member_probabilities(r['outcome_features']);cm=_calibrate_matrix(matrix,labs,scaler);truth=r.get('true_probabilities',{})
        for j,l in enumerate(labs):
            lo,hi=np.quantile(cm[:,j],[.05,.95]);widths.append(float(hi-lo));
            if l in truth:cover.append(float(lo<=float(truth[l])<=hi))
    met['interval_coverage']=float(np.mean(cover)) if cover else float('nan');met['interval_width']=float(np.mean(widths)) if widths else float('nan')
    freq=np.bincount(_f1_tensor(train,F1_OUTCOME_FEATURES)[2],minlength=len(labels)).astype(float);freq/=freq.sum();base=np.tile(freq,(len(test),1));baselines={'empirical_winner_rate':_metric_dict(base,ytest)}
    group_defs=[('A0 grid/position',["position_advantage","progress_position"]),('A1 + pace/reliability',["position_advantage","progress_position","pace_advantage","reliability_log"]),('A2 + learned driver state/context',["position_advantage","progress_position","pace_advantage","reliability_log","context_adjustment","latent_skill","latent_form","latent_health","latent_experience","latent_potential"]),('A3 + strategy/weather/live race',F1_OUTCOME_FEATURES)]
    ablations=[]
    for i,(label,feat) in enumerate(group_defs):
        _,X,y=_f1_tensor(train,feat);m=BootstrapConditionalSoftmaxEnsemble.fit_bootstrap(X,y,feat,n_members=7,seed=seed+30+i);c=_fit_f1_calibrator(m,cal,f'{model_version}-ablation-{i}');pr=_calibrate_matrix(_f1_raw_probs(m,test),labels,c);ablations.append({'stage':f'A{i}','label':label,'feature_count':len(feat),**_metric_dict(pr,ytest)})
    reliability=_top_reliability(probs,ytest);slices=[]
    for name,pred in [('wet_race',lambda r:any(float(v.get('wet_interaction',0))>0.05 for v in r['outcome_features'].values())),('late_race',lambda r:max(abs(float(v.get('progress_position',0))) for v in r['outcome_features'].values())>.55),('reliability_stress',lambda r:any(float(v.get('reliability_log',0))<-.08 for v in r['outcome_features'].values()))]:
        mask=np.asarray([pred(r) for r in test]);n=int(mask.sum());slices.append({'name':name,'count':n,**(_metric_dict(probs[mask],ytest[mask]) if n>=3 else {'status':'insufficient sample'})})
    rolling=[];by_month={}
    for r,p,y in zip(test,probs,ytest):by_month.setdefault(str(r['prediction_time'])[:7],[]).append((p,y))
    for month,items in sorted(by_month.items()):
        pp=np.asarray([x[0] for x in items]);yy=np.asarray([x[1] for x in items]);rolling.append({'period':month,'count':len(items),'brier':multiclass_brier(pp,yy),'log_loss':log_loss(pp,yy)})
    # Drift pools all driver/outcome rows because the scorer is shared.
    Xte=_f1_tensor(test,F1_OUTCOME_FEATURES)[1];drift=[]
    for i,name in enumerate(F1_OUTCOME_FEATURES):
        v=psi(Xtr[:,:,i].ravel(),Xte[:,:,i].ravel());drift.append({'feature':name,'psi':v,'level':'high' if v>.25 else 'moderate' if v>.1 else 'low'})
    drift=sorted(drift,key=lambda x:x['psi'],reverse=True)
    errors=[]
    for r,p,y in zip(test,probs,ytest):
        pred=int(np.argmax(p));conf=float(np.max(p))
        if pred!=int(y):errors.append({'event_id':r['event_id'],'prediction_time':r['prediction_time'],'predicted':labels[pred],'actual':labels[int(y)],'confidence':conf,'probabilities':{l:float(p[j]) for j,l in enumerate(labels)}})
    errors=sorted(errors,key=lambda x:x['confidence'],reverse=True)[:12];digest=_digest(rows)
    report=BacktestRun(run_id=f'f1-{model_version}-{digest[:8]}',sport=Sport.F1,competition='demo-f1',model_version=model_version,feature_schema_version='f1_features_v3_learned_world',train_window={'start':str(train[0]['prediction_time']),'end':str(train[-1]['prediction_time'])},calibration_window={'start':str(cal[0]['prediction_time']),'end':str(cal[-1]['prediction_time'])},test_window={'start':str(test[0]['prediction_time']),'end':str(test[-1]['prediction_time'])},split_method='chronological_holdout',prediction_horizons=['pre_race','in_race'],sample_counts={'train':len(train),'calibration':len(cal),'test':len(test)},metrics=met,baselines=baselines,ablations=ablations,slices=slices,leakage_violations=len(audit_rows(rows)),reliability=reliability,rolling=rolling,drift=drift,errors=errors,data_mode=data_mode,created_at=datetime.now(timezone.utc),data_snapshot_hash=digest)
    return model,scaler,report
