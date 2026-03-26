"""
Correlation warning engine — detects conflicting directional exposure.

XAUUSD buy (risk-off asset) + GBPJPY buy (risk-on) = conflicting macro thesis.
Tracks total USD exposure across all active signals.

Gold (XAUUSD) is a risk-off safe haven: it rises when markets are fearful,
USD is weakening, or real yields are falling.

GBPJPY is a risk-on pair: it rises in risk-on environments driven by
GBP strength and JPY weakness (carry trade unwind reversal).

Having both as BUY signals implies conflicting macro narratives — the app
warns the user so they can decide which thesis they believe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Total exposure limit before new signals are suppressed (§11.2)
_MAX_TOTAL_EXPOSURE_PCT = 4.0

# Approximate pip value per standard lot for exposure calculation
_PIP_VALUES = {
    "XAUUSD": 1.0,     # $1 per pip per lot
    "GBPJPY": 9.50,    # ~$9.50 per pip per lot (static fallback)
}


@dataclass
class CorrelationWarning:
    """
    Warning generated when a new signal creates a conflicting or over-exposed position.

    Attributes:
        type: Category of the warning.
            "macro_conflict"    — XAUUSD and GBPJPY pointing in conflicting risk directions
            "same_direction"    — Both pairs going same direction (concentrated macro bet)
            "exposure_limit"    — Total account exposure exceeds 4%
        message: Human-readable explanation shown in the app.
        severity: "warning" (show badge, allow trade) | "block" (suppress trade).
    """

    type: str       # "macro_conflict" | "exposure_limit" | "same_direction"
    message: str
    severity: str   # "warning" | "block"


class CorrelationEngine:
    """
    Analyses directional exposure across XAUUSD and GBPJPY active signals.

    This engine does not hold state between calls — it is a pure function of
    the active_signals list passed to each method.
    """

    def check_new_signal(
        self,
        pair: str,
        direction: str,
        lot_size: float,
        account_balance: float,
        active_signals: list[dict],
    ) -> Optional[CorrelationWarning]:
        """
        Check whether a new signal creates a conflicting or over-exposed position.

        Conflict rules:
        - XAUUSD BUY + GBPJPY BUY: risk-off vs risk-on conflict
        - XAUUSD SELL + GBPJPY SELL: both bearish — concentrated macro short
        - Total exposure across all signals > 4% of account: suppress

        Args:
            pair: The new signal's pair ("XAUUSD" or "GBPJPY").
            direction: "BUY" or "SELL".
            lot_size: Proposed lot size for the new signal.
            account_balance: Current account balance in USD.
            active_signals: List of currently active signal dicts. Each dict
                must contain: {"pair": str, "direction": str, "lot_size": float,
                "sl_pips": float}.

        Returns:
            CorrelationWarning if a conflict or limit is detected, else None.
        """
        direction = direction.upper()

        # ── Check exposure limit first (hardest block) ────────────────────────
        exposure = self.get_net_exposure(
            active_signals + [
                {
                    "pair": pair,
                    "direction": direction,
                    "lot_size": lot_size,
                    "sl_pips": active_signals[0].get("sl_pips", 10)
                    if active_signals
                    else 10,
                }
            ],
            account_balance,
        )

        if exposure["total_risk_pct"] > _MAX_TOTAL_EXPOSURE_PCT:
            return CorrelationWarning(
                type="exposure_limit",
                message=(
                    f"Total account exposure would reach {exposure['total_risk_pct']:.1f}% "
                    f"(limit: {_MAX_TOTAL_EXPOSURE_PCT}%). New signal suppressed — "
                    "you are effectively leveraged on a single macro thesis."
                ),
                severity="block",
            )

        # ── Check for macro direction conflicts ───────────────────────────────
        xau_direction = _get_pair_direction("XAUUSD", active_signals)
        gj_direction = _get_pair_direction("GBPJPY", active_signals)

        # What would the new directions look like after adding this signal?
        new_xau = direction if pair == "XAUUSD" else xau_direction
        new_gj = direction if pair == "GBPJPY" else gj_direction

        if new_xau and new_gj:
            # XAUUSD BUY (risk-off) + GBPJPY BUY (risk-on) = conflicting macro
            if new_xau == "BUY" and new_gj == "BUY":
                return CorrelationWarning(
                    type="macro_conflict",
                    message=(
                        "Conflicting macro thesis: XAUUSD BUY (risk-off safe haven) "
                        "conflicts with GBPJPY BUY (risk-on carry trade). "
                        "These setups reflect opposing market sentiment. "
                        "Review your macro bias before executing both."
                    ),
                    severity="warning",
                )

            # Both SELL — concentrated macro short, warn about DXY
            if new_xau == "SELL" and new_gj == "SELL":
                return CorrelationWarning(
                    type="same_direction",
                    message=(
                        "Both pairs bearish — check DXY strength. "
                        "Simultaneous XAUUSD SELL and GBPJPY SELL implies broad "
                        "USD strength or global risk-off. Verify DXY momentum "
                        "supports this thesis before executing both."
                    ),
                    severity="warning",
                )

        return None

    def get_net_exposure(
        self,
        active_signals: list[dict],
        account_balance: float,
    ) -> dict:
        """
        Calculate total USD exposure across all active signals.

        Exposure per signal = lot_size × sl_pips × pip_value_per_lot.
        This is the dollar amount at risk if every SL is hit.

        Args:
            active_signals: List of signal dicts, each with keys:
                pair (str), direction (str), lot_size (float), sl_pips (float).
            account_balance: Account balance in USD (used for % calculation).

        Returns:
            Dict with:
                total_risk_pct   — total exposure as % of balance
                xauusd_risk_pct  — XAUUSD-specific exposure %
                gbpjpy_risk_pct  — GBPJPY-specific exposure %
                direction_conflict — True if XAUUSD and GBPJPY point in conflicting directions
                total_risk_usd   — raw dollar exposure
        """
        if account_balance <= 0:
            return {
                "total_risk_pct": 0.0,
                "xauusd_risk_pct": 0.0,
                "gbpjpy_risk_pct": 0.0,
                "direction_conflict": False,
                "total_risk_usd": 0.0,
            }

        xau_risk_usd = 0.0
        gj_risk_usd = 0.0
        xau_directions: list[str] = []
        gj_directions: list[str] = []

        for sig in active_signals:
            pair = sig.get("pair", "")
            direction = sig.get("direction", "").upper()
            lot_size = float(sig.get("lot_size", 0.0))
            sl_pips = float(sig.get("sl_pips", 0.0))
            pip_val = _PIP_VALUES.get(pair, 10.0)

            dollar_risk = lot_size * sl_pips * pip_val

            if pair == "XAUUSD":
                xau_risk_usd += dollar_risk
                if direction:
                    xau_directions.append(direction)
            elif pair == "GBPJPY":
                gj_risk_usd += dollar_risk
                if direction:
                    gj_directions.append(direction)

        total_risk_usd = xau_risk_usd + gj_risk_usd

        # Direction conflict: dominant direction on each pair opposes risk-sentiment logic
        # XAUUSD BUY = risk-off, GBPJPY BUY = risk-on → conflict
        xau_dom = _dominant_direction(xau_directions)
        gj_dom = _dominant_direction(gj_directions)
        direction_conflict = bool(
            xau_dom and gj_dom and xau_dom == "BUY" and gj_dom == "BUY"
        )

        return {
            "total_risk_pct": round(total_risk_usd / account_balance * 100, 4),
            "xauusd_risk_pct": round(xau_risk_usd / account_balance * 100, 4),
            "gbpjpy_risk_pct": round(gj_risk_usd / account_balance * 100, 4),
            "direction_conflict": direction_conflict,
            "total_risk_usd": round(total_risk_usd, 2),
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_pair_direction(
    pair: str,
    active_signals: list[dict],
) -> Optional[str]:
    """
    Return the dominant direction for a pair from the active signals list.

    If there are both BUY and SELL signals for the same pair, returns None
    (ambiguous / no dominant direction). Returns None if no signals for the pair.
    """
    directions = [
        s["direction"].upper()
        for s in active_signals
        if s.get("pair") == pair and s.get("direction")
    ]
    return _dominant_direction(directions)


def _dominant_direction(directions: list[str]) -> Optional[str]:
    """Return "BUY" or "SELL" if all directions agree, else None."""
    if not directions:
        return None
    unique = set(directions)
    if len(unique) == 1:
        return unique.pop()
    return None  # Mixed — no dominant direction
