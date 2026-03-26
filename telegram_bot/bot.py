"""
Telegram Bot — made. trading signal notifications.

Features:
- Signal broadcast to a configured channel
- Personal DM alerts based on user preferences
- Daily rundown at 06:00 SGT (UTC+8 = UTC 22:00 previous day)
- Inline buttons: View in App (deep link), Skip, Acknowledge
- /start command with welcome message
- /status command showing engine health
- /help command
- /subscribe and /unsubscribe commands for pair/style filtering
- /rundown command to trigger manual daily summary

Configuration (from environment):
    TELEGRAM_BOT_TOKEN: Bot API token
    TELEGRAM_SIGNAL_CHANNEL_ID: Channel ID for signal broadcasts (e.g., @made_trading)
    TELEGRAM_ADMIN_IDS: Comma-separated admin user IDs
    APP_DEEP_LINK_BASE: Base URL for deep links (e.g., made://signal/)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from telegram_bot.formatters import (
    format_daily_rundown,
    format_signal_message,
    format_sl_hit,
    format_tp_hit,
)
from telegram_bot.scheduler import DailyRundownScheduler

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_PAIRS = {"XAUUSD", "GBPJPY"}
VALID_STYLES = {"scalping", "day_trading", "swing_trading", "position_trading"}

# Default preferences for new users
_DEFAULT_PREFS: dict = {
    "pairs": list(VALID_PAIRS),
    "styles": ["day_trading", "swing_trading"],
    "notifications": True,
}

# Callback data prefixes for inline buttons
_CB_SKIP = "skip:"
_CB_ACK = "ack:"
_CB_VIEW = "view:"

# Path where user preferences are persisted between restarts
_PREFS_FILE = Path(os.getenv("MADE_PREFS_FILE", "/tmp/made_user_prefs.json"))


# ─── User Preference Store ────────────────────────────────────────────────────

class _UserPreferenceStore:
    """Simple in-memory dict with JSON persistence.

    Keys are Telegram user IDs (int), values are preference dicts.
    """

    def __init__(self, path: Path = _PREFS_FILE) -> None:
        self._path = path
        self._data: dict[int, dict] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                # JSON keys are always strings; convert back to int
                self._data = {int(k): v for k, v in raw.items()}
                logger.info("Loaded preferences for %d users.", len(self._data))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load user prefs from %s: %s", self._path, exc)
                self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._data, indent=2))
        except OSError as exc:
            logger.error("Could not save user prefs to %s: %s", self._path, exc)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def get(self, user_id: int) -> dict:
        """Return preferences for user_id, creating defaults if absent."""
        if user_id not in self._data:
            self._data[user_id] = dict(_DEFAULT_PREFS)
            self._save()
        return self._data[user_id]

    def update(self, user_id: int, **kwargs: object) -> None:
        """Merge keyword arguments into the user's preferences and persist."""
        prefs = self.get(user_id)
        prefs.update(kwargs)
        self._save()

    def all_users(self) -> list[int]:
        """Return list of all registered user IDs."""
        return list(self._data.keys())

    def users_subscribed_to(self, pair: str, style: Optional[str] = None) -> list[int]:
        """Return user IDs whose preferences include the given pair (and optionally style)."""
        result = []
        for uid, prefs in self._data.items():
            if not prefs.get("notifications", True):
                continue
            if pair.upper() not in [p.upper() for p in prefs.get("pairs", [])]:
                continue
            if style and style.lower() not in [s.lower() for s in prefs.get("styles", [])]:
                continue
            result.append(uid)
        return result


# ─── Inline keyboard builders ─────────────────────────────────────────────────

