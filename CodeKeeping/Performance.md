# Performance Log

Backtest results, signal engine metrics, shadow mode outcomes, walk-forward validation, and live vs backtest comparisons.

## Format
```
### [DATE] — Run description (pair, style, period)
**Type:** Backtest | Shadow Mode | Live | Walk-Forward
**Config:** Pair, trading style, entry TF, HTF, date range
**Results:**
- TP1 Win Rate: X%
- TP2 Win Rate: X%
- Profit Factor: X.X
- Max Drawdown: X%
- Total Trades: N
- Avg R:R: X:X
- Monthly Return (avg): X%
**WFO Efficiency:** X (if applicable)
**GO/NO-GO:** GO | NO-GO | Conditional
**Notes:** Any anomalies, regime breakdown, module contribution highlights
```

---

## Targets Reference

| Metric | XAUUSD Min | GBPJPY Min |
|--------|-----------|-----------|
| TP1 Win Rate | >= 60% | >= 58% |
| Profit Factor | >= 1.4 | >= 1.3 |
| Max Drawdown | <= 15% | <= 18% |
| WFO Efficiency | >= 0.6 | >= 0.6 |
| Total Trades | >= 500 | >= 500 |
| Monthly Return | >= 3% | >= 2% |

---

## Log

