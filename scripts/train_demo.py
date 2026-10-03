from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))

from sportsworld.backtest.runner import run_football_backtest, run_basketball_backtest, run_f1_backtest
from sportsworld.backtest.splitter import ChronologicalSplit
from sportsworld.context.state_space import LatentStateSpaceModel
from sportsworld.schemas import ModelCard, Sport


def read_jsonl(path:Path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def save_model(*,sport:Sport,model,cal,report,version:str,algorithm:str,schema:str,features:list[str],filename:str,notes:list[str]):
    art_dir=ROOT/'models'/'artifacts';man_dir=ROOT/'models'/'manifests';bt_dir=ROOT/'data'/'fixtures'/'backtests'
    art_dir.mkdir(parents=True,exist_ok=True);man_dir.mkdir(parents=True,exist_ok=True);bt_dir.mkdir(parents=True,exist_ok=True)
    artifact={'model':model.to_dict(),'calibrator':cal.to_dict(),'data_mode':'synthetic_demo','warning':'Demo artifact trained on generated point-in-time-valid data. Do not present its metrics as real-world sports performance.'}
    (art_dir/filename).write_text(json.dumps(artifact,indent=2))
    card=ModelCard(model_version=version,sport=sport,algorithm=algorithm,feature_schema_version=schema,features=features,train_window=report.train_window,calibration_window=report.calibration_window,test_window=report.test_window,artifact_uri=filename,calibration_version=cal.version,metrics=report.metrics,data_mode='synthetic_demo',notes=notes)
    (man_dir/f'{sport.value}_active.json').write_text(card.model_dump_json(indent=2));(bt_dir/f'{sport.value}_demo.json').write_text(report.model_dump_json(indent=2))


def train_latent():
    rows=read_jsonl(ROOT/'data'/'fixtures'/'training'/'latent_state_sequences_demo.jsonl')
    model=LatentStateSpaceModel.fit_sequences(rows,version='latent_state_dynamics_demo_v1',data_mode='synthetic_demo')
    path=ROOT/'models'/'artifacts'/'latent_state_dynamics_demo_v1.json';model.save(path)
    meta={'version':model.version,'data_mode':model.data_mode,'dimensions':list(model.params),'training_sequences':len(rows),'warning':'Synthetic demo dynamics only. Refit on real longitudinal point-in-time entity evidence before empirical claims.'}
    (ROOT/'models'/'manifests'/'latent_state_active.json').write_text(json.dumps(meta,indent=2))
    return model


def main():
    train_latent()
    split=ChronologicalSplit(datetime.fromisoformat('2025-12-31T23:59:59+00:00'),datetime.fromisoformat('2026-04-30T23:59:59+00:00'))

    football=read_jsonl(ROOT/'data'/'fixtures'/'training'/'football_synthetic_v2_context.jsonl')
    fm,fc,fr=run_football_backtest(football,split,model_version='football_bootstrap_world_demo_v3',seed=7,data_mode='synthetic_demo')
    save_model(sport=Sport.FOOTBALL,model=fm,cal=fc,report=fr,version='football_bootstrap_world_demo_v3',algorithm='bootstrap_logistic',schema='football_features_v3_world_state',features=fm.members[0].features,filename='football_bootstrap_world_demo_v3.json',notes=['Learned bootstrap ensemble consumes learned latent-state aggregates, matchup/context, and live game state.','Synthetic demo artifact; replace with real chronological sports history before empirical claims.'])

    basketball=read_jsonl(ROOT/'data'/'fixtures'/'training'/'basketball_synthetic_v1_world.jsonl')
    bm,bc,br=run_basketball_backtest(basketball,split,model_version='basketball_bootstrap_world_demo_v1',seed=11,data_mode='synthetic_demo')
    save_model(sport=Sport.BASKETBALL,model=bm,cal=bc,report=br,version='basketball_bootstrap_world_demo_v1',algorithm='bootstrap_logistic',schema='basketball_features_v3_world_state',features=bm.members[0].features,filename='basketball_bootstrap_world_demo_v1.json',notes=['Learned basketball ensemble combines latent team/player state, matchup/context, lineup and possession state.','Synthetic demo artifact; replace with real chronological sports history before empirical claims.'])

    f1=read_jsonl(ROOT/'data'/'fixtures'/'training'/'f1_synthetic_v1_world.jsonl')
    mm,mc,mr=run_f1_backtest(f1,split,model_version='f1_conditional_softmax_world_demo_v1',seed=13,data_mode='synthetic_demo')
    save_model(sport=Sport.F1,model=mm,cal=mc,report=mr,version='f1_conditional_softmax_world_demo_v1',algorithm='bootstrap_conditional_softmax',schema='f1_features_v3_learned_world',features=mm.members[0].features,filename='f1_conditional_softmax_world_demo_v1.json',notes=['Shared learned driver scorer supports variable F1 outcome sets and combines live race state with learned latent driver state.','Synthetic demo artifact; replace with real chronological race history before empirical claims.'])

    print('trained latent dynamics + football + basketball + f1 hero models')

if __name__=='__main__':
    main()
