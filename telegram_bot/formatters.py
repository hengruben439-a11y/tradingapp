"""
Signal formatting helpers for the made. Telegram bot.

All functions return Telegram HTML-formatted strings suitable for
`parse_mode=ParseMode.HTML` in python-telegram-bot messages.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


# ─── Constants ────────────────────────────────────────────────────────────────

SGT_OFFSET = timedelta(hours=8)  # UTC+8

_CONFIDENCE_LABELS: list[tuple[float, str]] = [
    (0.80, "Very Strong"),
    (0.65, "Strong"),
    (0.50, "Moderate"),
    (0.30, "Weak"),
]

_IMPACT_EMOJI: dict[str, str] = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _confidence_label(score: float) -> str:
    """Convert a raw confluence score to a plain-English confidence label.

    Args:
        score: Absolute confidence score in range [0.0, 1.0].

    Returns:
        One of "Very Strong", "Strong", "Moderate", "Weak", or "Neutral".
    """
    abs_score = abs(score)
    for threshold, label in _CONFIDENCE_LABELS:
        if abs_score >= threshold:
            return label
    return "Neutral"


def _fmt_price(pair: str, price: float) -> str:
    """Format a price value consistently for the given pair.

    XAUUSD: 2 decimal places with comma thousands separator (e.g. 2,341.50).
    GBPJPY: 3 decimal places (e.g. 192.345).
    """
    if pair.upper() == "XAUUSD":
        return f"{price:,.2f}"
    return f"{price:.3f}"


def _to_sgt(dt: datetime) -> datetime:
    """Convert a UTC datetime to SGT (UTC+8).

    If the datetime is naive, it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(SGT_OFFSET))


def _sgt_time_str(dt: datetime) -> str:
    """Return a HH:MM SGT string from a UTC or timezone-aware datetime."""
    return _to_sgt(dt).strftime("%H:%M SGT")


# ─── Signal Message ───────────────────────────────────────────────────────────

def format_signal_message(signal: dict) -> str:
    """Return a Telegram HTML-formatted signal alert message.

    Expected keys in `signal`:
        pair (str): "XAUUSD" or "GBPJPY"
        direction (str): "BUY" or "SELL"
        entry (float): Entry price
        sl (float): Stop-loss price
        tp1 (float): Take-profit level 1
        tp2 (float): Take-profit level 2
        tp3 (float): Take-profit level 3
        confidence (float): Raw confluence score, 0.0–1.0
        kill_zone (str | None): Active kill zone name, e.g. "London"
        generated_at (datetime | None): UTC timestamp of signal generation
        timeframe (str | None): e.g. "15m", "1H", "4H"
        lot_size (float | None): Suggested lot size
        risk_usd (float | None): Dollar risk amount
        style (str | None): Trading style label e.g. "Day Trading"

    Returns:
        HTML-formatted string ready for Telegram.
    """
    pair: str = signal.get("pair", "UNKNOWN").upper()
    direction: str = signal.get("direction", "BUY").upper()
    entry: float = signal.get("entry", 0.0)
    sl: float = signal.get("sl", 0.0)
    tp1: float = signal.get("tp1", 0.0)
    tp2: float = signal.get("tp2", 0.0)
    tp3: float = signal.get("tp3", 0.0)
    confidence: float = abs(signal.get("confidence", 0.0))
    kill_zone: Optional[str] = signal.get("kill_zone")
    generated_at: Optional[datetime] = signal.get("generated_at")
    timeframe: Optional[str] = signal.get("timeframe")
    lot_size: Optional[float] = signal.get("lot_size")
    risk_usd: Optional[float] = signal.get("risk_usd")

    direction_emoji = "🟢" if direction == "BUY" else "🔴"
    conf_label = _confidence_label(confidence)
    conf_pct = f"{confidence * 100:.0f}%"

    p = lambda v: _fmt_price(pair, v)  # noqa: E731 — local alias

    header = f"{direction_emoji} <b>{direction} SIGNAL — {pair}</b>"
    if timeframe:
        header += f" <i>[{timeframe}]</i>"

    separator = "━━━━━━━━━━━━━━━━━━━━━"

    lines = [
        header,
        separator,
        f"📍 Entry:      <code>{p(entry)}</code>",
        f"🛡 Stop Loss:  <code>{p(sl)}</code>",
        f"🎯 TP1:        <code>{p(tp1)}</code> (40%)",
        f"🎯 TP2:        <code>{p(tp2)}</code> (30%)",
        f"🎯 TP3:        <code>{p(tp3)}</code> (30%)",
        separator,
        f"📊 Confidence: <b>{conf_label} ({conf_pct})</b>",
    ]

    if kill_zone:
        kz_display = kill_zone.replace("_", " ")
        lines.append(f"⏰ {kz_display} Kill Zone")

    if generated_at:
        lines.append(f"🕐 Generated:  {_sgt_time_str(generated_at)}")

    if lot_size is not None and risk_usd is not None:
        lines.append("")
        lines.append(f"<i>Risk 1% = {lot_size:.2f} lots = ${risk_usd:.2f}</i>")

    return "\n".join(lines)


