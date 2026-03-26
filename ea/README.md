# made. Expert Advisor — Installation Guide

The made. EA bridges the made. backend signal engine with your MetaTrader 4 or
MetaTrader 5 terminal running on an HFM account. It polls the backend for
confirmed signals, validates price, executes orders, manages 3-tier partial
closes, and reports outcomes back to the app.

## Files

| File | Platform | Notes |
|------|----------|-------|
| `made_EA_MT4.mq4` | MetaTrader 4 | For HFM MT4 accounts |
| `made_EA_MT5.mq5` | MetaTrader 5 | For HFM MT5 accounts |

---

## MT4 Installation

1. **Copy the file** — paste `made_EA_MT4.mq4` into:
   ```
   C:\Users\<YourName>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL4\Experts\
   ```
   Or use the MetaEditor shortcut: **File → Open Data Folder → MQL4 → Experts**.

2. **Compile** — Open `made_EA_MT4.mq4` in MetaEditor and press **F7**.
   The Toolbox at the bottom should show "0 errors".

3. **Attach to chart** — Open an XAUUSD or GBPJPY chart (any timeframe) and
   drag the EA from the Navigator panel onto the chart. Configure inputs:

   | Input | Default | Description |
   |-------|---------|-------------|
   | BackendURL | `http://localhost:8000` | made. API URL. Use server IP in production. |
   | MagicNumber | `20260101` | Must match the number in made. app settings. |
   | MaxSlippagePips | `2.0` | Reject orders where price moved more than this. |
   | EnableTrading | `true` | Set to `false` for monitor-only mode. |
   | EASecret | `ea-dev-secret` | Must match `EA_SECRET` env var on backend. |
   | PollIntervalSec | `5` | Seconds between backend polls. |

4. **Enable AutoTrading** — click the **AutoTrading** button in the MT4 toolbar
   (it should turn green). The EA will not place orders without this.

5. **Allow WebRequest** — go to:
   **Tools → Options → Expert Advisors → Allow WebRequest for listed URL**
   and add `http://localhost:8000` (or your backend URL).

---

## MT5 Installation

1. **Copy the file** — paste `made_EA_MT5.mq5` into:
   ```
   C:\Users\<YourName>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Experts\
   ```

2. **Compile** — open in MetaEditor, press **F7**. Zero errors required.

3. **Attach to chart** — same as MT4. Configure the same inputs.

4. **Enable AutoTrading** — same as MT4.

5. **Allow WebRequest** — same path as MT4 under Tools → Options.

---

## How It Works

1. Every `PollIntervalSec` seconds, the EA sends a GET request to
   `/broker/ea/pending?magic=<MagicNumber>`. The backend returns a JSON array
   of signals the user confirmed in the iOS app.

2. For each signal, the EA checks:
   - The signal's `pair` matches the chart symbol.
   - Current Ask/Bid is within `MaxSlippagePips` of `entry_price`.

3. If valid: market order is opened with SL = `sl`, TP = `tp1`.
   TP2 and TP3 levels are stored as MetaTrader GlobalVariables for the
   partial-close manager.

4. The EA POSTs the fill result to `/broker/ea/confirm`.

5. On each new bar, the partial-close manager:
   - **TP1 hit**: closes 40% of the position, moves SL to entry (breakeven).
   - **TP2 hit**: closes 50% of remaining, trails SL to TP1 price.
   - **TP3**: fully trailed — SL moves to TP2, let the remaining run.

6. TP hits are reported to `/broker/ea/tp_hit`. SL hits are reported to
   `/broker/ea/sl_hit` (which triggers automatic post-mortem in the app).

---

## Security Notes

- The `EASecret` input is sent as `X-EA-Secret` on every request. In production:
  - Keep the backend behind a firewall or VPN.
  - Use a strong random secret (32+ characters).
  - Set `EA_SECRET` as an environment variable on the server — never commit it.
- The EA never stores account credentials. MetaApi handles broker authentication
  separately on the backend.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "WebRequest not allowed" alert on attach | WebRequest URL not whitelisted | Add backend URL under Tools → Options → Expert Advisors |
| EA attached but no trades | AutoTrading disabled | Click the AutoTrading toolbar button (must be green) |
| Orders rejected with "price_deviation" | Market moved before EA executed | Increase `MaxSlippagePips` slightly, or widen validity window in app settings |
| EA shows in Experts tab but no logs | EnableLogging = false | Set `EnableLogging = true` in EA inputs |
| "Invalid EA secret" in backend logs | Mismatched secret | Ensure `EASecret` input matches `EA_SECRET` env var on backend |
