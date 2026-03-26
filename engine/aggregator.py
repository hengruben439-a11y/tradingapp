"""
Confluence Score Aggregator — Sprint 5 deliverable.

Combines all 9 module scores into a final directional signal score.
Applies regime gate, weighted sum, multiplier bonuses, and penalties.

Pipeline (5 steps):
    1. Regime gate — check ADX-based regime; apply threshold and penalty
    2. Weighted sum — pair-specific weights applied to capped module scores
    3. Multiplier bonuses — Unicorn, OTE+OB, OTE+FVG, Kill Zone, day-of-week
    4. Penalties — HTF conflict, news proximity, regime TRANSITIONAL
    5. Clamp — final score to [-1.0, +1.0]

Signal thresholds:
    |score| >= 0.80 → VERY_STRONG
    |score| >= 0.65 → STRONG (triggers alerts)
    |score| >= 0.50 → MODERATE (display only)
    |score| >= 0.30 → WEAK (watch only, free tier)
    |score|  < 0.30 → no signal

In RANGING regime: minimum MODERATE threshold raised to 0.70.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from engine.signal import Direction, MarketRegime, ModuleScore, SignalStrength
from engine.regime import RegimeDetector


# Base score cap — each module score is capped to this before weighting
# (headroom reserved for multiplier bonuses)
MODULE_SCORE_CAP = 0.85

# Signal generation thresholds
THRESHOLD_VERY_STRONG = 0.80
THRESHOLD_STRONG = 0.65
THRESHOLD_MODERATE = 0.50
THRESHOLD_WEAK = 0.30

# In RANGING regime, moderate threshold raises to:
THRESHOLD_MODERATE_RANGING = 0.70


@dataclass
class AggregatorInput:
    """Structured input for the aggregator."""
    # Raw module scores [-1.0, +1.0]
    market_structure: float
    order_blocks_fvg: float
    ote: float
    ema: float
    rsi: float
    macd: float
    bollinger: float
    kill_zone: float
    support_resistance: float

    # Context flags for multipliers/penalties
    unicorn_setup: bool = False         # OB + FVG overlap
    ote_ob_confluence: bool = False     # OTE + OB within zone
    ote_fvg_confluence: bool = False    # OTE + FVG within zone
    kill_zone_active: bool = False      # Any KZ is active
    htf_conflict: bool = False          # LTF signal opposes HTF bias
    news_proximity: bool = False        # High-impact news within 15 min
    regime: MarketRegime = MarketRegime.UNKNOWN
    day_of_week_modifier: float = 1.0   # From config, default 1.0x


@dataclass
class AggregatorResult:
    """Full result from the aggregator for signal construction."""
    raw_weighted_sum: float          # Pre-multiplier weighted sum
    confluence_score: float          # Final post-penalty, clamped score
    direction: Direction
    strength: SignalStrength
    module_scores: list[ModuleScore]
    applied_multipliers: list[str]
    regime: MarketRegime
    passes_threshold: bool
    unicorn_setup: bool
    ote_ob_confluence: bool
    ote_fvg_confluence: bool


# Module names (order matches the weights lists)
_MODULE_NAMES = [
    "Market Structure",
    "Order Blocks + FVG",
    "OTE Fibonacci",
    "EMA Alignment",
    "RSI",
    "MACD",
    "Bollinger Bands",
    "Kill Zones",
    "S&R / Liquidity",
]

# Pair-specific weights (must sum to 1.0)
WEIGHTS: dict[str, list[float]] = {
    "XAUUSD": [0.25, 0.20, 0.15, 0.10, 0.08, 0.07, 0.05, 0.05, 0.05],
    "GBPJPY": [0.25, 0.18, 0.15, 0.12, 0.08, 0.07, 0.05, 0.05, 0.05],
}


class ConfluenceAggregator:
    """
    Combines module scores into a single directional confluence score.

    Usage:
        agg = ConfluenceAggregator(pair="XAUUSD")
        result = agg.aggregate(inputs)
        if result.passes_threshold:
            # create Signal object
    """

    def __init__(self, pair: str):
        self.pair = pair
        self._weights = WEIGHTS.get(pair, WEIGHTS["XAUUSD"])

    def aggregate(self, inputs: AggregatorInput) -> AggregatorResult:
        """Run the full 5-step aggregation pipeline."""
        # Step 1 — Regime gate
        regime = inputs.regime
        ranging = (regime == MarketRegime.RANGING)

        # Step 2 — Weighted sum
        raw_scores = [
            inputs.market_structure,
            inputs.order_blocks_fvg,
            inputs.ote,
            inputs.ema,
            inputs.rsi,
            inputs.macd,
            inputs.bollinger,
            inputs.kill_zone,
            inputs.support_resistance,
        ]
        weighted_sum = self._compute_weighted_sum(raw_scores)

        # Step 3 — Multipliers
        score_after_mult, applied_multipliers = self._apply_multipliers(weighted_sum, inputs)

        # Step 4 — Penalties
        score_after_penalties = self._apply_penalties(score_after_mult, inputs)

        # Step 5 — Clamp and classify
        confluence_score = max(-1.0, min(1.0, score_after_penalties))
        direction = Direction.BUY if confluence_score >= 0 else Direction.SELL
        strength = self._classify_strength(confluence_score, ranging)
        module_scores = self._build_module_scores(raw_scores, direction)

        # Check threshold (RANGING raises moderate threshold to 0.70)
        min_threshold = THRESHOLD_MODERATE_RANGING if ranging else THRESHOLD_MODERATE
        passes = abs(confluence_score) >= min_threshold

        return AggregatorResult(
            raw_weighted_sum=weighted_sum,
            confluence_score=confluence_score,
            direction=direction,
            strength=strength,
            module_scores=module_scores,
            applied_multipliers=applied_multipliers,
            regime=regime,
            passes_threshold=passes,
            unicorn_setup=inputs.unicorn_setup,
            ote_ob_confluence=inputs.ote_ob_confluence,
            ote_fvg_confluence=inputs.ote_fvg_confluence,
        )

    def _cap_score(self, score: float) -> float:
        """Clamp a single module score to [-MODULE_SCORE_CAP, +MODULE_SCORE_CAP]."""
        return max(-MODULE_SCORE_CAP, min(MODULE_SCORE_CAP, score))

    def _compute_weighted_sum(self, raw_scores: list[float]) -> float:
        """
        Apply pair-specific weights to capped module scores.
        weighted_sum = sum(capped_score_i * weight_i)
        """
        capped = [self._cap_score(s) for s in raw_scores]
        return sum(c * w for c, w in zip(capped, self._weights))

    def _apply_multipliers(
        self,
        score: float,
        inputs: AggregatorInput,
    ) -> tuple[float, list[str]]:
        """
        Apply confluence bonus multipliers multiplicatively.

        Order (all multiply together):
            Unicorn (OB+FVG):   1.10x
            OTE+OB:             1.08x
            OTE+FVG:            1.06x
            Kill Zone active:   1.05x
            Outside all KZ:     0.95x
            Day-of-week:        modifier value

        Returns:
            (adjusted_score, list of applied multiplier names)
        """
        multiplier = 1.0
        applied: list[str] = []

        if inputs.unicorn_setup:
            multiplier *= 1.10
            applied.append("Unicorn (OB+FVG) 1.10x")
        if inputs.ote_ob_confluence:
            multiplier *= 1.08
            applied.append("OTE+OB 1.08x")
        if inputs.ote_fvg_confluence:
            multiplier *= 1.06
            applied.append("OTE+FVG 1.06x")
        if inputs.kill_zone_active:
            multiplier *= 1.05
            applied.append("Kill Zone active 1.05x")
        else:
            multiplier *= 0.95
            applied.append("Outside KZ 0.95x")
        if inputs.day_of_week_modifier != 1.0:
            multiplier *= inputs.day_of_week_modifier
            applied.append(f"Day-of-week {inputs.day_of_week_modifier:.2f}x")

        return score * multiplier, applied

    def _apply_penalties(
        self,
        score: float,
        inputs: AggregatorInput,
        regime_detector: Optional[RegimeDetector] = None,
    ) -> float:
        """
        Apply penalties for conflicting conditions.

        Penalties (applied to |score|, sign preserved):
            HTF conflict:       0.80x (15–25% reduction; using 20%)
            News proximity:     0.90x
            TRANSITIONAL regime: 0.90x (via regime.py)
        """
        sign = 1.0 if score >= 0 else -1.0
        magnitude = abs(score)

        if inputs.htf_conflict:
            magnitude *= 0.80
        if inputs.news_proximity:
            magnitude *= 0.90
        if inputs.regime == MarketRegime.TRANSITIONAL:
            magnitude *= 0.90

        return sign * magnitude

    def _classify_strength(self, score: float, ranging: bool) -> SignalStrength:
        """Map absolute score to SignalStrength enum."""
        abs_score = abs(score)
        min_moderate = THRESHOLD_MODERATE_RANGING if ranging else THRESHOLD_MODERATE
        if abs_score >= THRESHOLD_VERY_STRONG:
            return SignalStrength.VERY_STRONG
        elif abs_score >= THRESHOLD_STRONG:
            return SignalStrength.STRONG
        elif abs_score >= min_moderate:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK

    def _build_module_scores(
        self,
        raw_scores: list[float],
        direction: Direction,
    ) -> list[ModuleScore]:
        """
        Build ModuleScore objects for signal.module_scores field.
        aligned = True if module score sign matches signal direction.
        """
        result: list[ModuleScore] = []
        for name, raw, weight in zip(_MODULE_NAMES, raw_scores, self._weights):
            capped = self._cap_score(raw)
            weighted = capped * weight
            aligned = (raw >= 0 and direction == Direction.BUY) or (raw < 0 and direction == Direction.SELL)
            result.append(ModuleScore(
                name=name,
                weight=weight,
                raw_score=raw,
                capped_score=capped,
                weighted_contribution=weighted,
                aligned=aligned,
            ))
        return result
