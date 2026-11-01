"""Per-key in-memory rate limiter.

Thread-safe because FastAPI runs sync route handlers in a worker pool.
Not distributed — a single process's memory is the limiter state. A
multi-worker deployment needs a shared store (Redis); documented as a
known limitation.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def check(key: str, *, limit: int, window_seconds: int = 60) -> bool:
    """Record one attempt for `key`. Returns False if the key is over the limit.

    The failed attempt still counts toward the limit — brute-force resistance
    doesn't reset on every guess.
    """
    now = monotonic()
    cutoff = now - window_seconds
    with _lock:
        q = _windows[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def clear() -> None:
    """Reset all limiter state. Used by tests."""
    with _lock:
        _windows.clear()