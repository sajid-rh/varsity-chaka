"""A small in-memory limiter for failed login attempts.

Good enough for a single-process prototype. Limitations (state these in the report):
the counters live in memory, so they reset when the server restarts and are not
shared between several server processes. A production system would keep them in Redis.
"""
import math
import threading
import time


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        now = self._clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_seconds]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked_for(self, key: str) -> int:
        """Seconds the caller must still wait, or 0 if the key is not blocked."""
        with self._lock:
            recent = self._recent(key)
            if len(recent) < self.max_attempts:
                return 0
            return max(1, math.ceil(self.window_seconds - (self._clock() - recent[0])))

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._failures.setdefault(key, []).append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginRateLimiter()
