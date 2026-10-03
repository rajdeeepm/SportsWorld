from __future__ import annotations

import hashlib, json
from datetime import datetime, timezone
from typing import Any

from sportsworld.schemas import Observation, SourceType, Sport


def normalize_observation(*,event_id:str,sport:Sport|str,kind:str,payload:dict[str,Any],source_id:str,source_type:SourceType|str,known_to_model_time:datetime,event_time:datetime|None=None,ingestion_time:datetime|None=None,confidence:float=1.0,sequence_no:int=0,source_url_or_ref:str|None=None,parser_version:str|None=None,raw_record_ref:str|None=None,verified:bool=True)->Observation:
    return Observation(event_id=event_id,sport=sport,kind=kind,payload=payload,source_id=source_id,source_type=source_type,source_url_or_ref=source_url_or_ref,confidence=confidence,event_time=event_time,known_to_model_time=known_to_model_time,ingestion_time=ingestion_time or datetime.now(timezone.utc),sequence_no=sequence_no,parser_version=parser_version,raw_record_ref=raw_record_ref,verified=verified)


def stable_source_ref(raw:Any)->str:
    blob=json.dumps(raw,sort_keys=True,default=str).encode(); return hashlib.sha256(blob).hexdigest()[:20]
