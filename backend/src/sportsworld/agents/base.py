from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from sportsworld.schemas import Observation


@dataclass
class AgentStatus:
    name:str
    healthy:bool=True
    last_error:str|None=None
    emitted:int=0


class ObservationAgent(ABC):
    def __init__(self,name:str): self.status=AgentStatus(name)
    @abstractmethod
    async def observations(self)->AsyncIterator[Observation]: ...
