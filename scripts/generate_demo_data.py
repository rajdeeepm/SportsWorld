from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
UTC=timezone.utc


def iso(dt): return dt.isoformat().replace('+00:00','Z')


def write_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text('\n'.join(json.dumps(r,separators=(',',':')) for r in rows)+'\n')


def observation(event_id,sport,kind,payload,source_id,source_type,t,seq,confidence=1.0,verified=True):
    return {'event_id':event_id,'sport':sport,'kind':kind,'payload':payload,'source_id':source_id,'source_type':source_type,'confidence':confidence,'event_time':iso(t),'known_to_model_time':iso(t+timedelta(seconds=2)),'ingestion_time':iso(t+timedelta(seconds=3)),'sequence_no':seq,'verified':verified}


def demo_events():
    events=[
      {'event_id':'mich-osu-2026-demo','sport':'football','competition':'college_football','season':'2026','outcomes':['home','away'],'start_time':'2026-11-28T17:00:00Z','participants':['Michigan','Ohio State'],'venue':'Demo Stadium','initial_features':{'home_strength':0.34,'away_strength':0.29,'home_field':1.0,'state_confidence':0.98},'metadata':{'display_outcomes':{'home':'Michigan','away':'Ohio State'},'outcome_entity_ids':{'home':'team:michigan','away':'team:ohio-state'},'replay_mode':True,'data_mode':'synthetic_demo','context_mode':'synthetic_demo'}},
      {'event_id':'basketball-2026-demo','sport':'basketball','competition':'nba_style_demo','season':'2026','outcomes':['home','away'],'start_time':'2026-10-15T23:00:00Z','participants':['Home Five','Away Five'],'venue':'Demo Arena','initial_features':{'home_strength':0.22,'away_strength':0.18,'home_lineup_rating':3.0,'away_lineup_rating':2.1,'state_confidence':0.98},'metadata':{'display_outcomes':{'home':'Home Five','away':'Away Five'},'outcome_entity_ids':{'home':'team:home-five','away':'team:away-five'},'replay_mode':True,'data_mode':'synthetic_demo','context_mode':'synthetic_demo'}},
      {'event_id':'demo-gp-2026','sport':'f1','competition':'formula_1_demo','season':'2026','outcomes':['Norris','Verstappen','Leclerc','Other'],'start_time':'2026-10-04T12:00:00Z','participants':['Norris','Verstappen','Leclerc','Other'],'venue':'Demo Circuit','initial_features':{'lap':0,'total_laps':57,'rain_probability':0.08,'state_confidence':0.98,'drivers':{'Norris':{'position':1,'pace':-0.08,'reliability':0.985,'wet_skill':0.20,'tyre_age':0,'compound':'MEDIUM'},'Verstappen':{'position':2,'pace':-0.05,'reliability':0.988,'wet_skill':0.42,'tyre_age':0,'compound':'MEDIUM'},'Leclerc':{'position':3,'pace':0.02,'reliability':0.975,'wet_skill':0.10,'tyre_age':0,'compound':'MEDIUM'},'Other':{'position':4,'pace':0.12,'reliability':0.970,'wet_skill':0.05,'tyre_age':0,'compound':'MEDIUM'}}},'metadata':{'outcome_entity_ids':{'Norris':'driver:norris','Verstappen':'driver:verstappen','Leclerc':'driver:leclerc','Other':'driver:other'},'replay_mode':True,'data_mode':'synthetic_demo','context_mode':'synthetic_demo'}}
    ]
    p=ROOT/'data'/'fixtures'/'demo_events.json'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(events,indent=2))

    t=datetime(2026,11,28,17,0,tzinfo=UTC); rows=[]; seq=1
    def add(mins,kind,payload,src='replay-stats',typ='stats',confidence=1.0):
        nonlocal seq; rows.append(observation('mich-osu-2026-demo','football',kind,payload,src,typ,t+timedelta(minutes=mins),seq,confidence)); seq+=1
    add(2,'score_state',{'home_score':0,'away_score':0,'quarter':1,'seconds_remaining':3480,'possession':'home','down':1,'distance':10,'yard_line':25})
    add(18,'score',{'team':'home','points':7,'seconds_remaining':2750,'possession':'away'})
    add(36,'score',{'team':'away','points':7,'seconds_remaining':2050,'possession':'home'})
    add(55,'weather',{'severity':0.55},'replay-weather','weather')
    add(72,'score_state',{'home_score':14,'away_score':10,'quarter':3,'seconds_remaining':1190,'possession':'home','down':2,'distance':7,'yard_line':43})
    add(78,'injury_status',{'team':'away','role':'cornerback','status':'out','impact':-0.10},'official-team-report','official')
    add(84,'turnover',{'possession':'away','seconds_remaining':850,'yard_line':37},'replay-stats','stats')
    add(92,'injury_status',{'team':'home','role':'starting_qb','status':'questionable','impact':-0.04},'official-team-report','official',0.98)
    add(103,'score',{'team':'home','points':7,'seconds_remaining':310,'possession':'away'})
    write_jsonl(ROOT/'data'/'replays'/'mich-osu-2026-demo.jsonl',rows)

    t=datetime(2026,10,15,23,0,tzinfo=UTC); rows=[]; seq=1
    def addb(mins,kind,payload,src='replay-stats',typ='stats',confidence=1.0):
        nonlocal seq; rows.append(observation('basketball-2026-demo','basketball',kind,payload,src,typ,t+timedelta(minutes=mins),seq,confidence)); seq+=1
    addb(3,'score_state',{'home_score':8,'away_score':6,'seconds_remaining':2670,'possession':'away','pace':101})
    addb(19,'score_state',{'home_score':31,'away_score':29,'seconds_remaining':1820,'possession':'home','pace':104})
    addb(34,'lineup',{'team':'home','lineup_rating':6.0},'official-team-report','official')
    addb(41,'score_state',{'home_score':61,'away_score':65,'seconds_remaining':1050,'possession':'away','pace':108})
    addb(47,'foul',{'team':'away','player':'A7'},'replay-stats','stats')
    addb(51,'availability',{'team':'home','status':'limited','impact':-0.06},'official-team-report','official',0.95)
    addb(58,'score_state',{'home_score':96,'away_score':94,'seconds_remaining':165,'possession':'home','pace':106})
    write_jsonl(ROOT/'data'/'replays'/'basketball-2026-demo.jsonl',rows)

    t=datetime(2026,10,4,12,0,tzinfo=UTC); rows=[]; seq=1
    def addf(mins,kind,payload,src='replay-timing',typ='telemetry',confidence=1.0):
        nonlocal seq; rows.append(observation('demo-gp-2026','f1',kind,payload,src,typ,t+timedelta(minutes=mins),seq,confidence)); seq+=1
    addf(4,'race_state',{'lap':4,'drivers':{'Norris':{'position':1,'tyre_age':4},'Verstappen':{'position':2,'tyre_age':4},'Leclerc':{'position':3,'tyre_age':4},'Other':{'position':4,'tyre_age':4}}})
    addf(19,'pace',{'driver':'Verstappen','pace_delta':-0.13})
    addf(29,'weather',{'rain_probability':0.62},'replay-weather','weather')
    addf(36,'pit_stop',{'driver':'Norris','lap':28,'new_compound':'INTERMEDIATE','pit_duration_s':22.8,'rejoin_position':4})
    addf(40,'pit_stop',{'driver':'Verstappen','lap':29,'new_compound':'INTERMEDIATE','pit_duration_s':21.9,'rejoin_position':2})
    addf(47,'safety_car',{'active':True})
    addf(60,'reliability',{'driver':'Leclerc','reliability':0.78},'official-team-report','official')
    addf(72,'race_state',{'lap':48,'drivers':{'Norris':{'position':3,'tyre_age':20},'Verstappen':{'position':1,'tyre_age':19},'Leclerc':{'position':2,'tyre_age':19},'Other':{'position':4,'tyre_age':21}}})
    write_jsonl(ROOT/'data'/'replays'/'demo-gp-2026.jsonl',rows)



