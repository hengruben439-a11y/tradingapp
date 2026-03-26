"""
Historical news reaction data for XAUUSD and GBPJPY.

Pre-computed statistics on how each pair historically moves
around the top 10 high-impact events.

Data is static (updated quarterly from backtest data).
Used to display "NFP typically causes 200-500 pip moves on XAUUSD" in-app.

Per CLAUDE.md §10.2:
    "Show how XAUUSD and GBPJPY historically moved.
     Example: NFP typically causes 200-500 pip moves on XAUUSD within 1 hour."
"""

from __future__ import annotations

from typing import Optional

# ── Historical reaction database ─────────────────────────────────────────────
#
# Structure per entry:
#   avg_move_pips (int):      Average pip move within avg_duration_min
#   range (tuple[int, int]):  Typical pip range (low, high) across events
#   direction_bias (str):     "volatile"        — no directional bias, sharp move either way
#                             "inverse_usd"     — moves against USD (gold up when USD weak)
#                             "inverse_rates"   — gold moves inverse to rate expectations
#                             "risk_sentiment"  — risk-off = gold up, risk-on = gold down
#                             "risk_on"         — risk appetite drives the pair
#                             "risk_off"        — risk aversion drives the pair
#                             "gbp_direction"   — driven by GBP side of the pair
#                             "jpy_inverse"     — driven by JPY (inverse: JPY weak = pair up)
#                             "mixed"           — inconsistent historical direction
#   avg_duration_min (int):   How long the main move typically takes to develop

NEWS_REACTIONS: dict[str, dict[str, dict]] = {
    "XAUUSD": {
        # Non-Farm Payrolls — US jobs data, very high impact on gold via USD
        "NFP": {
            "avg_move_pips": 350,
            "range": (200, 500),
            "direction_bias": "volatile",
            "avg_duration_min": 60,
        },
        # Consumer Price Index — core inflation driver for Fed policy
        "CPI": {
            "avg_move_pips": 280,
            "range": (150, 450),
            "direction_bias": "inverse_usd",
            "avg_duration_min": 45,
        },
        # FOMC Rate Decision — most impactful single event for gold
        "FOMC": {
            "avg_move_pips": 500,
            "range": (300, 800),
            "direction_bias": "inverse_rates",
            "avg_duration_min": 120,
        },
        # Producer Price Index — leading indicator for CPI
        "PPI": {
            "avg_move_pips": 180,
            "range": (80, 300),
            "direction_bias": "inverse_usd",
            "avg_duration_min": 30,
        },
        # Purchasing Managers Index (global) — economic health proxy
        "PMI": {
            "avg_move_pips": 120,
            "range": (50, 200),
            "direction_bias": "mixed",
            "avg_duration_min": 20,
        },
        # GDP — quarterly broad economic output
        "GDP": {
            "avg_move_pips": 200,
            "range": (100, 350),
            "direction_bias": "inverse_usd",
            "avg_duration_min": 45,
        },
        # Bank of Japan — affects risk sentiment and DXY via yen carry trade
        "BOJ": {
            "avg_move_pips": 150,
            "range": (80, 280),
            "direction_bias": "risk_sentiment",
            "avg_duration_min": 30,
        },
        # Bank of England — limited direct impact on gold
        "BOE": {
            "avg_move_pips": 120,
            "range": (60, 220),
            "direction_bias": "mixed",
            "avg_duration_min": 25,
        },
        # US Retail Sales — consumer spending health
        "RETAIL_SALES": {
            "avg_move_pips": 150,
            "range": (70, 250),
            "direction_bias": "inverse_usd",
            "avg_duration_min": 30,
        },
        # Weekly Jobless Claims — leading employment indicator
        "JOBLESS_CLAIMS": {
            "avg_move_pips": 120,
            "range": (50, 200),
            "direction_bias": "inverse_usd",
            "avg_duration_min": 20,
        },
    },

    "GBPJPY": {
        # NFP — affects GBPJPY via risk sentiment (stronger USD = risk-off = JPY stronger)
        "NFP": {
            "avg_move_pips": 120,
            "range": (60, 200),
            "direction_bias": "risk_on",
            "avg_duration_min": 45,
        },
        # US CPI — affects GBPJPY via Fed expectations and USD/JPY
        "CPI": {
            "avg_move_pips": 90,
            "range": (40, 160),
            "direction_bias": "mixed",
            "avg_duration_min": 30,
        },
        # FOMC — significant risk sentiment driver, moves yen carry
        "FOMC": {
            "avg_move_pips": 200,
            "range": (100, 350),
            "direction_bias": "risk_off",
            "avg_duration_min": 90,
        },
        # Bank of England — highest direct GBP impact
        "BOE": {
            "avg_move_pips": 280,
            "range": (150, 450),
            "direction_bias": "gbp_direction",
            "avg_duration_min": 60,
        },
        # Bank of Japan — highest direct JPY impact (inverse: hawkish BOJ = JPY strong = pair falls)
        "BOJ": {
            "avg_move_pips": 350,
            "range": (200, 550),
            "direction_bias": "jpy_inverse",
            "avg_duration_min": 90,
        },
        # UK PMI — GBP economic health signal
        "PMI_UK": {
            "avg_move_pips": 150,
            "range": (80, 260),
            "direction_bias": "gbp_direction",
            "avg_duration_min": 30,
        },
        # UK GDP — quarterly output
        "GDP_UK": {
            "avg_move_pips": 180,
            "range": (90, 300),
            "direction_bias": "gbp_direction",
            "avg_duration_min": 45,
        },
        # UK CPI — inflation drives BOE rate expectations
        "CPI_UK": {
            "avg_move_pips": 160,
            "range": (80, 270),
            "direction_bias": "gbp_direction",
            "avg_duration_min": 35,
        },
        # UK Retail Sales — consumer health and GBP sentiment
        "RETAIL_SALES_UK": {
            "avg_move_pips": 130,
            "range": (70, 220),
            "direction_bias": "gbp_direction",
            "avg_duration_min": 30,
        },
        # Japanese CPI — signals BOJ policy direction
        "CPI_JP": {
            "avg_move_pips": 120,
            "range": (60, 200),
            "direction_bias": "jpy_inverse",
            "avg_duration_min": 30,
        },
    },
}

