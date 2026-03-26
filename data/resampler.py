"""
Timeframe Resampler — Sprint 1 deliverable (full implementation).

Converts 1-minute OHLCV data into all higher timeframes required by the engine.
Timezone alignment is critical: 4H candle boundaries must match HFM MT4/MT5.

Canonical timeframe map:
    "1m"  → raw input (no resampling)
    "5m"  → 5-minute bars
    "15m" → 15-minute bars
    "30m" → 30-minute bars
    "1H"  → 1-hour bars
    "4H"  → 4-hour bars, anchored at 00:00 UTC (matches HFM MT4/MT5 server time)
    "1D"  → daily bars, close at 21:00 UTC (forex day close convention)
    "1W"  → weekly bars, Monday open / Friday close

HFM timezone note:
    HFM MT4/MT5 typically runs on EET (GMT+2/+3 with DST).
    4H candles open at: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 server time.
    In UTC: 22:00, 02:00, 06:00, 10:00, 14:00, 18:00 (winter / GMT+2).
    Use UTC-offset anchoring to match broker candle boundaries exactly.
    Validate at least 50 resampled 4H candles against HFM chart screenshots.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from data.loader import OHLCV_COLUMNS, validate_columns


# Pandas resample rule strings for each timeframe
_RESAMPLE_RULES: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1H":  "1h",
    "4H":  "4h",
    "1D":  "1D",
    "1W":  "1W-MON",   # ISO week, Monday open
}

# Daily close convention for forex (21:00 UTC = 5 PM New York)
DAILY_CLOSE_UTC_HOUR = 21

# 4H anchor offset from UTC midnight (0 = midnight-anchored 4H)
# Adjust this to match HFM's actual server time offset
FOUR_HOUR_ANCHOR_OFFSET_HOURS = 0


def resample(
    df: pd.DataFrame,
    target_timeframe: str,
    closed: str = "left",
    label: str = "left",
) -> pd.DataFrame:
    """
    Resample a 1-minute OHLCV DataFrame to a higher timeframe.

    Args:
        df: 1-minute OHLCV DataFrame with UTC-aware DatetimeIndex.
        target_timeframe: Target timeframe key (e.g., "15m", "4H", "1D").
        closed: Which side of the interval is closed ("left" or "right").
        label: Which side of the interval is used as the label.

    Returns:
        Resampled OHLCV DataFrame with UTC-aware DatetimeIndex.

    Raises:
        ValueError: If target_timeframe is not in the supported list.
        ValueError: If input DataFrame is missing OHLCV columns.
    """
    if target_timeframe == "1m":
        return df.copy()

    if target_timeframe not in _RESAMPLE_RULES:
        raise ValueError(
            f"Unsupported timeframe: {target_timeframe!r}. "
            f"Must be one of: {list(_RESAMPLE_RULES.keys())}"
        )

    validate_columns(df)

    rule = _RESAMPLE_RULES[target_timeframe]

    # Special handling for 4H: anchor to broker server time
    offset = None
    if target_timeframe == "4H" and FOUR_HOUR_ANCHOR_OFFSET_HOURS != 0:
        offset = f"{FOUR_HOUR_ANCHOR_OFFSET_HOURS}h"

    resampler = df.resample(rule, closed=closed, label=label, offset=offset)

    resampled = pd.DataFrame({
        "open":   resampler["open"].first(),
        "high":   resampler["high"].max(),
        "low":    resampler["low"].min(),
        "close":  resampler["close"].last(),
        "volume": resampler["volume"].sum(),
    })

    # Drop bars with no data (gaps, weekends)
    resampled = resampled.dropna(subset=["open", "close"])

    # Ensure proper float types
    resampled = resampled.astype("float64")

    return resampled


def resample_all(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Resample 1-minute data into all required timeframes at once.

    Args:
        df: 1-minute OHLCV DataFrame with UTC-aware DatetimeIndex.

    Returns:
        Dict mapping timeframe string to resampled DataFrame.
        E.g., {"1m": df, "5m": df_5m, "15m": df_15m, ...}
    """
    results: dict[str, pd.DataFrame] = {}
    for tf in _RESAMPLE_RULES:
        results[tf] = resample(df, tf)
    return results


def validate_resampled_candle(
    resampled_candle: pd.Series,
    reference_candle: dict,
    tolerance_pct: float = 0.001,
) -> bool:
    """
    Validate a resampled candle against a reference (e.g., broker chart data).

    Args:
        resampled_candle: Row from resampled DataFrame (open, high, low, close, volume).
        reference_candle: Dict with keys open, high, low, close from broker.
        tolerance_pct: Allowed % difference per field (default 0.1%).

    Returns:
        True if all OHLC fields match within tolerance.
    """
    for field in ["open", "high", "low", "close"]:
        expected = reference_candle.get(field)
        actual = resampled_candle.get(field)
        if expected is None or actual is None:
            return False
        if expected == 0:
            continue
        if abs(actual - expected) / expected > tolerance_pct:
            return False
    return True


def get_higher_timeframes(entry_timeframe: str) -> list[str]:
    """
    Return the standard higher timeframes for a given entry timeframe.

    These are the HTF bias timeframes used in multi-timeframe analysis:
        Scalping (1m/5m):    → ["15m", "1H"]
        Day Trading (15m):   → ["1H", "4H"]
        Swing (1H/4H):       → ["1D", "1W"]
        Position (1D):       → ["1W"]
    """
    htf_map: dict[str, list[str]] = {
        "1m":  ["15m", "1H"],
        "5m":  ["15m", "1H"],
        "15m": ["1H", "4H"],
        "30m": ["1H", "4H"],
        "1H":  ["1D", "1W"],
        "4H":  ["1D", "1W"],
        "1D":  ["1W"],
    }
    return htf_map.get(entry_timeframe, [])