def context_demo():
    """Write synthetic longitudinal/context memory for all three hero demos.

    Raw values are intentionally human-readable (yards, TDs, ratings) while
    normalized values are model features. Every record is marked synthetic.
    """
    profiles=[
      # Football teams and high-impact people/units.
      {'entity_id':'team:michigan','sport':'football','entity_type':'team','display_name':'Michigan','attributes':{'side':'home','synthetic':True},'capabilities':{'skill':.43,'form':.26,'health':.34,'experience':.36,'potential':.44,'chemistry':.31,'rush_offense':.62,'pass_offense':.34,'run_defense':.55,'pass_defense':.40,'pass_protection':.48,'pass_rush':.45,'special_teams':.18},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'team:ohio-state','sport':'football','entity_type':'team','display_name':'Ohio State','attributes':{'side':'away','synthetic':True},'capabilities':{'skill':.46,'form':.18,'health':.39,'experience':.29,'potential':.52,'chemistry':.27,'rush_offense':.41,'pass_offense':.61,'run_defense':.44,'pass_defense':.56,'pass_protection':.40,'pass_rush':.64,'special_teams':.21},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'player:mich-qb1','sport':'football','entity_type':'player','display_name':'Michigan QB1','team_id':'team:michigan','role':'starting_qb','attributes':{'synthetic':True},'capabilities':{'skill':.38,'form':.28,'health':.72,'usage':.76,'experience':.18,'potential':.67},'importance':.98,'source_ids':['synthetic-history']},
      {'entity_id':'player:mich-rb1','sport':'football','entity_type':'player','display_name':'Michigan RB1','team_id':'team:michigan','role':'rb1','attributes':{'synthetic':True},'capabilities':{'skill':.48,'form':.41,'health':.61,'usage':.71,'experience':.31,'potential':.46},'importance':.84,'source_ids':['synthetic-history']},
      {'entity_id':'unit:mich-ol','sport':'football','entity_type':'unit','display_name':'Michigan Offensive Line','team_id':'team:michigan','role':'offensive_line','attributes':{'synthetic':True},'capabilities':{'skill':.40,'form':.35,'health':.45,'chemistry':.56,'rush_offense':.67,'pass_protection':.49},'importance':.88,'source_ids':['synthetic-history']},
      {'entity_id':'player:osu-qb1','sport':'football','entity_type':'player','display_name':'Ohio State QB1','team_id':'team:ohio-state','role':'starting_qb','attributes':{'synthetic':True},'capabilities':{'skill':.51,'form':.17,'health':.80,'usage':.79,'experience':.23,'potential':.70},'importance':.98,'source_ids':['synthetic-history']},
      {'entity_id':'player:osu-wr1','sport':'football','entity_type':'player','display_name':'Ohio State WR1','team_id':'team:ohio-state','role':'wr1','attributes':{'synthetic':True},'capabilities':{'skill':.59,'form':.33,'health':.69,'usage':.66,'experience':.16,'potential':.76},'importance':.87,'source_ids':['synthetic-history']},
      {'entity_id':'unit:osu-dl','sport':'football','entity_type':'unit','display_name':'Ohio State Defensive Front','team_id':'team:ohio-state','role':'defensive_line','attributes':{'synthetic':True},'capabilities':{'skill':.55,'form':.27,'health':.51,'chemistry':.44,'run_defense':.47,'pass_rush':.68},'importance':.90,'source_ids':['synthetic-history']},
      # Basketball.
      {'entity_id':'team:home-five','sport':'basketball','entity_type':'team','display_name':'Home Five','attributes':{'synthetic':True},'capabilities':{'skill':.35,'form':.31,'health':.40,'experience':.22,'potential':.38,'chemistry':.45,'shot_creation':.52,'shot_defense':.34,'rim_pressure':.48,'rim_protection':.31,'rebounding':.28,'turnover_control':.44,'turnover_pressure':.30},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'team:away-five','sport':'basketball','entity_type':'team','display_name':'Away Five','attributes':{'synthetic':True},'capabilities':{'skill':.31,'form':.20,'health':.46,'experience':.34,'potential':.30,'chemistry':.36,'shot_creation':.39,'shot_defense':.42,'rim_pressure':.35,'rim_protection':.45,'rebounding':.37,'turnover_control':.33,'turnover_pressure':.41},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'player:home-star','sport':'basketball','entity_type':'player','display_name':'Home Star','team_id':'team:home-five','role':'primary_creator','attributes':{'synthetic':True},'capabilities':{'skill':.58,'form':.44,'health':.63,'usage':.82,'experience':.40,'potential':.55},'importance':.98,'source_ids':['synthetic-history']},
      {'entity_id':'player:away-star','sport':'basketball','entity_type':'player','display_name':'Away Star','team_id':'team:away-five','role':'primary_creator','attributes':{'synthetic':True},'capabilities':{'skill':.53,'form':.29,'health':.72,'usage':.79,'experience':.47,'potential':.49},'importance':.98,'source_ids':['synthetic-history']},
      # F1 drivers.
      {'entity_id':'driver:norris','sport':'f1','entity_type':'driver','display_name':'Norris','role':'driver','attributes':{'synthetic':True},'capabilities':{'skill':.61,'form':.57,'health':.82,'experience':.49,'potential':.66,'chemistry':.46},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'driver:verstappen','sport':'f1','entity_type':'driver','display_name':'Verstappen','role':'driver','attributes':{'synthetic':True},'capabilities':{'skill':.76,'form':.51,'health':.85,'experience':.72,'potential':.73,'chemistry':.55},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'driver:leclerc','sport':'f1','entity_type':'driver','display_name':'Leclerc','role':'driver','attributes':{'synthetic':True},'capabilities':{'skill':.64,'form':.34,'health':.79,'experience':.63,'potential':.64,'chemistry':.43},'importance':1.0,'source_ids':['synthetic-history']},
      {'entity_id':'driver:other','sport':'f1','entity_type':'driver','display_name':'Other','role':'field','attributes':{'synthetic':True},'capabilities':{'skill':.32,'form':.28,'health':.74,'experience':.48,'potential':.37,'chemistry':.32},'importance':1.0,'source_ids':['synthetic-history']},
    ]
    metrics=[]
    def metric(entity,sport,name,dim,raw,norm,when,unit=None,sample=1,confidence=.95,opponent_id=None,tags=None):
        metrics.append({'entity_id':entity,'sport':sport,'metric':name,'dimension':dim,'raw_value':raw,'normalized_value':norm,'unit':unit,'sample_size':sample,'occurred_at':iso(when),'known_to_model_time':iso(when+timedelta(hours=2)),'source_id':'synthetic-history','source_type':'stats','confidence':confidence,'season':str(when.year),'opponent_id':opponent_id,'tags':['synthetic_demo',*(tags or [])]})
    # Football longitudinal examples: career + recent form + current availability.
    football_start=datetime(2026,11,28,17,tzinfo=UTC)
    metric('team:michigan','football','season_rush_yards_per_game','form',188,.34,football_start-timedelta(days=8),'yd/game',11,.97)
    metric('team:michigan','football','opponent_adjusted_efficiency','skill',.71,.44,football_start-timedelta(days=10),'index',11,.97)
    metric('team:ohio-state','football','season_pass_yards_per_game','form',282,.38,football_start-timedelta(days=8),'yd/game',11,.97)
    metric('team:ohio-state','football','opponent_adjusted_efficiency','skill',.74,.48,football_start-timedelta(days=10),'index',11,.97)
    # Matchup-specific history is explicit evidence and receives a modest boost only for this opponent.
    metric('team:michigan','football','last_3_vs_opponent_rush_yards_per_game','form',176,.28,football_start-timedelta(days=120),'yd/game',3,.90,opponent_id='team:ohio-state',tags=['matchup_history','rivalry'])
    metric('team:ohio-state','football','last_3_vs_opponent_pressure_rate','form',.36,.38,football_start-timedelta(days=120),'rate',3,.90,opponent_id='team:michigan',tags=['matchup_history','rivalry'])
    metric('player:mich-qb1','football','career_passing_touchdowns','skill',42,.36,football_start-timedelta(days=14),'TD',31,.98)
    metric('player:mich-qb1','football','last_5_epa_per_dropback','form',.19,.42,football_start-timedelta(days=6),'EPA/dropback',5,.96)
    metric('player:mich-qb1','football','practice_availability','health','full',.75,football_start-timedelta(days=2),None,1,.95)
    metric('player:mich-rb1','football','career_rushing_yards','skill',2550,.45,football_start-timedelta(days=21),'yd',28,.98)
    metric('player:mich-rb1','football','last_5_rush_yards_per_game','form',104,.51,football_start-timedelta(days=6),'yd/game',5,.96)
    metric('unit:mich-ol','football','last_5_stuff_rate_allowed','form','.15',.43,football_start-timedelta(days=6),'rate',5,.94)
    metric('player:osu-qb1','football','career_passing_touchdowns','skill',48,.46,football_start-timedelta(days=14),'TD',30,.98)
    metric('player:osu-qb1','football','last_5_epa_per_dropback','form',.12,.24,football_start-timedelta(days=6),'EPA/dropback',5,.96)
    metric('player:osu-wr1','football','career_receiving_touchdowns','skill',21,.52,football_start-timedelta(days=14),'TD',27,.98)
    metric('unit:osu-dl','football','season_pressure_rate','form',.39,.52,football_start-timedelta(days=7),'rate',11,.96)
    # Basketball examples.
    basketball_start=datetime(2026,10,15,23,tzinfo=UTC)
    metric('player:home-star','basketball','last_10_points','form',27.8,.46,basketball_start-timedelta(days=3),'pts/game',10,.97)
    metric('player:home-star','basketball','career_usage_rate','usage',.31,.58,basketball_start-timedelta(days=14),'rate',180,.99)
    metric('player:away-star','basketball','last_10_points','form',24.1,.31,basketball_start-timedelta(days=3),'pts/game',10,.97)
    metric('team:home-five','basketball','recent_net_rating','form',7.2,.40,basketball_start-timedelta(days=2),'per100',8,.95)
    metric('team:away-five','basketball','recent_net_rating','form',3.1,.20,basketball_start-timedelta(days=2),'per100',8,.95)
    # F1 historical and recent driver form.
    f1_start=datetime(2026,10,4,12,tzinfo=UTC)
    metric('driver:norris','f1','recent_qualifying_percentile','form',.86,.61,f1_start-timedelta(days=7),'percentile',6,.97)
    metric('driver:norris','f1','career_podium_rate','skill',.28,.52,f1_start-timedelta(days=21),'rate',120,.99)
    metric('driver:verstappen','f1','recent_qualifying_percentile','form',.89,.66,f1_start-timedelta(days=7),'percentile',6,.97)
    metric('driver:verstappen','f1','career_podium_rate','skill',.61,.78,f1_start-timedelta(days=21),'rate',180,.99)
    metric('driver:leclerc','f1','recent_qualifying_percentile','form',.77,.45,f1_start-timedelta(days=7),'percentile',6,.97)

    signals=[]
    def signal(event,sport,category,effect,label,summary,when,target=None,direction=0,strength=.5,volatility=0,sentiment='neutral',confidence=.95,source='synthetic-context'):
        signals.append({'event_id':event,'sport':sport,'category':category,'effect':effect,'label':label,'summary':summary,'target_entity_id':target,'direction':direction,'strength':strength,'volatility':volatility,'sentiment':sentiment,'observed_at':iso(when),'known_to_model_time':iso(when+timedelta(minutes=5)),'source_id':source,'source_type':'official' if source=='synthetic-official' else 'news','confidence':confidence,'verified':True,'public_evidence_only':True,'metadata':{'synthetic_demo':True,'runtime':False}})
    signal('mich-osu-2026-demo','football','rivalry','variance','Rivalry regime','Synthetic demo rivalry context: historical matchup is treated as a possible variance modifier, not a magic rivalry bonus.',football_start-timedelta(days=14),strength=.75,volatility=.48,confidence=.90)
    signal('mich-osu-2026-demo','football','environment','mean','Home environment','Synthetic demo home-field/crowd context for the listed home team.',football_start-timedelta(days=30),target='team:michigan',direction=.30,strength=.65,confidence=.98)
    signal('mich-osu-2026-demo','football','health','mean','QB practice status','Synthetic official-style note indicates Michigan QB1 practiced fully; this is public availability evidence, not an inferred mental/medical state.',football_start-timedelta(days=2),target='player:mich-qb1',direction=.24,strength=.55,sentiment='positive',confidence=.95,source='synthetic-official')
    signal('mich-osu-2026-demo','football','narrative','state_only','Public expectation split','Synthetic media/public narrative is mixed. Displayed for context; state_only means it does not directly move the mean forecast.',football_start-timedelta(days=1),strength=.35,sentiment='mixed',confidence=.70)
    signal('mich-osu-2026-demo','football','stakes','variance','High-stakes game','Synthetic high-stakes context increases modeled uncertainty rather than assigning a team a hand-written advantage.',football_start-timedelta(days=20),strength=.60,volatility=.30,confidence=.92)
    signal('basketball-2026-demo','basketball','rest','mean','Rest advantage','Synthetic home team has an extra rest day.',basketball_start-timedelta(days=2),target='team:home-five',direction=.24,strength=.45,confidence=.96)
    signal('basketball-2026-demo','basketball','sentiment','state_only','Lineup confidence note','Synthetic public lineup commentary is positive but displayed without directly changing the mean forecast.',basketball_start-timedelta(hours=8),target='team:home-five',strength=.25,sentiment='positive',confidence=.75)
    signal('demo-gp-2026','f1','weather','variance','Rain risk before start','Synthetic forecast indicates meaningful rain risk; this primarily increases race-state uncertainty before live weather arrives.',f1_start-timedelta(hours=5),strength=.55,volatility=.42,confidence=.92)
    signal('demo-gp-2026','f1','form','mean','Recent form context','Synthetic recent-form context modestly favors Norris.',f1_start-timedelta(days=2),target='driver:norris',direction=.28,strength=.42,confidence=.90)
    signal('demo-gp-2026','f1','experience','mean','Experience prior','Synthetic experience context modestly favors Verstappen.',f1_start-timedelta(days=5),target='driver:verstappen',direction=.30,strength=.38,confidence=.95)

    p=ROOT/'data'/'fixtures'/'context'/'context_demo.json'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({'profiles':profiles,'metrics':metrics,'signals':signals,'data_mode':'synthetic_demo'},indent=2))

