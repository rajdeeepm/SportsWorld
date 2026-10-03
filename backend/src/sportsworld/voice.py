from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from sportsworld.config import Settings

# ElevenLabs premade voice that works on every plan; used when the configured voice is not available on this account
FALLBACK_VOICE = "JBFqnCBsd6RMkjVDRZzb"


class ElevenLabsVoice:
    def __init__(self, settings: Settings, cache_dir: Path | None = None):
        self.settings = settings
        self.cache_dir = cache_dir
        self.voice_id = settings.elevenlabs_voice_id or FALLBACK_VOICE
        self.last_error: str | None = None

    @property
    def enabled(self):
        return bool(self.settings.elevenlabs_api_key)

    def synthesize(self, text: str) -> bytes:
        if not self.enabled:
            raise RuntimeError("ElevenLabs is not configured")
        key = hashlib.sha1(f"{self.voice_id}|{text}".encode()).hexdigest()
        cached = self.cache_dir / f"{key}.mp3" if self.cache_dir else None
        if cached and cached.exists():
            return cached.read_bytes()
        audio = self._tts(text, self.voice_id)
        if audio is None and self.voice_id != FALLBACK_VOICE:  # e.g. a library voice on a free plan
            self.voice_id = FALLBACK_VOICE
            audio = self._tts(text, self.voice_id)
        if audio is None:
            raise RuntimeError(self.last_error or "ElevenLabs synthesis failed")
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{hashlib.sha1(f'{self.voice_id}|{text}'.encode()).hexdigest()}.mp3").write_bytes(audio)
        return audio

    def _tts(self, text: str, voice: str) -> bytes | None:
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                       headers={"xi-api-key": self.settings.elevenlabs_api_key, "Content-Type": "application/json"},
                       json={"text": text, "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}},
                       timeout=40)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio"):
            return r.content
        self.last_error = f"{r.status_code}: {r.text[:160]}"
        return None
