"""
HTF vs LTF conflict analysis — 15 pre-written template patterns.

Per CLAUDE.md §5.4: When entry TF and HTF conflict, display both signals
with a template-based explanation drawn from ~15 pre-written patterns.

The LTF confidence score is automatically reduced by 15-25% when it conflicts
with HTF bias. Template selection is driven by the (entry_trend, htf_trend) tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConflictAnalysis:
    """Result of an HTF vs LTF conflict analysis."""
    title: str
    explanation: str
    confidence_penalty: float   # Fraction to subtract from score (0.15–0.25)
    recommendation: str         # "avoid" | "reduce_size" | "monitor_htf"


# ── Template library ──────────────────────────────────────────────────────────
# Keys: (entry_trend, htf_trend) where each is one of:
#   "bullish", "bearish", "ranging", "transitioning_bullish", "transitioning_bearish"

_TEMPLATES: dict[tuple[str, str], dict] = {

    # ── Direct reversals (highest penalty) ────────────────────────────────────

    ("bullish", "bearish"): {
        "title": "Counter-Trend Buy Against Bearish HTF",
        "explanation": (
            "The entry timeframe shows bullish structure (BOS confirmed) while the "
            "higher timeframe is still bearish (below EMA 200 and lower highs intact). "
            "This suggests a counter-trend move that may face significant resistance. "
            "HTF sellers are likely to step in, limiting upside potential."
        ),
        "confidence_penalty": 0.25,
        "recommendation": "avoid",
    },

    ("bearish", "bullish"): {
        "title": "Counter-Trend Sell Against Bullish HTF",
        "explanation": (
            "The entry timeframe signals a sell while the higher timeframe is in a "
            "clear bullish trend (above EMA 200, higher highs and higher lows). "
            "Selling into HTF strength carries elevated risk — institutional buyers "
            "may absorb selling pressure and resume the uptrend."
        ),
        "confidence_penalty": 0.25,
        "recommendation": "avoid",
    },

    # ── Range vs trend conflicts ───────────────────────────────────────────────

    ("bullish", "ranging"): {
        "title": "Bullish Breakout Attempt in HTF Range",
        "explanation": (
            "A bullish setup is forming on the entry timeframe, but the higher timeframe "
            "is in a range. The upper boundary of the HTF range acts as resistance overhead "
            "and may cap the move. Watch for rejection at the HTF range high before committing "
            "to full position size."
        ),
        "confidence_penalty": 0.18,
        "recommendation": "reduce_size",
    },

    ("bearish", "ranging"): {
        "title": "Bearish Setup in HTF Range",
        "explanation": (
            "The entry timeframe shows a bearish setup, but the higher timeframe is in a "
            "consolidation range. The HTF range low acts as potential support and may cushion "
            "the downside. Price could find buyers at the range boundary, limiting the move."
        ),
        "confidence_penalty": 0.18,
        "recommendation": "reduce_size",
    },

    ("ranging", "bullish"): {
        "title": "Entry TF Ranging in HTF Uptrend",
        "explanation": (
            "The entry timeframe is consolidating while the higher timeframe maintains "
            "a bullish trend. This is a typical pullback/consolidation phase within an "
            "uptrend. Signals from this range are mixed — wait for the entry TF to "
            "resolve direction before acting."
        ),
        "confidence_penalty": 0.15,
        "recommendation": "monitor_htf",
    },

    ("ranging", "bearish"): {
        "title": "Entry TF Ranging in HTF Downtrend",
        "explanation": (
            "The entry timeframe is in a range while the higher timeframe shows a "
            "bearish trend. This is a distribution phase — the range may resolve to "
            "the downside in alignment with HTF. Any entry-TF buy signals carry elevated "
            "risk given the HTF bearish context."
        ),
        "confidence_penalty": 0.15,
        "recommendation": "monitor_htf",
    },

    ("ranging", "ranging"): {
        "title": "Both Timeframes Ranging — Low Directional Edge",
        "explanation": (
            "Both the entry timeframe and higher timeframe are in consolidation. "
            "There is no clear directional bias from either timeframe. Signal confidence "
            "is significantly reduced. Only mean-reversion setups at clear S&R boundaries "
            "are valid in this environment."
        ),
        "confidence_penalty": 0.20,
        "recommendation": "avoid",
    },

    # ── Transitioning states (lower penalty — trend not yet confirmed) ─────────

    ("bullish", "transitioning_bearish"): {
        "title": "Bullish Entry as HTF Trend Shifts Bearish",
        "explanation": (
            "The entry timeframe is bullish, but the higher timeframe is showing early "
            "signs of a bearish reversal (first CHoCH printed). The HTF trend has not "
            "fully flipped yet, but momentum is shifting. This setup carries elevated "
            "reversal risk — the HTF may confirm bearish structure while the trade is open."
        ),
        "confidence_penalty": 0.20,
        "recommendation": "reduce_size",
    },

    ("bearish", "transitioning_bullish"): {
        "title": "Bearish Entry as HTF Trend Shifts Bullish",
        "explanation": (
            "The entry timeframe is bearish while the higher timeframe is showing early "
            "signs of a bullish reversal (first CHoCH printed on HTF). Shorting into a "
            "potential HTF trend flip is high-risk. Monitor whether HTF confirms the new "
            "bullish structure before committing."
        ),
        "confidence_penalty": 0.20,
        "recommendation": "reduce_size",
    },

    ("transitioning_bullish", "bearish"): {
        "title": "Early Bullish Signal in HTF Downtrend",
        "explanation": (
            "The entry timeframe is transitioning bullish (first CHoCH printed) but the "
            "higher timeframe remains in a bearish trend. This could be the beginning of "
            "a reversal or a temporary counter-trend move. Require a second CHoCH on the "
            "entry TF to confirm before treating this as a valid long setup."
        ),
        "confidence_penalty": 0.22,
        "recommendation": "monitor_htf",
    },

    ("transitioning_bearish", "bullish"): {
        "title": "Early Bearish Signal in HTF Uptrend",
        "explanation": (
            "The entry timeframe is transitioning bearish (first CHoCH printed) but the "
            "higher timeframe is still bullish. This may be a short-term pullback within "
            "a larger uptrend rather than a full reversal. HTF buyers could re-enter at "
            "key support levels, trapping early shorts."
        ),
        "confidence_penalty": 0.22,
        "recommendation": "monitor_htf",
    },

    ("transitioning_bullish", "transitioning_bearish"): {
        "title": "Opposing Transitions — High Regime Uncertainty",
        "explanation": (
            "Both timeframes are in transition with opposing directions — the entry TF "
            "is showing early bullish signs while the HTF is showing early bearish signs. "
            "Neither trend is confirmed. Market direction is highly uncertain. This is a "
            "low-probability environment for directional trades."
        ),
        "confidence_penalty": 0.25,
        "recommendation": "avoid",
    },

    ("transitioning_bearish", "transitioning_bullish"): {
        "title": "Opposing Transitions — High Regime Uncertainty",
        "explanation": (
            "Both timeframes are in transition with opposing directions — the entry TF "
            "is showing early bearish signs while the HTF shows early bullish signs. "
            "Neither trend is confirmed, and the resulting direction is unclear. Avoid "
            "trading until at least one timeframe confirms its new trend."
        ),
        "confidence_penalty": 0.25,
        "recommendation": "avoid",
    },

    # ── Alignment (no real conflict — low penalty, informational) ────────────

    ("bullish", "bullish"): {
        "title": "HTF and LTF Aligned Bullish",
        "explanation": (
            "Both the entry timeframe and higher timeframe are bullish — this is the "
            "ideal setup for a long trade. HTF structure supports the direction. "
            "No conflict detected."
        ),
        "confidence_penalty": 0.0,
        "recommendation": "monitor_htf",
    },

    ("bearish", "bearish"): {
        "title": "HTF and LTF Aligned Bearish",
        "explanation": (
            "Both the entry timeframe and higher timeframe are bearish — ideal setup "
            "for a short trade. HTF structure supports the direction. No conflict detected."
        ),
        "confidence_penalty": 0.0,
        "recommendation": "monitor_htf",
    },
}

# Default template when no specific match is found
_DEFAULT_TEMPLATE: dict = {
    "title": "Timeframe Bias Conflict Detected",
    "explanation": (
        "The entry timeframe and higher timeframe show differing market conditions. "
        "Proceed with caution and reduce position size. Monitor the higher timeframe "
        "for confirmation before adding to the position."
    ),
    "confidence_penalty": 0.15,
    "recommendation": "reduce_size",
}


class ConflictAnalyzer:
    """
    Analyzes HTF vs LTF conflicts and returns a pre-written template explanation.

    Template selection is based on the (entry_tf_state, htf_state) combination.
    When the two timeframes are fully aligned, the penalty is 0 and no conflict
    is surfaced to the user.
    """

    def analyze(
        self,
        entry_tf_state: str,
        htf_state: str,
        entry_tf: str,
        htf: str,
        pair: str,
    ) -> Optional[ConflictAnalysis]:
        """
        Analyze the conflict between entry TF and HTF market structure states.

        Args:
            entry_tf_state: Entry TF trend state. One of:
                "bullish", "bearish", "ranging",
                "transitioning_bullish", "transitioning_bearish"
            htf_state: HTF trend state (same options as entry_tf_state).
            entry_tf: Entry timeframe label, e.g. "15m" (used for display only).
            htf: Higher timeframe label, e.g. "4H" (used for display only).
            pair: Trading pair, e.g. "XAUUSD" (used for display only).

        Returns:
            ConflictAnalysis if a conflict is detected (or even for alignment, with
            zero penalty), or None if states are unrecognised.
        """
        entry_norm = self._normalize_state(entry_tf_state)
        htf_norm = self._normalize_state(htf_state)

        if entry_norm is None or htf_norm is None:
            return None

        key = (entry_norm, htf_norm)
        template = _TEMPLATES.get(key, _DEFAULT_TEMPLATE)

        # Enrich the explanation with timeframe labels
        explanation = self._inject_tf_labels(
            template["explanation"], entry_tf, htf, pair
        )

        return ConflictAnalysis(
            title=template["title"],
            explanation=explanation,
            confidence_penalty=float(template["confidence_penalty"]),
            recommendation=template["recommendation"],
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _normalize_state(self, state: str) -> Optional[str]:
        """
        Normalise various state string representations to canonical form.

        Handles the TrendState enum values from engine.modules.market_structure
        as well as plain strings passed directly.
        """
        s = str(state).lower().strip()

        # Direct matches
        _aliases: dict[str, str] = {
            # Bullish
            "bullish": "bullish",
            "bullish_trend": "bullish",
            "bull": "bullish",
            # Bearish
            "bearish": "bearish",
            "bearish_trend": "bearish",
            "bear": "bearish",
            # Ranging
            "ranging": "ranging",
            "range": "ranging",
            "sideways": "ranging",
            # Transitioning to bullish
            "transitioning_bullish": "transitioning_bullish",
            "transitioning": "transitioning_bullish",  # generic → assume bullish
            "transitional": "transitioning_bullish",
            # Transitioning to bearish
            "transitioning_bearish": "transitioning_bearish",
            # Unknown / insufficient data
            "unknown": None,
        }

        return _aliases.get(s)

    def _inject_tf_labels(
        self,
        explanation: str,
        entry_tf: str,
        htf: str,
        pair: str,
    ) -> str:
        """
        Replace generic timeframe references with actual TF labels for clarity.

        Replaces 'the entry timeframe' with e.g. 'the 15m timeframe' and
        'the higher timeframe' with e.g. 'the 4H timeframe'.
        """
        explanation = explanation.replace(
            "the entry timeframe", f"the {entry_tf} timeframe"
        )
        explanation = explanation.replace(
            "The entry timeframe", f"The {entry_tf} timeframe"
        )
        explanation = explanation.replace(
            "the higher timeframe", f"the {htf} timeframe"
        )
        explanation = explanation.replace(
            "The higher timeframe", f"The {htf} timeframe"
        )
        return explanation