# ─── Daily Rundown ────────────────────────────────────────────────────────────

def format_daily_rundown(events: list[dict], date: str) -> str:
    """Return a Telegram HTML-formatted daily economic calendar rundown.

    Args:
        events: List of event dicts. Expected keys per event:
            name (str): Event name, e.g. "NFP"
            time_utc (datetime | str): Event time in UTC (datetime or ISO string)
            currency (str): Affected currency, e.g. "USD"
            impact (str): "high", "medium", or "low"
            forecast (str | None): Forecast value
            previous (str | None): Previous value
        date: Display date string, e.g. "Thursday 26 Mar 2026"

    Returns:
        HTML-formatted string.
    """
    lines = [
        f"📅 <b>Daily Rundown — {date}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        "All times in SGT (UTC+8)",
        "",
    ]

    if not events:
        lines.append("✅ No high-impact events scheduled today.")
        lines.append("")
        lines.append("<i>Trade with care. Low-news days can still produce false breakouts.</i>")
        return "\n".join(lines)

    for event in events:
        name: str = event.get("name", "Unknown Event")
        currency: str = event.get("currency", "???")
        impact: str = str(event.get("impact", "medium")).lower()
        forecast: Optional[str] = event.get("forecast")
        previous: Optional[str] = event.get("previous")

        # Parse time
        time_raw = event.get("time_utc")
        if isinstance(time_raw, datetime):
            time_str = _sgt_time_str(time_raw)
        elif isinstance(time_raw, str) and time_raw:
            try:
                parsed = datetime.fromisoformat(time_raw.replace("Z", "+00:00"))
                time_str = _sgt_time_str(parsed)
            except ValueError:
                time_str = time_raw
        else:
            time_str = "TBD"

        impact_emoji = _IMPACT_EMOJI.get(impact, "⚪")
        event_line = f"{impact_emoji} <b>{time_str}</b>  {currency} — {name}"

        if forecast or previous:
            detail_parts = []
            if forecast:
                detail_parts.append(f"Forecast: {forecast}")
            if previous:
                detail_parts.append(f"Prev: {previous}")
            event_line += f"\n    <i>{' | '.join(detail_parts)}</i>"

        lines.append(event_line)

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("<i>⚠️ Signals are suppressed 15 min before and 5 min after 🔴 events.</i>")

    return "\n".join(lines)


# ─── TP Hit ───────────────────────────────────────────────────────────────────

