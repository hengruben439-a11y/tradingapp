"""
OHLCV Data Loader — Sprint 1 deliverable (full implementation).

Reads and writes Parquet files. Handles timezone normalization to UTC.
Validates that data meets minimum quality standards before use.

Supported sources:
    - Dukascopy CSV exports (primary historical data)
    - OANDA API responses (live + validation)
    - Parquet cache files (fast re-reads after initial load)

Column contract (output DataFrames always have these columns):
    open, high, low, close, volume  (float64)
    Index: DatetimeTZDtype("UTC")   (timezone-aware)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


# Standard column names used throughout the engine
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Data directories (relative to project root; git-ignored)
RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")


def load_parquet(
    pair: str,
    timeframe: str,
    data_dir: Path = PROCESSED_DATA_DIR,
) -> pd.DataFrame:
    """
    Load a processed OHLCV Parquet file and return a UTC-indexed DataFrame.

    Args:
        pair: e.g. "XAUUSD" or "GBPJPY"
        timeframe: e.g. "1m", "15m", "1H", "4H", "1D"
        data_dir: Root directory containing Parquet files.

    Returns:
        DataFrame with DatetimeTZDtype("UTC") index and [open,high,low,close,volume] columns.

    Raises:
        FileNotFoundError: If the Parquet file does not exist.
        ValueError: If the loaded DataFrame is missing required columns.
    """
    path = data_dir / f"{pair}_{timeframe}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    df = pd.read_parquet(path)
    df = _normalize_columns(df)
    df = _normalize_timezone(df)
    return df


def save_parquet(
    df: pd.DataFrame,
    pair: str,
    timeframe: str,
    data_dir: Path = PROCESSED_DATA_DIR,
) -> Path:
    """
    Save an OHLCV DataFrame to Parquet format.

    Args:
        df: OHLCV DataFrame with UTC-aware DatetimeIndex.
        pair: e.g. "XAUUSD"
        timeframe: e.g. "1m"
        data_dir: Root directory for output.

    Returns:
        Path to the written file.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{pair}_{timeframe}.parquet"
    df = _normalize_columns(df)
    df = _normalize_timezone(df)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path, compression="snappy")
    return path


def load_dukascopy_csv(csv_path: Path, pair: str) -> pd.DataFrame:
    """
    Parse a Dukascopy 1-minute CSV export into the standard OHLCV format.

    Dukascopy format:
        Gmt time,Open,High,Low,Close,Volume
        01.01.2021 00:00:00.000,1900.5,1901.0,1899.8,1900.7,1234

    Args:
        csv_path: Path to the CSV file.
        pair: Pair name for logging.

    Returns:
        Standard OHLCV DataFrame with UTC index.
    """
    df = pd.read_csv(
        csv_path,
        parse_dates=["Gmt time"],
        date_format="%d.%m.%Y %H:%M:%S.%f",
        index_col="Gmt time",
    )
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    return _normalize_columns(df)


def load_oanda_candles(response_json: dict) -> pd.DataFrame:
    """
    Parse an OANDA v20 REST API candles response into standard OHLCV format.

    Args:
        response_json: Parsed JSON from OANDA GET /instruments/{pair}/candles

    Returns:
        Standard OHLCV DataFrame with UTC index.
    """
    records = []
    for candle in response_json.get("candles", []):
        if not candle.get("complete", False):
            continue
        mid = candle["mid"]
        records.append({
            "timestamp": pd.Timestamp(candle["time"]),
            "open":   float(mid["o"]),
            "high":   float(mid["h"]),
            "low":    float(mid["l"]),
            "close":  float(mid["c"]),
            "volume": int(candle.get("volume", 0)),
        })

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    return df[OHLCV_COLUMNS]


def get_date_range(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the (first, last) timestamps in the DataFrame."""
    return df.index[0], df.index[-1]


def validate_columns(df: pd.DataFrame) -> None:
    """
    Raise ValueError if required OHLCV columns are missing.
    """
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names to lowercase and select OHLCV columns."""
    df = df.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    validate_columns(df)
    return df[OHLCV_COLUMNS].astype("float64")


def _normalize_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the DataFrame index is UTC-aware."""
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df
