from __future__ import annotations

import asyncio, json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sportsworld.schemas import Observation


@dataclass
class ReplaySession:
    event_id: str
    observations: list[Observation]
    cursor: int = 0
    speed: float = 5.0
    playing: bool = False
    task: asyncio.Task | None = None


class ReplayManager:
    def __init__(self, engine, replay_dir: Path, notify: Callable[[str,str,dict],None] | None=None):
        self.engine=engine; self.replay_dir=replay_dir; self.notify=notify; self.sessions: dict[str,ReplaySession]={}

    def load(self,event_id:str,file_name:str|None=None)->ReplaySession:
        path=self.replay_dir/(file_name or f"{event_id}.jsonl")
        observations=[]
        for line in path.read_text().splitlines():
            if line.strip(): observations.append(Observation.model_validate_json(line))
        self.sessions[event_id]=ReplaySession(event_id,observations); return self.sessions[event_id]

    def status(self,event_id:str)->dict:
        s=self.sessions[event_id]; return {"event_id":event_id,"cursor":s.cursor,"total":len(s.observations),"speed":s.speed,"playing":s.playing}

    async def step(self,event_id:str,count:int=1)->dict:
        s=self.sessions[event_id]
        for _ in range(count):
            if s.cursor>=len(s.observations): s.playing=False; break
            self.engine.ingest(s.observations[s.cursor]); s.cursor+=1
        st=self.status(event_id)
        if self.notify:self.notify(event_id,"replay.status",st)
        return st

    async def _play(self,event_id:str):
        s=self.sessions[event_id]; s.playing=True
        while s.playing and s.cursor<len(s.observations):
            before=s.observations[s.cursor-1].known_to_model_time if s.cursor>0 else s.observations[s.cursor].known_to_model_time
            current=s.observations[s.cursor].known_to_model_time
            wait=max(0.03,min(2.0,(current-before).total_seconds()/max(s.speed,0.1)))
            await self.step(event_id,1); await asyncio.sleep(wait)
        s.playing=False

    def play(self,event_id:str,speed:float=5.0):
        s=self.sessions[event_id]; s.speed=speed
        if s.task and not s.task.done(): return
        s.task=asyncio.create_task(self._play(event_id))

    def pause(self,event_id:str): self.sessions[event_id].playing=False

    def reset(self,event_id:str):
        s=self.sessions[event_id]; s.playing=False; self.engine.store.clear_event_runtime(event_id); self.engine._recent_drivers.pop(event_id,None); s.cursor=0
        base=self.engine.store.get_state(event_id,0); f=self.engine.forecast_state(base); self.engine.store.save_forecast(f)
        return self.status(event_id)
