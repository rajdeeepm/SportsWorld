from __future__ import annotations

import json,re
import httpx

from sportsworld.config import Settings
from sportsworld.schemas import ScenarioOperation, ScenarioParseResult, Sport, WorldState


class ScenarioParser:
    def __init__(self,settings:Settings): self.settings=settings

    def parse(self,text:str,state:WorldState)->ScenarioParseResult:
        # Deterministic, validated parser first; the LLM only handles phrasings the rules do not recognise,
        # and its output is schema-constrained to operation kinds the sport adapter actually supports.
        rules=self._parse_rules(text,state)
        if rules.operations or self.settings.llm_provider=='deterministic' or not self.settings.llm_base_url:
            return rules
        try:
            llm=self._parse_llm(text,state)
            if llm.operations: return llm
            rules.warnings.append('LLM produced no supported operation')
        except Exception as exc:
            rules.warnings.append(f'LLM parser unavailable or invalid output; deterministic parser used: {exc}')
        return rules

    def _parse_rules(self,text:str,state:WorldState)->ScenarioParseResult:
        low=text.lower(); ops=[]; warnings=[]
        if state.sport==Sport.F1:
            if 'rain' in low:
                m=re.search(r'lap\s*(\d+)',low); ops.append(ScenarioOperation(kind='weather',payload={'rain_probability':0.85},effective_lap=int(m.group(1)) if m else None))
            if 'pit' in low:
                driver=next((d for d in state.outcomes if d.lower() in low),state.outcomes[0]); m=re.search(r'lap\s*(\d+)',low)
                ops.append(ScenarioOperation(kind='pit_stop',payload={'driver':driver,'new_compound':'INTERMEDIATE' if 'rain' in low else 'MEDIUM','pit_duration_s':22.5,'rejoin_position':max(2,int(state.features.get('drivers',{}).get(driver,{}).get('position',1))+2)},effective_lap=int(m.group(1)) if m else None))
            if 'safety car' in low: ops.append(ScenarioOperation(kind='safety_car',payload={'active':True}))
        elif state.sport==Sport.FOOTBALL:
            team='home' if any(x in low for x in ['home','michigan']) else 'away' if 'away' in low else 'home'
            if any(x in low for x in ['qb','quarterback']) and any(x in low for x in ['out','injur','leaves','leave']): ops.append(ScenarioOperation(kind='injury_status',payload={'team':team,'role':'starting_qb','status':'out','impact':-0.18}))
            if 'rain' in low: ops.append(ScenarioOperation(kind='weather',payload={'severity':0.8}))
            if 'turnover' in low: ops.append(ScenarioOperation(kind='turnover',payload={'possession':'away' if team=='home' else 'home'}))
        elif state.sport==Sport.BASKETBALL:
            team='home' if 'away' not in low else 'away'
            if any(x in low for x in ['star','player']) and any(x in low for x in ['out','unavailable','injur']): ops.append(ScenarioOperation(kind='availability',payload={'team':team,'status':'out','impact':-0.2}))
            if 'pace' in low: ops.append(ScenarioOperation(kind='pace',payload={'pace':112.0 if any(x in low for x in ['increase','faster','fast']) else 92.0}))
        if not ops: warnings.append('No supported scenario operation was recognized; use typed controls or mention rain, pit, QB injury, turnover, star unavailable, or pace.')
        return ScenarioParseResult(text=text,operations=ops,parser='deterministic-rules-v1',warnings=warnings)

    def _parse_llm(self,text:str,state:WorldState)->ScenarioParseResult:
        from sportsworld.llm.client import LLMClient
        from sportsworld.sports import BasketballAdapter,F1Adapter,FootballAdapter,HockeyAdapter
        adapter={Sport.FOOTBALL:FootballAdapter,Sport.BASKETBALL:BasketballAdapter,Sport.F1:F1Adapter,Sport.HOCKEY:HockeyAdapter}[state.sport]()
        kinds=sorted(adapter.supported_observation_kinds()-{'correction','team_state','driver_state','game_end','race_end','score_state','race_state'})
        sides=state.metadata.get('display_outcomes') or {o:o for o in state.outcomes}
        schema={'type':'object','properties':{'operations':{'type':'array','items':{'type':'object','properties':{
            'kind':{'type':'string','enum':kinds},'team':{'type':['string','null'],'enum':list(state.outcomes)+[None]},
            'role':{'type':['string','null']},'status':{'type':['string','null'],'enum':['out','questionable','limited','available',None]},
            'effective_lap':{'type':['integer','null']}},'required':['kind'],'additionalProperties':False}}},
            'required':['operations'],'additionalProperties':False}
        system=('Convert a hypothetical sports scenario into typed operations. Use only the allowed kinds. '
                f'Teams: {json.dumps(sides)} (use the key, e.g. "home"). Never predict outcomes or invent facts.')
        data=LLMClient(self.settings).json_call(system,json.dumps({'text':text,'sport':state.sport.value}),schema,name='event_scenario',max_tokens=300)
        ops=[]
        for x in data.get('operations',[]):
            if x.get('kind') not in kinds: continue
            payload={k:v for k,v in {'team':x.get('team'),'role':x.get('role'),'status':x.get('status')}.items() if v is not None}
            ops.append(ScenarioOperation(kind=x['kind'],payload=payload,effective_lap=x.get('effective_lap')))
        return ScenarioParseResult(text=text,operations=ops,parser=f'llm:{self.settings.llm_model}',warnings=['LLM-structured operation: confirm before simulating'])
