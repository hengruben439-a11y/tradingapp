"""
made. API — FastAPI application entry point.

Serves the iOS app, Telegram bot, and signal engine webhooks.

Start locally:
    uvicorn api.main:app --reload --port 8000

Environment variables (see .env.example):
    SUPABASE_URL        — Supabase project URL
    SUPABASE_KEY        — Supabase service role key (never expose to clients)
    REDIS_URL           — Redis connection URL (default redis://localhost:6379)
    JWT_SECRET          — JWT signing secret (MUST be set in production)
    TRADING_ECONOMICS_KEY — TradingEconomics API key for calendar data
    INTERNAL_API_KEY    — API key for engine → API communication
    ENVIRONMENT         — "development" | "production" (default: development)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from api.redis_client import close_redis, get_redis
from api.routes import analytics, auth, broker, calendar, ea, journal, signals
from api.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_ENV = os.getenv("ENVIRONMENT", "development")
_IS_PROD = _ENV == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — startup and shutdown hooks."""
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("made. API starting (environment=%s)", _ENV)

    # Pre-warm Redis connection so the first WebSocket client doesn't wait
    redis = await get_redis()
    if redis is not None:
        logger.info("Redis connection established")
    else:
        logger.warning(
            "Redis unavailable — WebSocket signal streaming and caching disabled"
        )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("made. API shutting down")
    await close_redis()
    logger.info("Redis connection closed")


# ── Application factory ───────────────────────────────────────────────────────

app = FastAPI(
    title="made. API",
    description=(
        "Intelligent Trading Signal & Analysis Platform — XAUUSD · GBPJPY. "
        "Confluence-scored signals powered by ICT Smart Money Concepts + classical TA."
    ),
    version="1.0.0",
    docs_url="/docs" if not _IS_PROD else None,
    redoc_url="/redoc" if not _IS_PROD else None,
    openapi_url="/openapi.json" if not _IS_PROD else None,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Dev: allow all origins so the React Native metro bundler and Expo go can connect.
# Prod: lock down to the app's specific origins.
if _IS_PROD:
    _allowed_origins = [
        "https://made.app",
        "https://app.made.app",
        # Add Expo EAS build origins if using OTA updates
    ]
else:
    _allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Custom middleware (added after CORS — executes in reverse add order) ──────
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(signals.router)
app.include_router(calendar.router)
app.include_router(journal.router)
app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(ea.router)
app.include_router(broker.router)
app.include_router(ws_router)


# ── Root endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["meta"], summary="API root")
async def root() -> dict:
    """Return basic API identification."""
    return {"app": "made.", "version": "1.0.0"}


@app.get("/health", tags=["meta"], summary="Health check")
async def health_check() -> dict:
    """
    Health check endpoint for load balancer and monitoring probes.

    Returns {"status": "ok"} when the API is running.
    Does not check downstream dependencies (Redis, Supabase) — use /health/deep for that.
    """
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health/deep", tags=["meta"], summary="Deep health check", include_in_schema=False)
async def deep_health_check() -> dict:
    """Check Redis and Supabase connectivity."""
    from api.database import is_configured

    redis_status = "ok"
    redis = await get_redis()
    if redis is None:
        redis_status = "unavailable"
    else:
        try:
            await redis.ping()
        except Exception:
            redis_status = "error"

    supabase_status = "configured" if is_configured() else "unconfigured"

    overall = "ok" if redis_status == "ok" else "degraded"
    return {
        "status": overall,
        "version": "1.0.0",
        "dependencies": {
            "redis": redis_status,
            "supabase": supabase_status,
        },
    }