def format_tp_hit(signal: dict, tp_level: str) -> str:
    """Return a Telegram HTML message for a take-profit level being hit.

    Args:
        signal: Signal dict with same keys as `format_signal_message`.
        tp_level: One of "TP1", "TP2", "TP3".

    Returns:
        HTML-formatted string.
    """
    pair: str = signal.get("pair", "UNKNOWN").upper()
    direction: str = signal.get("direction", "BUY").upper()
    tp_level_upper = tp_level.upper()

    tp_prices: dict[str, Optional[float]] = {
        "TP1": signal.get("tp1"),
        "TP2": signal.get("tp2"),
        "TP3": signal.get("tp3"),
    }
    close_pcts: dict[str, str] = {
        "TP1": "40%",
        "TP2": "30%",
        "TP3": "30% (full target)",
    }
    sl_actions: dict[str, str] = {
        "TP1": "Move SL to breakeven",
        "TP2": "Trail SL to TP1",
        "TP3": "Position fully closed",
    }

    hit_price = tp_prices.get(tp_level_upper)
    p = lambda v: _fmt_price(pair, v) if v is not None else "—"  # noqa: E731

    direction_emoji = "🟢" if direction == "BUY" else "🔴"
    tp_emoji_map = {"TP1": "🥇", "TP2": "🥈", "TP3": "🏆"}
    tp_emoji = tp_emoji_map.get(tp_level_upper, "🎯")

    lines = [
        f"{tp_emoji} <b>{tp_level_upper} HIT — {pair}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{direction_emoji} Direction: <b>{direction}</b>",
        f"💰 {tp_level_upper} Price:  <code>{p(hit_price)}</code>",
        f"📦 Close: {close_pcts.get(tp_level_upper, '')} of position",
        "",
        f"➡️  Action: {sl_actions.get(tp_level_upper, '')}",
    ]

    if tp_level_upper == "TP1":
        lines.append("")
        lines.append("<i>TP2 and TP3 still active. Ride the move.</i>")
    elif tp_level_upper == "TP2":
        tp3_price = tp_prices.get("TP3")
        lines.append("")
        lines.append(f"<i>Final target TP3 at <code>{p(tp3_price)}</code>. SL trailed to TP1.</i>")
    else:
        lines.append("")
        lines.append("<i>Full target reached. Well traded. 🎯</i>")

    return "\n".join(lines)


# ─── SL Hit ───────────────────────────────────────────────────────────────────

def format_sl_hit(signal: dict) -> str:
    """Return a Telegram HTML message for a stop-loss hit with post-mortem excerpt.

    Args:
        signal: Signal dict. In addition to standard keys, may include:
            post_mortem (dict | None): Auto-generated post-mortem with keys:
                module_failed (str): e.g. "Order Block"
                what_happened (str): Brief description
                lesson (str): One-sentence takeaway

    Returns:
        HTML-formatted string.
    """
    pair: str = signal.get("pair", "UNKNOWN").upper()
    direction: str = signal.get("direction", "BUY").upper()
    sl: float = signal.get("sl", 0.0)
    entry: float = signal.get("entry", 0.0)

    p = lambda v: _fmt_price(pair, v)  # noqa: E731
    direction_emoji = "🟢" if direction == "BUY" else "🔴"

    # Rough P&L in pips (negative)
    if direction == "BUY":
        pip_delta = sl - entry
    else:
        pip_delta = entry - sl

    if pair == "XAUUSD":
        pips = pip_delta * 100  # XAU: 1 pip = $0.01
        pips_label = f"{pips:.0f} pips"
    else:
        pips = pip_delta * 100
        pips_label = f"{abs(pips):.1f} pips"

    lines = [
        f"🛑 <b>STOP LOSS HIT — {pair}</b>",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{direction_emoji} Direction: <b>{direction}</b>",
        f"📍 Entry:    <code>{p(entry)}</code>",
        f"🛡 SL Hit:   <code>{p(sl)}</code>  ({pips_label})",
        "",
        "📋 <b>Auto Post-Mortem</b>",
    ]

    post_mortem: Optional[dict] = signal.get("post_mortem")

    if post_mortem:
        module_failed: str = post_mortem.get("module_failed", "Unknown module")
        what_happened: str = post_mortem.get(
            "what_happened",
            "Price invalidated the trade setup.",
        )
        lesson: str = post_mortem.get(
            "lesson",
            "Review the setup conditions before the next trade.",
        )
        lines += [
            f"❌ <b>Module:</b> {module_failed}",
            f"🔍 <b>What happened:</b> {what_happened}",
            f"📚 <b>Lesson:</b> <i>{lesson}</i>",
        ]
    else:
        lines += [
            "❌ <b>Module:</b> Analysis unavailable",
            (
                "🔍 <b>What happened:</b> Price moved against the trade thesis "
                "and hit the structural invalidation level."
            ),
            "<i>Open the app for a full post-mortem breakdown.</i>",
        ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "<i>Losses are part of any edge-based strategy. Review in your journal.</i>",
    ]

    return "\n".join(lines)
