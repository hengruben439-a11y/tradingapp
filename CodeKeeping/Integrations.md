# Integrations Log

Third-party API setup notes, credentials placeholders, service configuration, and gotchas discovered during integration.

> **Security:** Never log actual API keys or passwords here. Use placeholders and reference your secrets manager or .env file.

## Format
```
### [SERVICE NAME]
**Status:** Not Started | Configured | Tested | Live
**Account/Plan:** Free | Paid | Enterprise
**Auth Method:** API Key | OAuth | JWT | Webhook
**Env Var:** `ENV_VAR_NAME` (stored in .env)
**Notes:** Any rate limits, quirks, version pins, or integration gotchas
**Docs:** URL
```

---

## Services

### OANDA (Primary Market Data)
**Status:** Not Started
**Account/Plan:** Practice → Live
**Auth Method:** API Key (Bearer token)
**Env Var:** `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`
**Notes:** Supports 1-min historical back to 2005. REST + streaming. Free tier available. Check rate limits for historical pulls (500 candles per request max). Streaming feed for live data.
**Docs:** https://developer.oanda.com/rest-live-v20/introduction/

### Twelve Data (Secondary/Failover Market Data)
**Status:** Not Started
**Account/Plan:** Free → Basic
**Auth Method:** API Key
**Env Var:** `TWELVE_DATA_API_KEY`
**Notes:** Automatic failover when OANDA heartbeat missed for 2x expected interval. Check free tier rate limits — may need paid plan for 1-min data at required frequency.
**Docs:** https://twelvedata.com/docs

### TradingEconomics (Economic Calendar — Primary)
**Status:** Not Started
**Account/Plan:** Paid required for real-time
**Auth Method:** API Key
**Env Var:** `TRADING_ECONOMICS_API_KEY`
**Notes:** Returns actual/forecast/previous values and importance ratings. Used for signal suppression 15 min pre / 5 min post high-impact events.
**Docs:** https://docs.tradingeconomics.com

### JBlanked News API (Economic Calendar — Fallback)
**Status:** Not Started
**Account/Plan:** TBD
**Auth Method:** API Key
**Env Var:** `JBLANKED_API_KEY`
**Notes:** Forex Factory-compatible. ML-predicted impact. Used only when TradingEconomics is unavailable.

### MetaApi (HFM MT4/MT5 Broker Bridge)
**Status:** Not Started
**Account/Plan:** Paid (per connected account ~$5-15/month)
**Auth Method:** MetaApi token
**Env Var:** `META_API_TOKEN`
**Notes:** Test with HFM demo account in Sprint 13 (Week 29) before live. Supports investor-password (read-only) and trade-password (execution). Validate connectivity before building full execution flow.
**Docs:** https://metaapi.cloud/docs/

### Supabase (Database)
**Status:** Not Started
**Account/Plan:** Free → Pro
**Auth Method:** Supabase service role key (server-side); anon key (client-side)
**Env Var:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`
**Notes:** Managed PostgreSQL with RLS, auth, real-time subscriptions, and auto-generated REST API. Redis still needed separately for engine state checkpointing (requires <10ms latency).

### Apple Push Notification Service (APNS)
**Status:** Not Started
**Account/Plan:** Apple Developer Program ($99/year)
**Auth Method:** APNs Auth Key (.p8 file) or Certificate
**Env Var:** `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`
**Notes:** Use token-based auth (.p8) — certificates expire annually. Required for signal alerts, TP/SL hits, news countdowns.

### Telegram Bot API
**Status:** Not Started
**Account/Plan:** Free
**Auth Method:** Bot token (from @BotFather)
**Env Var:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`
**Notes:** Register bot via @BotFather. Set up webhook endpoint on FastAPI server. Rich message formatting with MarkdownV2.

