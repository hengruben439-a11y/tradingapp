"""
Backtest Report Generator — Sprint 1 scaffold, Sprint 6 full implementation.

Generates the official backtest report for each pair and trading style.

Report contents:
    - Executive summary: GO/NO-GO verdict with criteria table
    - Equity curve with drawdown overlay
    - Monthly P&L heatmap (months as columns, years as rows)
    - Win rate breakdown by: TP level, Kill Zone, day of week, news/no-news
    - Module contribution analysis
    - Trade duration distribution
    - Consecutive loss analysis
    - Risk-adjusted metrics: Sharpe, Sortino, Calmar
    - Walk-forward efficiency ratio (if WFO run)

Output formats:
    - JSON (for programmatic use / API)
    - HTML report (for browser viewing)
    - Console summary (for CI/terminal output)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from backtest.harness import BacktestResult
from backtest.metrics import BacktestMetrics, GONOGO_CRITERIA


class BacktestReporter:
    """
    Generates structured reports from backtest results.

    Usage:
        reporter = BacktestReporter(output_dir=Path("reports"))
        reporter.save(result, format="json")
        reporter.print_summary(result)
    """

    def __init__(self, output_dir: Path = Path("reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_summary(self, result: BacktestResult) -> None:
        """Print a formatted console summary of backtest results."""
        m = result.metrics
        cfg = result.config
        pair = cfg.pair
        criteria = GONOGO_CRITERIA.get(pair, {})

        print("\n" + "=" * 60)
        print(f"  BACKTEST RESULTS — {pair} / {cfg.trading_style.upper()}")
        print("=" * 60)
        print(f"  Period:        {result.start_date} → {result.end_date}")
        print(f"  Total Trades:  {m.total_trades}")
        print()
        print(f"  Win Rate (TP1): {m.win_rate_tp1:.1%}  "
              f"[target: >={criteria.get('win_rate_tp1', 0):.0%}]")
        print(f"  Win Rate (TP2): {m.win_rate_tp2:.1%}")
        print(f"  Win Rate (TP3): {m.win_rate_tp3:.1%}")
        print()
        print(f"  Profit Factor:  {m.profit_factor:.2f}  "
              f"[target: >={criteria.get('profit_factor', 0):.2f}]")
        print(f"  Max Drawdown:   {m.max_drawdown_pct:.1f}%  "
              f"[limit: <={criteria.get('max_drawdown_pct', 0):.0f}%]")
        print(f"  Avg R:R:        {m.average_rr:.2f}")
        print()
        print(f"  Sharpe:         {m.sharpe_ratio:.2f}")
        print(f"  Sortino:        {m.sortino_ratio:.2f}")
        print(f"  Calmar:         {m.calmar_ratio:.2f}")
        print()
        print(f"  Total P&L:      {m.total_pnl_pips:+.1f} pips  /  ${m.total_pnl_usd:+,.2f}")
        print(f"  Trades/Week:    {m.trades_per_week:.1f}")
        print()

        # GO/NO-GO verdict
        passes = m.passes_xauusd if pair == "XAUUSD" else m.passes_gbpjpy
        if passes is True:
            print("  ✓ GO — All criteria met. Proceed to Phase 2.")
        elif passes is False:
            print("  ✗ NO-GO — One or more criteria not met. Revise engine.")
        else:
            print("  ? Verdict not computed.")
        print("=" * 60 + "\n")

    def to_dict(self, result: BacktestResult) -> dict:
        """Serialize a BacktestResult to a plain dict (JSON-safe)."""
        m = result.metrics
        return {
            "pair": result.config.pair,
            "trading_style": result.config.trading_style,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "total_trades": m.total_trades,
            "win_rate_tp1": round(m.win_rate_tp1, 4),
            "win_rate_tp2": round(m.win_rate_tp2, 4),
            "win_rate_tp3": round(m.win_rate_tp3, 4),
            "win_rate_overall": round(m.win_rate_overall, 4),
            "profit_factor": round(m.profit_factor, 4),
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "max_drawdown_usd": round(m.max_drawdown_usd, 2),
            "sharpe_ratio": round(m.sharpe_ratio, 4),
            "sortino_ratio": round(m.sortino_ratio, 4),
            "calmar_ratio": round(m.calmar_ratio, 4),
            "average_rr": round(m.average_rr, 4),
            "total_pnl_pips": round(m.total_pnl_pips, 2),
            "total_pnl_usd": round(m.total_pnl_usd, 2),
            "trades_per_week": round(m.trades_per_week, 2),
            "max_consecutive_losses": m.max_consecutive_losses,
            "max_consecutive_wins": m.max_consecutive_wins,
            "passes": m.passes_xauusd if result.config.pair == "XAUUSD" else m.passes_gbpjpy,
            "monthly_pnl": m.monthly_pnl,
            "by_day_of_week": m.by_day_of_week,
            "by_kill_zone": m.by_kill_zone,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def save(
        self,
        result: BacktestResult,
        fmt: str = "json",
        filename: Optional[str] = None,
    ) -> Path:
        """
        Save the backtest report to disk.

        Args:
            result: BacktestResult to serialize.
            fmt: "json" (default) or "html" (Sprint 6 implementation).
            filename: Optional output filename. Auto-generated if None.

        Returns:
            Path to saved file.
        """
        if filename is None:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
            filename = f"{result.config.pair}_{result.config.trading_style}_{ts}.{fmt}"

        path = self.output_dir / filename

        if fmt == "json":
            data = self.to_dict(result)
            path.write_text(json.dumps(data, indent=2))
        elif fmt == "html":
            raise NotImplementedError("HTML report generation: implement in Sprint 6")
        else:
            raise ValueError(f"Unsupported format: {fmt!r}")

        return path

    def compute_wfo_efficiency(self, oos_results: list[BacktestResult]) -> float:
        """
        Compute the Walk-Forward Optimization efficiency ratio.

        WFO efficiency = avg OOS profit factor / avg IS profit factor
        Acceptance criterion: >= 0.6

        Sprint 6 implementation: requires IS results alongside OOS.
        For now, returns the average OOS profit factor directly.
        """
        if not oos_results:
            return 0.0
        pf_values = [r.metrics.profit_factor for r in oos_results if r.metrics.profit_factor < float("inf")]
        return sum(pf_values) / len(pf_values) if pf_values else 0.0
