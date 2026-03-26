"""
Automatic post-mortem generator — triggered on SL hit.

Analyzes which module failed and why, cross-references economic calendar,
and generates a structured human-readable explanation.

Per CLAUDE.md §14.2:
- Which module was wrong (strongest module that voted in signal direction but was invalidated)
- What happened (news event? HTF structural break? Liquidity grab?)
- Lesson (one-sentence takeaway)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Lesson templates keyed by failure category ────────────────────────────────

LESSONS: dict[str, str] = {
    "news_spike": (
        "This trade was hit by news volatility — consider avoiding entries within "
        "30 min of high-impact events."
    ),
    "stop_hunt": (
        "Price swept liquidity below/above the SL before reversing — widen stop by "
        "0.5x ATR or wait for liquidity grab confirmation."
    ),
    "structural_break": (
        "The {module} zone was breached — this signals a structural shift against "
        "the trade direction."
    ),
    "gap": (
        "A gap open invalidated the setup — check for weekend or major news gaps "
        "before holding positions."
    ),
    "trend_reversal": (
        "Higher-timeframe structure shifted against the trade — always confirm HTF "
        "bias before entry."
    ),
    "normal": (
        "The {module} setup did not hold — this is within normal statistical loss rates."
    ),
}

# What-happened descriptions per failure category
_WHAT_HAPPENED: dict[str, str] = {
    "news_spike": (
        "A high-impact news event caused a sharp spike that triggered the stop loss. "
        "News-driven moves often exceed normal ATR ranges and are unpredictable."
    ),
    "stop_hunt": (
        "Price briefly penetrated the stop loss level in a liquidity grab before "
        "reversing — a classic institutional sweep of retail stop orders."
    ),
    "structural_break": (
        "Price broke through the {module} zone without respecting it, indicating "
        "that the institutional order flow shifted against the trade direction."
    ),
    "gap": (
        "Price gapped past the stop loss level at session open, likely due to "
        "overnight news or weekend market events."
    ),
    "trend_reversal": (
        "The higher-timeframe trend reversed against the trade, overriding the "
        "entry-timeframe setup with stronger opposing momentum."
    ),
    "normal": (
        "Price moved against the trade and hit the stop loss. The {module} setup "
        "did not play out as expected within the signal's validity window."
    ),
}

# Module display names for human-readable output
_MODULE_DISPLAY: dict[str, str] = {
    "market_structure": "Market Structure (CHoCH/BOS)",
    "order_blocks_fvg": "Order Block / FVG",
    "ote": "OTE Fibonacci",
    "ema": "EMA Alignment",
    "rsi": "RSI",
    "macd": "MACD",
    "bollinger": "Bollinger Bands",
    "kill_zone": "Kill Zone Timing",
    "support_resistance": "Support & Resistance",
}


@dataclass
class PostMortem:
    """Structured post-mortem report for a stopped-out trade."""
    signal_id: str
    failed_module: str
    failure_category: str
    what_happened: str
    lesson: str
    news_attributed: bool
    was_stop_hunt: bool
    was_gap: bool


class PostMortemGenerator:
    """
    Generates a structured post-mortem report when a trade hits its stop loss.

    The generator identifies the primary module that failed (the strongest module
    that voted in the signal's direction), determines the failure category by
    cross-referencing the exit bar and any nearby news events, and renders
    human-readable explanations with pre-written templates.
    """

    # Stop hunt threshold: price must exceed SL by this fraction before reversing
    STOP_HUNT_MULTIPLIER = 2.0  # 2x pip size = likely stop hunt

    # Pip sizes for rough comparison
    _PIP_SIZES: dict[str, float] = {
        "XAUUSD": 0.1,
        "GBPJPY": 0.01,
    }

    def generate(
        self,
        signal: dict,
        exit_bar: dict,
        news_events: list[dict] | None = None,
    ) -> PostMortem:
        """
        Generate a post-mortem for a stopped-out trade.

        Args:
            signal: Signal dict with keys:
                - direction (str): "BUY" or "SELL"
                - entry_price (float)
                - stop_loss (float)
                - module_scores (dict[str, float]): module name → raw score
                - generated_at (datetime): when the signal was created
                - pair (str): "XAUUSD" or "GBPJPY"
                - signal_id (str, optional)
            exit_bar: Bar dict with keys:
                - open, high, low, close (float)
                - timestamp (datetime)
                - pair (str)
            news_events: List of news event dicts with keys:
                - name (str): event name
                - timestamp (datetime): event time
                - impact (str): "HIGH", "MEDIUM", or "LOW"

        Returns:
            PostMortem dataclass with all fields populated.
        """
        signal_id = signal.get("signal_id", "unknown")
        direction = signal.get("direction", "BUY")
        pair = signal.get("pair", exit_bar.get("pair", "XAUUSD"))
        stop_loss = float(signal.get("stop_loss", 0.0))
        module_scores: dict[str, float] = signal.get("module_scores", {})

        # Identify the failed module (highest-magnitude score agreeing with direction)
        failed_module = self._identify_failed_module(direction, module_scores)

        # Classify the failure
        was_news = self._check_news_proximity(
            exit_bar.get("timestamp"), news_events or []
        )
        was_stop_hunt = self._check_stop_hunt(direction, stop_loss, exit_bar, pair)
        was_gap = self._check_gap(direction, stop_loss, exit_bar)

        failure_category = self._categorize_failure(
            signal, exit_bar, news_events or [],
            was_news=was_news,
            was_stop_hunt=was_stop_hunt,
            was_gap=was_gap,
        )

        # Render human-readable text
        module_display = _MODULE_DISPLAY.get(failed_module, failed_module)
        what_happened = _WHAT_HAPPENED.get(failure_category, _WHAT_HAPPENED["normal"])
        what_happened = what_happened.format(module=module_display)

        lesson = LESSONS.get(failure_category, LESSONS["normal"])
        lesson = lesson.format(module=module_display)

        return PostMortem(
            signal_id=signal_id,
            failed_module=failed_module,
            failure_category=failure_category,
            what_happened=what_happened,
            lesson=lesson,
            news_attributed=was_news,
            was_stop_hunt=was_stop_hunt,
            was_gap=was_gap,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _identify_failed_module(
        self, direction: str, module_scores: dict[str, float]
    ) -> str:
        """
        Find the highest-magnitude module that agreed with the signal direction.

        For a BUY signal, we look for the module with the highest positive score.
        For a SELL signal, we look for the module with the most negative score
        (highest absolute negative value).
        """
        if not module_scores:
            return "market_structure"

        is_buy = direction.upper() == "BUY"
        best_module = None
        best_magnitude = -1.0

        for module, score in module_scores.items():
            # Check that the score agrees with signal direction
            if is_buy and score > 0:
                if abs(score) > best_magnitude:
                    best_magnitude = abs(score)
                    best_module = module
            elif not is_buy and score < 0:
                if abs(score) > best_magnitude:
                    best_magnitude = abs(score)
                    best_module = module

        # Fall back to the module with largest absolute score if none agreed
        if best_module is None:
            best_module = max(module_scores, key=lambda m: abs(module_scores[m]))

        return best_module

    def _check_news_proximity(
        self,
        exit_timestamp: datetime | None,
        news_events: list[dict],
    ) -> bool:
        """
        Return True if any high-impact news event occurred within 30 min of exit.
        """
        if exit_timestamp is None or not news_events:
            return False

        # Ensure timezone awareness
        if exit_timestamp.tzinfo is None:
            exit_timestamp = exit_timestamp.replace(tzinfo=timezone.utc)

        window = timedelta(minutes=30)

        for event in news_events:
            impact = str(event.get("impact", "")).upper()
            if impact not in ("HIGH", "EXTREME"):
                continue

            event_time = event.get("timestamp")
            if event_time is None:
                continue

            if isinstance(event_time, str):
                try:
                    from datetime import datetime as dt_cls
                    event_time = dt_cls.fromisoformat(event_time)
                except ValueError:
                    continue

            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            if abs(exit_timestamp - event_time) <= window:
                return True

        return False

    def _check_stop_hunt(
        self,
        direction: str,
        stop_loss: float,
        exit_bar: dict,
        pair: str,
    ) -> bool:
        """
        Return True if price exceeded the SL by more than 2x pip size,
        suggesting a liquidity sweep rather than a genuine structural break.

        A stop hunt typically shows as: price spikes through SL level then
        the bar closes back near or above SL (on the bar's close vs low).
        """
        pip_size = self._PIP_SIZES.get(pair, 0.1)
        threshold = self.STOP_HUNT_MULTIPLIER * pip_size

        bar_low = float(exit_bar.get("low", 0.0))
        bar_high = float(exit_bar.get("high", 0.0))
        bar_close = float(exit_bar.get("close", 0.0))

        if direction.upper() == "BUY":
            # SL is below entry; stop hunt = price wick significantly below SL
            overshoot = stop_loss - bar_low
            if overshoot >= threshold:
                # Close recovered back above SL level — confirms stop hunt
                if bar_close > stop_loss:
                    return True
                # Even if close is below, a large wick (>2x pip) indicates sweep
                if overshoot >= threshold * 2:
                    return True
        else:  # SELL
            overshoot = bar_high - stop_loss
            if overshoot >= threshold:
                if bar_close < stop_loss:
                    return True
                if overshoot >= threshold * 2:
                    return True

        return False

    def _check_gap(
        self,
        direction: str,
        stop_loss: float,
        exit_bar: dict,
    ) -> bool:
        """
        Return True if price gapped past the SL (bar open already beyond SL).

        This happens at session opens when overnight news causes the market
        to open far from the previous close, skipping over the stop level.
        """
        bar_open = float(exit_bar.get("open", 0.0))

        if direction.upper() == "BUY":
            # A gap down for a long position opens below the SL
            return bar_open < stop_loss
        else:
            # A gap up for a short position opens above the SL
            return bar_open > stop_loss

    def _categorize_failure(
        self,
        signal: dict,
        exit_bar: dict,
        news_events: list[dict],
        *,
        was_news: bool,
        was_stop_hunt: bool,
        was_gap: bool,
    ) -> str:
        """
        Determine the primary failure category.

        Priority order:
        1. news_spike  — news event drove the move
        2. gap         — price gapped past SL (often news-related but distinct)
        3. stop_hunt   — price swept SL then reversed
        4. structural_break — market structure broke (BOS/CHoCH against trade)
        5. trend_reversal  — HTF trend reversed
        6. normal      — no clear cause; within statistical norms

        Returns one of: "news_spike", "stop_hunt", "gap", "structural_break",
                        "trend_reversal", "normal"
        """
        if was_news:
            return "news_spike"

        if was_gap:
            return "gap"

        if was_stop_hunt:
            return "stop_hunt"

        # Check if market structure module had the highest score (structural failure)
        module_scores: dict[str, float] = signal.get("module_scores", {})
        direction = signal.get("direction", "BUY")
        failed_module = self._identify_failed_module(direction, module_scores)

        if failed_module in ("market_structure", "order_blocks_fvg", "ote", "support_resistance"):
            return "structural_break"

        if failed_module in ("ema",):
            return "trend_reversal"

        return "normal"