def synthetic_training():
    rng=np.random.default_rng(20261001); start=datetime(2024,1,1,12,tzinfo=UTC); rows=[]
    for i in range(1000):
        dt=start+timedelta(days=i)
        strength=float(rng.normal(0,0.7)); historical=float(np.clip(.65*strength+rng.normal(0,.35),-1,1)); recent=float(np.clip(.40*strength+rng.normal(0,.5),-1,1)); health=float(rng.normal(0,.28)); usage=float(rng.normal(0,.25)); experience=float(rng.normal(0,.3)); potential=float(rng.normal(0,.34)); chemistry=float(rng.normal(0,.28)); matchup=float(np.clip(.35*strength+rng.normal(0,.5),-1,1)); context=float(rng.normal(0,.2)); human=float(rng.normal(0,.16)); environment=float(rng.normal(.08,.18)); volatility=float(np.clip(rng.beta(1.6,5),0,1))
        elapsed=float(rng.uniform(0,0.92)); score_scaled=float(rng.normal((.20*strength+.16*historical+.10*matchup),0.75)*(0.2+elapsed)); possession=float(rng.choice([-1,1])); field=float(rng.uniform(-1,1)); hqb=float(rng.choice([0,0.5,1],p=[.04,.06,.90])); aqb=float(rng.choice([0,0.5,1],p=[.04,.06,.90])); weather=float(rng.beta(1.5,4.5)); home_field=1.0
        interaction=score_scaled*elapsed
        features={'strength_diff':strength,'historical_strength_diff':historical,'recent_form_diff':recent,'health_diff':health,'usage_stability_diff':usage,'experience_diff':experience,'potential_diff':potential,'chemistry_diff':chemistry,'matchup_advantage':matchup,'context_mean_shift':context,'human_context_diff':human,'environment_context_diff':environment,'context_volatility':volatility,'score_diff_scaled':score_scaled,'time_elapsed':elapsed,'score_time_interaction':interaction,'possession_home':possession,'field_position_home':field,'home_qb_available':hqb,'away_qb_available':aqb,'weather_severity':weather,'home_field':home_field}
        z=.48*strength+.42*historical+.32*recent+.22*health+.08*usage+.10*experience+.09*potential+.10*chemistry+.34*matchup+.20*context+.08*human+.08*environment+1.18*score_scaled+1.72*interaction+.16*possession+.10*field+.88*(hqb-aqb)-.08*weather+.20
        p=1/(1+np.exp(-z)); target=int(rng.random()<p)
        prediction=dt+timedelta(hours=float(rng.uniform(0,3)))
        rows.append({'event_id':f'synth-{i:04d}','prediction_time':iso(prediction),'max_known_to_model_time':iso(prediction-timedelta(seconds=int(rng.integers(0,90)))),'competition':'synthetic_demo','feature_schema_version':'football_features_v3_world_state','features':features,'target_home_win':target,'true_home_probability':float(p)})
    write_jsonl(ROOT/'data'/'fixtures'/'training'/'football_synthetic_v2_context.jsonl',rows)




