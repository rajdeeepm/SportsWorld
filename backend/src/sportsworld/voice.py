from __future__ import annotations

import httpx
from sportsworld.config import Settings


class ElevenLabsVoice:
    def __init__(self,settings:Settings): self.settings=settings
    @property
    def enabled(self): return bool(self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id)
    def synthesize(self,text:str)->bytes:
        if not self.enabled: raise RuntimeError('ElevenLabs is not configured')
        url=f'https://api.elevenlabs.io/v1/text-to-speech/{self.settings.elevenlabs_voice_id}'
        headers={'xi-api-key':self.settings.elevenlabs_api_key,'Content-Type':'application/json'}
        r=httpx.post(url,headers=headers,json={'text':text,'model_id':'eleven_multilingual_v2'},timeout=20); r.raise_for_status(); return r.content
