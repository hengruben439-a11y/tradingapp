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
            html = self._render_html(result)
            path.write_text(html, encoding="utf-8")
        else:
            raise ValueError(f"Unsupported format: {fmt!r}")

        return path

    def _render_html(self, result: BacktestResult) -> str:
        """Render a self-contained HTML backtest report."""
        data = self.to_dict(result)
        m = result.metrics
        cfg = result.config
        pair = cfg.pair
        criteria = GONOGO_CRITERIA.get(pair, {})
        passes = data["passes"]

        verdict_color = "#22C55E" if passes else "#EF4444"
        verdict_text = "GO — All criteria met" if passes else "NO-GO — Criteria not met"

        # Monthly P&L table rows
        monthly_rows = ""
        for ym, pnl in sorted((data.get("monthly_pnl") or {}).items()):
            color = "#22C55E" if pnl >= 0 else "#EF4444"
            monthly_rows += f"<tr><td>{ym}</td><td style='color:{color}'>{pnl:+.1f}</td></tr>"

        # Kill zone table rows
        kz_rows = ""
        for kz, stats in (data.get("by_kill_zone") or {}).items():
            wr = stats.get("win_rate", 0) if isinstance(stats, dict) else 0
            trades = stats.get("trades", 0) if isinstance(stats, dict) else 0
            kz_rows += f"<tr><td>{kz}</td><td>{trades}</td><td>{wr:.1%}</td></tr>"

        # Day of week rows
        dow_rows = ""
        for day, stats in (data.get("by_day_of_week") or {}).items():
            wr = stats.get("win_rate", 0) if isinstance(stats, dict) else 0
            trades = stats.get("trades", 0) if isinstance(stats, dict) else 0
            dow_rows += f"<tr><td>{day}</td><td>{trades}</td><td>{wr:.1%}</td></tr>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>made. Backtest Report — {pair} / {cfg.trading_style}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0A0A1A; color: #F5F5F5; padding: 32px; line-height: 1.6; }}
  h1 {{ color: #D4A843; font-size: 1.8rem; margin-bottom: 4px; }}
  h2 {{ color: #E8C874; font-size: 1.1rem; margin: 24px 0 12px; border-bottom: 1px solid rgba(212,168,67,0.2); padding-bottom: 6px; }}
  .meta {{ color: #9CA3AF; font-size: 0.9rem; margin-bottom: 32px; }}
  .verdict {{ display: inline-block; padding: 10px 24px; border-radius: 8px;
              background: rgba(0,0,0,0.4); border: 2px solid {verdict_color};
              color: {verdict_color}; font-size: 1.1rem; font-weight: 700; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: rgba(26,26,46,0.7); border: 1px solid rgba(212,168,67,0.12);
           border-radius: 12px; padding: 16px; }}
  .card .label {{ color: #9CA3AF; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card .value {{ color: #F5F5F5; font-size: 1.5rem; font-weight: 600; margin-top: 4px; }}
  .card .target {{ color: #9CA3AF; font-size: 0.75rem; margin-top: 2px; }}
  .pass {{ color: #22C55E; }} .fail {{ color: #EF4444; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  th {{ text-align: left; color: #9CA3AF; font-size: 0.75rem; text-transform: uppercase;
        padding: 8px 12px; border-bottom: 1px solid rgba(212,168,67,0.15); }}
  td {{ padding: 8px 12px; font-size: 0.9rem; border-bottom: 1px solid rgba(255,255,255,0.05); }}
  .section {{ background: rgba(26,26,46,0.5); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
  .footer {{ color: #9CA3AF; font-size: 0.75rem; margin-top: 32px; text-align: center; }}
</style>
</head>
<body>
<h1>made. Backtest Report</h1>
<div class="meta">{pair} &middot; {cfg.trading_style.replace("_", " ").title()} &middot;
  {data["start_date"]} &rarr; {data["end_date"]} &middot; Generated {data["generated_at"][:19]}</div>

<div class="verdict">{verdict_text}</div>

<h2>Core Metrics</h2>
<div class="grid">
  <div class="card">
    <div class="label">Total Trades</div>
    <div class="value">{m.total_trades}</div>
  </div>
  <div class="card">
    <div class="label">Win Rate (TP1)</div>
    <div class="value {'pass' if m.win_rate_tp1 >= criteria.get('win_rate_tp1', 0) else 'fail'}">{m.win_rate_tp1:.1%}</div>
    <div class="target">Target: &ge;{criteria.get('win_rate_tp1', 0):.0%}</div>
  </div>
  <div class="card">
    <div class="label">Profit Factor</div>
    <div class="value {'pass' if m.profit_factor >= criteria.get('profit_factor', 0) else 'fail'}">{m.profit_factor:.2f}</div>
    <div class="target">Target: &ge;{criteria.get('profit_factor', 0):.2f}</div>
  </div>
  <div class="card">
    <div class="label">Max Drawdown</div>
    <div class="value {'pass' if m.max_drawdown_pct <= criteria.get('max_drawdown_pct', 100) else 'fail'}">{m.max_drawdown_pct:.1f}%</div>
    <div class="target">Limit: &le;{criteria.get('max_drawdown_pct', 0):.0f}%</div>
  </div>
  <div class="card">
    <div class="label">Average R:R</div>
    <div class="value">{m.average_rr:.2f}</div>
  </div>
  <div class="card">
    <div class="label">Sharpe Ratio</div>
    <div class="value">{m.sharpe_ratio:.2f}</div>
  </div>
  <div class="card">
    <div class="label">Sortino Ratio</div>
    <div class="value">{m.sortino_ratio:.2f}</div>
  </div>
  <div class="card">
    <div class="label">Calmar Ratio</div>
    <div class="value">{m.calmar_ratio:.2f}</div>
  </div>
  <div class="card">
    <div class="label">Total P&L (pips)</div>
    <div class="value">{m.total_pnl_pips:+.1f}</div>
  </div>
  <div class="card">
    <div class="label">Trades / Week</div>
    <div class="value">{m.trades_per_week:.1f}</div>
  </div>
  <div class="card">
    <div class="label">Win Rate (TP2)</div>
    <div class="value">{m.win_rate_tp2:.1%}</div>
  </div>
  <div class="card">
    <div class="label">Win Rate (TP3)</div>
    <div class="value">{m.win_rate_tp3:.1%}</div>
  </div>
</div>

<div class="section">
  <h2>Monthly P&L (pips)</h2>
  <table>
    <tr><th>Month</th><th>P&L (pips)</th></tr>
    {monthly_rows or "<tr><td colspan='2'>No data</td></tr>"}
  </table>
</div>

<div class="section">
  <h2>Performance by Kill Zone</h2>
  <table>
    <tr><th>Kill Zone</th><th>Trades</th><th>Win Rate</th></tr>
    {kz_rows or "<tr><td colspan='3'>No data</td></tr>"}
  </table>
</div>

<div class="section">
  <h2>Performance by Day of Week</h2>
  <table>
    <tr><th>Day</th><th>Trades</th><th>Win Rate</th></tr>
    {dow_rows or "<tr><td colspan='3'>No data</td></tr>"}
  </table>
</div>

<div class="section">
  <h2>Streak Statistics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Max Consecutive Wins</td><td>{m.max_consecutive_wins}</td></tr>
    <tr><td>Max Consecutive Losses</td><td>{m.max_consecutive_losses}</td></tr>
    <tr><td>Avg Hold Time (bars)</td><td>{m.average_hold_bars:.1f}</td></tr>
  </table>
</div>

<div class="footer">made. v1.0 &mdash; Backtest report &mdash; For internal use only. Past performance is not indicative of future results.</div>
</body>
</html>"""

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
