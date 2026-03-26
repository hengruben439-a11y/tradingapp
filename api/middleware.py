"""
FastAPI middleware for the made. API.

Middleware stack (applied in reverse order — last added = outermost):
1. RequestLoggingMiddleware — logs method, path, status, duration
2. RateLimitMiddleware — 100 req/min (public) / 1000 req/min (authenticated)

Rate limiting uses a simple in-memory sliding window counter per IP.
For production at scale, replace with Redis-backed rate limiting.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ── Rate limiting constants ───────────────────────────────────────────────────
_PUBLIC_LIMIT = 100     # requests per minute for unauthenticated IPs
_AUTH_LIMIT = 1000      # requests per minute for authenticated IPs
_WINDOW_SECONDS = 60    # Sliding window size


def _get_client_ip(request: Request) -> str:
    """
    Extract client IP from request headers.

    Respects X-Forwarded-For (set by AWS ALB / CloudFront) to get the real
    client IP behind a load balancer or CDN.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_authenticated(request: Request) -> bool:
    """Check if the request carries an Authorization Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    return auth_header.lower().startswith("bearer ")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory sliding window rate limiter.

    - Public endpoints: 100 requests/minute per IP
    - Authenticated endpoints: 1000 requests/minute per IP
    - WebSocket connections are exempt (they use a persistent connection model)
    - Health check and root endpoints are exempt

    Response on limit exceeded: 429 Too Many Requests with Retry-After header.
    """

    _EXEMPT_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Deque of request timestamps per IP: {ip: deque([timestamp, ...])}
        self._timestamps: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Exempt WebSocket upgrades and specific paths
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        ip = _get_client_ip(request)
        limit = _AUTH_LIMIT if _is_authenticated(request) else _PUBLIC_LIMIT
        now = time.time()
        window_start = now - _WINDOW_SECONDS

        timestamps = self._timestamps[ip]

        # Remove timestamps outside the sliding window
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = int(_WINDOW_SECONDS - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured request/response logging.

    Logs: method, path, query string, status code, and duration (ms).
    Uses INFO level for 2xx/3xx, WARNING for 4xx, ERROR for 5xx.
    WebSocket upgrades are logged at DEBUG level only.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip verbose logging for WebSocket upgrades
        is_ws = request.headers.get("upgrade", "").lower() == "websocket"
        if is_ws:
            logger.debug("WS upgrade: %s", request.url.path)
            return await call_next(request)

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s %s — ERROR %.1fms — %s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        status_code = response.status_code

        # Choose log level based on status code
        if status_code >= 500:
            log_fn = logger.error
        elif status_code >= 400:
            log_fn = logger.warning
        else:
            log_fn = logger.info

        query = f"?{request.url.query}" if request.url.query else ""
        log_fn(
            "%s %s%s → %d (%.1fms)",
            request.method,
            request.url.path,
            query,
            status_code,
            duration_ms,
        )

        return response
