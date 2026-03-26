"""
Notification Manager — routes alerts to APNS, Telegram, and in-app.

Single entry point for all notifications. Checks user preferences
before sending to each channel.

Per CLAUDE.md §14:
    - New Signal:    Push + Telegram + In-App
    - TP Hit:        Push + In-App
    - SL Hit:        Push + In-App (with post-mortem lesson)
    - News Alert:    Push + In-App
    - Daily Rundown: Push + Telegram (broadcast to all subscribed users)

User preferences (from subscription dict):
    - push_enabled (bool)
    - telegram_enabled (bool)
    - subscription_tier: "free" | "premium" | "pro"
    - pairs: list of enabled pairs
    - trading_style: "scalping" | "day_trading" | "swing_trading" | "position_trading"
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Orchestrates all notification delivery across APNS, Telegram, and in-app channels.

    Designed to be instantiated once at application startup and reused for the
    lifetime of the server process.

    Args:
        apns: APNSSender instance for Apple push notifications.
        telegram_bot: Telegram bot instance (duck-typed; must expose
                      send_signal_alert, send_tp_notification, etc.).
        redis_client: Redis client for in-app WebSocket broadcast and
                      device token caching.

    Example:
        manager = NotificationManager(apns=apns, telegram_bot=bot, redis_client=redis)
        await manager.notify_new_signal(signal, user_subscriptions)
    """

    # Redis key prefix for device token lookup
    _DEVICE_TOKEN_KEY = "device_tokens:{user_id}"
    _DEVICE_TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days

    def __init__(
        self,
        apns,
        telegram_bot,
        redis_client,
    ) -> None:
        self._apns = apns
        self._telegram = telegram_bot
        self._redis = redis_client

    # ── Public notification methods ───────────────────────────────────────────

    async def notify_new_signal(
        self,
        signal: dict,
        user_subscriptions: list[dict],
    ) -> None:
        """
        Fan-out a new signal to all eligible users across all channels.

        Only sends push/Telegram for signals with strength "strong" or
        "very_strong" (score >= 0.65). Moderate signals (0.50–0.64) are
        shown in-app only without push/Telegram.

        Args:
            signal: Signal dict with at minimum: signal_id, pair, direction,
                    entry_price, stop_loss, tp1, confluence_score, strength.
            user_subscriptions: List of user subscription dicts, each with:
                - user_id (str)
                - push_enabled (bool)
                - telegram_chat_id (str | None)
                - pairs (list[str])
                - subscription_tier (str)
        """
        pair = signal.get("pair", "")
        strength = str(signal.get("strength", "")).lower()
        score = float(signal.get("confluence_score", 0.0))

        # Determine which channels to activate based on signal strength
        send_push = strength in ("strong", "very_strong") or abs(score) >= 0.65
        send_telegram = send_push  # Same threshold as push

        # Collect eligible user IDs and tokens for batch push
        push_tokens: list[str] = []
        telegram_ids: list[str] = []

        for sub in user_subscriptions:
            user_id = sub.get("user_id", "")
            user_pairs = [p.upper() for p in sub.get("pairs", [])]

            # Skip users who haven't subscribed to this pair
            if pair.upper() not in user_pairs:
                continue

            # Push notification
            if send_push and sub.get("push_enabled", False):
                tokens = await self._get_user_device_tokens([user_id])
                push_tokens.extend(tokens.get(user_id, []))

            # Telegram notification
            if send_telegram and sub.get("telegram_chat_id"):
                telegram_ids.append(sub["telegram_chat_id"])

        # Batch push
        if push_tokens and self._apns:
            try:
                failed = await self._apns.send_signal_alert(push_tokens, signal)
                if failed:
                    logger.warning(
                        "APNS: %d tokens failed for signal %s",
                        len(failed),
                        signal.get("signal_id", ""),
                    )
            except Exception as exc:
                logger.error("APNS send_signal_alert failed: %s", exc)

        # Telegram
        if telegram_ids and self._telegram:
            for chat_id in telegram_ids:
                try:
                    await self._telegram.send_signal_alert(chat_id, signal)
                except Exception as exc:
                    logger.error(
                        "Telegram signal alert failed for chat %s: %s", chat_id, exc
                    )

        # In-app via Redis pub/sub
        await self._publish_inapp("signal_new", signal)

    async def notify_tp_hit(
        self,
        signal_id: str,
        tp_level: str,
        pnl_pips: float,
        user_id: str,
    ) -> None:
        """
        Notify a user that a take-profit level has been hit.

        Args:
            signal_id: The originating signal UUID.
            tp_level: Which TP was hit: "TP1", "TP2", or "TP3".
            pnl_pips: P&L in pips at this TP (positive for profit).
            user_id: The user's ID.
        """
        pair = await self._get_signal_pair(signal_id)
        pnl_usd = await self._pips_to_usd(pnl_pips, pair)

        # Push notification
        tokens = await self._get_user_device_tokens([user_id])
        user_tokens = tokens.get(user_id, [])

        if user_tokens and self._apns:
            for token in user_tokens:
                try:
                    await self._apns.send_tp_notification(
                        device_token=token,
                        pair=pair,
                        tp_level=tp_level,
                        pnl=pnl_usd,
                    )
                except Exception as exc:
                    logger.error("APNS TP notification failed: %s", exc)

        # In-app
        await self._publish_inapp("tp_hit", {
            "signal_id": signal_id,
            "tp_level": tp_level,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
            "pair": pair,
            "user_id": user_id,
        })

    async def notify_sl_hit(
        self,
        signal_id: str,
        pnl_pips: float,
        post_mortem: dict,
        user_id: str,
    ) -> None:
        """
        Notify a user that their stop loss was hit, including a post-mortem lesson.

        Args:
            signal_id: The originating signal UUID.
            pnl_pips: P&L in pips (negative for a loss).
            post_mortem: PostMortem dict (or dataclass converted to dict) with
                         at minimum: failed_module, failure_category, lesson.
            user_id: The user's ID.
        """
        pair = await self._get_signal_pair(signal_id)
        pnl_usd = await self._pips_to_usd(pnl_pips, pair)
        lesson = post_mortem.get("lesson", "Review the post-mortem in the journal.")

        tokens = await self._get_user_device_tokens([user_id])
        user_tokens = tokens.get(user_id, [])

        if user_tokens and self._apns:
            for token in user_tokens:
                try:
                    await self._apns.send_sl_notification(
                        device_token=token,
                        pair=pair,
                        pnl=pnl_usd,
                        lesson=lesson,
                    )
                except Exception as exc:
                    logger.error("APNS SL notification failed: %s", exc)

        # In-app
        await self._publish_inapp("sl_hit", {
            "signal_id": signal_id,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
            "pair": pair,
            "post_mortem": post_mortem,
            "user_id": user_id,
        })

    async def notify_news_alert(
        self,
        event: dict,
        affected_users: list[str],
    ) -> None:
        """
        Broadcast a high-impact news alert to affected users.

        Args:
            event: Calendar event dict with: title, scheduled_at, impact, currency.
            affected_users: List of user IDs who should receive this alert.
        """
        if not affected_users:
            return

        # Batch all tokens from affected users
        token_map = await self._get_user_device_tokens(affected_users)
        all_tokens = [
            token
            for user_id in affected_users
            for token in token_map.get(user_id, [])
        ]

        if all_tokens and self._apns:
            try:
                failed = await self._apns.send_news_alert(all_tokens, event)
                if failed:
                    logger.warning(
                        "APNS: %d tokens failed for news alert '%s'",
                        len(failed),
                        event.get("title", ""),
                    )
            except Exception as exc:
                logger.error("APNS news alert failed: %s", exc)

        # In-app broadcast
        await self._publish_inapp("news_alert", event)

    async def send_daily_rundown(
        self,
        events: list[dict],
    ) -> None:
        """
        Broadcast the daily economic calendar rundown to all subscribed users.

        This is called at 6:00 AM SGT via a scheduled job (see CLAUDE.md §10.2).
        Sends to all users who have push or Telegram enabled.

        Args:
            events: List of today's calendar event dicts.
        """
        # Get all active subscriber user IDs from Redis
        all_user_ids = await self._get_all_subscriber_user_ids()

        if not all_user_ids:
            logger.info("Daily rundown: no subscribed users found.")
            return

        token_map = await self._get_user_device_tokens(all_user_ids)
        all_tokens = [
            token
            for tokens in token_map.values()
            for token in tokens
        ]

        if all_tokens and self._apns:
            try:
                failed = await self._apns.send_daily_rundown(all_tokens, events)
                if failed:
                    logger.warning(
                        "APNS: %d tokens failed for daily rundown", len(failed)
                    )
            except Exception as exc:
                logger.error("APNS daily rundown failed: %s", exc)

        # Telegram broadcast via bot
        if self._telegram:
            try:
                await self._telegram.send_daily_rundown(events)
            except Exception as exc:
                logger.error("Telegram daily rundown failed: %s", exc)

        # In-app
        await self._publish_inapp("daily_rundown", {"events": events})

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_user_device_tokens(
        self,
        user_ids: list[str],
    ) -> dict[str, list[str]]:
        """
        Retrieve APNS device tokens for a list of user IDs.

        Checks Redis cache first (tokens stored as Redis sets under
        key "device_tokens:{user_id}"). Falls back to empty list if
        user has no registered tokens or Redis is unavailable.

        Args:
            user_ids: List of user IDs to look up.

        Returns:
            Dict mapping user_id → list of device token strings.
        """
        result: dict[str, list[str]] = {uid: [] for uid in user_ids}

        if self._redis is None:
            return result

        for user_id in user_ids:
            key = self._DEVICE_TOKEN_KEY.format(user_id=user_id)
            try:
                # Tokens stored as a Redis set
                if hasattr(self._redis, "smembers"):
                    raw = await self._redis.smembers(key)
                    result[user_id] = [
                        t.decode() if isinstance(t, bytes) else t
                        for t in (raw or [])
                    ]
                elif hasattr(self._redis, "lrange"):
                    raw = await self._redis.lrange(key, 0, -1)
                    result[user_id] = [
                        t.decode() if isinstance(t, bytes) else t
                        for t in (raw or [])
                    ]
            except Exception as exc:
                logger.warning(
                    "Redis device token lookup failed for user %s: %s", user_id, exc
                )

        return result

    async def _get_all_subscriber_user_ids(self) -> list[str]:
        """
        Return user IDs of all users with push notifications enabled.

        In production this would query Supabase or a Redis set of active
        subscribers. This implementation reads from a Redis set keyed
        "push_subscribers".
        """
        if self._redis is None:
            return []

        try:
            if hasattr(self._redis, "smembers"):
                raw = await self._redis.smembers("push_subscribers")
                return [
                    uid.decode() if isinstance(uid, bytes) else uid
                    for uid in (raw or [])
                ]
        except Exception as exc:
            logger.warning("Redis push_subscribers lookup failed: %s", exc)

        return []

    async def _get_signal_pair(self, signal_id: str) -> str:
        """
        Look up the trading pair for a signal ID from Redis cache.

        Falls back to "XAUUSD" if not found (conservative default for pip value).
        """
        if self._redis is None:
            return "XAUUSD"

        try:
            key = f"signal_pair:{signal_id}"
            if hasattr(self._redis, "get"):
                raw = await self._redis.get(key)
                if raw:
                    pair = raw.decode() if isinstance(raw, bytes) else raw
                    return pair
        except Exception as exc:
            logger.debug("Redis signal pair lookup failed for %s: %s", signal_id, exc)

        return "XAUUSD"

    async def _pips_to_usd(self, pnl_pips: float, pair: str) -> float:
        """
        Convert P&L in pips to approximate USD value.

        Uses standard lot sizing assumptions from CLAUDE.md §11.1.
        Per standard lot:
            XAUUSD: $1.00/pip (100 oz * $0.01)
            GBPJPY: ~$9.50/pip (fallback when live USDJPY unavailable)

        For notification purposes, assumes 0.1 lot (mini lot) as a typical
        position size. The actual P&L is computed precisely in the journal.
        """
        if pair == "XAUUSD":
            pip_value_per_lot = 1.0  # $1/pip per standard lot
        elif pair == "GBPJPY":
            pip_value_per_lot = 9.50  # $9.50/pip per standard lot (fallback)
        else:
            pip_value_per_lot = 1.0

        # Assume 0.1 lot (mini lot) for notification display
        assumed_lots = 0.1
        return round(pnl_pips * pip_value_per_lot * assumed_lots, 2)

    async def _publish_inapp(self, event_type: str, data: Any) -> None:
        """
        Publish an in-app event to the Redis pub/sub channel.

        The FastAPI WebSocket handler subscribes to "inapp_events" and
        forwards messages to connected iOS clients in real time.

        Args:
            event_type: Event type string (e.g. "signal_new", "tp_hit").
            data: Payload dict to include in the message.
        """
        if self._redis is None:
            return

        import json

        message = json.dumps({"type": event_type, "payload": data}, default=str)

        try:
            if hasattr(self._redis, "publish"):
                await self._redis.publish("inapp_events", message)
        except Exception as exc:
            logger.warning("Redis pub/sub publish failed (%s): %s", event_type, exc)
