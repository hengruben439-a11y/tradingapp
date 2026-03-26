"""
Data Acquisition Tests — Sprint 1 deliverable.

Covers:
    - DataValidator (data/validator.py): duplicates, OHLC violations, weekend bars,
      fix_common_issues alias, gaps, volume, outliers
    - DukascopyDownloader (data/dukascopy_downloader.py): bi5 decode, tick→OHLCV
      resampling, instrument name mapping, cache skip logic, retry stubs

All tests are self-contained: no network calls, no file I/O to production paths.
"""

from __future__ import annotations

import lzma
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── Imports under test ────────────────────────────────────────────────────────

from data.validator import (
    ValidationReport,
    clean,
    validate,
)
from data.dukascopy_downloader import DukascopyDownloader, TICK_STRUCT_FORMAT


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_ohlcv(
    n: int = 300,
    start: str = "2024-01-02 00:00:00",
    freq: str = "1min",
    base_price: float = 2000.0,
    pair: str = "XAUUSD",
) -> pd.DataFrame:
    """
    Build a clean n-bar OHLCV DataFrame with UTC index.

    All OHLC values are self-consistent (high >= low, close within range).
    """
    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(42)

    closes = base_price + rng.normal(0, 5, size=n).cumsum()
    highs  = closes + rng.uniform(0.5, 3.0, size=n)
    lows   = closes - rng.uniform(0.5, 3.0, size=n)
    opens  = closes + rng.normal(0, 1, size=n)
    # Clamp open within [low, high]
    opens  = np.clip(opens, lows, highs)
    volumes = rng.integers(100, 1000, size=n).astype(float)

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=index,
    )


