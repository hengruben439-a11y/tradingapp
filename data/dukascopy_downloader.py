"""
Dukascopy Historical Data Downloader

Downloads 1-minute OHLCV data from Dukascopy's free historical data service.
Saves to Parquet format in data/raw/.

Dukascopy stores per-hour tick data as LZMA-compressed binary files (bi5):
    http://datafeed.dukascopy.com/datafeed/{INSTRUMENT}/{YEAR}/{MONTH:02d}/{DAY:02d}/{HOUR:02d}h_ticks.bi5

Each bi5 file contains variable-length tick data. Tick record format:
    Offset  Size  Type     Field
    0       4     uint32   milliseconds from top of hour (big-endian)
    4       4     uint32   ask * 100000 (big-endian integer)
    8       4     uint32   bid * 100000 (big-endian integer)
    12      4     float32  ask volume (big-endian)
    16      4     float32  bid volume (big-endian)
    Total: 20 bytes per tick.

Usage:
    python data/dukascopy_downloader.py --pair XAUUSD --start 2021-01-01 --end 2026-03-01
    python data/dukascopy_downloader.py --all --workers 4
    python data/dukascopy_downloader.py --pair GBPJPY --start 2024-01-01 --end 2024-06-01 --output data/raw
"""

from __future__ import annotations

import argparse
import logging
import lzma
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DUKASCOPY_BASE_URL = "http://datafeed.dukascopy.com/datafeed"

# Dukascopy instrument names (may differ from common pair notation)
INSTRUMENT_MAP: dict[str, str] = {
    "XAUUSD": "XAUUSD",
    "GBPJPY": "GBPJPY",
}

# Tick record: 20 bytes, big-endian
TICK_STRUCT_FORMAT = ">IIIff"
TICK_STRUCT_SIZE = struct.calcsize(TICK_STRUCT_FORMAT)  # 20 bytes

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.0

# Sessions where Dukascopy genuinely has no ticks (weekends + forex close)
# We skip 22:00 Fri UTC through 22:00 Sun UTC for forex pairs.
_FOREX_CLOSE_HOURS: set[tuple[int, int]] = set()  # populated lazily


