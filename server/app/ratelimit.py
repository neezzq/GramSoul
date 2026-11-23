"""Small in-memory sliding-window rate limiter (the API runs as one process)."""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: float) -> float | None:
        """Register a hit. Returns ``None`` when allowed, otherwise seconds to wait."""
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            return max(1.0, window_s - (now - q[0]))
        q.append(now)
        if len(self._hits) > 50_000:  # crude memory guard
            self._gc(now)
        return None

    def _gc(self, now: float) -> None:
        for k in list(self._hits.keys()):
            q = self._hits[k]
            if not q or q[-1] < now - 86400:
                del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()
