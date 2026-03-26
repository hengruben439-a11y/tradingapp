"""
Signal confidence decay calculator.

Formula: displayed_score = base_score × (1 - 0.25 × elapsed_fraction)
where elapsed_fraction = elapsed_time / expiry_window (0 → 1)

Per CLAUDE.md §5.3.1:
    - At 0% elapsed:  displayed_score = base_score × 1.0     (no decay)
    - At 50% elapsed: displayed_score = base_score × 0.875   (12.5% decay)
    - At 100% elapsed: displayed_score = base_score × 0.75   (25% decay)

Decay thresholds:
    - displayed_score < 0.50: mark "Fading"
    - displayed_score < 0.30: auto-expire

Signal expiry bars per timeframe (CLAUDE.md §8.4):
    1m/5m:    5 bars
    15m/30m:  8 bars
    1H/4H:   12 bars
    1D:       5 bars
    1W:       3 bars
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class DecayResult:
    """Result of a signal decay calculation."""
    displayed_score: float          # Decayed score for display
    elapsed_fraction: float         # How far through the expiry window (0–1)
    is_fading: bool                 # True when displayed_score < 0.50
    is_expired: bool                # True when displayed_score < 0.30
    time_remaining_seconds: int     # Seconds until signal expires (0 if expired)


# ── Expiry table from CLAUDE.md §8.4 ─────────────────────────────────────────

_EXPIRY_BARS: dict[str, int] = {
    "1m":  5,
    "5m":  5,
    "15m": 8,
    "30m": 8,
    "1H":  12,
    "4H":  12,
    "1D":  5,
    "1W":  3,
}

# Canonical bar durations in minutes
_BAR_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1H":  60,
    "4H":  240,
    "1D":  1440,
    "1W":  10080,
}

# Decay coefficient (25% reduction by window end, per §5.3.1)
_DECAY_COEFFICIENT = 0.25


class SignalDecay:
    """
    Calculates time-based confidence decay for active signals.

    The decay model is linear: the score starts at base_score when generated
    and reaches base_score × 0.75 at the end of the expiry window.
    If the decayed score falls below 0.30, the signal is auto-expired.

    Example:
        decay = SignalDecay()
        result = decay.compute(
            base_score=0.80,
            generated_at=signal_time,
            expiry_window_bars=12,
            bar_interval_minutes=60,   # 1H bars
        )
        print(result.displayed_score)  # 0.70 at 50% elapsed
        print(result.is_fading)        # False (0.70 >= 0.50)
    """

    def compute(
        self,
        base_score: float,
        generated_at: datetime,
        expiry_window_bars: int,
        bar_interval_minutes: int,
    ) -> DecayResult:
        """
        Compute the current decayed score for a signal.

        Args:
            base_score: Original confluence score at generation time (0–1).
            generated_at: UTC-aware datetime when the signal was generated.
            expiry_window_bars: Number of bars until signal expires (e.g. 12).
            bar_interval_minutes: Duration of each bar in minutes (e.g. 60 for 1H).

        Returns:
            DecayResult with all fields computed.
        """
        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)

        # Total expiry window in seconds
        expiry_window_seconds = expiry_window_bars * bar_interval_minutes * 60
        elapsed_seconds = max(0.0, (now - generated_at).total_seconds())

        # Clamp elapsed_fraction to [0, 1]
        if expiry_window_seconds <= 0:
            elapsed_fraction = 1.0
        else:
            elapsed_fraction = min(1.0, elapsed_seconds / expiry_window_seconds)

        # Apply decay formula: displayed = base × (1 - 0.25 × elapsed_fraction)
        decay_factor = 1.0 - (_DECAY_COEFFICIENT * elapsed_fraction)
        displayed_score = round(abs(base_score) * decay_factor, 4)

        # Preserve sign of original score
        if base_score < 0:
            displayed_score = -displayed_score

        is_expired = abs(displayed_score) < 0.30
        is_fading = (not is_expired) and abs(displayed_score) < 0.50

        time_remaining_seconds = max(
            0,
            int(expiry_window_seconds - elapsed_seconds),
        )

        return DecayResult(
            displayed_score=displayed_score,
            elapsed_fraction=round(elapsed_fraction, 4),
            is_fading=is_fading,
            is_expired=is_expired,
            time_remaining_seconds=time_remaining_seconds,
        )

    def get_expiry_bars(self, trading_style: str, tf: str) -> int:
        """
        Return the signal expiry in bars for a given timeframe.

        Matches the table in CLAUDE.md §8.4:
            1m/5m:   5 bars
            15m/30m: 8 bars
            1H/4H:   12 bars
            1D:      5 bars
            1W:      3 bars

        Args:
            trading_style: Trading style (not used for lookup but available
                           for future per-style overrides, e.g. scalping vs swing).
            tf: Timeframe string, e.g. "1m", "5m", "15m", "1H", "4H", "1D", "1W".

        Returns:
            Number of bars before the signal expires.

        Raises:
            ValueError: If the timeframe is not recognised.
        """
        tf_clean = tf.strip()
        expiry = _EXPIRY_BARS.get(tf_clean)

        if expiry is None:
            raise ValueError(
                f"Unknown timeframe: {tf!r}. "
                f"Valid options: {list(_EXPIRY_BARS.keys())}"
            )

        return expiry

    def is_expired(
        self,
        base_score: float,
        generated_at: datetime,
        expiry_window_bars: int,
        bar_interval_minutes: int,
    ) -> bool:
        """
        Return True if the signal has decayed past the 0.30 auto-expiry threshold.

        Convenience wrapper around `compute()` for simple expiry checks.

        Args:
            base_score: Original confluence score at generation time.
            generated_at: UTC-aware datetime when the signal was generated.
            expiry_window_bars: Number of bars until signal expires.
            bar_interval_minutes: Duration of each bar in minutes.

        Returns:
            True if the signal should be auto-expired.
        """
        result = self.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=expiry_window_bars,
            bar_interval_minutes=bar_interval_minutes,
        )
        return result.is_expired

    def bar_interval_minutes_for_tf(self, tf: str) -> int:
        """
        Return the bar interval in minutes for a given timeframe string.

        Args:
            tf: Timeframe label, e.g. "1H", "4H", "15m".

        Returns:
            Bar duration in minutes.

        Raises:
            ValueError: If the timeframe is not recognised.
        """
        tf_clean = tf.strip()
        minutes = _BAR_MINUTES.get(tf_clean)

        if minutes is None:
            raise ValueError(
                f"Unknown timeframe for bar interval: {tf!r}. "
                f"Valid options: {list(_BAR_MINUTES.keys())}"
            )

        return minutes