def _signal_keyboard(signal_id: str, deep_link_base: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a new signal alert: [View in App | Skip]."""
    app_url = f"{deep_link_base.rstrip('/')}/{signal_id}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📲 View in App", url=app_url),
            InlineKeyboardButton("⏭ Skip", callback_data=f"{_CB_SKIP}{signal_id}"),
        ]
    ])


def _outcome_keyboard(signal_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard for TP/SL notifications: [Acknowledge]."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Acknowledge", callback_data=f"{_CB_ACK}{signal_id}")]
    ])


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — register user and send welcome message."""
    if update.effective_user is None or update.message is None:
        return
    user = update.effective_user
    prefs: _UserPreferenceStore = context.bot_data["prefs"]
    prefs.get(user.id)  # creates default entry if new

    welcome = (
        f"👋 <b>Welcome to made., {user.first_name}!</b>\n\n"
        "made. is your intelligent trading signal platform for "
        "<b>XAUUSD</b> and <b>GBPJPY</b>.\n\n"
        "You'll receive:\n"
        "• 🟢🔴 Buy/Sell signals with entry, SL, and 3 TP levels\n"
        "• 📅 Daily economic calendar at 06:00 SGT\n"
        "• ⚠️ News alerts before high-impact events\n"
        "• TP and SL hit notifications\n\n"
        "Use /help to see all commands.\n\n"
        "<i>Trading foreign exchange carries significant risk. "
        "made. provides analysis only — not financial advice.</i>"
    )
    await update.message.reply_html(welcome)


async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — list all available commands."""
    if update.message is None:
        return
    text = (
        "📖 <b>made. Commands</b>\n\n"
        "/start — Register and see welcome message\n"
        "/status — Engine health and last signal time\n"
        "/subscribe <code>[pair] [style]</code> — Subscribe to alerts\n"
        "  <i>Pairs: XAUUSD, GBPJPY (or ALL)</i>\n"
        "  <i>Styles: scalping, day_trading, swing_trading, position_trading (or ALL)</i>\n"
        "/unsubscribe <code>[pair]</code> — Unsubscribe from a pair\n"
        "/rundown — Trigger today's economic calendar now\n"
        "/help — Show this message\n\n"
        "<i>Signal alerts require an active subscription. "
        "Use /subscribe to manage your preferences.</i>"
    )
    await update.message.reply_html(text)


async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — show engine health info stored in bot_data."""
    if update.message is None:
        return
    engine_status: dict = context.bot_data.get("engine_status", {})
    last_signal_at: Optional[datetime] = engine_status.get("last_signal_at")
    engine_live: bool = engine_status.get("live", False)
    data_feed: str = engine_status.get("data_feed", "Unknown")

    status_emoji = "🟢" if engine_live else "🔴"
    last_sig_str = (
        last_signal_at.strftime("%H:%M:%S UTC") if last_signal_at else "No signals yet"
    )

    text = (
        f"{status_emoji} <b>Engine Status</b>\n\n"
        f"Engine:     {'Live' if engine_live else 'Offline'}\n"
        f"Data feed:  {data_feed}\n"
        f"Last signal: {last_sig_str}\n"
        f"Server time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    )
    await update.message.reply_html(text)


async def _cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /subscribe [pair] [style] — add a pair or style to user preferences."""
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    prefs: _UserPreferenceStore = context.bot_data["prefs"]
    args = context.args or []

    if not args:
        await update.message.reply_html(
            "Usage: /subscribe <code>[pair]</code> <code>[style]</code>\n\n"
            "Examples:\n"
            "  /subscribe XAUUSD\n"
            "  /subscribe GBPJPY day_trading\n"
            "  /subscribe ALL ALL"
        )
        return

    pair_arg = args[0].upper() if args else None
    style_arg = args[1].lower() if len(args) > 1 else None

    user_prefs = prefs.get(user_id)
    current_pairs: list[str] = user_prefs.get("pairs", [])
    current_styles: list[str] = user_prefs.get("styles", [])
    changes: list[str] = []

    # Handle pair subscription
    if pair_arg == "ALL":
        new_pairs = list(VALID_PAIRS)
        if set(new_pairs) != set(current_pairs):
            prefs.update(user_id, pairs=new_pairs)
            changes.append("subscribed to all pairs (XAUUSD, GBPJPY)")
    elif pair_arg in VALID_PAIRS:
        if pair_arg not in current_pairs:
            prefs.update(user_id, pairs=list(set(current_pairs) | {pair_arg}))
            changes.append(f"subscribed to {pair_arg}")
        else:
            changes.append(f"already subscribed to {pair_arg}")
    else:
        await update.message.reply_html(
            f"❌ Unknown pair: <code>{pair_arg}</code>. Valid pairs: XAUUSD, GBPJPY, ALL"
        )
        return

    # Handle style subscription
    if style_arg:
        if style_arg == "all":
            new_styles = list(VALID_STYLES)
            prefs.update(user_id, styles=new_styles)
            changes.append("subscribed to all trading styles")
        elif style_arg in VALID_STYLES:
            if style_arg not in current_styles:
                prefs.update(user_id, styles=list(set(current_styles) | {style_arg}))
                changes.append(f"added style: {style_arg}")
            else:
                changes.append(f"already subscribed to style: {style_arg}")
        else:
            await update.message.reply_html(
                f"❌ Unknown style: <code>{style_arg}</code>. "
                f"Valid: {', '.join(sorted(VALID_STYLES))}, ALL"
            )
            return

    summary = "\n• ".join(changes)
    await update.message.reply_html(f"✅ Updated preferences:\n• {summary}")


async def _cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unsubscribe [pair] — remove pair from user preferences."""
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    prefs: _UserPreferenceStore = context.bot_data["prefs"]
    args = context.args or []

    if not args:
        await update.message.reply_html(
            "Usage: /unsubscribe <code>[pair]</code>\n\n"
            "Example: /unsubscribe XAUUSD"
        )
        return

    pair_arg = args[0].upper()
    user_prefs = prefs.get(user_id)
    current_pairs: list[str] = user_prefs.get("pairs", [])

    if pair_arg == "ALL":
        prefs.update(user_id, pairs=[], notifications=False)
        await update.message.reply_html(
            "✅ Unsubscribed from all alerts. Use /subscribe to re-enable."
        )
        return

    if pair_arg not in VALID_PAIRS:
        await update.message.reply_html(
            f"❌ Unknown pair: <code>{pair_arg}</code>. Valid: XAUUSD, GBPJPY, ALL"
        )
        return

    if pair_arg in current_pairs:
        new_pairs = [p for p in current_pairs if p != pair_arg]
        prefs.update(user_id, pairs=new_pairs)
        await update.message.reply_html(f"✅ Unsubscribed from {pair_arg} alerts.")
    else:
        await update.message.reply_html(f"ℹ️ You were not subscribed to {pair_arg}.")


async def _cmd_rundown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rundown — send today's economic calendar summary to the requester."""
    if update.message is None:
        return
    calendar_fn = context.bot_data.get("calendar_fn")

    if not calendar_fn:
        await update.message.reply_html(
            "⚠️ Calendar data is not configured. Contact admin."
        )
        return

    await update.message.reply_html("⏳ Fetching today's economic calendar...")
    try:
        events: list[dict] = await calendar_fn()
        from datetime import timezone as _tz_mod, timedelta as _td
        now_sgt = datetime.now(_tz_mod.utc).astimezone(_tz_mod(_td(hours=8)))
        date_str = now_sgt.strftime("%A %d %b %Y")
        text = format_daily_rundown(events, date_str)
        await update.message.reply_html(text)
    except Exception as exc:  # noqa: BLE001
        logger.error("Manual rundown failed: %s", exc, exc_info=True)
        await update.message.reply_html("❌ Failed to fetch calendar data. Try again later.")


# ─── Callback Query Handler ───────────────────────────────────────────────────

async def _on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses: Skip, Acknowledge, View (deep-link is a URL so no CB)."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()  # stops the loading spinner on the button

    data: str = query.data or ""

    if data.startswith(_CB_SKIP):
        signal_id = data[len(_CB_SKIP):]
        logger.debug("User %s skipped signal %s.", query.from_user.id, signal_id)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass  # message may be too old to edit — swallow silently

    elif data.startswith(_CB_ACK):
        signal_id = data[len(_CB_ACK):]
        logger.debug("User %s acknowledged signal %s.", query.from_user.id, signal_id)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_html("✅ Acknowledged. Check your journal for details.")
        except Exception:  # noqa: BLE001
            pass

    else:
        logger.warning("Unknown callback data: %s", data)


# ─── TradingBot ───────────────────────────────────────────────────────────────

class TradingBot:
    """Async Telegram bot for the made. trading signal platform.

    Lifecycle::

        bot = TradingBot()
        await bot.start()
        ...
        await bot.broadcast_signal(signal_data)
        ...
        await bot.stop()

    Configuration is read from environment variables at instantiation time.
    All send methods are safe to call from external coroutines.
    """

    def __init__(self) -> None:
        self._token: str = os.environ["TELEGRAM_BOT_TOKEN"]
        self._channel_id: str = os.getenv("TELEGRAM_SIGNAL_CHANNEL_ID", "")
        self._deep_link_base: str = os.getenv("APP_DEEP_LINK_BASE", "made://signal/")
        self._admin_ids: list[int] = [
            int(x.strip())
            for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
            if x.strip().isdigit()
        ]

        self._prefs = _UserPreferenceStore()
        self._scheduler = DailyRundownScheduler()
        self._app: Optional[Application] = None

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(
        self,
        calendar_fn=None,
        engine_status: Optional[dict] = None,
    ) -> None:
        """Build the Application, register handlers, and start polling.

        Args:
            calendar_fn: Async callable ``() -> list[dict]`` for calendar data.
                Pass None to disable the daily rundown scheduler.
            engine_status: Optional dict that can be mutated externally to
                reflect live engine health (shown by /status).
        """
        self._app = (
            ApplicationBuilder()
            .token(self._token)
            .build()
        )

        # Store shared state in bot_data (accessible from all handlers)
        self._app.bot_data["prefs"] = self._prefs
        self._app.bot_data["scheduler"] = self._scheduler
        self._app.bot_data["calendar_fn"] = calendar_fn
        self._app.bot_data["trading_bot"] = self
        self._app.bot_data["engine_status"] = engine_status or {
            "live": False,
            "data_feed": "Not connected",
            "last_signal_at": None,
        }

        # Register command handlers
        handlers = [
            CommandHandler("start", _cmd_start),
            CommandHandler("help", _cmd_help),
            CommandHandler("status", _cmd_status),
            CommandHandler("subscribe", _cmd_subscribe),
            CommandHandler("unsubscribe", _cmd_unsubscribe),
            CommandHandler("rundown", _cmd_rundown),
            CallbackQueryHandler(_on_callback_query),
        ]
        for handler in handlers:
            self._app.add_handler(handler)

        # Set up recurring daily rundown if calendar_fn is provided
        if calendar_fn:
            self._scheduler.schedule_daily_rundown(self, calendar_fn)

        logger.info("Starting made. Telegram bot (polling).")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        """Gracefully stop polling, scheduler, and the Application."""
        self._scheduler.shutdown()
        if self._app:
            logger.info("Stopping made. Telegram bot.")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    # ─── Broadcast helpers ────────────────────────────────────────────────────

    def _get_bot(self) -> Bot:
        """Return the underlying Bot instance, raising if not started."""
        if self._app is None:
            raise RuntimeError("TradingBot is not started. Call await start() first.")
        return self._app.bot

    async def broadcast_signal(self, signal_data: dict) -> None:
        """Send a signal alert to the configured broadcast channel.

        Also sends DM alerts to all users subscribed to the signal's pair.
        The channel message includes [View in App | Skip] inline buttons.

        Args:
            signal_data: Signal dict as expected by ``format_signal_message``.
                Must include ``pair`` and ``direction`` keys.
                Optional ``signal_id`` key; falls back to a timestamp-based ID.
        """
        bot = self._get_bot()
        signal_id: str = signal_data.get(
            "signal_id",
            f"{signal_data.get('pair', 'UNK')}_{int(datetime.now(timezone.utc).timestamp())}",
        )
        text = format_signal_message(signal_data)
        keyboard = _signal_keyboard(signal_id, self._deep_link_base)

        # Broadcast to channel (if configured)
        if self._channel_id:
            try:
                await bot.send_message(
                    chat_id=self._channel_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                logger.info("Signal broadcast to channel: %s", signal_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Channel broadcast failed for %s: %s", signal_id, exc)

        # DM alerts to subscribed users
        pair: str = signal_data.get("pair", "")
        style: Optional[str] = signal_data.get("style")
        subscribers = self._prefs.users_subscribed_to(pair, style)

        for user_id in subscribers:
            await self.send_dm_alert(user_id, signal_data)

    async def send_dm_alert(self, user_id: int, signal_data: dict) -> None:
        """Send a signal alert DM to a specific user.

        Silently skips if the user has notifications disabled. Each DM includes
        the [View in App | Skip] inline keyboard.

        Args:
            user_id: Telegram user ID.
            signal_data: Signal dict as expected by ``format_signal_message``.
        """
        prefs = self._prefs.get(user_id)
        if not prefs.get("notifications", True):
            return

        bot = self._get_bot()
        signal_id: str = signal_data.get(
            "signal_id",
            f"{signal_data.get('pair', 'UNK')}_{int(datetime.now(timezone.utc).timestamp())}",
        )
        text = format_signal_message(signal_data)
        keyboard = _signal_keyboard(signal_id, self._deep_link_base)

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            logger.debug("DM sent to user %d for signal %s.", user_id, signal_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DM to user %d failed: %s", user_id, exc)

    async def send_daily_rundown(self, events: list[dict]) -> None:
        """Send the daily economic calendar rundown to all subscribed users.

        Also posts to the broadcast channel if configured.

        Args:
            events: List of event dicts as expected by ``format_daily_rundown``.
        """
        now_sgt = datetime.now(timezone.utc).astimezone(
            __import__("datetime").timezone(
                __import__("datetime").timedelta(hours=8)
            )
        )
        date_str = now_sgt.strftime("%A %d %b %Y")
        text = format_daily_rundown(events, date_str)

        bot = self._get_bot()

        # Broadcast to channel
        if self._channel_id:
            try:
                await bot.send_message(
                    chat_id=self._channel_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                logger.info("Daily rundown broadcast to channel.")
            except Exception as exc:  # noqa: BLE001
                logger.error("Channel daily rundown failed: %s", exc)

        # DM to all registered users with notifications enabled
        for user_id in self._prefs.all_users():
            prefs = self._prefs.get(user_id)
            if not prefs.get("notifications", True):
                continue
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Daily rundown DM to user %d failed: %s", user_id, exc)

    async def send_tp_notification(self, user_id: int, signal_data: dict, tp_level: str) -> None:
        """Send a TP hit notification to a specific user with [Acknowledge] button.

        Args:
            user_id: Telegram user ID.
            signal_data: Signal dict as expected by ``format_tp_hit``.
            tp_level: One of "TP1", "TP2", "TP3".
        """
        bot = self._get_bot()
        signal_id: str = signal_data.get("signal_id", "unknown")
        text = format_tp_hit(signal_data, tp_level)
        keyboard = _outcome_keyboard(signal_id)

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            logger.debug("TP%s notification sent to user %d.", tp_level, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("TP notification to user %d failed: %s", user_id, exc)

    async def send_sl_notification(self, user_id: int, signal_data: dict) -> None:
        """Send an SL hit notification with auto post-mortem to a specific user.

        Args:
            user_id: Telegram user ID.
            signal_data: Signal dict. May include a ``post_mortem`` key with
                auto-generated post-mortem data.
        """
        bot = self._get_bot()
        signal_id: str = signal_data.get("signal_id", "unknown")
        text = format_sl_hit(signal_data)
        keyboard = _outcome_keyboard(signal_id)

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            logger.debug("SL notification sent to user %d.", user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SL notification to user %d failed: %s", user_id, exc)

    async def send_admin_alert(self, message: str) -> None:
        """Send a plain-text alert to all configured admin users.

        Args:
            message: Plain text message to send.
        """
        if not self._admin_ids:
            return
        bot = self._get_bot()
        for admin_id in self._admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=f"[ADMIN] {message}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Admin alert to %d failed: %s", admin_id, exc)

    # ─── Properties ───────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True if the bot application is started."""
        return self._app is not None


# ─── Entry point ──────────────────────────────────────────────────────────────

async def _main() -> None:
    """Minimal async entry point for running the bot standalone."""
    import asyncio
    import signal as _signal
    from datetime import timezone as _tz

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # ── Calendar function ─────────────────────────────────────────────────────
    # Try to use the live CalendarProvider; fall back to static mock events so
    # /rundown is always functional even without API credentials.

    _calendar_fn = None

    try:
        from live.providers.calendar_provider import CalendarProvider
        _cal_provider = CalendarProvider()

        async def _live_calendar_fn() -> list[dict]:
            raw = await _cal_provider.get_events()
            # Normalise CalendarEvent objects / dicts to the format
            # expected by format_daily_rundown
            result = []
            for ev in raw:
                if hasattr(ev, "__dict__"):
                    ev = ev.__dict__
                result.append({
                    "name": ev.get("title") or ev.get("name", "Event"),
                    "time_utc": ev.get("time_utc") or ev.get("time"),
                    "currency": ev.get("currency", ""),
                    "impact": ev.get("impact", "medium"),
                    "forecast": ev.get("forecast"),
                    "previous": ev.get("previous"),
                })
            return result

        _calendar_fn = _live_calendar_fn
        logger.info("Calendar: using live CalendarProvider")
    except Exception as _exc:
        logger.warning("CalendarProvider unavailable (%s) — using mock calendar", _exc)

        async def _mock_calendar_fn() -> list[dict]:
            """Return a realistic set of today's high-impact events as fallback."""
            now_utc = datetime.now(_tz.utc)
            def _offset(hours: float) -> str:
                from datetime import timedelta
                return (now_utc + timedelta(hours=hours)).isoformat()

            return [
                {
                    "name": "US CPI (MoM)",
                    "time_utc": _offset(1.5),
                    "currency": "USD",
                    "impact": "high",
                    "forecast": "0.3%",
                    "previous": "0.2%",
                },
                {
                    "name": "FOMC Minutes",
                    "time_utc": _offset(4),
                    "currency": "USD",
                    "impact": "high",
                    "forecast": None,
                    "previous": None,
                },
                {
                    "name": "BOJ Policy Rate",
                    "time_utc": _offset(8),
                    "currency": "JPY",
                    "impact": "high",
                    "forecast": "0.50%",
                    "previous": "0.50%",
                },
                {
                    "name": "UK GDP (QoQ)",
                    "time_utc": _offset(10),
                    "currency": "GBP",
                    "impact": "high",
                    "forecast": "0.4%",
                    "previous": "0.3%",
                },
            ]

        _calendar_fn = _mock_calendar_fn

    # ── Start bot ─────────────────────────────────────────────────────────────
    bot = TradingBot()
    await bot.start(calendar_fn=_calendar_fn)
    logger.info("Bot is running. Press Ctrl+C to stop.")

    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):  # noqa: ANN001
        logger.info("Received signal %s — shutting down.", sig)
        stop_event.set()

    _signal.signal(_signal.SIGINT, _handle_signal)
    _signal.signal(_signal.SIGTERM, _handle_signal)

    await stop_event.wait()
    await bot.stop()
    logger.info("Bot stopped.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
