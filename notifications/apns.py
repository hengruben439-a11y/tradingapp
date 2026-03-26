"""
Apple Push Notification Service (APNS) sender.

Uses the HTTP/2 APNS provider API with JWT authentication.
Sends: new signals, TP hits, SL hits, news alerts, daily rundown.

Config (from env):
    APNS_KEY_ID: Key ID from Apple Developer account
    APNS_TEAM_ID: Team ID from Apple Developer account
    APNS_BUNDLE_ID: App bundle ID (e.g., com.made.trading)
    APNS_AUTH_KEY_PATH: Path to .p8 private key file
    APNS_SANDBOX: "true" for sandbox (dev), "false" for production

APNS HTTP/2 endpoint:
    Production: api.push.apple.com
    Sandbox:    api.sandbox.push.apple.com

JWT token must be refreshed every 45 minutes (APNS rejects tokens older than 1 hour).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# APNS error codes that indicate a permanently invalid device token
_REMOVE_TOKEN_CODES = {
    "BadDeviceToken",    # 400 — token format is invalid
    "Unregistered",      # 410 — device has unregistered from notifications
    "DeviceTokenNotForTopic",  # 400 — token doesn't match bundle ID
    "TopicDisallowed",   # 400 — topic not allowed
}

# APNS error codes that indicate a rate limit — back off before retrying
_BACKOFF_CODES = {
    "TooManyRequests",   # 429
    "TooManyProviderTokenUpdates",  # 403
}

# JWT token lifetime before refresh (45 minutes)
_TOKEN_TTL_SECONDS = 45 * 60


class APNSSender:
    """
    Asynchronous APNS notification sender using HTTP/2.

    Requires httpx with HTTP/2 support (pip install httpx[http2]).
    JWT tokens are signed with ES256 using the .p8 key from Apple.

    Example:
        sender = APNSSender()
        failed = await sender.send_signal_alert(tokens, signal)
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        team_id: Optional[str] = None,
        bundle_id: Optional[str] = None,
        auth_key_path: Optional[str] = None,
        sandbox: Optional[bool] = None,
    ):
        self.key_id = key_id or os.environ.get("APNS_KEY_ID", "")
        self.team_id = team_id or os.environ.get("APNS_TEAM_ID", "")
        self.bundle_id = bundle_id or os.environ.get("APNS_BUNDLE_ID", "com.made.trading")
        self.auth_key_path = auth_key_path or os.environ.get("APNS_AUTH_KEY_PATH", "")

        # Determine environment
        if sandbox is None:
            sandbox_env = os.environ.get("APNS_SANDBOX", "true").lower()
            sandbox = sandbox_env == "true"
        self.sandbox = sandbox

        host = "api.sandbox.push.apple.com" if sandbox else "api.push.apple.com"
        self._base_url = f"https://{host}"

        # JWT state
        self._jwt_token: Optional[str] = None
        self._jwt_issued_at: float = 0.0

        # Lazy-loaded httpx client (created on first use in async context)
        self._client = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def send_signal_alert(
        self,
        device_tokens: list[str],
        signal: dict,
    ) -> list[str]:
        """
        Send a new signal push notification to a list of device tokens.

        Args:
            device_tokens: List of APNS device tokens (hex strings).
            signal: Signal dict with at minimum: pair, direction, entry_price,
                    stop_loss, tp1, signal_id.

        Returns:
            List of device tokens that failed (invalid/unregistered).
        """
        pair = signal.get("pair", "")
        direction = signal.get("direction", "")
        entry = signal.get("entry_price", 0.0)
        tp1 = signal.get("tp1", 0.0)
        sl = signal.get("stop_loss", 0.0)

        emoji = "🟢" if direction.upper() == "BUY" else "🔴"
        title = f"{emoji} {direction.upper()} {pair}"
        body = f"Entry: {entry:.2f} | TP1: {tp1:.2f} | SL: {sl:.2f}"

        payload = self._build_payload(
            alert_type="signal",
            data={
                "title": title,
                "body": body,
                "signal_id": signal.get("signal_id", ""),
                "pair": pair,
                "direction": direction,
            },
        )

        failed = []
        for token in device_tokens:
            success = await self._send_notification(token, payload)
            if not success:
                failed.append(token)

        return failed

    async def send_tp_notification(
        self,
        device_token: str,
        pair: str,
        tp_level: str,
        pnl: float,
    ) -> None:
        """
        Send a take-profit hit notification.

        Args:
            device_token: APNS device token.
            pair: Trading pair (e.g. "XAUUSD").
            tp_level: Level hit (e.g. "TP1", "TP2", "TP3").
            pnl: Profit/loss in USD (positive for profit).
        """
        sign = "+" if pnl >= 0 else ""
        payload = self._build_payload(
            alert_type="tp_hit",
            data={
                "title": f"✅ {tp_level} Hit — {pair}",
                "body": f"P&L: {sign}${pnl:.2f} | Move SL to breakeven",
                "pair": pair,
                "tp_level": tp_level,
                "pnl": pnl,
            },
        )
        await self._send_notification(device_token, payload)

    async def send_sl_notification(
        self,
        device_token: str,
        pair: str,
        pnl: float,
        lesson: str,
    ) -> None:
        """
        Send a stop-loss hit notification with a post-mortem lesson.

        Args:
            device_token: APNS device token.
            pair: Trading pair.
            pnl: P&L in USD (negative for a loss).
            lesson: One-sentence post-mortem lesson from PostMortemGenerator.
        """
        payload = self._build_payload(
            alert_type="sl_hit",
            data={
                "title": f"🛑 SL Hit — {pair}",
                "body": f"P&L: ${pnl:.2f} | {lesson}",
                "pair": pair,
                "pnl": pnl,
                "lesson": lesson,
            },
        )
        await self._send_notification(device_token, payload)

    async def send_news_alert(
        self,
        device_tokens: list[str],
        event: dict,
    ) -> list[str]:
        """
        Send a high-impact news countdown alert.

        Args:
            device_tokens: List of APNS device tokens.
            event: Calendar event dict with: title, scheduled_at, impact, currency.

        Returns:
            List of failed device tokens.
        """
        title_text = event.get("title", "High-Impact News")
        currency = event.get("currency", "")
        impact = event.get("impact", "HIGH")
        scheduled_at = event.get("scheduled_at", "")

        # Format scheduled_at if it's a datetime
        if isinstance(scheduled_at, datetime):
            # Convert to SGT (UTC+8) for display
            sgt_offset = timedelta(hours=8)
            sgt_time = scheduled_at.astimezone(timezone.utc) + sgt_offset
            time_str = sgt_time.strftime("%H:%M SGT")
        else:
            time_str = str(scheduled_at)

        payload = self._build_payload(
            alert_type="news_alert",
            data={
                "title": f"📅 {impact} Impact: {title_text}",
                "body": f"{currency} news at {time_str} — signals paused",
                "event_title": title_text,
                "currency": currency,
                "impact": impact,
            },
        )

        failed = []
        for token in device_tokens:
            success = await self._send_notification(token, payload)
            if not success:
                failed.append(token)

        return failed

    async def send_daily_rundown(
        self,
        device_tokens: list[str],
        events: list[dict],
    ) -> list[str]:
        """
        Send the daily economic calendar rundown at 6:00 AM SGT.

        Args:
            device_tokens: List of APNS device tokens.
            events: List of today's high-impact calendar event dicts.

        Returns:
            List of failed device tokens.
        """
        high_impact_count = sum(
            1 for e in events
            if str(e.get("impact", "")).upper() == "HIGH"
        )

        if high_impact_count == 0:
            body = "No high-impact events today. Good conditions for signals."
        elif high_impact_count == 1:
            body = f"1 high-impact event today. Check calendar for timing."
        else:
            body = f"{high_impact_count} high-impact events today. Plan around news windows."

        payload = self._build_payload(
            alert_type="daily_rundown",
            data={
                "title": "☀️ made. Daily Rundown",
                "body": body,
                "event_count": len(events),
                "high_impact_count": high_impact_count,
            },
        )

        failed = []
        for token in device_tokens:
            success = await self._send_notification(token, payload)
            if not success:
                failed.append(token)

        return failed

    # ── Payload builder ───────────────────────────────────────────────────────

    def _build_payload(self, alert_type: str, data: dict) -> dict:
        """
        Build an APNS JSON payload dict.

        Args:
            alert_type: Notification type string (e.g. "signal", "tp_hit").
            data: Alert-specific data; must include "title" and "body".

        Returns:
            APNS payload dict ready for JSON serialisation.

        Payload structure:
            {
                "aps": {
                    "alert": {"title": "...", "body": "..."},
                    "sound": "default",
                    "badge": 1,
                    "mutable-content": 1,
                    "content-available": 1
                },
                "type": "signal",
                "pair": "XAUUSD",
                ...
            }
        """
        title = data.pop("title", "made.")
        body = data.pop("body", "")

        payload: dict = {
            "aps": {
                "alert": {
                    "title": title,
                    "body": body,
                },
                "sound": "default",
                "badge": 1,
                "mutable-content": 1,
                "content-available": 1,
            },
            "type": alert_type,
        }

        # Merge remaining data keys into the top-level payload
        payload.update(data)

        return payload

    # ── JWT authentication ────────────────────────────────────────────────────

    def _sign_jwt(self) -> str:
        """
        Generate a JWT provider token for APNS HTTP/2 authentication.

        The token is signed with ES256 using the .p8 private key from Apple.
        APNS requires:
            - Header: {"alg": "ES256", "kid": "<APNS_KEY_ID>"}
            - Payload: {"iss": "<TEAM_ID>", "iat": <issued_at_unix_timestamp>}

        Returns:
            Signed JWT string.

        Raises:
            ImportError: If PyJWT or cryptography are not installed.
            FileNotFoundError: If the .p8 key file is not found.
            ValueError: If key_id or team_id are not configured.
        """
        try:
            import jwt as pyjwt
        except ImportError as exc:
            raise ImportError(
                "PyJWT is required for APNS JWT signing. "
                "Install it with: pip install PyJWT[crypto]"
            ) from exc

        if not self.key_id:
            raise ValueError("APNS_KEY_ID is not configured.")
        if not self.team_id:
            raise ValueError("APNS_TEAM_ID is not configured.")
        if not self.auth_key_path:
            raise ValueError("APNS_AUTH_KEY_PATH is not configured.")

        with open(self.auth_key_path, "r") as key_file:
            private_key = key_file.read()

        issued_at = int(time.time())
        self._jwt_issued_at = issued_at

        token = pyjwt.encode(
            payload={"iss": self.team_id, "iat": issued_at},
            key=private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )

        # PyJWT >= 2.0 returns str; < 2.0 returns bytes
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        self._jwt_token = token
        return token

    def _get_jwt(self) -> str:
        """
        Return a valid JWT, refreshing if older than TOKEN_TTL_SECONDS.
        """
        now = time.time()
        if (
            self._jwt_token is None
            or (now - self._jwt_issued_at) >= _TOKEN_TTL_SECONDS
        ):
            self._sign_jwt()
        return self._jwt_token  # type: ignore[return-value]

    # ── HTTP/2 send ───────────────────────────────────────────────────────────

    async def _get_client(self):
        """Lazily create and return the shared httpx AsyncClient with HTTP/2."""
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise ImportError(
                    "httpx with HTTP/2 support is required. "
                    "Install it with: pip install httpx[http2]"
                ) from exc

            self._client = httpx.AsyncClient(http2=True)

        return self._client

    async def _send_notification(
        self,
        device_token: str,
        payload: dict,
    ) -> bool:
        """
        Send a single push notification to one device token.

        Handles APNS error responses:
        - 400/410 BadDeviceToken / Unregistered → logs token for removal, returns False
        - 429 TooManyRequests → logs backoff warning, returns False
        - Other errors → logs and returns False

        Args:
            device_token: APNS hex device token.
            payload: APNS payload dict (will be JSON-serialised).

        Returns:
            True on HTTP 200, False on any error.
        """
        import json

        url = f"{self._base_url}/3/device/{device_token}"
        headers = {
            "authorization": f"bearer {self._get_jwt()}",
            "apns-topic": self.bundle_id,
            "apns-push-type": "alert",
            "content-type": "application/json",
        }

        try:
            client = await self._get_client()
            response = await client.post(
                url,
                headers=headers,
                content=json.dumps(payload),
            )
        except Exception as exc:
            logger.error("APNS send failed for token %s: %s", device_token[:8], exc)
            return False

        if response.status_code == 200:
            return True

        # Parse APNS error reason from response body
        reason = ""
        try:
            body = response.json()
            reason = body.get("reason", "")
        except Exception:
            pass

        if reason in _REMOVE_TOKEN_CODES or response.status_code == 410:
            logger.warning(
                "APNS: invalid/unregistered token %s... (reason: %s) — mark for removal",
                device_token[:8],
                reason,
            )
            return False

        if reason in _BACKOFF_CODES or response.status_code == 429:
            logger.warning(
                "APNS: rate limit hit (reason: %s) — back off before retrying", reason
            )
            return False

        logger.error(
            "APNS: unexpected error %s for token %s... (reason: %s)",
            response.status_code,
            device_token[:8],
            reason,
        )
        return False

    async def close(self) -> None:
        """Close the underlying HTTP/2 client connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
