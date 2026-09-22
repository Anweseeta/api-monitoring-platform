"""Tiny in-memory sliding-window rate limiter for auth endpoints.

Not a distributed limiter — for a single-process deployment (the Render
target) it is enough to blunt credential-stuffing against /login and
mass-registration abuse. Counts are keyed by client IP.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.schemas.common import error_response

# endpoint -> (max_attempts, window_seconds)
_LIMITS: dict[str, tuple[int, int]] = {
    "login": (10, 60),
    "register": (10, 60),
}

_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(endpoint: str):
    max_attempts, window = _LIMITS[endpoint]

    async def _dependency(request: Request) -> None:
        # Disabled in the test environment so the suite can register/log in
        # freely; production and dev keep the brute-force protection.
        if get_settings().environment.strip().lower() == "test":
            return
        now = time.monotonic()
        key = f"{endpoint}:{_client_ip(request)}"
        hits = _hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_response(
                    "Too many attempts. Please wait a minute and try again.",
                    "RATE_LIMITED",
                ),
            )
        hits.append(now)

    return _dependency
