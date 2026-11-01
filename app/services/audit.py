"""In-memory audit ring buffer for the /admin/v1/audit endpoint.

Not durable across restarts — documented as a known limitation. Production
would persist to a table or ship events to an external sink; the in-memory
buffer is enough to satisfy the design contract for this exercise.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock

_MAX_EVENTS = 1000

_events: deque[dict] = deque(maxlen=_MAX_EVENTS)
_lock = Lock()


def record(event: str, *, actor_id: int | None = None, **fields: object) -> None:
    """Record one audit event. Thread-safe, bounded."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "actor_id": actor_id,
        **fields,
    }
    with _lock:
        _events.append(entry)


def recent(limit: int = 100) -> list[dict]:
    """Return the most recent events, newest last. Thread-safe."""
    with _lock:
        return list(_events)[-limit:]


def clear() -> None:
    """Wipe the buffer. Used by tests."""
    with _lock:
        _events.clear()