def synthetic_basketball_training():
    rng=np.random.default_rng(20261002);start=datetime(2024,1,1,12,tzinfo=UTC);rows=[]
    for i in range(1000):
        dt=start+timedelta(days=i)
        strength=float(rng.normal(0,.62));historical=float(np.clip(.66*strength+rng.normal(0,.30),-1,1));recent=float(np.clip(.46*strength+rng.normal(0,.42),-1,1));health=float(rng.normal(0,.25));experience=float(rng.normal(0,.28));chem=float(rng.normal(0,.27));matchup=float(np.clip(.36*strength+rng.normal(0,.45),-1,1));context=float(rng.normal(0,.18));human=float(rng.normal(0,.13));environment=float(rng.normal(.05,.13));vol=float(np.clip(rng.beta(1.8,6),0,1));elapsed=float(rng.uniform(0,.96));score=float(rng.normal(.20*strength+.15*recent,.72)*(0.2+elapsed));pos=float(rng.choice([-1,1]));lineup=float(rng.normal(.28*strength,.40));star=float(rng.choice([-1,-.5,0,.5,1],p=[.03,.05,.84,.05,.03]));pace=float(rng.normal(0,.45));home=1.0
        feats={'strength_diff':strength,'historical_strength_diff':historical,'recent_form_diff':recent,'health_diff':health,'experience_diff':experience,'chemistry_diff':chem,'matchup_advantage':matchup,'context_mean_shift':context,'human_context_diff':human,'environment_context_diff':environment,'context_volatility':vol,'score_diff_scaled':score,'score_time_interaction':score*elapsed,'possession_home':pos,'lineup_diff':lineup,'star_availability_diff':star,'pace_scaled':pace,'home_field':home}
        z=.48*strength+.36*historical+.34*recent+.22*health+.12*experience+.17*chem+.31*matchup+.19*context+.07*human+.06*environment+1.02*score+1.63*score*elapsed+.09*pos+.34*lineup+.61*star+.04*pace+.15
        pr=1/(1+np.exp(-z));target=int(rng.random()<pr);prediction=dt+timedelta(hours=float(rng.uniform(0,3)))
        rows.append({'event_id':f'bball-synth-{i:04d}','prediction_time':iso(prediction),'max_known_to_model_time':iso(prediction-timedelta(seconds=int(rng.integers(0,90)))),'competition':'synthetic_demo','feature_schema_version':'basketball_features_v3_world_state','features':feats,'target_home_win':target,'true_home_probability':float(pr)})
    write_jsonl(ROOT/'data'/'fixtures'/'training'/'basketball_synthetic_v1_world.jsonl',rows)


