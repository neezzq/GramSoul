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

    def peek(self, key: str, limit: int, window_s: float) -> float | None:
        """Like check, but does not register a hit (register it with check once the action succeeded)."""
        now = time.monotonic()
        q = self._hits.get(key) or ()
        recent = [t for t in q if t > now - window_s]
        if len(recent) >= limit:
            return max(1.0, window_s - (now - recent[0]))
        return None

    def _gc(self, now: float) -> None:
        for k in list(self._hits.keys()):
            q = self._hits[k]
            if not q or q[-1] < now - 86400:
                del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()
