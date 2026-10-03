from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Any
from uuid import uuid4

from fastapi import WebSocket
from sportsworld.schemas import WSMessage


class WebSocketHub:
    def __init__(self,history_size:int=250):
        self.clients:dict[str,set[WebSocket]]=defaultdict(set); self.history:dict[str,deque[WSMessage]]=defaultdict(lambda:deque(maxlen=history_size)); self.seq:dict[str,int]=defaultdict(int); self._loop:asyncio.AbstractEventLoop|None=None
    def bind_loop(self):
        try:self._loop=asyncio.get_running_loop()
        except RuntimeError:pass
    async def connect(self,event_id:str,ws:WebSocket,last_seen_sequence:int=0):
        await ws.accept(); self.clients[event_id].add(ws)
        for m in self.history[event_id]:
            if m.sequence>last_seen_sequence: await ws.send_json(m.model_dump(mode='json'))
    def disconnect(self,event_id:str,ws:WebSocket): self.clients[event_id].discard(ws)
    async def broadcast(self,event_id:str,msg_type:str,payload:dict[str,Any]):
        self.seq[event_id]+=1; state_version=payload.get('state_version') or payload.get('forecast',{}).get('state_version') or payload.get('state',{}).get('state_version')
        msg=WSMessage(type=msg_type,event_id=event_id,sequence=self.seq[event_id],state_version=state_version,payload=payload); self.history[event_id].append(msg)
        dead=[]
        for ws in list(self.clients[event_id]):
            try: await ws.send_json(msg.model_dump(mode='json'))
            except Exception: dead.append(ws)
        for ws in dead:self.disconnect(event_id,ws)
    def publish_sync(self,event_id:str,msg_type:str,payload:dict[str,Any]):
        if self._loop and self._loop.is_running(): self._loop.create_task(self.broadcast(event_id,msg_type,payload))