class DukascopyDownloader:
    """
    Downloads and processes Dukascopy historical tick data into 1-minute OHLCV.

    Thread-safe: multiple instances or threads can download different hours
    simultaneously. The hour-level cache (data/raw/cache/) prevents re-downloading.
    """

    def __init__(self, output_dir: str = "data/raw", workers: int = 4) -> None:
        self.output_dir = Path(output_dir)
        self.cache_dir = self.output_dir / "cache"
        self.workers = workers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "made-signal-engine/1.0"})
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def download_range(
        self,
        pair: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Download all tick data for pair between start and end, aggregate to 1-minute OHLCV.

        Args:
            pair:  "XAUUSD" or "GBPJPY"
            start: Start datetime (UTC). Hour-aligned recommended.
            end:   End datetime (UTC, exclusive).

        Returns:
            DataFrame with UTC DatetimeIndex and [open, high, low, close, volume] columns.
            Returns empty DataFrame if no data is available.
        """
        instrument = self._instrument_name(pair)
        hours = list(self._iter_hours(start, end))
        logger.info(
            "Downloading %s: %d hours from %s to %s",
            pair, len(hours), start.date(), end.date(),
        )

        all_ticks: list[pd.DataFrame] = []

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(self._download_hour, instrument, dt): dt
                for dt in hours
            }
            with tqdm(total=len(hours), desc=f"{pair} download", unit="hr") as pbar:
                for future in as_completed(futures):
                    dt = futures[future]
                    try:
                        ticks = future.result()
                        if ticks is not None and not ticks.empty:
                            all_ticks.append(ticks)
                    except Exception as exc:
                        logger.warning("Failed to download %s %s: %s", instrument, dt, exc)
                    pbar.update(1)

        if not all_ticks:
            logger.warning("No tick data retrieved for %s %s–%s", pair, start, end)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        ticks_df = pd.concat(all_ticks).sort_index()
        ohlcv = self._ticks_to_ohlcv(ticks_df)
        return ohlcv

    def save_parquet(
        self,
        df: pd.DataFrame,
        pair: str,
        output_dir: Optional[str] = None,
    ) -> Path:
        """
        Save an OHLCV DataFrame to Parquet (snappy compression).

        File path: <output_dir>/<PAIR>_1m.parquet
        """
        out = Path(output_dir) if output_dir else self.output_dir
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{pair}_1m.parquet"
        df.to_parquet(path, compression="snappy", engine="pyarrow")
        logger.info("Saved %d bars to %s", len(df), path)
        return path

    def load_parquet(
        self,
        pair: str,
        input_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Load a previously saved OHLCV Parquet file.

        Raises FileNotFoundError if the file does not exist.
        """
        src = Path(input_dir) if input_dir else self.output_dir
        path = src / f"{pair}_1m.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")
        df = pd.read_parquet(path, engine="pyarrow")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        return df

    # ── Core download logic ───────────────────────────────────────────────────

    def _download_hour(self, instrument: str, dt: datetime) -> Optional[pd.DataFrame]:
        """
        Download one hour of tick data from Dukascopy.

        Returns a DataFrame of raw ticks, or None if the hour is empty
        (weekend, holiday, or no-data).

        Uses a file-level cache: if the raw bi5 bytes are already stored in
        data/raw/cache/{INSTRUMENT}/{YEAR}/{MONTH}/{DAY}/{HOUR}.bi5, they
        are read from disk instead of fetching from the network.
        """
        cache_path = self._cache_path(instrument, dt)

        if cache_path.exists():
            raw_bytes = cache_path.read_bytes()
        else:
            url = self._build_url(instrument, dt)
            raw_bytes = self._fetch_with_retry(url)
            if raw_bytes is None:
                return None
            # Cache empty responses too (as zero-length files) to skip re-requesting
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw_bytes)

        if len(raw_bytes) == 0:
            return None

        try:
            ticks = self._decode_bi5(raw_bytes, dt)
        except Exception as exc:
            logger.warning("bi5 decode error %s %s: %s", instrument, dt, exc)
            return None

        return ticks

    def _decode_bi5(self, data: bytes, hour_dt: datetime) -> pd.DataFrame:
        """
        Decompress LZMA-encoded bi5 data and parse the binary tick records.

        Args:
            data:    Raw bytes from Dukascopy (LZMA-compressed).
            hour_dt: The hour this file represents (UTC, e.g. 2024-01-15 13:00:00).

        Returns:
            DataFrame with UTC DatetimeIndex and columns:
                ask, bid, ask_vol, bid_vol, mid

        The tick binary format per record (20 bytes, big-endian):
            uint32  ms_from_hour  — milliseconds elapsed since hour_dt
            uint32  ask_raw       — ask price × 100000 (integer)
            uint32  bid_raw       — bid price × 100000 (integer)
            float32 ask_vol       — ask-side volume
            float32 bid_vol       — bid-side volume
        """
        try:
            decompressed = lzma.decompress(data)
        except lzma.LZMAError as exc:
            raise ValueError(f"LZMA decompression failed: {exc}") from exc

        n_ticks = len(decompressed) // TICK_STRUCT_SIZE
        if n_ticks == 0:
            return pd.DataFrame(columns=["ask", "bid", "ask_vol", "bid_vol", "mid"])

        records = []
        base_ms = int(hour_dt.timestamp() * 1000)

        for i in range(n_ticks):
            offset = i * TICK_STRUCT_SIZE
            ms_from_hour, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack_from(
                TICK_STRUCT_FORMAT, decompressed, offset
            )
            ts_ms = base_ms + ms_from_hour
            ask = ask_raw / 100_000.0
            bid = bid_raw / 100_000.0
            records.append((ts_ms, ask, bid, float(ask_vol), float(bid_vol)))

        if not records:
            return pd.DataFrame(columns=["ask", "bid", "ask_vol", "bid_vol", "mid"])

        timestamps_ms, asks, bids, ask_vols, bid_vols = zip(*records)

        index = pd.to_datetime(list(timestamps_ms), unit="ms", utc=True)
        df = pd.DataFrame(
            {
                "ask": asks,
                "bid": bids,
                "ask_vol": ask_vols,
                "bid_vol": bid_vols,
            },
            index=index,
        )
        df["mid"] = (df["ask"] + df["bid"]) / 2.0
        return df

    def _ticks_to_ohlcv(
        self,
        ticks: pd.DataFrame,
        freq: str = "1min",
    ) -> pd.DataFrame:
        """
        Resample tick data to OHLCV bars.

        Uses mid price (ask+bid)/2 for O/H/L/C.
        Volume = sum of (ask_vol + bid_vol) per bar.

        Args:
            ticks: DataFrame with columns [ask, bid, ask_vol, bid_vol, mid],
                   UTC DatetimeIndex.
            freq:  Pandas resample frequency string (default "1min" = 1-minute bars).

        Returns:
            DataFrame with columns [open, high, low, close, volume], UTC DatetimeIndex.
            Bars with no ticks are dropped (not forward-filled) so the validator
            can detect real gaps.
        """
        if ticks.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        price = ticks["mid"]
        total_vol = ticks["ask_vol"] + ticks["bid_vol"]

        ohlcv = price.resample(freq).ohlc()
        ohlcv["volume"] = total_vol.resample(freq).sum()

        # Drop bars where no ticks fell (resample creates NaN rows for empty windows)
        ohlcv = ohlcv.dropna(subset=["open"])
        ohlcv.columns = ["open", "high", "low", "close", "volume"]
        ohlcv = ohlcv.astype({"open": "float64", "high": "float64",
                               "low": "float64", "close": "float64",
                               "volume": "float64"})
        return ohlcv

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _instrument_name(self, pair: str) -> str:
        """
        Map a common pair name to Dukascopy's instrument identifier.

        XAUUSD → "XAUUSD"  (Dukascopy uses the same notation for gold)
        GBPJPY → "GBPJPY"
        """
        name = INSTRUMENT_MAP.get(pair.upper())
        if name is None:
            raise ValueError(
                f"Unknown pair '{pair}'. Supported: {list(INSTRUMENT_MAP.keys())}"
            )
        return name

    def _build_url(self, instrument: str, dt: datetime) -> str:
        """
        Build the Dukascopy bi5 download URL for the given instrument and hour.

        URL format:
            http://datafeed.dukascopy.com/datafeed/{INSTRUMENT}/{YEAR}/{MONTH:02d}/{DAY:02d}/{HOUR:02d}h_ticks.bi5

        Note: Dukascopy uses zero-indexed months in the URL (January = 00).
        """
        return (
            f"{DUKASCOPY_BASE_URL}/{instrument}"
            f"/{dt.year}"
            f"/{dt.month - 1:02d}"   # zero-indexed month
            f"/{dt.day:02d}"
            f"/{dt.hour:02d}h_ticks.bi5"
        )

    def _cache_path(self, instrument: str, dt: datetime) -> Path:
        """Return the local cache file path for a given hour."""
        return (
            self.cache_dir
            / instrument
            / str(dt.year)
            / f"{dt.month:02d}"
            / f"{dt.day:02d}"
            / f"{dt.hour:02d}.bi5"
        )

    def _fetch_with_retry(self, url: str) -> Optional[bytes]:
        """
        Fetch a URL with up to MAX_RETRIES retries on HTTP errors.

        Returns raw bytes on success, or None if all retries fail or the
        server returns 404 (no data for that hour).
        """
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 404:
                    # No data for this hour (weekend, holiday, market closed)
                    return b""
                if resp.status_code == 200:
                    return resp.content
                logger.warning(
                    "HTTP %d for %s (attempt %d/%d)",
                    resp.status_code, url, attempt + 1, MAX_RETRIES,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "Request error for %s (attempt %d/%d): %s",
                    url, attempt + 1, MAX_RETRIES, exc,
                )

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

        logger.error("All retries exhausted for %s", url)
        return None

    @staticmethod
    def _iter_hours(start: datetime, end: datetime):
        """
        Yield each UTC hour between start (inclusive) and end (exclusive).

        Skips Saturday and Sunday entirely since Dukascopy will return empty
        bi5 files — skipping saves bandwidth and avoids polluting the cache.
        """
        current = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        end_utc = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end

        while current < end_utc:
            # Skip weekends (Saturday=5, Sunday=6)
            if current.weekday() not in (5, 6):
                yield current
            current += timedelta(hours=1)

    def can_skip_hour(self, instrument: str, dt: datetime) -> bool:
        """
        Return True if this hour is already cached and can be skipped.

        Used by the progress-tracking layer to report accurate completion %.
        """
        return self._cache_path(instrument, dt).exists()


