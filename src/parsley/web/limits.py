"""Limits of a public deployment, read from the environment.

The site spends its owner's API key, so model calls are limited three ways: requests per address
and minute, calls per session, and calls per UTC day across the server. Reaching one never fails
a request: ``LimitedProvider`` refuses the call, and the pipeline keeps the rule result with
``W515``. Only the hard rate, which is far above normal use, answers ``429``.

Every count lives in this one process, so a restart clears it: a host that sleeps when idle
gets a new daily budget each time it wakes (docs/DEPLOY.md). A malformed value stops the server
at start, because a limit that is silently ignored protects nothing.
"""

from __future__ import annotations

import datetime
import ipaddress
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from parsley.web.sessions import DEFAULT_CAPACITY, DEFAULT_TTL, WebSession

DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
WINDOW = 60.0  # seconds
MAX_ADDRESSES = 10_000
MAX_HITS = 10_000  # per address; a count only has to reach the hard limit
UNKNOWN_ADDRESS = "unknown"

TOO_FAST = "too many requests from this address"
SESSION_SPENT = "this session has used its LLM allowance"
DAY_SPENT = "the daily LLM allowance is used up"


def _whole(environ: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    text = environ.get(name, "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"{name} must be a whole number") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _origins(environ: Mapping[str, str]) -> tuple[str, ...]:
    origins = tuple(o.strip() for o in environ.get("PARSLEY_ALLOWED_ORIGINS", "").split(",") if o.strip())
    for origin in origins:
        parts = urlsplit(origin)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.path:
            raise ValueError(f"PARSLEY_ALLOWED_ORIGINS holds {origin!r}, which is not an origin like https://host")
    return origins or DEFAULT_ORIGINS


@dataclass(frozen=True)
class WebLimits:
    soft_rate: int = 20  # requests a minute per address; above this, no model calls
    hard_rate: int = 120  # requests a minute per address; above this, 429
    daily_llm_calls: int = 500
    session_llm_calls: int = 50
    max_sessions: int = DEFAULT_CAPACITY
    session_ttl: float = DEFAULT_TTL
    allowed_origins: tuple[str, ...] = DEFAULT_ORIGINS
    client_ip_header: str | None = None  # only a header the host itself sets can be trusted
    frame_ancestors: str = "'none'"

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> WebLimits:
        return cls(
            soft_rate=_whole(environ, "PARSLEY_RATE_LIMIT_PER_MINUTE", cls.soft_rate),
            hard_rate=_whole(environ, "PARSLEY_HARD_RATE_LIMIT_PER_MINUTE", cls.hard_rate, 1),
            daily_llm_calls=_whole(environ, "PARSLEY_LLM_DAILY_CAP", cls.daily_llm_calls),
            session_llm_calls=_whole(environ, "PARSLEY_LLM_SESSION_CAP", cls.session_llm_calls),
            max_sessions=_whole(environ, "PARSLEY_MAX_SESSIONS", cls.max_sessions, 1),
            session_ttl=_whole(environ, "PARSLEY_SESSION_TTL", int(cls.session_ttl), 1),
            allowed_origins=_origins(environ),
            client_ip_header=environ.get("PARSLEY_CLIENT_IP_HEADER", "").strip() or None,
            frame_ancestors=environ.get("PARSLEY_FRAME_ANCESTORS", "").strip() or cls.frame_ancestors,
        )


def client_ip(request: Any, header: str | None) -> str:
    """The address to count: ``header``'s last entry if it is an address, else the socket's.

    Only the last entry of a list was written by the nearest proxy; a client can put anything
    in front of it. Without a configured header nothing the client sends is believed.
    """
    if header:
        value = request.headers.get(header.lower(), "").rsplit(",", 1)[-1].strip()
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.client.host if request.client else UNKNOWN_ADDRESS


class RateLimiter:
    """Requests per address in a sliding window, in bounded memory."""

    def __init__(
        self, window: float = WINDOW, max_addresses: int = MAX_ADDRESSES, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window
        self._max_addresses = max_addresses
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._hits)

    def hit(self, address: str) -> int:
        """Record one request; how many ``address`` made in the window, this one included."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(address)
            if hits is None:
                self._make_room(now)
                hits = self._hits[address] = deque(maxlen=MAX_HITS)
            while hits and now - hits[0] > self._window:
                hits.popleft()
            hits.append(now)
            return len(hits)

    def _make_room(self, now: float) -> None:
        if len(self._hits) < self._max_addresses:
            return
        for stale in [a for a, hits in self._hits.items() if now - hits[-1] > self._window]:
            del self._hits[stale]
        while len(self._hits) >= self._max_addresses:
            del self._hits[next(iter(self._hits))]  # the address seen first


def _utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


class DailyBudget:
    """Model calls left today, across the server; a new UTC day starts again."""

    def __init__(self, cap: int, today: Callable[[], datetime.date] = _utc_today) -> None:
        self._cap = cap
        self._today = today
        self._day = today()
        self._spent = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        if (day := self._today()) != self._day:
            self._day, self._spent = day, 0

    def remaining(self) -> bool:
        with self._lock:
            self._roll()
            return self._spent < self._cap

    def take(self) -> bool:
        """Spend one call, if one is left."""
        with self._lock:
            self._roll()
            if self._spent >= self._cap:
                return False
            self._spent += 1
            return True


@dataclass(frozen=True)
class LimitedProvider:
    """``inner`` for one request: refuses the call when a limit says so.

    Sits around the provider because only a sentence the rules could not settle reaches the
    model, so a limit is spent or hit only when a call would really happen.
    """

    inner: Any
    budget: DailyBudget
    web: WebSession
    session_cap: int
    too_fast: bool

    @property
    def name(self) -> str:
        return self.inner.name

    def propose(self, sentence: str, context: Any) -> Any:
        from parsley.llm.provider import ProviderLimited

        if self.too_fast:
            raise ProviderLimited(TOO_FAST)
        if self.web.llm_calls >= self.session_cap:
            raise ProviderLimited(SESSION_SPENT)
        if not self.budget.take():
            raise ProviderLimited(DAY_SPENT)
        self.web.llm_calls += 1  # the caller holds the session's lock
        return self.inner.propose(sentence, context)
