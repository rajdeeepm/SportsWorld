from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class FixedWindowRateLimiter:
    """Small dependency-free per-client limiter for expensive demo endpoints.

    Production deployments can swap this for Redis/API Gateway limits without
    changing the route contract. The in-process limiter is intentionally simple
    and deterministic enough for a single-instance hackathon deployment.
    """

    def __init__(self, limit: int = 20, window_seconds: float = 60.0):
        self.limit = int(limit)
        self.window_seconds = float(window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.RLock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(retry_after)})
            q.append(now)

    def dependency(self, request: Request) -> bool:
        client = request.client.host if request.client else "unknown"
        self.check(client)
        return True
