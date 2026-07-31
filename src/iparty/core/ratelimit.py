"""Dependency-free in-process rate limiter (token bucket).

Sufficient for the first-100-users, single-instance deployment. At multi-
instance scale, replace with a shared store (Redis) behind the same allow()."""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, rate_per_min: float, burst: int) -> bool:
        now = time.monotonic()
        refill = rate_per_min / 60.0
        with self._lock:
            tokens, last = self._buckets.get(key, (float(burst), now))
            tokens = min(float(burst), tokens + (now - last) * refill)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > 100_000:      # bound memory
                self._buckets = dict(list(self._buckets.items())[-50_000:])
            return True


limiter = RateLimiter()


def client_key(request) -> str:
    """Best-effort client identity behind a proxy (Render sets X-Forwarded-For)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
