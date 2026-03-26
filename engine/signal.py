"""
Signal dataclass — the output object of the confluence scoring pipeline.

Every signal produced by the engine is a Signal instance. This is the
canonical shape for storage, display, and API responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Pair(str, Enum):
    XAUUSD = "XAUUSD"
    GBPJPY = "GBPJPY"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradingStyle(str, Enum):
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"


class SignalStrength(str, Enum):
    VERY_STRONG = "very_strong"   # >= 0.80
    STRONG = "strong"              # 0.65–0.79
    MODERATE = "moderate"          # 0.50–0.64
    WEAK = "weak"                  # 0.30–0.49 (watch only)


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    TRANSITIONAL = "TRANSITIONAL"
    UNKNOWN = "UNKNOWN"


class UIMode(str, Enum):
    """User-facing UI complexity mode (§8.3 of PRD)."""
    SIMPLE = "simple"    # Beginners — top 1-2 signals, plain labels
    PRO = "pro"          # Intermediate — full signal detail, module dissent
    MAX = "max"          # Expert — raw scores, decay timer, advanced analytics


@dataclass
class ModuleScore:
    """Score and metadata from a single confluence module."""
    name: str
    weight: float              # Module weight for this pair (0.0–0.30)
    raw_score: float           # Pre-cap score (-1.0 to +1.0)
    capped_score: float        # After 0.85 cap
    weighted_contribution: float  # capped_score * weight
    aligned: bool              # True if score direction matches signal direction
    note: Optional[str] = None  # Human-readable explanation for UI dissent section


@dataclass
class TPLevel:
    """A single take-profit level."""
    level: int           # 1, 2, or 3
    price: float
    rr_ratio: float      # Risk:Reward ratio (e.g., 2.0 = 1:2)
    close_pct: float     # Fraction of position to close at this level (0.40/0.30/0.30)
    source: str          # "structural" | "atr_fallback" | "fibonacci_extension"


@dataclass
class Signal:
    """
    The canonical signal object produced by the made. confluence engine.

    Lifecycle: ACTIVE → EXPIRED (via decay, time, or manual close)
                       → SL_HIT (with auto post-mortem generated)
                       → TP1_HIT → TP2_HIT → TP3_HIT
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    signal_id: str                   # UUID
    pair: Pair
    direction: Direction
    trading_style: TradingStyle
    entry_timeframe: str             # e.g. "15m"
    htf_timeframes: list[str]        # e.g. ["1H", "4H"]

    # ── Prices ────────────────────────────────────────────────────────────────
    entry_price: float
    stop_loss: float
    tp1: TPLevel
    tp2: TPLevel
    tp3: TPLevel
    sl_distance_pips: float
    sl_distance_atr_multiple: float

    # ── Confluence Scoring ────────────────────────────────────────────────────
    confluence_score: float          # Final post-penalty score (-1.0 to +1.0)
    raw_weighted_sum: float          # Pre-multiplier weighted sum
    strength: SignalStrength
    module_scores: list[ModuleScore]  # One per module (9 total)

    # ── Context Flags ─────────────────────────────────────────────────────────
    regime: MarketRegime
    kill_zone_active: str | None     # Name of active KZ, or None
    htf_conflict: bool               # True if LTF signal conflicts with HTF
    htf_conflict_description: str | None  # Template-based explanation
    news_risk: bool                  # True if high-impact news within 15 min
    news_event_name: str | None      # e.g. "NFP" if news_risk is True

    # ── Multipliers Applied ───────────────────────────────────────────────────
    unicorn_setup: bool              # OB + FVG overlap detected
    ote_ob_confluence: bool
    ote_fvg_confluence: bool
    applied_multipliers: list[str]   # Human-readable list for Max mode display
    day_of_week_modifier: float      # From config (default 1.0x)

    # ── Timing ────────────────────────────────────────────────────────────────
    generated_at: datetime           # Bar close time when signal was created
    expiry_bars: int                 # Signal valid for N bars
    expiry_at: datetime | None       # Absolute expiry timestamp (set on generation)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: str = "ACTIVE"           # ACTIVE | TP1_HIT | TP2_HIT | TP3_HIT | SL_HIT | EXPIRED
    tp1_hit_at: datetime | None = None
    tp2_hit_at: datetime | None = None
    tp3_hit_at: datetime | None = None
    sl_hit_at: datetime | None = None

    # ── Risk Calculator (populated per user account) ──────────────────────────
    account_balance: float | None = None
    risk_pct: float = 1.0
    lot_size: float | None = None
    dollar_risk: float | None = None

    # ── Backtest metadata (set during backtesting, None in live) ──────────────
    is_backtest: bool = False
    execution_price: float | None = None  # Next-bar-open fill price
    spread_applied: float | None = None   # Spread in pips at execution

    def decayed_score(self, elapsed_fraction: float) -> float:
        """
        Return the displayed confluence score adjusted for time decay.
        Formula: base_score * (1 - 0.25 * elapsed_fraction)
        elapsed_fraction: 0.0 (just generated) → 1.0 (at expiry)
        """
        return abs(self.confluence_score) * (1 - 0.25 * elapsed_fraction)

    @property
    def is_fading(self) -> bool:
        """Signal is marked Fading when decayed_score < 0.50."""
        return abs(self.confluence_score) < 0.50

    @property
    def dissenting_modules(self) -> list[ModuleScore]:
        """Modules whose score direction opposes the signal direction."""
        return [m for m in self.module_scores if not m.aligned]

    @property
    def aligned_modules(self) -> list[ModuleScore]:
        """Modules whose score direction matches the signal direction."""
        return [m for m in self.module_scores if m.aligned]

    def to_simple_display(self) -> dict:
        """Simplified signal card data for Simple UI mode."""
        return {
            "pair": self.pair.value,
            "direction": self.direction.value,
            "entry": self.entry_price,
            "tp1": self.tp1.price,
            "sl": self.stop_loss,
            "strength_label": {
                SignalStrength.VERY_STRONG: "Very Strong",
                SignalStrength.STRONG: "Strong",
                SignalStrength.MODERATE: "Moderate",
            }.get(self.strength, "Moderate"),
        }

    def to_pro_display(self) -> dict:
        """Full signal data for Pro UI mode."""
        return {
            **self.to_simple_display(),
            "tp2": self.tp2.price,
            "tp3": self.tp3.price,
            "confluence_score": self.confluence_score,
            "regime": self.regime.value,
            "kill_zone": self.kill_zone_active,
            "htf_conflict": self.htf_conflict,
            "news_risk": self.news_risk,
            "module_scores": [
                {
                    "name": m.name,
                    "aligned": m.aligned,
                    "weighted_contribution": m.weighted_contribution,
                    "note": m.note,
                }
                for m in self.module_scores
            ],
        }

    def to_max_display(self) -> dict:
        """Full signal data including raw scores for Max UI mode."""
        return {
            **self.to_pro_display(),
            "raw_module_scores": [
                {
                    "name": m.name,
                    "raw_score": m.raw_score,
                    "capped_score": m.capped_score,
                    "weight": m.weight,
                }
                for m in self.module_scores
            ],
            "applied_multipliers": self.applied_multipliers,
            "day_of_week_modifier": self.day_of_week_modifier,
            "unicorn_setup": self.unicorn_setup,
            "ote_ob_confluence": self.ote_ob_confluence,
            "ote_fvg_confluence": self.ote_fvg_confluence,
            "expiry_bars": self.expiry_bars,
            "sl_atr_multiple": self.sl_distance_atr_multiple,
        }
