"""
Redis async client for the made. API.

Redis is used for:
- Signal pub/sub broadcasting to WebSocket clients (<10ms latency requirement)
- Engine state checkpointing (market structure FSM, active OBs, FVGs)
- Live signal caching (faster than Supabase for real-time reads)

Uses redis.asyncio for non-blocking I/O within FastAPI's async event loop.
"""

from __future__ import annotations

import json
import os
from typing import Optional

try:
    import redis.asyncio as aioredis

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    aioredis = None  # type: ignore[assignment]

_redis: Optional[object] = None

# Channel names — keep in sync with the signal engine publisher
SIGNALS_CHANNEL = "signals"
ENGINE_HEARTBEAT_CHANNEL = "engine:heartbeat"


async def get_redis() -> Optional[object]:
    """
    Get or create the async Redis client singleton.

    Returns None if the redis package is not installed or if the connection
    cannot be established. Callers must handle None gracefully.

    The client is lazily created on first call and reused thereafter.
    REDIS_URL defaults to localhost for local development.
    """
    global _redis

    if not _REDIS_AVAILABLE:
        return None

    if _redis is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis = aioredis.from_url(url, decode_responses=True)

    return _redis


async def publish_signal(signal_dict: dict) -> None:
    """
    Publish a signal event to the Redis pub/sub channel.

    The signal engine calls this on each new signal. WebSocket clients
    subscribed via the /ws endpoint receive it in near real-time.

    Args:
        signal_dict: Signal data as a serialisable dictionary.

    Silently no-ops if Redis is unavailable (dev mode without Redis).
    """
    r = await get_redis()
    if r is None:
        return
    await r.publish(SIGNALS_CHANNEL, json.dumps(signal_dict, default=str))


async def cache_signal(signal_id: str, signal_dict: dict, ttl_seconds: int = 3600) -> None:
    """
    Cache a signal in Redis for fast reads.

    Signals expire from the cache after ttl_seconds (default 1 hour).
    The Supabase DB remains the persistent store; Redis is the hot path.

    Args:
        signal_id: Unique signal identifier (UUID).
        signal_dict: Signal data as a serialisable dictionary.
        ttl_seconds: Time-to-live in seconds.
    """
    r = await get_redis()
    if r is None:
        return
    key = f"signal:{signal_id}"
    await r.setex(key, ttl_seconds, json.dumps(signal_dict, default=str))


async def get_cached_signal(signal_id: str) -> Optional[dict]:
    """
    Retrieve a cached signal from Redis.

    Args:
        signal_id: Unique signal identifier.

    Returns:
        Signal dict if found in cache, else None.
    """
    r = await get_redis()
    if r is None:
        return None
    raw = await r.get(f"signal:{signal_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def delete_cached_signal(signal_id: str) -> None:
    """Remove a signal from the Redis cache (e.g. on expiry or SL hit)."""
    r = await get_redis()
    if r is None:
        return
    await r.delete(f"signal:{signal_id}")


async def close_redis() -> None:
    """Close the Redis connection gracefully on application shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
