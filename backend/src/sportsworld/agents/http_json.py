from __future__ import annotations

import asyncio
from datetime import datetime
from typing import AsyncIterator, Callable

import httpx
from sportsworld.agents.base import ObservationAgent
from sportsworld.schemas import Observation


class HTTPJSONAgent(ObservationAgent):
    '''Generic bounded collector used by Stats/Weather/Timing source adapters.'''
    def __init__(self,name:str,url:str,parser:Callable[[dict,datetime],list[Observation]],poll_seconds:float=15.0,timeout:float=5.0):
        super().__init__(name); self.url=url; self.parser=parser; self.poll_seconds=poll_seconds; self.timeout=timeout
    async def observations(self)->AsyncIterator[Observation]:
        seen=set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                try:
                    r=await client.get(self.url); r.raise_for_status();
                    from datetime import timezone
                    now=datetime.now(timezone.utc)
                    for obs in self.parser(r.json(),now):
                        if obs.dedupe_key in seen: continue
                        seen.add(obs.dedupe_key); self.status.emitted+=1; yield obs
                    self.status.healthy=True; self.status.last_error=None
                except Exception as exc:
                    self.status.healthy=False; self.status.last_error=str(exc)
                await asyncio.sleep(self.poll_seconds)