# ── CLI entry point ───────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Dukascopy 1-minute OHLCV data for made. signal engine.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pair", choices=list(INSTRUMENT_MAP.keys()),
                       help="Single pair to download.")
    group.add_argument("--all", action="store_true", dest="all_pairs",
                       help="Download all supported pairs (XAUUSD + GBPJPY).")

    parser.add_argument("--start", default="2021-01-01",
                        help="Start date (YYYY-MM-DD, UTC).")
    parser.add_argument("--end", default="2026-03-01",
                        help="End date (YYYY-MM-DD, UTC, exclusive).")
    parser.add_argument("--output", default="data/raw",
                        help="Output directory for Parquet files.")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel download threads.")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging verbosity.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt   = datetime.strptime(args.end,   "%Y-%m-%d").replace(tzinfo=timezone.utc)

    pairs = list(INSTRUMENT_MAP.keys()) if args.all_pairs else [args.pair]

    downloader = DukascopyDownloader(output_dir=args.output, workers=args.workers)

    for pair in pairs:
        logger.info("=== Downloading %s (%s → %s) ===", pair, args.start, args.end)
        df = downloader.download_range(pair, start_dt, end_dt)

        if df.empty:
            logger.error("No data retrieved for %s — check your date range.", pair)
            continue

        path = downloader.save_parquet(df, pair, output_dir=args.output)
        logger.info(
            "%s complete: %d 1-min bars, %s → %s. Saved to %s",
            pair, len(df),
            df.index[0].isoformat(), df.index[-1].isoformat(),
            path,
        )


if __name__ == "__main__":
    main()