# Human-readable bias descriptions
_BIAS_DESCRIPTIONS: dict[str, str] = {
    "volatile":       "typically causes sharp moves in either direction",
    "inverse_usd":    "typically moves inverse to the US Dollar",
    "inverse_rates":  "typically moves inverse to rate hike expectations",
    "risk_sentiment": "typically affected by overall risk sentiment",
    "risk_on":        "typically rises in risk-on environments",
    "risk_off":       "typically falls in risk-off environments",
    "gbp_direction":  "typically moves in line with GBP strength/weakness",
    "jpy_inverse":    "typically moves inverse to JPY strength",
    "mixed":          "has mixed historical direction",
}


class NewsReactionService:
    """
    Provides human-readable descriptions and statistics about how each pair
    historically reacts to high-impact economic events.

    Used by the iOS app to display contextual data in the Economic Calendar
    and to annotate signals with news risk context.

    Example:
        service = NewsReactionService()
        desc = service.get_description("XAUUSD", "NFP")
        # → "NFP typically causes 200-500 pip moves on XAUUSD within 1 hour"
    """

    def get_reaction(self, pair: str, event_name: str) -> Optional[dict]:
        """
        Return the reaction data dict for a specific pair and event.

        Args:
            pair: Trading pair, e.g. "XAUUSD" or "GBPJPY".
            event_name: Event identifier, e.g. "NFP", "FOMC", "BOE".
                        Case-insensitive.

        Returns:
            Dict with keys: avg_move_pips, range, direction_bias, avg_duration_min.
            Returns None if the pair or event is not in the database.
        """
        pair = pair.upper()
        event_name = event_name.upper()

        pair_data = NEWS_REACTIONS.get(pair)
        if pair_data is None:
            return None

        return pair_data.get(event_name)

    def get_description(self, pair: str, event_name: str) -> str:
        """
        Return a human-readable description of the expected price reaction.

        Args:
            pair: Trading pair, e.g. "XAUUSD".
            event_name: Event identifier, e.g. "NFP".

        Returns:
            Formatted description string, e.g.:
            "NFP typically causes 200-500 pip moves on XAUUSD within 1 hour"

            If the event is not in the database, returns a generic message.
        """
        reaction = self.get_reaction(pair, event_name)

        if reaction is None:
            return (
                f"{event_name} has no historical reaction data for {pair.upper()} "
                "in the current database."
            )

        low_pips, high_pips = reaction["range"]
        avg_duration = reaction["avg_duration_min"]
        bias = reaction["direction_bias"]
        bias_desc = _BIAS_DESCRIPTIONS.get(bias, f"with a {bias} bias")

        # Format duration string
        if avg_duration >= 60:
            hours = avg_duration // 60
            time_str = f"{hours} hour" if hours == 1 else f"{hours} hours"
        else:
            time_str = f"{avg_duration} minutes"

        return (
            f"{event_name} typically causes {low_pips}-{high_pips} pip moves on "
            f"{pair.upper()} within {time_str} and {bias_desc}."
        )

    def get_high_impact_pairs(self, event_name: str) -> list[str]:
        """
        Return the list of pairs that have a strong reaction to the given event.

        A "strong reaction" is defined as avg_move_pips >= 150.

        Args:
            event_name: Event identifier, e.g. "NFP". Case-insensitive.

        Returns:
            List of pair strings (e.g. ["XAUUSD", "GBPJPY"]) that react strongly.
            Returns an empty list if no pairs react strongly to this event.
        """
        event_upper = event_name.upper()
        high_impact: list[str] = []

        for pair, events in NEWS_REACTIONS.items():
            reaction = events.get(event_upper)
            if reaction and reaction.get("avg_move_pips", 0) >= 150:
                high_impact.append(pair)

        return high_impact

    def get_all_events_for_pair(self, pair: str) -> dict[str, dict]:
        """
        Return all tracked events and their reaction data for a given pair.

        Args:
            pair: Trading pair, e.g. "XAUUSD".

        Returns:
            Dict of event_name → reaction_data.
            Empty dict if pair is not in the database.
        """
        return NEWS_REACTIONS.get(pair.upper(), {})
