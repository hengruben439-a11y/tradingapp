"""
Shadow Mode Monitor — CLI dashboard for Phase 1.5 validation.

Reads reports/shadow_log.jsonl and reports GO/NO-GO status against
backtest targets. Supports filtering by pair and trading style.

Usage:
    python -m live.shadow_monitor
    python -m live.shadow_monitor --pair XAUUSD --style day_trading
    python -m live.shadow_monitor --log /path/to/shadow_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Backtest reference targets per (pair, style).
# GO/NO-GO checks are measured against these.
# Source: PRD §17.2 and Sprint 6 Go/No-Go table.
# ---------------------------------------------------------------------------
_BACKTEST_TARGETS: dict[tuple[str, str], dict] = {
    ("XAUUSD", "day_trading"):    {"tp1_win_rate": 0.60, "profit_factor": 1.4},
    ("XAUUSD", "scalping"):       {"tp1_win_rate": 0.62, "profit_factor": 1.4},
    ("XAUUSD", "swing_trading"):  {"tp1_win_rate": 0.60, "profit_factor": 1.4},
    ("GBPJPY", "day_trading"):    {"tp1_win_rate": 0.58, "profit_factor": 1.3},
    ("GBPJPY", "scalping"):       {"tp1_win_rate": 0.58, "profit_factor": 1.3},
    ("GBPJPY", "swing_trading"):  {"tp1_win_rate": 0.58, "profit_factor": 1.3},
}

# Minimum shadow signals required before a verdict can be issued
_MIN_SIGNALS_FOR_VERDICT = 50

# Shadow TP1 win rate must be >= backtest × this ratio (15% degradation allowed)
_DEGRADATION_TOLERANCE = 0.85

# Minimum acceptable profit factor in shadow mode
_MIN_PROFIT_FACTOR = 1.2

DEFAULT_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "reports", "shadow_log.jsonl"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ShadowStats:
    pair: Optional[str]
    style: Optional[str]
    total_signals: int = 0
    resolved_signals: int = 0
    tp1_hits: int = 0
    tp2_hits: int = 0
    tp3_hits: int = 0
    sl_hits: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    # Computed metrics
    tp1_win_rate: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    rolling_loss_rate: float = 0.0   # last 20 signals
    signal_frequency_per_day: float = 0.0
    backtest_degradation: float = 0.0  # shadow / backtest target ratio (1.0 = exact match)
    # Verdict
    go_no_go: str = "INSUFFICIENT_DATA"  # "GO" | "NO-GO" | "INSUFFICIENT_DATA"
    # Raw outcome history for rolling calcs
    _outcomes: list[str] = field(default_factory=list, repr=False)
    _timestamps: list[str] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class ShadowMonitor:
    """
    Reads shadow_log.jsonl, computes statistics, and prints a GO/NO-GO report.

    The JSONL file contains two record types written by ShadowRunner:
      - type "signal":  initial signal log entry (written on emission)
      - type "outcome": resolved entry appended when TP/SL is hit

    Only outcome records are used for win-rate and profit-factor calculations.
    Signal records are counted for total_signals and frequency.
    """

    def load_signals(self, log_path: str) -> list[dict]:
        """
        Load and parse all records from shadow_log.jsonl.

        Raises FileNotFoundError if the log does not exist.
        Returns an empty list if the log is empty.
        """
        if not os.path.exists(log_path):
            raise FileNotFoundError(
                f"Shadow log not found at {log_path!r}. "
                "Has the shadow runner produced any signals yet?"
            )

        records: list[dict] = []
        with open(log_path, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    # Log malformed lines but do not abort — partial writes can
                    # happen if the process was killed mid-write.
                    print(
                        f"[warn] Skipping malformed line {line_no} in shadow log: {exc}",
                        file=sys.stderr,
                    )
        return records

    def compute_stats(
        self,
        signals: list[dict],
        pair: Optional[str] = None,
        style: Optional[str] = None,
    ) -> ShadowStats:
        """
        Compute ShadowStats from raw log records.

        Args:
            signals:  List of dicts loaded from shadow_log.jsonl.
            pair:     Filter to this pair only (e.g. "XAUUSD"). None = all pairs.
            style:    Filter to this trading style (e.g. "day_trading"). None = all.

        Returns:
            ShadowStats dataclass with all metrics populated and go_no_go set.
        """
        stats = ShadowStats(pair=pair, style=style)

        # --- Filter records -----------------------------------------------
        filtered = signals
        if pair:
            filtered = [r for r in filtered if r.get("pair") == pair]
        if style:
            filtered = [r for r in filtered if r.get("style") == style]

        # Separate by record type
        signal_records = [r for r in filtered if r.get("type") != "outcome" and r.get("shadow")]
        outcome_records = [r for r in filtered if r.get("type") == "outcome"]

        stats.total_signals = len(signal_records)

        # Timestamps for frequency calculation
        stats._timestamps = [
            r["signal_time"] for r in signal_records if r.get("signal_time")
        ]

        # --- Outcome stats ------------------------------------------------
        consecutive = 0
        max_consecutive = 0

        for rec in outcome_records:
            outcome = rec.get("outcome", "")
            entry = float(rec.get("entry", 0) or 0)
            sl = float(rec.get("sl", 0) or 0)
            risk = abs(entry - sl) if entry and sl else 1.0

            stats.resolved_signals += 1
            stats._outcomes.append(outcome)

            if outcome == "TP1_HIT":
                stats.tp1_hits += 1
                tp_price = float(rec.get("tp1", entry) or entry)
                stats.gross_profit += abs(tp_price - entry)
                consecutive = 0
            elif outcome == "TP2_HIT":
                stats.tp2_hits += 1
                tp_price = float(rec.get("tp2", entry) or entry)
                stats.gross_profit += abs(tp_price - entry)
                consecutive = 0
            elif outcome == "TP3_HIT":
                stats.tp3_hits += 1
                tp_price = float(rec.get("tp3", entry) or entry)
                stats.gross_profit += abs(tp_price - entry)
                consecutive = 0
            elif outcome == "SL_HIT":
                stats.sl_hits += 1
                stats.gross_loss += risk
                consecutive += 1
                if consecutive > max_consecutive:
                    max_consecutive = consecutive

        stats.max_consecutive_losses = max_consecutive

        # Derived metrics
        if stats.resolved_signals > 0:
            stats.tp1_win_rate = round(stats.tp1_hits / stats.resolved_signals, 4)

        if stats.gross_loss > 0:
            stats.profit_factor = round(stats.gross_profit / stats.gross_loss, 4)
        elif stats.gross_profit > 0:
            stats.profit_factor = float("inf")
        else:
            stats.profit_factor = 0.0

        # Rolling loss rate: last 20 resolved signals
        recent = stats._outcomes[-20:]
        if recent:
            sl_recent = sum(1 for o in recent if o == "SL_HIT")
            stats.rolling_loss_rate = round(sl_recent / len(recent), 4)

        # Signal frequency: signals per calendar day
        stats.signal_frequency_per_day = self._compute_frequency(stats._timestamps)

        # Backtest degradation ratio
        target = self._get_target(pair, style)
        if target and target["tp1_win_rate"] > 0:
            stats.backtest_degradation = round(
                stats.tp1_win_rate / target["tp1_win_rate"], 4
            )

        # Verdict
        go, _ = self.check_go_no_go(stats)
        stats.go_no_go = "GO" if go is True else ("NO-GO" if go is False else "INSUFFICIENT_DATA")

        return stats

    def check_go_no_go(
        self, stats: ShadowStats
    ) -> tuple[Optional[bool], list[str]]:
        """
        Evaluate GO/NO-GO criteria.

        Returns:
            (verdict, reasons) where verdict is:
              True  — GO
              False — NO-GO
              None  — INSUFFICIENT_DATA
            reasons is a list of human-readable failure/pass strings.
        """
        reasons: list[str] = []

        # Gate: need minimum signals before any verdict
        if stats.resolved_signals < _MIN_SIGNALS_FOR_VERDICT:
            reasons.append(
                f"Only {stats.resolved_signals} resolved signals "
                f"(need >= {_MIN_SIGNALS_FOR_VERDICT} for verdict)"
            )
            return None, reasons

        # Check 1: TP1 win rate vs backtest target with tolerance
        target = self._get_target(stats.pair, stats.style)
        if target:
            min_allowed_wr = target["tp1_win_rate"] * _DEGRADATION_TOLERANCE
            if stats.tp1_win_rate >= min_allowed_wr:
                reasons.append(
                    f"TP1 win rate {stats.tp1_win_rate:.1%} >= minimum {min_allowed_wr:.1%} "
                    f"({_DEGRADATION_TOLERANCE:.0%} of backtest target {target['tp1_win_rate']:.1%})"
                )
            else:
                reasons.append(
                    f"FAIL — TP1 win rate {stats.tp1_win_rate:.1%} < minimum {min_allowed_wr:.1%} "
                    f"(backtest target {target['tp1_win_rate']:.1%})"
                )
                return False, reasons
        else:
            # No specific target: use absolute floor
            abs_floor = 0.50
            if stats.tp1_win_rate >= abs_floor:
                reasons.append(
                    f"TP1 win rate {stats.tp1_win_rate:.1%} >= absolute floor {abs_floor:.1%}"
                )
            else:
                reasons.append(
                    f"FAIL — TP1 win rate {stats.tp1_win_rate:.1%} < absolute floor {abs_floor:.1%}"
                )
                return False, reasons

        # Check 2: Profit factor
        if stats.profit_factor == float("inf") or stats.profit_factor >= _MIN_PROFIT_FACTOR:
            reasons.append(
                f"Profit factor {stats.profit_factor:.2f} >= minimum {_MIN_PROFIT_FACTOR:.2f}"
            )
        else:
            reasons.append(
                f"FAIL — Profit factor {stats.profit_factor:.2f} < minimum {_MIN_PROFIT_FACTOR:.2f}"
            )
            return False, reasons

        # Check 3: No catastrophic consecutive losses
        max_allowed_consec = 10
        if stats.max_consecutive_losses <= max_allowed_consec:
            reasons.append(
                f"Max consecutive losses {stats.max_consecutive_losses} <= {max_allowed_consec}"
            )
        else:
            reasons.append(
                f"FAIL — {stats.max_consecutive_losses} consecutive losses "
                f"(threshold: {max_allowed_consec})"
            )
            return False, reasons

        # All checks passed
        return True, reasons

    def print_report(self, stats: ShadowStats) -> None:
        """
        Print a formatted terminal report.

        Uses rich if available, falls back to plain ANSI text.
        """
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text
            self._print_rich(stats, Console())
        except ImportError:
            self._print_plain(stats)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_target(
        self, pair: Optional[str], style: Optional[str]
    ) -> Optional[dict]:
        if pair and style:
            return _BACKTEST_TARGETS.get((pair, style))
        return None

    @staticmethod
    def _compute_frequency(timestamps: list[str]) -> float:
        """Average signals per calendar day from ISO timestamp list."""
        if len(timestamps) < 2:
            return 0.0
        try:
            parsed = sorted(
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
                for ts in timestamps
            )
            span_days = (parsed[-1] - parsed[0]).total_seconds() / 86_400
            if span_days < 0.1:
                return 0.0
            return round(len(timestamps) / span_days, 2)
        except (ValueError, TypeError):
            return 0.0

    def _print_rich(self, stats: ShadowStats, console) -> None:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text

        # Header
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        filter_str = ""
        if stats.pair:
            filter_str += f"  Pair: {stats.pair}"
        if stats.style:
            filter_str += f"  Style: {stats.style}"

        verdict_color = {
            "GO": "bold green",
            "NO-GO": "bold red",
            "INSUFFICIENT_DATA": "bold yellow",
        }.get(stats.go_no_go, "white")

        console.print()
        console.print(
            Panel(
                f"[bold gold1]made.[/bold gold1] Shadow Mode Monitor — {now}{filter_str}",
                border_style="gold1",
            )
        )

        # Metrics table
        table = Table(show_header=True, header_style="bold dim", border_style="dim")
        table.add_column("Metric", style="dim", width=30)
        table.add_column("Value", justify="right", width=20)
        table.add_column("Target", justify="right", width=20)
        table.add_column("Status", justify="center", width=10)

        target = self._get_target(stats.pair, stats.style) or {}

        def status_icon(ok: bool) -> str:
            return "[green]PASS[/green]" if ok else "[red]FAIL[/red]"

        def fmt_pct(v: float) -> str:
            if v == float("inf"):
                return "inf"
            return f"{v:.1%}"

        def fmt_f(v: float, decimals: int = 2) -> str:
            if v == float("inf"):
                return "inf"
            return f"{v:.{decimals}f}"

        min_wr = target.get("tp1_win_rate", 0.50) * _DEGRADATION_TOLERANCE
        min_pf = _MIN_PROFIT_FACTOR

        table.add_row(
            "Total signals emitted",
            str(stats.total_signals),
            f">= {_MIN_SIGNALS_FOR_VERDICT}",
            status_icon(stats.total_signals >= _MIN_SIGNALS_FOR_VERDICT),
        )
        table.add_row(
            "Resolved (TP/SL hit)",
            str(stats.resolved_signals),
            f">= {_MIN_SIGNALS_FOR_VERDICT}",
            status_icon(stats.resolved_signals >= _MIN_SIGNALS_FOR_VERDICT),
        )
        table.add_row(
            "  TP1 hits",
            str(stats.tp1_hits),
            "",
            "",
        )
        table.add_row(
            "  TP2 hits",
            str(stats.tp2_hits),
            "",
            "",
        )
        table.add_row(
            "  TP3 hits",
            str(stats.tp3_hits),
            "",
            "",
        )
        table.add_row(
            "  SL hits",
            str(stats.sl_hits),
            "",
            "",
        )
        table.add_row(
            "TP1 win rate",
            fmt_pct(stats.tp1_win_rate),
            f">= {fmt_pct(min_wr)} (85% of {fmt_pct(target.get('tp1_win_rate', 0.50))})",
            status_icon(stats.tp1_win_rate >= min_wr) if stats.resolved_signals >= _MIN_SIGNALS_FOR_VERDICT else "[yellow]—[/yellow]",
        )
        table.add_row(
            "Profit factor",
            fmt_f(stats.profit_factor),
            f">= {min_pf:.2f}",
            status_icon(stats.profit_factor == float("inf") or stats.profit_factor >= min_pf) if stats.resolved_signals >= _MIN_SIGNALS_FOR_VERDICT else "[yellow]—[/yellow]",
        )
        table.add_row(
            "Max consecutive losses",
            str(stats.max_consecutive_losses),
            "<= 10",
            status_icon(stats.max_consecutive_losses <= 10),
        )
        table.add_row(
            "Rolling loss rate (last 20)",
            fmt_pct(stats.rolling_loss_rate),
            "< 50%",
            status_icon(stats.rolling_loss_rate < 0.50),
        )
        table.add_row(
            "Signal freq (per day)",
            fmt_f(stats.signal_frequency_per_day),
            "",
            "",
        )
        if stats.backtest_degradation > 0:
            table.add_row(
                "Backtest degradation ratio",
                fmt_f(stats.backtest_degradation),
                ">= 0.85",
                status_icon(stats.backtest_degradation >= _DEGRADATION_TOLERANCE),
            )

        console.print(table)

        # GO/NO-GO verdict
        console.print()
        verdict_panel = Panel(
            Text(f"  VERDICT: {stats.go_no_go}  ", justify="center", style=verdict_color),
            border_style=verdict_color.replace("bold ", ""),
        )
        console.print(verdict_panel)
        console.print()

    def _print_plain(self, stats: ShadowStats) -> None:
        """Fallback plain-text report when rich is not installed."""
        sep = "=" * 60
        print(sep)
        print("made. Shadow Mode Monitor")
        print(f"Pair: {stats.pair or 'ALL'}  |  Style: {stats.style or 'ALL'}")
        print(sep)
        print(f"Total signals emitted  : {stats.total_signals}")
        print(f"Resolved signals       : {stats.resolved_signals}")
        print(f"  TP1 hits             : {stats.tp1_hits}")
        print(f"  TP2 hits             : {stats.tp2_hits}")
        print(f"  TP3 hits             : {stats.tp3_hits}")
        print(f"  SL hits              : {stats.sl_hits}")
        tp1_str = f"{stats.tp1_win_rate:.1%}" if stats.resolved_signals else "n/a"
        pf_str = f"{stats.profit_factor:.2f}" if stats.profit_factor != float("inf") else "inf"
        print(f"TP1 win rate           : {tp1_str}")
        print(f"Profit factor          : {pf_str}")
        print(f"Max consecutive losses : {stats.max_consecutive_losses}")
        print(f"Rolling loss rate (20) : {stats.rolling_loss_rate:.1%}")
        print(f"Signal freq / day      : {stats.signal_frequency_per_day:.2f}")
        if stats.backtest_degradation > 0:
            print(f"Backtest degradation   : {stats.backtest_degradation:.3f}")
        print(sep)
        print(f"VERDICT: {stats.go_no_go}")
        print(sep)

        _, reasons = self.check_go_no_go(stats)
        for r in reasons:
            prefix = "  [PASS]" if "FAIL" not in r else "  [FAIL]"
            print(f"{prefix} {r}")
        print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="made. Shadow Mode Monitor — GO/NO-GO dashboard for Phase 1.5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--pair",
        choices=["XAUUSD", "GBPJPY"],
        default=None,
        help="Filter stats to a single pair",
    )
    parser.add_argument(
        "--style",
        choices=["scalping", "day_trading", "swing_trading", "position_trading"],
        default=None,
        help="Filter stats to a single trading style",
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG_PATH,
        help=f"Path to shadow_log.jsonl (default: {DEFAULT_LOG_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    monitor = ShadowMonitor()

    try:
        records = monitor.load_signals(args.log)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    stats = monitor.compute_stats(records, pair=args.pair, style=args.style)
    monitor.print_report(stats)

    # Exit with non-zero code when NO-GO so CI/scripts can detect failure
    if stats.go_no_go == "NO-GO":
        sys.exit(2)


if __name__ == "__main__":
    main()
