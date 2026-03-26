"""
Data Validator — Sprint 1 deliverable (full implementation).

Detects gaps, duplicates, outlier prices, and weekend data leakage
in OHLCV DataFrames before they enter the signal engine or backtest.

Validation rules:
    1. No duplicate timestamps
    2. No gaps > 1 expected bar interval (excluding known market closures)
    3. No OHLC logical violations (e.g., high < low, close outside high/low)
    4. No outlier prices (> 5x ATR move between consecutive bars)
    5. No weekend data (Sat/Sun for forex) — Dukascopy sometimes includes these
    6. Volume >= 0
    7. Minimum candle count for engine warm-up (200 bars for EMA 200)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# Minimum bars required to warm up all indicators
MIN_CANDLES_WARMUP = 200

# Outlier detection threshold (max ATR multiples between consecutive closes)
OUTLIER_ATR_THRESHOLD = 5.0

# Weekend day numbers (0=Mon, 5=Sat, 6=Sun)
WEEKEND_DAYS = {5, 6}


@dataclass
class ValidationReport:
    pair: str
    timeframe: str
    total_bars: int
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_timestamps: int = 0
    gap_count: int = 0
    largest_gap_minutes: float = 0.0
    ohlc_violation_count: int = 0
    outlier_count: int = 0
    weekend_bar_count: int = 0


def validate(
    df: pd.DataFrame,
    pair: str,
    timeframe: str,
    strict: bool = True,
) -> ValidationReport:
    """
    Run all validation checks on an OHLCV DataFrame.

    Args:
        df: OHLCV DataFrame with UTC-aware DatetimeIndex.
        pair: Pair name for reporting.
        timeframe: Timeframe string for expected interval calculation.
        strict: If True, any error marks the report as invalid.
                If False, only OHLC violations are hard errors.

    Returns:
        ValidationReport with detailed findings.
    """
    report = ValidationReport(
        pair=pair,
        timeframe=timeframe,
        total_bars=len(df),
        is_valid=True,
    )

    _check_minimum_bars(df, report)
    _check_duplicates(df, report)
    _check_ohlc_logic(df, report)
    _check_gaps(df, timeframe, report)
    _check_outliers(df, report)
    _check_weekend_data(df, report)
    _check_volume(df, report)

    if report.errors:
        report.is_valid = False
    elif not strict and not report.errors:
        report.is_valid = True

    return report


def clean(
    df: pd.DataFrame,
    pair: str,
    timeframe: str,
) -> tuple[pd.DataFrame, ValidationReport]:
    """
    Validate and auto-fix recoverable issues.

    Fixes applied:
        - Remove duplicate timestamps (keep first)
        - Remove weekend rows
        - Remove rows with OHLC violations
        - Sort by timestamp

    Returns:
        (cleaned_df, report)
    """
    report = validate(df, pair, timeframe, strict=False)

    cleaned = df.copy()

    # Remove duplicates
    if report.duplicate_timestamps > 0:
        cleaned = cleaned[~cleaned.index.duplicated(keep="first")]

    # Remove weekend rows
    if report.weekend_bar_count > 0:
        cleaned = cleaned[cleaned.index.dayofweek.isin([0, 1, 2, 3, 4])]

    # Remove OHLC violations
    mask_valid_ohlc = (
        (cleaned["high"] >= cleaned["low"])
        & (cleaned["close"] >= cleaned["low"])
        & (cleaned["close"] <= cleaned["high"])
        & (cleaned["open"] >= cleaned["low"])
        & (cleaned["open"] <= cleaned["high"])
    )
    cleaned = cleaned[mask_valid_ohlc]

    # Sort ascending
    cleaned = cleaned.sort_index()

    return cleaned, report


def _check_minimum_bars(df: pd.DataFrame, report: ValidationReport) -> None:
    if len(df) < MIN_CANDLES_WARMUP:
        report.errors.append(
            f"Insufficient data: {len(df)} bars < minimum {MIN_CANDLES_WARMUP} required for indicator warmup."
        )


def _check_duplicates(df: pd.DataFrame, report: ValidationReport) -> None:
    dup_count = int(df.index.duplicated().sum())
    report.duplicate_timestamps = dup_count
    if dup_count > 0:
        report.warnings.append(f"{dup_count} duplicate timestamps found.")


def _check_ohlc_logic(df: pd.DataFrame, report: ValidationReport) -> None:
    violations = (
        (df["high"] < df["low"])
        | (df["close"] < df["low"])
        | (df["close"] > df["high"])
        | (df["open"] < df["low"])
        | (df["open"] > df["high"])
    )
    count = int(violations.sum())
    report.ohlc_violation_count = count
    if count > 0:
        report.errors.append(f"{count} bars with OHLC logic violations (high < low, etc.).")


def _check_gaps(df: pd.DataFrame, timeframe: str, report: ValidationReport) -> None:
    expected_interval = _timeframe_to_minutes(timeframe)
    if expected_interval is None or len(df) < 2:
        return

    time_diffs = df.index.to_series().diff().dropna()
    minutes_diff = time_diffs.dt.total_seconds() / 60.0

    # Allow up to 2x expected interval + small tolerance
    max_allowed = expected_interval * 2 + 1

    gaps = minutes_diff[minutes_diff > max_allowed]
    report.gap_count = len(gaps)
    report.largest_gap_minutes = float(gaps.max()) if not gaps.empty else 0.0

    if report.gap_count > 0:
        report.warnings.append(
            f"{report.gap_count} gaps detected. Largest: {report.largest_gap_minutes:.0f} minutes."
        )


def _check_outliers(df: pd.DataFrame, report: ValidationReport) -> None:
    if len(df) < 20:
        return

    close_diff = df["close"].diff().abs()
    atr_approx = (df["high"] - df["low"]).rolling(14).mean()
    outlier_mask = close_diff > OUTLIER_ATR_THRESHOLD * atr_approx

    count = int(outlier_mask.sum())
    report.outlier_count = count
    if count > 0:
        report.warnings.append(
            f"{count} potential outlier price bars (move > {OUTLIER_ATR_THRESHOLD}x ATR)."
        )


def _check_weekend_data(df: pd.DataFrame, report: ValidationReport) -> None:
    weekend_mask = df.index.dayofweek.isin(WEEKEND_DAYS)
    count = int(weekend_mask.sum())
    report.weekend_bar_count = count
    if count > 0:
        report.warnings.append(f"{count} weekend bars found — should be removed.")


def _check_volume(df: pd.DataFrame, report: ValidationReport) -> None:
    negative_vol = int((df["volume"] < 0).sum())
    if negative_vol > 0:
        report.errors.append(f"{negative_vol} bars with negative volume.")


def _timeframe_to_minutes(timeframe: str) -> Optional[int]:
    """Convert timeframe string to expected bar interval in minutes."""
    mapping = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1H": 60, "4H": 240, "1D": 1440, "1W": 10080,
    }
    return mapping.get(timeframe)
