from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator
from sportsworld.agents.base import ObservationAgent
from sportsworld.schemas import Observation


class ReplayAgent(ObservationAgent):
    def __init__(self,path:Path,speed:float=20.0): super().__init__(f'replay:{path.name}'); self.path=path; self.speed=speed
    async def observations(self)->AsyncIterator[Observation]:
        records=[Observation.model_validate_json(x) for x in self.path.read_text().splitlines() if x.strip()]
        previous=None
        for obs in records:
            if previous is not None: await asyncio.sleep(max(.02,min(1.0,(obs.known_to_model_time-previous).total_seconds()/max(self.speed,.1))))
            previous=obs.known_to_model_time; self.status.emitted+=1; yield obs
