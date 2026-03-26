"""
Kill Zone Timing Module — Weight: 5% (XAU + GJ)

Session-based probability scoring. Kill Zones are defined windows where
institutional activity is highest and setups have better follow-through.

UTC reference (authoritative):
    Asian (GBPJPY):     00:00–02:00 UTC
    Shanghai Open (XAU): 00:15–02:15 UTC  [precedence if both apply]
    London:             07:00–10:00 UTC
    New York:           13:00–16:00 UTC
    London Close:       15:00–17:00 UTC   [retracement / counter-trend]

Sprint 5 deliverable: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Optional

import pandas as pd
import yaml


@dataclass
class KillZone:
    name: str
    pair: str            # "XAUUSD" | "GBPJPY" | "ALL"
    utc_start: time      # UTC start time
    utc_end: time        # UTC end time
    score: float         # Directional score boost (in trend direction)
    is_counter_trend: bool  # True for London Close (retracement)


# Hard-coded reference Kill Zones (config/kill_zones.yaml is the canonical source)
_KILL_ZONES: list[KillZone] = [
    KillZone("Asian",         "GBPJPY", time(0, 0),  time(2, 0),  0.3,  False),
    KillZone("Shanghai_Open", "XAUUSD", time(0, 15), time(2, 15), 0.6,  False),
    KillZone("London",        "ALL",    time(7, 0),  time(10, 0), 0.8,  False),
    KillZone("New_York",      "ALL",    time(13, 0), time(16, 0), 1.0,  False),
    KillZone("London_Close",  "ALL",    time(15, 0), time(17, 0), 0.5,  True),
]

# Multiplier values
KZ_ACTIVE_MULTIPLIER = 1.05
KZ_OUTSIDE_MULTIPLIER = 0.95


class KillZoneModule:
    """
    Determines if the current bar falls within a Kill Zone and scores accordingly.

    Direction is provided externally (from MarketStructureModule HTF state).

    Score logic:
        Asian KZ:        +0.3 (moderate, lower volatility)
        Shanghai KZ:     +0.6 (PBOC, SGE physical demand drivers)
        London KZ:       +0.8 (high probability trend initiation)
        New York KZ:     +1.0 (highest volatility, confirms London)
        London Close KZ: +0.5 in counter-trend direction (retracement)
        Outside all KZs: -0.3 (penalty, not disqualification)

    Usage:
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(bar_timestamp)
        score = module.score(is_bullish_trend=True)
    """

    def __init__(self, pair: str):
        self.pair = pair
        self._active_kz: Optional[KillZone] = None
        self._current_utc_time: Optional[time] = None

    def update_bar(self, bar_timestamp: datetime) -> None:
        """
        Determine which (if any) Kill Zone is active at the given bar timestamp.
        bar_timestamp should be UTC-aware or will be converted to UTC.

        Sprint 5 implementation notes:
        - Convert bar_timestamp to UTC
        - Check each KZ; for XAUUSD prefer Shanghai_Open over Asian
        - Handle overnight spans (if utc_start > utc_end, zone spans midnight)
        - Set self._active_kz
        """
        raise NotImplementedError("Implement in Sprint 5")

    def score(self, is_bullish_trend: bool) -> float:
        """
        Return directional score based on active Kill Zone.

        Args:
            is_bullish_trend: True = bullish HTF trend; False = bearish.
                              Used to determine sign of counter-trend KZ scores.

        Returns:
            float in [-1.0, +1.0]
        """
        raise NotImplementedError("Implement in Sprint 5")

    @property
    def active_kill_zone(self) -> Optional[KillZone]:
        """Return the currently active Kill Zone or None."""
        return self._active_kz

    @property
    def active_kz_name(self) -> Optional[str]:
        """Return name of active KZ or None."""
        return self._active_kz.name if self._active_kz else None

    def get_multiplier(self) -> float:
        """
        Return the KZ multiplier for use in the confluence aggregator.
        Active KZ: 1.05x. No active KZ: 0.95x.
        """
        return KZ_ACTIVE_MULTIPLIER if self._active_kz else KZ_OUTSIDE_MULTIPLIER

    def _is_time_in_zone(self, current: time, start: time, end: time) -> bool:
        """
        Check if current time falls within [start, end).
        Handles overnight spans (e.g., 23:00–01:00 UTC).
        """
        if start <= end:
            return start <= current < end
        # Overnight span
        return current >= start or current < end

    def _get_applicable_zones(self) -> list[KillZone]:
        """Filter Kill Zones applicable to this module's pair."""
        return [kz for kz in _KILL_ZONES if kz.pair in (self.pair, "ALL")]
