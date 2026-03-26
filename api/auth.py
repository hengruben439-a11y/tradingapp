"""
JWT authentication utilities for the made. API.

Provides token creation, verification, and FastAPI dependency injection.
Uses python-jose for JWT signing/verification.

Secret key is read from JWT_SECRET environment variable.
Default value is dev-only — must be overridden in production.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# ── Configuration ──────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# OAuth2 bearer scheme — tokenUrl is informational for OpenAPI docs only
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token for a given user.

    Args:
        user_id: The user's unique identifier (UUID or Supabase user ID).
        expires_delta: Custom expiry window. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """
    Create a longer-lived refresh token.

    Refresh tokens are used to obtain new access tokens without re-authentication.

    Args:
        user_id: The user's unique identifier.

    Returns:
        Encoded JWT string with REFRESH_TOKEN_EXPIRE_DAYS lifetime.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


# ── Token verification ─────────────────────────────────────────────────────────

def verify_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: Raw JWT string.
        expected_type: "access" or "refresh" — validated against the token's type claim.

    Returns:
        Decoded payload dict containing at minimum {"sub": user_id, "type": ...}.

    Raises:
        HTTPException 401: If the token is missing, expired, invalid, or wrong type.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception

    user_id: Optional[str] = payload.get("sub")
    token_type: Optional[str] = payload.get("type")

    if user_id is None:
        raise credentials_exception

    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type: expected '{expected_type}', got '{token_type}'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency — extracts and validates the current authenticated user.

    Usage in route handlers:
        @router.get("/protected")
        async def protected(user: dict = Depends(get_current_user)):
            return {"user_id": user["sub"]}

    Returns:
        Decoded JWT payload dict with at minimum {"sub": user_id}.

    Raises:
        HTTPException 401: If no token provided or token is invalid.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(token, expected_type="access")


async def get_optional_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    """
    FastAPI dependency — returns the current user if authenticated, else None.

    Used for endpoints that behave differently for authenticated vs anonymous users
    (e.g., signals endpoint shows more data to premium users).
    """
    if token is None:
        return None
    try:
        return verify_token(token, expected_type="access")
    except HTTPException:
        return None
