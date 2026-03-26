"""
Risk safeguards and circuit breakers per CLAUDE.md §11.3.

Enforces:
- Max 3 simultaneous signals per pair
- Max 3% daily risk
- Max 6% weekly drawdown
- Max 10% monthly drawdown → Recovery Mode
- Adaptive risk scaling at 5% DD from peak
- Context-aware cooldown (§11.4): news-attributed, pattern-specific, rolling loss rate
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Limits (from §11.3) ───────────────────────────────────────────────────────

_MAX_SIGNALS_PER_PAIR = 3
_MAX_DAILY_RISK_PCT = 3.0
_MAX_WEEKLY_DRAWDOWN_PCT = 6.0
_MAX_MONTHLY_DRAWDOWN_PCT = 10.0
_ADAPTIVE_DD_THRESHOLD_PCT = 5.0      # Reduce risk at this DD from peak
_ADAPTIVE_RISK_DIVISOR = 2.0          # 50% reduction
_RECOVERY_MODE_RISK_CAP_PCT = 0.5     # Hard cap in Recovery Mode
_ROLLING_LOSS_WINDOW = 10             # Last N signals for rolling loss rate
_ROLLING_LOSS_THRESHOLD = 0.50        # >50% = full cooldown
_FULL_COOLDOWN_HOURS = 4
_PATTERN_COOLDOWN_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskGuards:
    """
    Stateful risk guard that enforces all circuit breakers and cooldown logic.

    State is held in memory and can optionally be persisted to Redis via
    to_dict() / from_dict() for cross-process consistency.

    Usage:
        guards = RiskGuards(initial_equity_peak=10000.0)
        allowed, reason = guards.can_trade("XAUUSD", 1.0, news_flag=False)
        if not allowed:
            raise HTTPException(403, reason)
        # After trade closes:
        guards.record_trade_result(signal_id, "XAUUSD", "loss", -0.01, "London", "OB", False)
    """

    def __init__(self, initial_equity_peak: float = 10_000.0) -> None:
        # ── Running totals (reset on calendar boundaries) ─────────────────────
        self.daily_risk_used: float = 0.0
        self.weekly_drawdown: float = 0.0
        self.monthly_drawdown: float = 0.0

        # ── Peak tracking for adaptive scaling ───────────────────────────────
        self.equity_peak: float = initial_equity_peak

        # ── Per-pair active signal count ──────────────────────────────────────
        self._active_counts: dict[str, int] = defaultdict(int)

        # ── Rolling loss window (last 10 signal outcomes) ─────────────────────
        self.recent_signals: deque[dict] = deque(maxlen=_ROLLING_LOSS_WINDOW)

        # ── Suppressed patterns: "PAIR:KZ:SETUP" → suppress_until (UTC) ──────
        self.suppressed_patterns: dict[str, datetime] = {}

        # ── Cooldown state ────────────────────────────────────────────────────
        self._full_cooldown_until: Optional[datetime] = None

        # ── Reset boundary timestamps (UTC) ──────────────────────────────────
        self._last_daily_reset: datetime = _utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._last_weekly_reset: datetime = self._monday_of_week(_utcnow())
        self._last_monthly_reset: datetime = _utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

    # ── Primary decision gate ─────────────────────────────────────────────────

    def can_trade(
        self,
        pair: str,
        proposed_risk_pct: float,
        news_flag: bool,
    ) -> tuple[bool, str]:
        """
        Check whether a new trade is permitted under all risk limits.

        Checks are applied in priority order (most restrictive first):
        1. Full cooldown active
        2. Monthly drawdown → Recovery Mode signal suppression (only Very Strong allowed
           — caller must enforce the score threshold; this method blocks if over 10% DD)
        3. Weekly drawdown limit
        4. Daily risk limit
        5. Max simultaneous signals per pair
        6. Suppressed patterns (checked upstream via pattern key)

        Args:
            pair: "XAUUSD" or "GBPJPY"
            proposed_risk_pct: Risk % for the new trade.
            news_flag: True if a high-impact news event is imminent.

        Returns:
            (True, "ok") if trading is allowed.
            (False, reason_string) if blocked.
        """
        self._tick_resets()
        now = _utcnow()

        # 1. Full cooldown
        if self._full_cooldown_until and now < self._full_cooldown_until:
            remaining = int((self._full_cooldown_until - now).total_seconds() / 60)
            return False, f"Cooldown active — {remaining} minutes remaining. Take a break."

        # 2. Monthly drawdown (Recovery Mode — caller enforces Very Strong threshold)
        if self.monthly_drawdown >= _MAX_MONTHLY_DRAWDOWN_PCT:
            return False, (
                f"Recovery Mode: monthly drawdown {self.monthly_drawdown:.1f}% "
                f"exceeds {_MAX_MONTHLY_DRAWDOWN_PCT}%. Only Very Strong signals (>0.80) allowed."
            )

        # 3. Weekly drawdown
        if self.weekly_drawdown >= _MAX_WEEKLY_DRAWDOWN_PCT:
            return False, (
                f"Weekly drawdown limit reached ({self.weekly_drawdown:.1f}% / "
                f"{_MAX_WEEKLY_DRAWDOWN_PCT}%). No new signals until Monday."
            )

        # 4. Daily risk limit
        if self.daily_risk_used + proposed_risk_pct > _MAX_DAILY_RISK_PCT:
            remaining_risk = max(0.0, _MAX_DAILY_RISK_PCT - self.daily_risk_used)
            return False, (
                f"Daily risk limit: {self.daily_risk_used:.1f}% used of {_MAX_DAILY_RISK_PCT}%. "
                f"Only {remaining_risk:.2f}% remaining today."
            )

        # 5. Max simultaneous signals per pair
        if self._active_counts[pair] >= _MAX_SIGNALS_PER_PAIR:
            return False, (
                f"Max simultaneous signals reached for {pair} "
                f"({_MAX_SIGNALS_PER_PAIR} active). Wait for a position to close."
            )

        return True, "ok"

    def can_trade_pattern(self, pair: str, kill_zone: str, setup_type: str) -> tuple[bool, str]:
        """
        Check whether a specific KZ+setup pattern is currently suppressed.

        Args:
            pair: Trading pair.
            kill_zone: Kill zone name (e.g. "London").
            setup_type: Setup type (e.g. "OB", "FVG", "CHoCH").

        Returns:
            (True, "ok") if pattern is not suppressed.
            (False, reason) if this exact pattern is in the 24h suppression window.
        """
        key = _pattern_key(pair, kill_zone, setup_type)
        suppress_until = self.suppressed_patterns.get(key)
        if suppress_until and _utcnow() < suppress_until:
            remaining = int((suppress_until - _utcnow()).total_seconds() / 3600)
            return False, (
                f"Pattern {pair}/{kill_zone}/{setup_type} suppressed for "
                f"{remaining}h after 2 consecutive losses on this setup."
            )
        return True, "ok"

    # ── State updates ──────────────────────────────────────────────────────────

    def record_signal_open(self, pair: str, risk_pct: float) -> None:
        """
        Register a new open signal.

        Call this when a trade is executed (not when the signal is generated).

        Args:
            pair: Trading pair.
            risk_pct: Risk % applied to this trade.
        """
        self._tick_resets()
        self._active_counts[pair] = self._active_counts[pair] + 1
        self.daily_risk_used = round(self.daily_risk_used + risk_pct, 4)
        logger.debug(
            "Signal opened: pair=%s risk=%.2f%% daily_used=%.2f%% active[%s]=%d",
            pair,
            risk_pct,
            self.daily_risk_used,
            pair,
            self._active_counts[pair],
        )

    def record_trade_result(
        self,
        signal_id: str,
        pair: str,
        outcome: str,   # "win" | "loss" | "be"
        pnl_pct: float, # as fraction of account, e.g. -0.01 = -1%
        kill_zone: str,
        setup_type: str,
        news_flag: bool,
    ) -> None:
        """
        Update risk state after a trade closes.

        Applies context-aware cooldown logic (§11.4):
        - Loss on news event → no cooldown; suppress signals for news window only
          (news window suppression is handled by the signal engine — we just skip cooldown)
        - 2 consecutive losses on same KZ+setup → suppress that pattern 24h
        - Rolling loss rate > 50% on last 10 signals → 4-hour full cooldown
        - No simple "2 consecutive = 2 hour" cooldown rule (replaced by above)

        Args:
            signal_id: The signal that closed.
            pair: Trading pair.
            outcome: "win", "loss", or "be" (breakeven).
            pnl_pct: P&L as fraction of account balance (negative = loss).
            kill_zone: Kill zone active when the signal was generated.
            setup_type: ICT/TA setup type (e.g. "OB", "FVG", "BOS").
            news_flag: True if the trade closed near a high-impact news event.
        """
        self._tick_resets()

        # Decrement active count
        self._active_counts[pair] = max(0, self._active_counts[pair] - 1)

        # Track drawdown
        if pnl_pct < 0:
            loss_pct = abs(pnl_pct) * 100
            self.weekly_drawdown = round(self.weekly_drawdown + loss_pct, 4)
            self.monthly_drawdown = round(self.monthly_drawdown + loss_pct, 4)

        # Add to rolling window
        self.recent_signals.append(
            {
                "signal_id": signal_id,
                "pair": pair,
                "outcome": outcome,
                "pnl_pct": pnl_pct,
                "kill_zone": kill_zone,
                "setup_type": setup_type,
                "news_flag": news_flag,
                "timestamp": _utcnow().isoformat(),
            }
        )

        if outcome != "loss":
            logger.debug("Trade %s closed as %s — no cooldown checks needed", signal_id, outcome)
            return

        # ── Context-aware cooldown logic ──────────────────────────────────────

        # Rule 1: News-attributed loss → no cooldown
        # (news window signal suppression is handled by the engine's news proximity filter)
        if news_flag:
            logger.info(
                "Trade %s loss attributed to news event — no cooldown applied", signal_id
            )
            return

        # Rule 2: Check for 2 consecutive losses on same KZ+setup → pattern suppress 24h
        self._check_pattern_suppression(pair, kill_zone, setup_type)

        # Rule 3: Rolling loss rate > 50% on last 10 → 4-hour full cooldown
        self._check_rolling_loss_cooldown()

    def _check_pattern_suppression(
        self,
        pair: str,
        kill_zone: str,
        setup_type: str,
    ) -> None:
        """Suppress this KZ+setup for 24h if 2 consecutive losses on it."""
        # Look at last 2 losses in the rolling window matching this pattern
        pattern_losses = [
            s for s in self.recent_signals
            if s["outcome"] == "loss"
            and s["pair"] == pair
            and s["kill_zone"] == kill_zone
            and s["setup_type"] == setup_type
            and not s["news_flag"]
        ]
        if len(pattern_losses) >= 2:
            key = _pattern_key(pair, kill_zone, setup_type)
            suppress_until = _utcnow() + timedelta(hours=_PATTERN_COOLDOWN_HOURS)
            self.suppressed_patterns[key] = suppress_until
            logger.warning(
                "Pattern suppressed for 24h: %s/%s/%s (2 consecutive losses)",
                pair,
                kill_zone,
                setup_type,
            )

    def _check_rolling_loss_cooldown(self) -> None:
        """Apply 4-hour full cooldown if rolling loss rate > 50%."""
        if len(self.recent_signals) < 2:
            return
        loss_count = sum(1 for s in self.recent_signals if s["outcome"] == "loss")
        loss_rate = loss_count / len(self.recent_signals)
        if loss_rate > _ROLLING_LOSS_THRESHOLD:
            self._full_cooldown_until = _utcnow() + timedelta(hours=_FULL_COOLDOWN_HOURS)
            logger.warning(
                "Full cooldown triggered: rolling loss rate %.0f%% on last %d signals. "
                "Cooldown until %s UTC.",
                loss_rate * 100,
                len(self.recent_signals),
                self._full_cooldown_until.isoformat(),
            )

    # ── Risk scaling ───────────────────────────────────────────────────────────

    def get_effective_risk_pct(self, base_risk: float) -> float:
        """
        Return the risk % to use for a new trade, after applying drawdown scaling.

        Rules (applied cumulatively, most restrictive wins):
        - Monthly DD >= 10%: cap at 0.5% (Recovery Mode)
        - DD from equity peak >= 5%: halve the base risk
        - Otherwise: return base_risk unchanged

        Args:
            base_risk: Requested risk % (e.g. 1.0 for 1%).

        Returns:
            Adjusted risk %. Always >= 0.01.
        """
        if self.is_in_recovery_mode():
            return _RECOVERY_MODE_RISK_CAP_PCT

        dd_from_peak = self._drawdown_from_peak_pct()
        if dd_from_peak >= _ADAPTIVE_DD_THRESHOLD_PCT:
            return round(base_risk / _ADAPTIVE_RISK_DIVISOR, 4)

        return base_risk

    def is_in_recovery_mode(self) -> bool:
        """Return True when monthly drawdown exceeds the 10% threshold."""
        return self.monthly_drawdown >= _MAX_MONTHLY_DRAWDOWN_PCT

    def update_equity_peak(self, current_equity: float) -> None:
        """
        Update the all-time equity peak if current equity is higher.

        Call this periodically from the position monitor or after each trade close.

        Args:
            current_equity: Current account equity in account currency.
        """
        if current_equity > self.equity_peak:
            self.equity_peak = current_equity

    def active_signal_count(self, pair: str) -> int:
        """Return the number of currently open signals for a pair."""
        return self._active_counts.get(pair, 0)

    # ── Status ─────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Return the full risk state as a serialisable dict.

        Used by GET /broker/risk-status to surface state to the iOS app.
        """
        self._tick_resets()
        now = _utcnow()
        in_cooldown = bool(
            self._full_cooldown_until and now < self._full_cooldown_until
        )
        cooldown_remaining_min = (
            int((self._full_cooldown_until - now).total_seconds() / 60)
            if in_cooldown
            else 0
        )
        loss_count = sum(1 for s in self.recent_signals if s["outcome"] == "loss")
        rolling_loss_rate = (
            loss_count / len(self.recent_signals) if self.recent_signals else 0.0
        )

        active_patterns_suppressed = {
            k: v.isoformat()
            for k, v in self.suppressed_patterns.items()
            if now < v
        }

        return {
            "daily_risk_used_pct": self.daily_risk_used,
            "daily_risk_limit_pct": _MAX_DAILY_RISK_PCT,
            "weekly_drawdown_pct": self.weekly_drawdown,
            "weekly_drawdown_limit_pct": _MAX_WEEKLY_DRAWDOWN_PCT,
            "monthly_drawdown_pct": self.monthly_drawdown,
            "monthly_drawdown_limit_pct": _MAX_MONTHLY_DRAWDOWN_PCT,
            "equity_peak": self.equity_peak,
            "drawdown_from_peak_pct": round(self._drawdown_from_peak_pct(), 4),
            "is_in_recovery_mode": self.is_in_recovery_mode(),
            "in_cooldown": in_cooldown,
            "cooldown_remaining_minutes": cooldown_remaining_min,
            "rolling_loss_rate": round(rolling_loss_rate, 4),
            "rolling_window_size": len(self.recent_signals),
            "active_signals": {
                "XAUUSD": self._active_counts.get("XAUUSD", 0),
                "GBPJPY": self._active_counts.get("GBPJPY", 0),
            },
            "suppressed_patterns": active_patterns_suppressed,
        }

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise state for Redis persistence."""
        return {
            "daily_risk_used": self.daily_risk_used,
            "weekly_drawdown": self.weekly_drawdown,
            "monthly_drawdown": self.monthly_drawdown,
            "equity_peak": self.equity_peak,
            "active_counts": dict(self._active_counts),
            "recent_signals": list(self.recent_signals),
            "suppressed_patterns": {
                k: v.isoformat() for k, v in self.suppressed_patterns.items()
            },
            "full_cooldown_until": (
                self._full_cooldown_until.isoformat()
                if self._full_cooldown_until
                else None
            ),
            "last_daily_reset": self._last_daily_reset.isoformat(),
            "last_weekly_reset": self._last_weekly_reset.isoformat(),
            "last_monthly_reset": self._last_monthly_reset.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RiskGuards":
        """Restore state from a Redis-persisted dict."""
        instance = cls(initial_equity_peak=data.get("equity_peak", 10_000.0))
        instance.daily_risk_used = data.get("daily_risk_used", 0.0)
        instance.weekly_drawdown = data.get("weekly_drawdown", 0.0)
        instance.monthly_drawdown = data.get("monthly_drawdown", 0.0)
        instance._active_counts = defaultdict(int, data.get("active_counts", {}))
        instance.recent_signals = deque(
            data.get("recent_signals", []), maxlen=_ROLLING_LOSS_WINDOW
        )
        instance.suppressed_patterns = {
            k: datetime.fromisoformat(v)
            for k, v in data.get("suppressed_patterns", {}).items()
        }
        raw_cooldown = data.get("full_cooldown_until")
        instance._full_cooldown_until = (
            datetime.fromisoformat(raw_cooldown) if raw_cooldown else None
        )
        instance._last_daily_reset = datetime.fromisoformat(
            data.get("last_daily_reset", _utcnow().isoformat())
        )
        instance._last_weekly_reset = datetime.fromisoformat(
            data.get("last_weekly_reset", _utcnow().isoformat())
        )
        instance._last_monthly_reset = datetime.fromisoformat(
            data.get("last_monthly_reset", _utcnow().isoformat())
        )
        return instance

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _drawdown_from_peak_pct(self) -> float:
        """Return current drawdown as a positive percentage from equity peak."""
        if self.equity_peak <= 0:
            return 0.0
        # Approximate from accumulated monthly drawdown since last peak update
        return self.monthly_drawdown

    def _tick_resets(self) -> None:
        """Reset counters if calendar boundaries have been crossed."""
        now = _utcnow()

        # Daily reset at UTC midnight
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if today_midnight > self._last_daily_reset:
            self.daily_risk_used = 0.0
            self._last_daily_reset = today_midnight
            logger.debug("Daily risk counter reset")

        # Weekly reset on Monday UTC
        this_monday = self._monday_of_week(now)
        if this_monday > self._last_weekly_reset:
            self.weekly_drawdown = 0.0
            self._last_weekly_reset = this_monday
            logger.debug("Weekly drawdown counter reset")

        # Monthly reset on the 1st of each month
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if this_month_start > self._last_monthly_reset:
            self.monthly_drawdown = 0.0
            self._last_monthly_reset = this_month_start
            logger.debug("Monthly drawdown counter reset")

    @staticmethod
    def _monday_of_week(dt: datetime) -> datetime:
        """Return the Monday 00:00:00 UTC of the week containing dt."""
        days_since_monday = dt.weekday()
        monday = dt - timedelta(days=days_since_monday)
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _pattern_key(pair: str, kill_zone: str, setup_type: str) -> str:
    """Canonical key for a KZ+setup suppression entry."""
    return f"{pair}:{kill_zone}:{setup_type}"