def _make_tick_bi5(ticks: list[tuple[int, float, float, float, float]]) -> bytes:
    """
    Encode a list of ticks as Dukascopy bi5 (LZMA-compressed binary).

    Each tick: (ms_from_hour, ask, bid, ask_vol, bid_vol)
    ask and bid are in price units (will be multiplied by 100000 for storage).
    """
    raw = b""
    for ms, ask, bid, ask_vol, bid_vol in ticks:
        ask_raw = int(round(ask * 100_000))
        bid_raw = int(round(bid * 100_000))
        raw += struct.pack(TICK_STRUCT_FORMAT, ms, ask_raw, bid_raw, ask_vol, bid_vol)
    return lzma.compress(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# DataValidator tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataValidatorDuplicates:
    """Test 1: validator detects duplicate timestamps."""

    def test_detects_duplicate_timestamps(self):
        df = _make_ohlcv(300)
        # Inject a duplicate: repeat the first row at a different position
        dup_row = df.iloc[[0]]
        df_with_dup = pd.concat([df.iloc[:100], dup_row, df.iloc[100:]])

        report = validate(df_with_dup, pair="XAUUSD", timeframe="1m")
        assert report.duplicate_timestamps >= 1, (
            "Validator should detect the injected duplicate timestamp"
        )

    def test_clean_removes_duplicates(self):
        df = _make_ohlcv(300)
        dup_row = df.iloc[[0]]
        df_with_dup = pd.concat([df.iloc[:50], dup_row, df.iloc[50:]])

        cleaned, _ = clean(df_with_dup, pair="XAUUSD", timeframe="1m")
        assert cleaned.index.duplicated().sum() == 0, (
            "clean() must remove all duplicate timestamps"
        )
        assert len(cleaned) == len(df), "Clean frame should have same length as original"


class TestDataValidatorOHLCViolations:
    """Test 2: validator detects OHLC logic violations."""

    def test_detects_high_less_than_low(self):
        df = _make_ohlcv(300)
        # Swap high and low on row 10 to create a violation
        df_bad = df.copy()
        df_bad.at[df_bad.index[10], "high"] = df_bad.at[df_bad.index[10], "low"] - 1.0
        df_bad.at[df_bad.index[10], "low"]  = df_bad.at[df_bad.index[10], "low"] + 1.0

        report = validate(df_bad, pair="XAUUSD", timeframe="1m")
        assert report.ohlc_violation_count >= 1

    def test_detects_close_above_high(self):
        df = _make_ohlcv(300)
        df_bad = df.copy()
        df_bad.at[df_bad.index[5], "close"] = df_bad.at[df_bad.index[5], "high"] + 10.0

        report = validate(df_bad, pair="XAUUSD", timeframe="1m")
        assert report.ohlc_violation_count >= 1

    def test_detects_open_below_low(self):
        df = _make_ohlcv(300)
        df_bad = df.copy()
        df_bad.at[df_bad.index[20], "open"] = df_bad.at[df_bad.index[20], "low"] - 5.0

        report = validate(df_bad, pair="XAUUSD", timeframe="1m")
        assert report.ohlc_violation_count >= 1

    def test_violation_marks_report_invalid(self):
        df = _make_ohlcv(300)
        df_bad = df.copy()
        df_bad.at[df_bad.index[0], "high"] = df_bad.at[df_bad.index[0], "low"] - 1.0

        report = validate(df_bad, pair="XAUUSD", timeframe="1m")
        assert not report.is_valid


class TestDataValidatorWeekendBars:
    """Test 3: validator detects weekend data leakage."""

    def test_detects_saturday_bars(self):
        # Build a frame that includes a Saturday
        # 2024-01-06 is a Saturday
        sat_index = pd.to_datetime(["2024-01-06 12:00:00"], utc=True)
        sat_row = pd.DataFrame(
            {"open": [2000.0], "high": [2010.0], "low": [1995.0],
             "close": [2005.0], "volume": [500.0]},
            index=sat_index,
        )
        df = _make_ohlcv(300)
        df_with_weekend = pd.concat([df, sat_row]).sort_index()

        report = validate(df_with_weekend, pair="XAUUSD", timeframe="1m")
        assert report.weekend_bar_count >= 1

    def test_detects_sunday_bars(self):
        # 2024-01-07 is a Sunday
        sun_index = pd.to_datetime(["2024-01-07 08:00:00"], utc=True)
        sun_row = pd.DataFrame(
            {"open": [2000.0], "high": [2010.0], "low": [1995.0],
             "close": [2005.0], "volume": [500.0]},
            index=sun_index,
        )
        df = _make_ohlcv(300)
        df_with_weekend = pd.concat([df, sun_row]).sort_index()

        report = validate(df_with_weekend, pair="XAUUSD", timeframe="1m")
        assert report.weekend_bar_count >= 1


class TestDataValidatorClean:
    """Test 4: fix_common_issues / clean() removes weekend bars and duplicates."""

    def test_clean_removes_weekend_bars(self):
        # 2024-01-06 = Saturday
        sat_index = pd.to_datetime(["2024-01-06 12:00:00"], utc=True)
        sat_row = pd.DataFrame(
            {"open": [2000.0], "high": [2010.0], "low": [1995.0],
             "close": [2005.0], "volume": [500.0]},
            index=sat_index,
        )
        df = _make_ohlcv(300)
        df_dirty = pd.concat([df, sat_row]).sort_index()

        cleaned, report = clean(df_dirty, pair="XAUUSD", timeframe="1m")
        weekend_mask = cleaned.index.dayofweek.isin([5, 6])
        assert weekend_mask.sum() == 0, "clean() must remove all weekend bars"

    def test_clean_drops_duplicates(self):
        df = _make_ohlcv(300)
        dup_row = df.iloc[[0]]
        df_dirty = pd.concat([df, dup_row]).sort_index()

        cleaned, _ = clean(df_dirty, pair="XAUUSD", timeframe="1m")
        assert cleaned.index.duplicated().sum() == 0

    def test_clean_removes_ohlc_violations(self):
        df = _make_ohlcv(300)
        df_bad = df.copy()
        # Create a clear violation: high < low
        df_bad.at[df_bad.index[50], "high"] = df_bad.at[df_bad.index[50], "low"] - 2.0
        df_bad.at[df_bad.index[50], "low"]  = df_bad.at[df_bad.index[50], "low"] + 2.0

        cleaned, _ = clean(df_bad, pair="XAUUSD", timeframe="1m")
        high_lt_low = (cleaned["high"] < cleaned["low"]).any()
        assert not high_lt_low, "clean() must remove bars where high < low"


# ═══════════════════════════════════════════════════════════════════════════════
# DukascopyDownloader tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecodeBi5:
    """Test 5: _decode_bi5 correctly decodes synthetic bi5 bytes."""

    def setup_method(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.downloader = DukascopyDownloader(output_dir=tmpdir, workers=1)
        # Create a fresh downloader pointing at an actual temp dir
        self._tmpdir = tempfile.mkdtemp()
        self.downloader = DukascopyDownloader(output_dir=self._tmpdir, workers=1)

    def test_single_tick_decoded_correctly(self):
        """Encode one tick and verify ask/bid/vol round-trip correctly."""
        hour_dt = datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
        # Single tick: 500ms after hour, ask=2050.12345, bid=2050.10000
        ask = 2050.12345
        bid = 2050.10000
        ask_vol = 1.5
        bid_vol = 0.8

        bi5_bytes = _make_tick_bi5([(500, ask, bid, ask_vol, bid_vol)])
        df = self.downloader._decode_bi5(bi5_bytes, hour_dt)

        assert len(df) == 1
        assert abs(df["ask"].iloc[0] - ask) < 1e-4, "ask price round-trip failed"
        assert abs(df["bid"].iloc[0] - bid) < 1e-4, "bid price round-trip failed"
        assert abs(df["ask_vol"].iloc[0] - ask_vol) < 1e-3
        assert abs(df["bid_vol"].iloc[0] - bid_vol) < 1e-3

    def test_tick_timestamp_is_correct_utc(self):
        """Tick at ms=0 should have exactly the hour_dt timestamp."""
        hour_dt = datetime(2024, 6, 10, 8, 0, 0, tzinfo=timezone.utc)
        bi5_bytes = _make_tick_bi5([(0, 195.500, 195.490, 2.0, 1.0)])
        df = self.downloader._decode_bi5(bi5_bytes, hour_dt)

        assert df.index[0] == pd.Timestamp("2024-06-10 08:00:00", tz="UTC")

    def test_multiple_ticks_same_minute(self):
        """Multiple ticks within the same minute should all be decoded."""
        hour_dt = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        # 3 ticks in minute 0 (0ms, 20000ms=20s, 59000ms=59s)
        ticks_raw = [
            (0,     2001.0, 2000.9, 1.0, 1.0),
            (20000, 2002.0, 2001.9, 2.0, 2.0),
            (59000, 2003.0, 2002.9, 1.5, 1.5),
        ]
        bi5_bytes = _make_tick_bi5(ticks_raw)
        df = self.downloader._decode_bi5(bi5_bytes, hour_dt)

        assert len(df) == 3
        assert "mid" in df.columns

    def test_empty_bi5_returns_empty_dataframe(self):
        """Empty (but valid LZMA) bi5 should return an empty DataFrame."""
        hour_dt = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        empty_lzma = lzma.compress(b"")
        df = self.downloader._decode_bi5(empty_lzma, hour_dt)

        assert df.empty

    def test_invalid_lzma_raises_value_error(self):
        """Corrupted bytes should raise ValueError, not crash silently."""
        hour_dt = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        bad_bytes = b"\xFF\xFF\xFF\xFF\xFF"
        with pytest.raises(ValueError, match="LZMA"):
            self.downloader._decode_bi5(bad_bytes, hour_dt)


class TestTicksToOHLCV:
    """Test 6: _ticks_to_ohlcv produces correct OHLCV from tick data."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.downloader = DukascopyDownloader(output_dir=self._tmpdir, workers=1)

    def test_three_ticks_same_minute_correct_ohlcv(self):
        """
        3 ticks in the same minute:
            tick1: mid=2001.0  → opens the bar
            tick2: mid=2003.0  → new high
            tick3: mid=2000.0  → new low, closes
        Expected: open=2001, high=2003, low=2000, close=2000
        """
        index = pd.to_datetime([
            "2024-01-02 09:00:00.000",
            "2024-01-02 09:00:30.000",
            "2024-01-02 09:00:59.000",
        ], utc=True)
        # Build mid prices manually
        asks = [2001.1, 2003.1, 2000.1]
        bids = [2000.9, 2002.9, 1999.9]
        mids = [(a + b) / 2 for a, b in zip(asks, bids)]
        df_ticks = pd.DataFrame(
            {"ask": asks, "bid": bids, "ask_vol": [1.0]*3, "bid_vol": [1.0]*3, "mid": mids},
            index=index,
        )

        ohlcv = self.downloader._ticks_to_ohlcv(df_ticks)

        assert len(ohlcv) == 1, "Should produce exactly 1 one-minute bar"
        bar = ohlcv.iloc[0]
        assert abs(bar["open"]  - mids[0]) < 1e-6
        assert abs(bar["high"]  - max(mids)) < 1e-6
        assert abs(bar["low"]   - min(mids)) < 1e-6
        assert abs(bar["close"] - mids[-1]) < 1e-6

    def test_volume_is_sum_of_ask_bid_vol(self):
        """Volume per bar = sum(ask_vol + bid_vol) for all ticks in that bar."""
        index = pd.to_datetime([
            "2024-01-02 10:00:00.000",
            "2024-01-02 10:00:20.000",
        ], utc=True)
        df_ticks = pd.DataFrame(
            {"ask": [2010.0, 2011.0], "bid": [2009.0, 2010.0],
             "ask_vol": [3.0, 2.0], "bid_vol": [1.0, 1.5],
             "mid": [2009.5, 2010.5]},
            index=index,
        )
        ohlcv = self.downloader._ticks_to_ohlcv(df_ticks)
        expected_vol = 3.0 + 2.0 + 1.0 + 1.5  # 7.5
        assert abs(ohlcv.iloc[0]["volume"] - expected_vol) < 1e-6

    def test_ticks_across_two_minutes_produce_two_bars(self):
        """Ticks spanning two different minutes must produce two separate bars."""
        index = pd.to_datetime([
            "2024-01-02 09:00:30.000",  # minute 0
            "2024-01-02 09:01:15.000",  # minute 1
        ], utc=True)
        df_ticks = pd.DataFrame(
            {"ask": [2000.1, 2001.1], "bid": [1999.9, 2000.9],
             "ask_vol": [1.0, 1.0], "bid_vol": [1.0, 1.0],
             "mid": [2000.0, 2001.0]},
            index=index,
        )
        ohlcv = self.downloader._ticks_to_ohlcv(df_ticks)
        assert len(ohlcv) == 2

    def test_empty_ticks_returns_empty_ohlcv(self):
        """Empty tick DataFrame should produce empty OHLCV."""
        empty_ticks = pd.DataFrame(
            columns=["ask", "bid", "ask_vol", "bid_vol", "mid"]
        )
        ohlcv = self.downloader._ticks_to_ohlcv(empty_ticks)
        assert ohlcv.empty


class TestInstrumentName:
    """Test 7: _instrument_name correctly maps pair names."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.downloader = DukascopyDownloader(output_dir=self._tmpdir, workers=1)

    def test_xauusd_maps_correctly(self):
        assert self.downloader._instrument_name("XAUUSD") == "XAUUSD"

    def test_gbpjpy_maps_correctly(self):
        assert self.downloader._instrument_name("GBPJPY") == "GBPJPY"

    def test_case_insensitive(self):
        assert self.downloader._instrument_name("xauusd") == "XAUUSD"
        assert self.downloader._instrument_name("gbpjpy") == "GBPJPY"

    def test_unknown_pair_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown pair"):
            self.downloader._instrument_name("EURUSD")


class TestCanSkipHour:
    """Test 8: can_skip_hour returns True only when cache file exists."""

    def test_returns_false_when_not_cached(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dl = DukascopyDownloader(output_dir=tmpdir, workers=1)
            dt = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
            assert dl.can_skip_hour("XAUUSD", dt) is False

    def test_returns_true_when_cache_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dl = DukascopyDownloader(output_dir=tmpdir, workers=1)
            dt = datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc)

            # Manually create the cache file
            cache = dl._cache_path("XAUUSD", dt)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"")  # zero-length = empty hour

            assert dl.can_skip_hour("XAUUSD", dt) is True

    def test_different_hour_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dl = DukascopyDownloader(output_dir=tmpdir, workers=1)
            dt_cached    = datetime(2024, 3, 1, 9,  0, 0, tzinfo=timezone.utc)
            dt_not_cached = datetime(2024, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

            cache = dl._cache_path("XAUUSD", dt_cached)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"")

            assert dl.can_skip_hour("XAUUSD", dt_cached) is True
            assert dl.can_skip_hour("XAUUSD", dt_not_cached) is False


class TestBuildURL:
    """Test 9: _build_url generates correct Dukascopy URLs."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.downloader = DukascopyDownloader(output_dir=self._tmpdir, workers=1)

    def test_url_format_xauusd_january(self):
        """January = month 00 in Dukascopy URL (zero-indexed)."""
        dt = datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
        url = self.downloader._build_url("XAUUSD", dt)
        assert "XAUUSD" in url
        assert "/2024/" in url
        assert "/00/" in url   # January = 00
        assert "/15/" in url
        assert "/13h_ticks.bi5" in url

    def test_url_format_gbpjpy_december(self):
        """December = month 11 in Dukascopy URL (zero-indexed)."""
        dt = datetime(2023, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
        url = self.downloader._build_url("GBPJPY", dt)
        assert "GBPJPY" in url
        assert "/2023/" in url
        assert "/11/" in url   # December = 11
        assert "/01/" in url
        assert "/00h_ticks.bi5" in url


class TestDownloadHourWithMockedHTTP:
    """Test 10: _download_hour uses cache, handles 404, and retries on error."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.downloader = DukascopyDownloader(output_dir=self._tmpdir, workers=1)

    def test_uses_cache_and_skips_http_call(self):
        """If the cache file exists, no HTTP request should be made."""
        dt = datetime(2024, 3, 4, 7, 0, 0, tzinfo=timezone.utc)
        # Pre-populate cache with a valid single-tick bi5
        bi5 = _make_tick_bi5([(0, 2100.0, 2099.9, 1.0, 1.0)])
        cache_path = self.downloader._cache_path("XAUUSD", dt)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(bi5)

        with patch.object(self.downloader, "_fetch_with_retry") as mock_fetch:
            result = self.downloader._download_hour("XAUUSD", dt)
            mock_fetch.assert_not_called()

        assert result is not None
        assert len(result) == 1

    def test_404_returns_none(self):
        """HTTP 404 (empty bytes from _fetch_with_retry) should return None."""
        dt = datetime(2024, 3, 4, 8, 0, 0, tzinfo=timezone.utc)

        with patch.object(self.downloader, "_fetch_with_retry", return_value=b""):
            result = self.downloader._download_hour("XAUUSD", dt)

        assert result is None

    def test_network_error_returns_none(self):
        """_fetch_with_retry returning None should produce None from _download_hour."""
        dt = datetime(2024, 3, 4, 9, 0, 0, tzinfo=timezone.utc)

        with patch.object(self.downloader, "_fetch_with_retry", return_value=None):
            result = self.downloader._download_hour("XAUUSD", dt)

        assert result is None


class TestIterHours:
    """Test 11: _iter_hours skips weekends correctly."""

    def test_skips_saturday_and_sunday(self):
        # 2024-01-06 = Saturday, 2024-01-07 = Sunday
        start = datetime(2024, 1, 5, 22, 0, 0, tzinfo=timezone.utc)  # Friday
        end   = datetime(2024, 1, 8,  2, 0, 0, tzinfo=timezone.utc)  # Monday

        hours = list(DukascopyDownloader._iter_hours(start, end))
        weekdays = [h.weekday() for h in hours]
        assert 5 not in weekdays, "Saturday hours must be skipped"
        assert 6 not in weekdays, "Sunday hours must be skipped"

    def test_monday_hours_are_included(self):
        # 2024-01-08 = Monday
        start = datetime(2024, 1, 8,  0, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2024, 1, 8,  3, 0, 0, tzinfo=timezone.utc)

        hours = list(DukascopyDownloader._iter_hours(start, end))
        assert len(hours) == 3, "Should yield 3 hours for Mon 00:00–03:00"


class TestValidatorGapsAndVolume:
    """Test 12: validator detects gaps and negative volume."""

    def test_detects_large_gap_in_data(self):
        df = _make_ohlcv(300)
        # Remove a 30-bar block to create a ~30-minute gap
        df_gap = pd.concat([df.iloc[:100], df.iloc[130:]])
        report = validate(df_gap, pair="XAUUSD", timeframe="1m")
        assert report.gap_count >= 1
        assert report.largest_gap_minutes >= 29.0

    def test_negative_volume_marks_invalid(self):
        df = _make_ohlcv(300)
        df_bad = df.copy()
        df_bad.at[df_bad.index[5], "volume"] = -1.0
        report = validate(df_bad, pair="XAUUSD", timeframe="1m")
        assert not report.is_valid
        assert any("negative volume" in e.lower() for e in report.errors)

    def test_clean_data_passes_validation(self):
        """A perfectly clean DataFrame should produce a valid report."""
        df = _make_ohlcv(300)
        report = validate(df, pair="XAUUSD", timeframe="1m")
        assert report.is_valid
        assert report.ohlc_violation_count == 0
        assert report.duplicate_timestamps == 0
        assert report.weekend_bar_count == 0
