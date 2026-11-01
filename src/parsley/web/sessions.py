"""In-memory web sessions with a time-to-live and a cap.

Nothing is persisted. A session unused for ``ttl`` seconds is gone, and at ``capacity`` the
least recently used one makes room. ``WebSession.lock`` serializes the requests of one
session, because a model call can take seconds and FastAPI runs handlers on a thread pool.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from parsley.pipeline import PipelineResult
from parsley.session import Session

DEFAULT_TTL = 3600.0  # seconds
DEFAULT_CAPACITY = 1000


@dataclass
class WebSession:
    """One browser session: the compiler session, plus what the API must remember around it."""

    id: str
    used_at: float
    session: Session = field(default_factory=Session)
    statements: list[str] = field(default_factory=list)  # the English of each accepted statement
    pending: PipelineResult | None = None  # the open question
    pending_sentence: str = ""
    mode: str = "rules"
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    def __init__(
        self, ttl: float = DEFAULT_TTL, capacity: int = DEFAULT_CAPACITY, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._capacity = capacity
        self._clock = clock
        self._sessions: dict[str, WebSession] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._sessions)

    def create(self) -> WebSession:
        now = self._clock()
        with self._lock:
            for expired in [s.id for s in self._sessions.values() if self._is_expired(s, now)]:
                del self._sessions[expired]
            while len(self._sessions) >= self._capacity:
                del self._sessions[min(self._sessions.values(), key=lambda s: s.used_at).id]
            web = WebSession(secrets.token_urlsafe(32), now)
            self._sessions[web.id] = web
            return web

    def get(self, session_id: str) -> WebSession | None:
        """The live session, renewed; None if it is unknown or has expired."""
        now = self._clock()
        with self._lock:
            web = self._sessions.get(session_id)
            if web is None:
                return None
            if self._is_expired(web, now):
                del self._sessions[session_id]
                return None
            web.used_at = now
            return web

    def touch(self, web: WebSession) -> None:
        """Renew a session after a request that may have outlasted the time-to-live."""
        web.used_at = self._clock()

    def _is_expired(self, web: WebSession, now: float) -> bool:
        return now - web.used_at > self._ttl and not web.lock.locked()  # busy: a model call is running
