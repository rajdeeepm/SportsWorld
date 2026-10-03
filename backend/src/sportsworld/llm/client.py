"""OpenAI-compatible chat client for the self-hosted Llama 3.3 70B (vLLM on a self-hosted GPU server).

Every call requests schema-constrained JSON (vLLM guided decoding via `response_format:
json_schema`), validates the result again on our side, and never returns free text into
quantitative state. Failures raise; callers fall back to deterministic parsers.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from sportsworld.config import Settings


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings):
        self.base = (settings.llm_base_url or "").rstrip("/")
        self.key = settings.llm_api_key or "none"
        self.model = settings.llm_model
        self.enabled = bool(self.base) and settings.llm_provider != "deterministic"
        self.last_latency_ms: float | None = None

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        try:
            r = httpx.get(f"{self.base}/models", headers={"Authorization": f"Bearer {self.key}"}, timeout=3)
            return {"enabled": True, "ok": r.status_code == 200, "models": [m["id"] for m in r.json().get("data", [])]}
        except Exception as exc:
            return {"enabled": True, "ok": False, "error": str(exc)}

    def json_call(self, system: str, user: str, schema: dict, *, name: str = "output", max_tokens: int = 800, timeout: float = 120) -> dict:
        if not self.enabled:
            raise LLMUnavailable("LLM not configured (set LLM_PROVIDER=openai_compatible, LLM_BASE_URL)")
        body = {
            "model": self.model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
        }
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.base}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"}, timeout=timeout)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(str(exc)) from exc
        self.last_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        content = r.json()["choices"][0]["message"]["content"].strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(content)