def synthetic_f1_training():
    rng=np.random.default_rng(20261003);start=datetime(2024,1,1,12,tzinfo=UTC);rows=[];labels=['Norris','Verstappen','Leclerc','Other']
    weights={'position_advantage':1.12,'progress_position':2.25,'pace_advantage':.58,'reliability_log':.80,'wet_interaction':.64,'pit_penalty':.61,'tyre_penalty':.22,'penalty_penalty':.92,'context_adjustment':.51,'latent_skill':.48,'latent_form':.37,'latent_health':.20,'latent_experience':.13,'latent_potential':.10,'safety_car_position_relief':.16}
    for i in range(1200):
        dt=start+timedelta(days=i);progress=float(rng.uniform(0,.94));rain=float(rng.beta(1.4,4.8));sc=float(rng.random()<.12);base_skill=np.asarray([.55,.72,.61,.32])+rng.normal(0,.08,4);positions=np.argsort(np.argsort(-(base_skill+rng.normal(0,.35,4))))+1
        outcome_features={};scores=[]
        for j,label in enumerate(labels):
            pos_adv=1-2*(positions[j]-1)/3;pace_adv=float(np.clip(base_skill[j]+rng.normal(0,.35),-1.5,1.5));rel=float(np.clip(.96+rng.normal(0,.02),.82,.999));wet_skill=float(np.clip(base_skill[j]+rng.normal(0,.25),-1,1));pit=float(rng.choice([0,0,0,float(rng.uniform(.6,1.1))]));tyre=float(rng.uniform(0,35));pen=float(rng.choice([0,0,0,0,5,10]));ctx=float(rng.normal(.15*base_skill[j],.18));skill=float(np.clip(base_skill[j]+rng.normal(0,.12),-1,1));form=float(np.clip(.55*base_skill[j]+rng.normal(0,.25),-1,1));health=float(np.clip(.72+rng.normal(0,.12),-1,1));exp=float(np.clip(.45+.25*base_skill[j]+rng.normal(0,.18),-1,1));pot=float(np.clip(.50+.2*base_skill[j]+rng.normal(0,.2),-1,1))
            feats={'position_advantage':float(pos_adv),'progress_position':float(progress*pos_adv),'pace_advantage':pace_adv,'reliability_log':float(np.log(rel)+.02),'wet_interaction':rain*wet_skill,'pit_penalty':-pit,'tyre_penalty':-max(0,tyre-18)/30,'penalty_penalty':-pen/10,'context_adjustment':ctx,'latent_skill':skill,'latent_form':form,'latent_health':health,'latent_experience':exp,'latent_potential':pot,'safety_car_position_relief':sc*(-pos_adv)}
            outcome_features[label]=feats;scores.append(sum(weights[k]*feats[k] for k in weights))
        scores=np.asarray(scores);ex=np.exp(scores-scores.max());pr=ex/ex.sum();target=str(rng.choice(labels,p=pr));prediction=dt+timedelta(hours=float(rng.uniform(0,3)))
        rows.append({'event_id':f'f1-synth-{i:04d}','prediction_time':iso(prediction),'max_known_to_model_time':iso(prediction-timedelta(seconds=int(rng.integers(0,90)))),'competition':'synthetic_demo','feature_schema_version':'f1_features_v3_learned_world','outcome_features':outcome_features,'target_winner':target,'true_probabilities':{label:float(pr[j]) for j,label in enumerate(labels)}})
    write_jsonl(ROOT/'data'/'fixtures'/'training'/'f1_synthetic_v1_world.jsonl',rows)


