import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class LimitRule:
    max_requests: int
    window_seconds: int


TRUST_X_FORWARDED_FOR = os.getenv("TRUST_X_FORWARDED_FOR", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def enforce(self, scope: str, identifier: str, rule: LimitRule) -> None:
        key = f"{scope}:{identifier}"
        now = time.time()
        window_start = now - rule.window_seconds

        with self._lock:
            events = self._events[key]
            while events and events[0] < window_start:
                events.popleft()

            if len(events) >= rule.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Retry after {rule.window_seconds} seconds.",
                )

            events.append(now)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if TRUST_X_FORWARDED_FOR and forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    return request.client.host if request.client else "unknown"


rate_limiter = RateLimiter()

AUTH_LOGIN_LIMIT = LimitRule(max_requests=8, window_seconds=60)
AUTH_REGISTER_LIMIT = LimitRule(max_requests=5, window_seconds=60)
CATALOG_LIMIT = LimitRule(max_requests=120, window_seconds=60)
SEARCH_LIMIT = LimitRule(max_requests=160, window_seconds=60)
CART_LIMIT = LimitRule(max_requests=120, window_seconds=60)
RECOMMEND_LIMIT = LimitRule(max_requests=180, window_seconds=60)
TRACK_VIEW_LIMIT = LimitRule(max_requests=30, window_seconds=60)
ADMIN_LIMIT = LimitRule(max_requests=60, window_seconds=60)
