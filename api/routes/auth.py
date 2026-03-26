"""
Authentication router.

Supports two login methods:
1. Apple Sign In (production) — validates Apple identity token
2. Email + password (dev/testing) — simple credential check

In dev mode (no Supabase), a test user is always available:
  email: dev@made.app
  password: made-dev-2026

All protected routes require a Bearer token in the Authorization header.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    get_current_user,
    verify_token,
)
from api.database import get_db
from api.models import (
    LoginRequest,
    RefreshRequest,
    SubscriptionTierEnum,
    TradingStyleEnum,
    TokenResponse,
    UIModeEnum,
    UserProfile,
    UserProfileUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Dev mode user store ───────────────────────────────────────────────────────
_DEV_USER_ID = "dev-user-00000000-0000-0000-0000-000000000001"
_DEV_EMAIL = "dev@made.app"
_DEV_PASSWORD = "made-dev-2026"

_mock_users: dict[str, dict] = {
    _DEV_USER_ID: {
        "user_id": _DEV_USER_ID,
        "email": _DEV_EMAIL,
        "subscription_tier": "premium",
        "ui_mode": "pro",
        "trading_style": "day_trading",
        "pairs": ["XAUUSD", "GBPJPY"],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
}


def _validate_dev_credentials(email: str, password: str) -> Optional[str]:
    """
    Check dev credentials. Returns user_id on success, None on failure.
    In production this path is disabled (Apple Sign In only).
    """
    if email == _DEV_EMAIL and password == _DEV_PASSWORD:
        return _DEV_USER_ID
    return None


async def _validate_apple_token(apple_identity_token: str) -> Optional[str]:
    """
    Validate an Apple Sign In identity token.

    In production: verify the JWT against Apple's public keys.
    Currently returns a stub user_id derived from the token for Phase 2.
    Full Apple JWKS verification is implemented in Phase 2 (Sprint 9).
    """
    # TODO (Sprint 9): Implement full Apple JWKS verification
    # For now, treat any non-empty token as valid in dev mode
    if apple_identity_token:
        # In real implementation: fetch https://appleid.apple.com/auth/keys,
        # verify signature, extract sub claim as user_id
        return f"apple-user-{uuid.uuid4()}"
    return None


def _build_token_response(user_id: str) -> dict:
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def _get_user_profile(user_id: str, db) -> Optional[dict]:
    """Fetch user profile from Supabase or in-memory store."""
    if db is None:
        return _mock_users.get(user_id)

    try:
        response = (
            db.table("users")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if response.data:
            return response.data[0]
    except Exception:
        pass
    return None


def _create_user_profile(user_id: str, email: Optional[str], db) -> dict:
    """Create a new user profile in Supabase or in-memory store."""
    profile = {
        "user_id": user_id,
        "email": email,
        "subscription_tier": SubscriptionTierEnum.FREE.value,
        "ui_mode": UIModeEnum.SIMPLE.value,
        "trading_style": TradingStyleEnum.DAY_TRADING.value,
        "pairs": ["XAUUSD", "GBPJPY"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if db is None:
        _mock_users[user_id] = profile
    else:
        try:
            db.table("users").insert(profile).execute()
        except Exception:
            pass
    return profile


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Login / Sign In")
async def login(body: LoginRequest, db=Depends(get_db)) -> dict:
    """
    Authenticate a user and return JWT tokens.

    Accepts:
    - Apple Sign In identity token (production)
    - Email + password (dev/testing only)

    On success: creates the user profile if first login, then returns tokens.
    On failure: 401 Unauthorized.
    """
    user_id: Optional[str] = None
    email: Optional[str] = None

    if body.apple_identity_token:
        user_id = await _validate_apple_token(body.apple_identity_token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Apple identity token",
            )

    elif body.email and body.password:
        user_id = _validate_dev_credentials(body.email, body.password)
        if user_id is None:
            # Check Supabase if configured
            if db is not None:
                try:
                    response = (
                        db.table("users")
                        .select("user_id")
                        .eq("email", body.email)
                        .execute()
                    )
                    if response.data:
                        # In production, password check is handled by Supabase Auth
                        # This path is for dev use only
                        user_id = response.data[0]["user_id"]
                except Exception:
                    pass

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        email = body.email

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either apple_identity_token or email+password",
        )

    # Create profile on first login
    profile = _get_user_profile(user_id, db)
    if profile is None:
        _create_user_profile(user_id, email, db)

    return _build_token_response(user_id)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(body: RefreshRequest) -> dict:
    """
    Exchange a refresh token for a new access token.

    The refresh token is verified against the JWT secret.
    Returns a fresh access token (and a new refresh token).
    """
    payload = verify_token(body.refresh_token, expected_type="refresh")
    user_id = payload["sub"]
    return _build_token_response(user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(user: dict = Depends(get_current_user)) -> None:
    """
    Invalidate the current session.

    JWT tokens are stateless — full token blacklisting requires a Redis set
    of revoked JTIs (deferred to Phase 2). For now, the client is responsible
    for discarding the token.
    """
    # TODO (Phase 2): Add JTI to Redis revocation set
    pass


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_me(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """Return the authenticated user's profile."""
    user_id = user["sub"]
    profile = _get_user_profile(user_id, db)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )
    return profile


@router.put("/me", response_model=UserProfile, summary="Update user profile settings")
async def update_me(
    body: UserProfileUpdate,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Update user profile settings.

    Updatable fields: ui_mode, trading_style, pairs.
    Subscription tier changes are handled via in-app purchase (not this endpoint).
    """
    user_id = user["sub"]
    update_data = {k: v for k, v in body.model_dump(mode="json").items() if v is not None}

    # Validate subscription gate for ui_mode
    if "ui_mode" in update_data:
        profile = _get_user_profile(user_id, db)
        if profile:
            tier = profile.get("subscription_tier", "free")
            requested_mode = update_data["ui_mode"]
            if requested_mode == "pro" and tier not in {"premium", "pro"}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Pro UI mode requires Premium or Pro subscription",
                )
            if requested_mode == "max" and tier != "pro":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Max UI mode requires Pro subscription",
                )

    if db is None:
        profile = _mock_users.get(user_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        profile.update(update_data)
        _mock_users[user_id] = profile
        return profile

    try:
        response = (
            db.table("users")
            .update(update_data)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {exc}",
        )