def synthetic_latent_sequences():
    rng=np.random.default_rng(20261004)
    truth={
      'skill':(.997,.004,.085,30.0),'form':(.90,.05,.09,7.0),'health':(.78,.09,.075,7.0),
      'usage':(.88,.045,.08,7.0),'experience':(.999,.001,.10,30.0),'potential':(.994,.006,.12,30.0),
      'chemistry':(.96,.018,.095,14.0),'coaching':(.985,.012,.10,30.0)
    }
    rows=[]
    for dim,(phi,q,r,unit) in truth.items():
        for seq_id in range(48):
            length=int(rng.integers(12,25));x=float(rng.normal(0,.35));values=[float(np.clip(x+rng.normal(0,np.sqrt(r)),-1,1))];deltas=[0.0]
            for _ in range(1,length):
                dt=float(rng.choice([3,7,10,14,21]));a=phi**(dt/unit);x=a*x+rng.normal(0,np.sqrt(q*max(dt/unit,1e-6)));x=float(np.clip(x,-1,1));values.append(float(np.clip(x+rng.normal(0,np.sqrt(r)),-1,1)));deltas.append(dt)
            rows.append({'sequence_id':f'{dim}-{seq_id:03d}','dimension':dim,'values':values,'delta_days':deltas,'data_mode':'synthetic_demo'})
    write_jsonl(ROOT/'data'/'fixtures'/'training'/'latent_state_sequences_demo.jsonl',rows)


if __name__=='__main__': demo_events(); context_demo(); synthetic_training(); synthetic_basketball_training(); synthetic_f1_training(); synthetic_latent_sequences(); print('demo data written')
