"""
Supabase client wrapper for the made. API.

Supabase provides:
- PostgreSQL (users, signals, journal, analytics)
- Row Level Security (RLS) for per-user data isolation
- Real-time subscriptions (used for journal updates)
- Auth (managed separately from our JWT layer)

The client is lazily initialised from environment variables.
If SUPABASE_URL or SUPABASE_KEY are not set, the client returns None and
all database-dependent routes fall back to dev/mock mode.
"""

from __future__ import annotations

import os
from typing import Generator, Optional

# supabase-py is synchronous — do NOT use await with its methods
try:
    from supabase import Client, create_client

    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore[misc,assignment]

_client: Optional["Client"] = None


def get_client() -> Optional["Client"]:
    """
    Get or create the Supabase client singleton.

    Returns None if SUPABASE_URL / SUPABASE_KEY env vars are not set,
    or if the supabase package is not installed. Callers must handle None
    gracefully and return mock/empty data in that case.

    Note: supabase-py is synchronous. Never await Supabase calls.
    """
    global _client

    if not _SUPABASE_AVAILABLE:
        return None

    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if url and key:
            _client = create_client(url, key)

    return _client


def get_db() -> Generator[Optional["Client"], None, None]:
    """
    FastAPI dependency that yields the Supabase client.

    Usage in route handlers:
        @router.get("/items")
        def list_items(db: Client | None = Depends(get_db)):
            if db is None:
                return []  # dev mode fallback
            result = db.table("items").select("*").execute()
            return result.data

    Yields:
        Supabase Client if configured, else None (dev mode).
    """
    yield get_client()


def is_configured() -> bool:
    """Return True if Supabase credentials are available."""
    return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY"))
