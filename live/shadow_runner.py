"""
Shadow Mode Runner — runs engine on live data, logs signals but does NOT push to users.

For Phase 1.5 validation: compare shadow signal outcomes against backtest expectations.
Logs every signal + its outcome (TP1/2/3 hit or SL hit) to shadow_log.jsonl.

Shadow mode GO/NO-GO criteria:
    - TP1 win rate within 15% of backtest TP1 win rate
    - Profit factor >= 1.2
    - No catastrophic failure patterns (10+ consecutive losses)
    - Signal frequency within ±30% of backtest expectations
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from backtest.executor import TradeRecord, TradeStatus
from live.engine_runner import EngineRunner

logger = logging.getLogger(__name__)

SHADOW_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "reports", "shadow_log.jsonl"
)

# Maximum consecutive losses before a warning is logged
_CONSECUTIVE_LOSS_WARN_THRESHOLD = 10


class ShadowRunner(EngineRunner):
    """
    Shadow mode engine runner.

    Differences from EngineRunner:
    - _publish_signal() writes to shadow_log.jsonl ONLY — no Redis broadcast.
    - Tracks open signals and monitors price action to detect outcomes.
    - Maintains rolling stats for live GO/NO-GO assessment.
    """

    def __init__(self, trading_styles: Optional[list[str]] = None) -> None:
        super().__init__(trading_styles=trading_styles)

        # Active shadow signals awaiting outcome: signal_id → dict
        self._open_shadows: dict[str, dict] = {}

        # Rolling stats
        self._total_signals: int = 0
        self._tp1_hits: int = 0
        self._tp2_hits: int = 0
        self._tp3_hits: int = 0
        self._sl_hits: int = 0
        self._consecutive_losses: int = 0

        # Track gross profit/loss for profit factor calculation
        self._gross_profit: float = 0.0
        self._gross_loss: float = 0.0

        # Recent outcome history (last 10 for rolling loss rate)
        self._recent_outcomes: deque[str] = deque(maxlen=10)

    # ── Override: no Redis, file only ─────────────────────────────────────────

    async def _publish_signal(
        self,
        signal: TradeRecord,
        pair: str,
        style: str,
    ) -> None:
        """
        Log signal to shadow_log.jsonl only — never publish to Redis or users.
        """
        self._total_signals += 1

        signal_dict = self._serialise_signal(signal, pair, style)
        signal_dict["shadow"] = True

        try:
            os.makedirs(os.path.dirname(SHADOW_LOG_PATH), exist_ok=True)
            with open(SHADOW_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(signal_dict, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write shadow signal to log")

        # Register for outcome tracking
        self._open_shadows[signal.signal_id] = {
            "signal_id":  signal.signal_id,
            "pair":       pair,
            "style":      style,
            "direction":  (
                signal.direction.value
                if hasattr(signal.direction, "value")
                else str(signal.direction)
            ),
            "entry":      signal.entry_price,
            "sl":         signal.stop_loss,
            "tp1":        signal.tp1,
            "tp2":        signal.tp2,
            "tp3":        signal.tp3,
            "signal_time": signal.signal_time.isoformat() if signal.signal_time else None,
            "outcome":    None,
        }

        logger.info(
            "[SHADOW] Signal logged: %s %s | entry=%.2f SL=%.2f TP1=%.2f | id=%s",
            pair,
            signal_dict["direction"],
            signal.entry_price,
            signal.stop_loss,
            signal.tp1,
            signal.signal_id[:8],
        )

    # ── Outcome Tracking ──────────────────────────────────────────────────────

    def _track_outcome(
        self,
        signal_id: str,
        pair: str,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float,
        tp3: float,
    ) -> None:
        """
        Register a signal for outcome tracking.

        The _on_bar_close handler calls this whenever the current price
        crosses a TP or SL level for an open shadow signal.

        Note: This method is called synchronously from _on_bar_close. Outcome
        resolution is performed via _check_outcomes() on each bar.
        """
        self._open_shadows[signal_id] = {
            "signal_id": signal_id,
            "pair":      pair,
            "entry":     entry,
            "sl":        sl,
            "tp1":       tp1,
            "tp2":       tp2,
            "tp3":       tp3,
            "outcome":   None,
        }

    def _check_outcomes(self, pair: str, bar_high: float, bar_low: float) -> None:
        """
        Check all open shadow signals for this pair against the current bar's range.

        Called from the bar-close callback after the buffer is updated.
        """
        resolved = []
        for sid, shadow in self._open_shadows.items():
            if shadow["pair"] != pair:
                continue

            direction = shadow.get("direction", "BUY")
            sl = shadow["sl"]
            tp1 = shadow["tp1"]
            tp2 = shadow["tp2"]
            tp3 = shadow["tp3"]
            outcome = None

            if direction == "BUY":
                if bar_low <= sl:
                    outcome = TradeStatus.SL_HIT.value
                elif bar_high >= tp3:
                    outcome = TradeStatus.TP3_HIT.value
                elif bar_high >= tp2:
                    outcome = TradeStatus.TP2_HIT.value
                elif bar_high >= tp1:
                    outcome = TradeStatus.TP1_HIT.value
            else:  # SELL
                if bar_high >= sl:
                    outcome = TradeStatus.SL_HIT.value
                elif bar_low <= tp3:
                    outcome = TradeStatus.TP3_HIT.value
                elif bar_low <= tp2:
                    outcome = TradeStatus.TP2_HIT.value
                elif bar_low <= tp1:
                    outcome = TradeStatus.TP1_HIT.value

            if outcome is not None:
                shadow["outcome"] = outcome
                shadow["resolved_at"] = datetime.now(timezone.utc).isoformat()
                resolved.append(sid)
                self._record_outcome(outcome, shadow)
                self._append_outcome_to_log(shadow)

        for sid in resolved:
            del self._open_shadows[sid]

    def _record_outcome(self, outcome: str, shadow: dict) -> None:
        """Update rolling statistics with a resolved outcome."""
        is_win = outcome in (
            TradeStatus.TP1_HIT.value,
            TradeStatus.TP2_HIT.value,
            TradeStatus.TP3_HIT.value,
        )

        if outcome == TradeStatus.TP1_HIT.value:
            self._tp1_hits += 1
        elif outcome == TradeStatus.TP2_HIT.value:
            self._tp2_hits += 1
        elif outcome == TradeStatus.TP3_HIT.value:
            self._tp3_hits += 1
        elif outcome == TradeStatus.SL_HIT.value:
            self._sl_hits += 1

        # Approximate R multiples for profit factor
        entry = shadow.get("entry", 0.0)
        sl = shadow.get("sl", 0.0)
        risk = abs(entry - sl) if entry and sl else 1.0

        if is_win:
            tp_key = {"TP1_HIT": "tp1", "TP2_HIT": "tp2", "TP3_HIT": "tp3"}.get(outcome, "tp1")
            tp_price = shadow.get(tp_key, entry)
            reward = abs(tp_price - entry)
            self._gross_profit += reward
            self._consecutive_losses = 0
        else:
            self._gross_loss += risk
            self._consecutive_losses += 1
            if self._consecutive_losses >= _CONSECUTIVE_LOSS_WARN_THRESHOLD:
                logger.warning(
                    "[SHADOW] %d consecutive losses — review signal quality",
                    self._consecutive_losses,
                )

        self._recent_outcomes.append(outcome)

        logger.info(
            "[SHADOW] Outcome: %s → %s | running stats: %d signals, TP1=%d, SL=%d",
            shadow.get("signal_id", "")[:8],
            outcome,
            self._total_signals,
            self._tp1_hits,
            self._sl_hits,
        )

    def _append_outcome_to_log(self, shadow: dict) -> None:
        """Append the resolved shadow record (with outcome) to shadow_log.jsonl."""
        try:
            os.makedirs(os.path.dirname(SHADOW_LOG_PATH), exist_ok=True)
            with open(SHADOW_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({**shadow, "type": "outcome"}, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write outcome to shadow log")

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_shadow_stats(self) -> dict:
        """
        Return current shadow mode statistics.

        Returns:
            dict with keys:
                total_signals, tp1_hits, tp2_hits, tp3_hits, sl_hits,
                tp1_win_rate, profit_factor, consecutive_losses,
                rolling_loss_rate (over last 10 signals).
        """
        resolved = self._tp1_hits + self._tp2_hits + self._tp3_hits + self._sl_hits
        tp1_win_rate = self._tp1_hits / resolved if resolved > 0 else 0.0
        profit_factor = (
            self._gross_profit / self._gross_loss
            if self._gross_loss > 0
            else float("inf") if self._gross_profit > 0 else 0.0
        )

        recent = list(self._recent_outcomes)
        sl_recent = sum(1 for o in recent if o == TradeStatus.SL_HIT.value)
        rolling_loss_rate = sl_recent / len(recent) if recent else 0.0

        return {
            "total_signals":      self._total_signals,
            "resolved":           resolved,
            "tp1_hits":           self._tp1_hits,
            "tp2_hits":           self._tp2_hits,
            "tp3_hits":           self._tp3_hits,
            "sl_hits":            self._sl_hits,
            "tp1_win_rate":       round(tp1_win_rate, 4),
            "profit_factor":      round(profit_factor, 4),
            "consecutive_losses": self._consecutive_losses,
            "rolling_loss_rate":  round(rolling_loss_rate, 4),
            "open_shadows":       len(self._open_shadows),
        }


if __name__ == "__main__":
    import asyncio
    runner = ShadowRunner()
    asyncio.run(runner.start())
