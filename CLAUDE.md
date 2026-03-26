# made. — Project Context

---

## PRODUCT REQUIREMENTS DOCUMENT

**made.**

Intelligent Trading Signal & Analysis Platform

XAUUSD · GBPJPY

Version 1.0 | March 2026 | Confidential

### 1. Executive Summary

made. is an intelligent trading signal and analysis platform designed to replace unreliable copy-trading services with a transparent, multi-layered confluence-based signal engine. The platform serves beginner-to-intermediate traders who want actionable buy/sell signals with clearly defined entry, take-profit (3 levels), and stop-loss levels for XAUUSD (Gold) and GBPJPY.

The signal engine fuses ICT Smart Money Concepts (Order Blocks, Fair Value Gaps, Change of Character, Break of Structure, Optimal Trade Entry, Kill Zones) with classical technical analysis (RSI, MACD, Bollinger Bands, EMA 20/50/100/200, Fibonacci, ATR) through a weighted confluence scoring system that adapts to timeframe and trading style.

The app delivers signals via iOS mobile app, Telegram bot, and push notifications. It integrates with HFM broker via MT4/MT5 Expert Advisors for confirmation-based trade execution. An economic calendar with countdown timers (defaulting to SGT/UTC+8) provides news event awareness with historical impact data for XAUUSD and GBPJPY.

**MVP Priority: Signal Accuracy**

Phase 1 focuses entirely on building and backtesting the confluence scoring engine against 5 years of data (2021-2026) before investing in UI polish or secondary features.

### 2. Product Vision & Problem Statement

#### 2.1 Vision

To become the most trusted, transparent, and beginner-friendly trading signal platform globally — one that replaces the predatory copy-trading industry with honest, data-driven analysis that educates as it signals.

#### 2.2 Problem

The retail trading signal space is dominated by scams: fake Telegram groups showing manipulated screenshots, copy-trading services with hidden fees, and black-box algorithms with unverifiable track records. Beginners lose money not because the market is impossible, but because they lack a reliable, educational tool that shows them why a trade makes sense — not just what to trade.

#### 2.3 Solution

made. provides transparent, confluence-scored signals where every recommendation shows exactly which indicators aligned, what the confidence level is, and why the trade setup exists. Each signal is an education moment, not a blind instruction.

### 3. Target Users & Personas

| Persona | Description | Needs |
|---------|-------------|-------|
| The Burned Beginner | Traded for 6-18 months, lost money with copy-trading services, still motivated to learn | Reliable signals with education on WHY, risk management guidance, honest track record |
| The Self-Taught Trader | Watches YouTube, understands basics of TA, but struggles with consistency and discipline | Confluence confirmation of their own analysis, structured approach, trade journal |
| The Busy Professional | Has capital but not time, wants a trusted assistant that flags setups during their schedule | Push notifications, clear entry/exit levels, news awareness, quick-glance signals |

### 4. Technical Architecture

#### 4.1 System Overview

| Component | Technology |
|-----------|-----------|
| Mobile App (iOS → Android) | React Native with dark glassmorphism design system (enables Android reuse in Phase 5) |
| Backend API | Python FastAPI on AWS with WebSocket for real-time signals (same language as engine = simpler stack) |
| Signal Engine | Python (pandas, numpy, numba, ta-lib) running on server, processing candle data every bar close. Hot paths optimized with Numba/Cython. |
| Market Data (Primary) | OANDA REST API for OHLCV (reliable, well-documented, supports 1-min historical) |
| Market Data (Secondary) | Twelve Data API as automatic failover. If primary hasn't sent data in 2x expected interval, switch to secondary. Pause signal generation if both feeds are down. |
| Economic Calendar | TradingEconomics API (primary) + JBlanked News API (fallback) |
| Broker Integration | MQL4/MQL5 Expert Advisors for HFM MT4/MT5 via MetaApi cloud REST API |
| Notifications | Apple Push Notification Service (APNS) + Telegram Bot API |
| Database | Supabase (managed PostgreSQL) for user data, trade journal, signal history — provides auth, RLS, real-time subscriptions, and auto-generated REST API. Redis for engine state checkpointing and live signal caching (requires <10ms latency, beyond Supabase real-time scope). |
| Backtesting | Python vectorbt framework against 5 years of 1-min OHLCV data |
| State Persistence | Engine state (market structure FSM, active OBs, FVGs, swing points) serialized to Redis on every bar close. On restart, rebuild from last checkpoint or replay from recent candle history (minimum 200 bars per TF to warm up EMA 200). |

#### 4.2 Data Flow

1. Market Data Provider streams OHLCV candles to the Signal Engine at each bar close for all active timeframes. Dual-feed architecture monitors primary (OANDA) and secondary (Twelve Data) sources with heartbeat detection and automatic failover.
2. Signal Engine runs the Confluence Scoring Pipeline: Regime detection > ICT analysis > Classical TA analysis > Multi-Timeframe alignment check > News proximity filter > Final score calculation. HTF analysis is pre-computed on bar close and cached (it doesn't change mid-bar); only entry-TF modules run on each new bar.
3. If confluence score exceeds threshold, a Signal Object is created with entry price, 3 TP levels, SL level, confidence score, rationale breakdown, and module dissent flags.
4. Signal Object is pushed to: (a) iOS app via WebSocket, (b) Push notification, (c) Telegram bot channel.
5. User reviews signal in-app, optionally taps Confirm which sends the order to their linked MT4/MT5 account via MetaApi (or Paper Trading account for simulation).
6. Trade is logged in the journal with entry, management, and eventual outcome. If SL is hit, auto-generated post-mortem identifies which module failed and why.

**Latency Budget (target <2s end-to-end, <1s at 12 months):**

| Step | Target | Notes |
|------|--------|-------|
| Data arrival to engine | <100ms | WebSocket feed |
| HTF cache lookup | <10ms | Pre-computed on HTF bar close |
| 9 modules on entry TF | <300ms | Numba-optimized hot paths |
| TP/SL calculation | <50ms | Structural lookup + ATR |
| Score aggregation + regime check | <20ms | Simple math |
| WebSocket push to app | <100ms | Local server → client |
| APNS + Telegram push | <500ms | Network-dependent, async |

### 5. Signal Engine: Confluence Scoring System

#### 5.1 Philosophy

No single indicator is reliable on its own. The made. engine uses a weighted confluence model where multiple independent analysis methods must agree before a signal is generated. The system is designed to be conservative — it is better to miss a trade than to signal a bad one.

#### 5.2 Confluence Score Calculation

Each analysis module produces a directional score between -1.0 (strong sell) and +1.0 (strong buy). These are weighted and summed into a final Confluence Score. Base module scores are capped at 0.85 maximum to reserve headroom for confluence bonuses, which are applied as multipliers (not additive) to preserve score distribution integrity. Note: individual module specs may define raw scores up to +1.0 — these are pre-cap values. The aggregator applies the 0.85 cap before weighting. Module unit tests should validate pre-cap output values.

| Module | XAU Wt. | GJ Wt. | Logic |
|--------|---------|--------|-------|
| Market Structure (CHoCH/BOS) | 25% | 25% | Identifies trend direction via structural breaks |
| Order Blocks + FVGs | 20% | 18% | Detects institutional entry zones |
| OTE Fibonacci (61.8%-78.6%) | 15% | 15% | Confirms entry in discount/premium zone |
| EMA Alignment (20/50/100/200) | 10% | 12% | Trend confirmation via EMA stacking |
| RSI (14) | 8% | 8% | Overbought/oversold + divergence detection |
| MACD (12,26,9) | 7% | 7% | Momentum via histogram and crossovers |
| Bollinger Bands (20,2) | 5% | 5% | Volatility context and squeeze detection |
| Kill Zone Timing | 5% | 5% | Session-based probability boost |
| S&R / Liquidity Levels | 5% | 5% | Key swing highs/lows, equal highs/lows |

**Confluence Bonus System (Multipliers, not additive):**
- ICT Unicorn Setup (OB + FVG overlap): 1.10x multiplier on pre-clamp score
- OTE + OB within zone: 1.08x multiplier
- OTE + FVG within zone: 1.06x multiplier
- Kill Zone active: 1.05x multiplier (already factored into KZ module score direction)
- Outside all Kill Zones: 0.95x multiplier
- Day-of-week modifier: derived from walk-forward backtest per-pair day performance data (e.g., if Friday scalping on XAU has <50% win rate historically, apply 0.90x penalty). Default to 1.0x until backtest data confirms pair-specific values. Store in `/config/day_of_week_modifiers.yaml`. Recalibrate quarterly using the rolling 6-month backtest window.

#### 5.3 Signal Thresholds

| Score Range | Strength | Label | Action |
|-------------|----------|-------|--------|
| 0.80 to 1.00 | Very Strong | Strong Buy/Sell | Full signal + alert |
| 0.65 to 0.79 | Strong | Buy/Sell | Full signal + alert |
| 0.50 to 0.64 | Moderate | Lean Buy/Sell | Signal shown, no push alert |
| 0.30 to 0.49 | Weak | Watch | Displayed as idea only (free tier) |
| < 0.30 | No Signal | Neutral | No signal generated |

#### 5.3.1 Confidence Decay

Signals lose relevance over time. The displayed confluence score decays proportionally from generation time to expiry using:

`displayed_score = base_score × (1 - 0.25 × elapsed_fraction)`

where `elapsed_fraction` = elapsed_time / expiry_window (0 → 1). This applies a 25% total reduction by window end. Examples: a 0.80 signal shows 0.80×0.875 = **0.70** at 50% elapsed; a 0.65 signal shows 0.65×0.775 = **0.50** at 90% elapsed; a 0.50 signal shows **0.44** at 50% elapsed. If the decayed score falls below 0.50, the signal is visually dimmed and marked "Fading." If it falls below 0.30, it is auto-expired.

#### 5.4 Higher-Timeframe Conflict Handling

When the selected timeframe and the HTF produce opposing signals, made. displays both signals side-by-side with a Conflicting Bias warning badge. The app provides a template-based analysis explaining the conflict, drawn from ~15 pre-written conflict patterns (e.g., "The 4H timeframe shows bullish structure (BOS confirmed) while the Daily is still bearish (below EMA 200). This suggests a counter-trend move that may have limited upside."). Template-based analysis is faster and more reliable than LLM calls for a core feature; LLM-powered analysis is deferred to Phase 5. The lower-timeframe signal confidence score is automatically reduced by 15-25% when it conflicts with HTF bias.

### 6. ICT Smart Money Concepts Integration

#### 6.1 Order Blocks (OB)

Detection: Identify the last opposing candle before a displacement move (3+ ATR candle). A bullish OB is the last bearish candle before a strong bullish move. Validation requires: the OB must have caused a break of structure, left an imbalance (FVG), remain unmitigated (price has not returned to it yet), and the displacement candle must have above-average tick volume (filters false OBs where price moved on low participation).

#### 6.2 Fair Value Gaps (FVG)

Detection: Three-candle pattern where Candle 1 high does not overlap Candle 3 low (bullish) or Candle 1 low does not overlap Candle 3 high (bearish). The engine tracks: FVG creation, partial fill, full fill, and FVG inversion. Confluence boost: 1.10x multiplier when FVG overlaps with an Order Block (ICT Unicorn setup).

#### 6.3 Change of Character (CHoCH) / Break of Structure (BOS)

BOS: Price breaks a recent swing high (bullish) or swing low (bearish) in the direction of the existing trend — confirms continuation. CHoCH: Price breaks a swing point against the prevailing trend — signals potential reversal. The engine tracks market structure on each active timeframe independently and uses HTF structure as primary directional bias.

#### 6.4 Optimal Trade Entry (OTE)

After identifying a dealing range, the Fibonacci retracement is applied. The OTE zone is between 61.8% and 78.6% retracement (0.618–0.786), with 70.5% as the sweet spot. The engine scores entries higher when price retraces into OTE and finds confluence with an Order Block or FVG within that zone. Stop loss: 10-20 pips beyond the 100% retracement level.

#### 6.5 Kill Zones (Session Timing)

**GBPJPY Kill Zones:**

| Kill Zone | EST Time | SGT Time (UTC+8) | Character |
|-----------|----------|-------------------|-----------|
| Asian | 7:00 PM - 9:00 PM | 8:00 AM - 10:00 AM | Range-bound, scalping |
| London | 2:00 AM - 5:00 AM | 3:00 PM - 6:00 PM | High volume, trend start |
| New York | 8:00 AM - 11:00 AM | 9:00 PM - 12:00 AM | Highest volatility |
| London Close | 10:00 AM - 12:00 PM | 11:00 PM - 1:00 AM | Retracement, closing |

**XAUUSD Kill Zones (pair-specific — gold is driven by US rates, DXY, risk sentiment):**

| Kill Zone | EST Time | SGT Time (UTC+8) | Character |
|-----------|----------|-------------------|-----------|
| Shanghai Open | 8:15 PM - 10:15 PM | 9:15 AM - 11:15 AM | PBOC fixing, SGE activity, Asian physical demand |
| London | 2:00 AM - 5:00 AM | 3:00 PM - 6:00 PM | Institutional volume, trend initiation |
| New York | 8:00 AM - 11:00 AM | 9:00 PM - 12:00 AM | Highest volatility, US data releases |
| London Close | 10:00 AM - 12:00 PM | 11:00 PM - 1:00 AM | Retracement, profit-taking |

Kill Zone confluence is applied as a multiplier: active KZ = 1.05x, outside all KZs = 0.95x.

#### 6.6 Kill Zone UTC Reference (Authoritative)

All engine code uses UTC exclusively. EST times assume non-DST (UTC-5); adjust by +1h during EDT (UTC-4, March–November). The §5.1 Kill Zone module uses the UTC values below as the single source of truth.

| Kill Zone | UTC (non-DST) | Pairs | Notes |
|-----------|--------------|-------|-------|
| Asian | 00:00–02:00 | Both | Range-bound, lower volatility |
| Shanghai Open | 00:15–02:15 | XAUUSD only | PBOC fixing, SGE physical demand — starts 15 min into Asian |
| London | 07:00–10:00 | Both | Institutional volume, trend initiation |
| New York | 13:00–16:00 | Both | Highest volatility, US data releases |
| London Close | 15:00–17:00 | Both | Retracement, profit-taking |

Note: Shanghai Open overlaps with Asian; for XAUUSD during 00:15–02:00 UTC, use the Shanghai Open score (+0.6) which takes precedence over the generic Asian score (+0.3).

### 7. Classical Technical Analysis Layer

#### 7.1 EMA Stack (20/50/100/200)

The engine tracks EMA alignment across 20, 50, 100, and 200 periods. A perfect bullish stack (20 > 50 > 100 > 200 with price above all) scores +1.0. Partial alignment scores proportionally. Golden Cross (50 EMA above 200) and Death Cross (50 below 200) generate additional bias signals. Price position relative to the 200 EMA is the macro trend filter.

#### 7.2 RSI (14-period)

Standard RSI with overbought at 70 and oversold at 30. The engine also detects RSI divergence: price makes higher high but RSI makes lower high (bearish), or price makes lower low but RSI makes higher low (bullish). Divergence signals carry higher weight than simple OB/OS readings. For scalping (1m/5m), thresholds shift to 65/35.

#### 7.3 MACD (12, 26, 9)

Buy on MACD crossing above signal line, confirmed by histogram turning positive. Sell on inverse. Prioritizes crossovers near zero line (stronger momentum shifts) over those far from zero. MACD histogram divergence also tracked as a leading indicator.

#### 7.4 Bollinger Bands (20, 2)

Primary use: volatility context and squeeze detection. When BB width contracts to 20-period low, a squeeze is flagged. The engine does NOT use band touches as standalone signals. BB squeeze + directional breakout + MACD confirmation = valid signal. Band width also used to adjust ATR-based SL/TP distances.

#### 7.5 Fibonacci Retracement

Applied to most recent significant swing. Key levels: 38.2%, 50%, 61.8%, 70.5%, 78.6%. Boosts confluence when Fib levels align with Order Blocks, FVGs, or S&R levels.

#### 7.6 ATR (14-period)

Used for: (a) dynamic SL/TP calculation, (b) volatility normalization, (c) displacement detection (candle > 2x ATR = displacement). ATR adapts per pair — XAUUSD typically has 2-5x the ATR of forex majors.

**ATR Normalization (critical for XAUUSD):** Gold moved from ~$1800 (2021) to ~$3000+ (2025-2026), so absolute ATR values changed dramatically. All ATR-based thresholds (displacement detection, FVG minimums, SL buffers) must be expressed as a percentage of price or as ATR percentile relative to its own 50-period rolling average — NOT as fixed pip/dollar values. Fixed SL buffers ($0.50-$2.00) should be replaced with 0.03%-0.07% of price. This ensures the engine behaves consistently across the full 5-year backtest window despite gold's 60%+ price increase.

### 7.7 Market Regime Detection (Filter, not scored module)

Markets alternate between trending and ranging regimes. The confluence engine uses fixed weights regardless of regime, which generates false signals during ranges. A regime classifier gates signal generation.

**Classification Method:**
- ADX(14) > 25 = TRENDING regime
- ADX(14) < 20 = RANGING regime
- ADX(14) 20-25 = TRANSITIONAL (use caution)
- Secondary confirmation: Bollinger Band width vs 50-period BB width MA — squeeze = ranging, expansion = trending

**Regime Impact on Signals:**
- TRENDING: Normal signal generation, standard thresholds
- RANGING: Increase confluence threshold from 0.50 to 0.70 for Moderate signals, suppress trend-following setups, reduce signal frequency. Only mean-reversion setups (RSI oversold at support, BB lower band bounce) are valid.
- TRANSITIONAL: Flag all signals with "Regime Uncertain" badge, reduce confidence by 10%

Regime is assessed on both entry TF and HTF. If regimes conflict (entry TF trending, HTF ranging), apply the more conservative interpretation.

### 8. Multi-Timeframe Analysis & Trading Styles

#### 8.1 User-Selected Trading Style

The user manually selects their preferred trading style. Each style adjusts signal parameters, TP/SL ratios, and which timeframes are analyzed.

| Style | Entry TF | HTF Bias TFs | Min R:R | Hold Time |
|-------|----------|-------------|---------|-----------|
| Scalping | 1m, 5m | 15m, 1H | 1:1.5 | 1-30 min |
| Day Trading | 15m, 30m | 1H, 4H | 1:2 | 1-8 hours |
| Swing Trading | 1H, 4H | 1D, 1W | 1:3 | 1-14 days |
| Position Trading | 1D | 1W, 1M | 1:4 | 2-12 weeks |

#### 8.2 Top-Down Analysis Flow

Step 1 - HTF Bias: Determine overall market direction from two higher timeframes using market structure (CHoCH/BOS) and EMA 200 position. Step 2 - Entry TF Setup: Look for confluence of ICT + classical TA on entry timeframe in HTF direction. Step 3 - Entry Trigger: Price must enter a zone of interest (OB, FVG, OTE) and show a reaction before generating signal.

#### 8.3 UI Complexity Modes

The app has three UI modes, selectable in Settings. Default on first launch: **Simple**. Mode persists per user account and can be changed at any time. Mode is separate from subscription tier — it controls information density, not feature access.

| Mode | Target User | Subscription Gate |
|------|------------|-----------------|
| Simple | Beginners — first 6-18 months of trading | All tiers |
| Pro | Intermediate — understands TA, wants full context | Premium + Pro |
| Max | Expert — needs raw data, custom controls, advanced analytics | Pro only |

**Simple Mode:**
- Shows top 1-2 highest-confidence signals per day only (Beginner Focus)
- Signal card: pair flag, direction (BUY / SELL in large text), entry price, TP1, SL — nothing else
- Confidence displayed as plain-English label only: "Very Strong", "Strong", "Moderate"
- All contextual tooltips visible by default (no need to long-press — always shown inline)
- Risk calculator simplified: one risk % slider, shows only dollar risk and lot size
- No module breakdown, no regime badge, no dissent section
- Economic calendar shows only High-impact events (filters Medium/Low)
- Journal shows P&L, direction, pair — no module attribution
- Onboarding quiz on first launch to confirm beginner profile
- After 7 days, if user consistently taps "View Analysis" on signal cards → suggest upgrading to Pro mode

**Pro Mode:**
- All active signals across selected timeframes and pairs
- Signal card: full entry + TP1/TP2/TP3 + SL with R:R displayed
- Module dissent bars: horizontal bar chart, color-coded (green=aligned, red=opposing, amber=neutral)
- Confluence score as percentage with animated confidence ring
- Regime badge: TRENDING / RANGING / TRANSITIONAL
- News risk badge when within 15 min of high-impact event
- Conflict warning: HTF vs LTF disagreement badge with template-based explanation
- Full risk calculator: balance input, risk % slider, live lot size, margin estimate, pip value display
- Economic calendar: all impact levels, historical reaction data shown on event expand
- Journal: full P&L with module contribution and post-mortem on SL hit

**Max Mode (Pro subscribers only):**
- Everything in Pro, plus:
- Raw module scores visible on signal detail (e.g., "Market Structure: +0.85 | OB/FVG: +0.70 | RSI: -0.40")
- Signal decay timer: live countdown showing elapsed/expiry and real-time decayed score
- HTF conflict side-by-side: both timeframe signals displayed in a split card with crossover annotations
- Advanced journal analytics: Sharpe ratio, Sortino ratio, Calmar ratio, rolling win rate chart
- In-app backtest report access: view historical 5-year backtest equity curve, MDD chart, monthly heatmap
- Signal filtering panel: filter active signals by Kill Zone, pair, setup type (OB/FVG/OTE/BOS/CHoCH)
- CSV export: journal history, signal log, and performance metrics
- Parameter visibility: expandable section on signal card showing which ATR period, FVG min size, and swing N were used for that signal's timeframe
- Custom risk parameters: extend risk % range to 0.1–5% in 0.1% steps; set per-pair daily loss limits

#### 8.4 Timeframe-Specific Parameters

| Parameter | 1m/5m | 15m/30m | 1H/4H | 1D | 1W |
|-----------|-------|---------|-------|-----|-----|
| RSI OB/OS | 65/35 | 70/30 | 70/30 | 75/25 | 80/20 |
| Min OB candles | 1 | 2 | 3 | 5 | 10 |
| ATR period | 10 | 14 | 14 | 14 | 14 |
| FVG min size | 0.5x ATR | 0.75x ATR | 1x ATR | 1.5x ATR | 2x ATR |
| Signal expiry | 5 bars | 8 bars | 12 bars | 5 bars | 3 bars |

### 9. TP/SL Hybrid Calculation Engine

The TP/SL system uses a hybrid approach combining ATR-based dynamic levels with structural levels (S&R, OBs, liquidity zones).

#### 9.1 Stop Loss Calculation

Primary: Place SL beyond the nearest structural invalidation point. Validation: SL must be 1-3x ATR from entry. If structural SL is beyond 3x ATR, signal is downgraded. Buffer: Add 5-10 pips (GBPJPY) or 0.03%-0.07% of price (XAUUSD — percentage-based to handle $1800-$3000+ price range) beyond structural level for stop hunt protection.

#### 9.2 Take Profit Levels (3-Tier)

| TP | Calculation | Purpose | Close % |
|----|------------|---------|---------|
| TP1 | Nearest S&R or 1:1 R:R | Lock in profit, move SL to BE | 40% |
| TP2 | Next S&R, opposing OB, or 1:2 R:R | Core profit, trail SL to TP1 | 30% |
| TP3 | Major liquidity level, FVG fill, or 1:3 R:R | Aspirational, fully trailed SL | 30% |

The hybrid selects the most conservative TP1 and most ambitious TP3, ensuring minimum R:R of 1:1.5 for scalping and 1:2 for other styles.

### 10. Economic Calendar & News Integration

#### 10.1 Data Sources

Primary: TradingEconomics API - real-time calendar with actual/forecast/previous values and importance ratings. Secondary: JBlanked News API (Forex Factory-compatible) - event history, ML predictions, price action data.

#### 10.2 Features

**Daily Rundown:** Every day at 6:00 AM SGT, push summary of high-impact events with SGT times, pairs affected, and expected impact.

**Countdown Timers:** Cascading alerts at 1 hour, 30 min, 15 min, 5 min, and 1 min before high-impact events.

**Historical Reaction Data:** Show how XAUUSD and GBPJPY historically moved. Example: NFP typically causes 200-500 pip moves on XAUUSD within 1 hour.

**Signal Suppression:** 15 min before and 5 min after high-impact news: active signals flagged with News Risk badge, no new signals generated.

**Timezone:** Default SGT (UTC+8). Swappable to EST, GMT, or auto-detect local timezone.

#### 10.3 Key Events Tracked

| Event | Frequency | XAU Impact | GJ Impact |
|-------|-----------|-----------|-----------|
| NFP (Non-Farm Payrolls) | Monthly | Very High | High |
| CPI (Consumer Price Index) | Monthly | Very High | High |
| FOMC Rate Decision | 8x/year | Extreme | Very High |
| PPI (Producer Price Index) | Monthly | High | Medium |
| PMI (Purchasing Managers) | Monthly | Medium | High (UK) |
| BOE Rate Decision | 8x/year | Low | Extreme |
| BOJ Rate Decision | 8x/year | Low | Extreme |
| GDP Releases | Quarterly | High | High |
| Geopolitical Events | Ongoing | Extreme | High |

### 11. Risk Management Module

Every signal includes a built-in risk calculator in USD denomination.

#### 11.1 Lot Size Calculator

Inputs: Account Balance (USD), Risk % (default 1%, range 0.5-5%), SL Distance (auto from signal), Pair. Output: Lot size, dollar risk, margin required. Formula: Lot Size = (Balance x Risk %) / (SL pips x Pip Value). Display: Risking 1% of $10,000 = $100.00 > 0.15 lots on XAUUSD with 65-pip SL.

**Pip Value Reference (per standard lot, USD account):**

| Pair | Pip Definition | Pip Value (1 std lot) | Notes |
|------|---------------|----------------------|-------|
| XAUUSD | $0.01 price move (2nd decimal) | $1.00/pip | 100 oz × $0.01 = $1 |
| GBPJPY | 0.01 JPY move (2nd decimal) | ~$9–10/pip | (0.01 / USDJPY) × 100,000 — dynamic, recalculate at signal time |

For GBPJPY, fetch the current USDJPY rate at signal time to compute live pip value. Use $9.50 as a default fallback if rate is unavailable.

#### 11.2 Correlation Warnings & Net Exposure Tracking

When both pairs have active signals, the app checks for risk sentiment conflicts. XAUUSD buy (risk-off) + GBPJPY buy (risk-on) triggers a warning. DXY strength/weakness monitored as meta-indicator.

**Net Directional Exposure:** Track total dollar exposure across all active signals. If 3 active gold signals and 3 active GJ signals all go the same direction, the user is effectively 6x leveraged on a single macro thesis. If total exposure exceeds 4% of account, suppress new signals regardless of individual signal quality.

#### 11.3 Exposure Limits & Drawdown Circuit Breakers

| Limit | Threshold | Action |
|-------|-----------|--------|
| Max simultaneous signals | 3 per pair | Suppress new signals for that pair |
| Max daily risk | 3% of account | Suppress all signals for remainder of day |
| Max weekly drawdown | 6% of account | Suppress all signals for remainder of week |
| Max monthly drawdown | 10% of account | Enter "Recovery Mode" — reduce risk per trade to 0.5%, show only Very Strong signals (>0.80) |
| Adaptive risk scaling | At 5% DD from peak | Auto-reduce risk from 1% to 0.5% per trade until equity recovers |

#### 11.4 Context-Aware Cooldown Mode

The simple "2 consecutive losses = 2 hour cooldown" is replaced with intelligent cooldown:

- **News-attributed losses:** If both losses occurred within 15 minutes of a high-impact news event, attribute to news volatility — no cooldown, but suppress signals for the remainder of the news window.
- **Setup-pattern losses:** If both losses occurred on the same Kill Zone + same setup type (e.g., London OB buy), flag that specific pattern and suppress it for 24 hours. Other setups remain active.
- **Rolling loss rate:** Track losses per last N signals (N=10). If rolling loss rate exceeds 50%, enter cooldown regardless of consecutive count. Cooldown duration: 4 hours (not 2).
- **Encouragement UX:** During cooldown, show the user their long-term equity curve, historical recovery times from similar drawdowns, and educational content. Avoid making cooldown feel punitive.

### 12. Trade Journal & Performance Tracking

#### 12.1 Auto-Logged Data

Each entry records: timestamp, pair, timeframe, style, direction, entry/SL/TP prices, confluence score, contributing indicators, actual exit, P&L (USD + pips), R:R achieved, hold duration, news activity flag, and user notes.

#### 12.2 Analytics Dashboard

Win rate by pair, timeframe, style, and day of week. Profit factor, average R:R, best/worst sessions, equity curve, streak tracking, and monthly P&L summary.

### 13. Broker Integration (HFM MT4/MT5)

#### 13.1 Architecture

Integration via MetaApi cloud REST API connecting to HFM MT4 and MT5 servers. Supports all HFM account types. Uses investor-password access for monitoring and trade-password for execution.

#### 13.2 Paper Trading Mode (Available from Phase 2)

Before broker integration, users can practice with simulated capital:
- Virtual account with configurable starting balance (default $10,000)
- Takes signals with simulated execution at current market price + realistic spread
- Full P&L tracking, equity curve, and journal — identical to live mode
- Serves as: (a) safe onboarding for beginners, (b) live forward-test of engine, (c) user confidence builder before going live
- Paper trades are clearly marked in the journal and analytics (never mixed with live)

#### 13.3 Execution Flow (Confirmation Mode)

1. Signal fires with validity window (entry is valid if price is still within 0.5x ATR of signal entry price).
2. User reviews details, risk, and module dissent flags.
3. User taps Confirm Trade (or selects Limit Order at signal entry price as alternative to market order).
4. App validates current price is within acceptable slippage tolerance (configurable, default 1x ATR).
5. App sends order via MetaApi to HFM. Order includes symbol, direction, lot size, entry type, SL, TP1.
6. If requote/rejection: retry once at current price if still within validity window, else abort and notify user.
7. If partial fill: accept partial, adjust TP/SL lot sizes proportionally, notify user.
8. App monitors and notifies at each TP hit and SL hit.
9. All execution data logged to journal (including signal price vs fill price slippage).

#### 13.4 Custom Expert Advisor

Custom EA provided that: receives webhooks from made. backend, validates signal against current price (rejects if moved >1 ATR), executes with slippage tolerance, manages partial closes at TP levels, and confirms back to app. Free download for premium users.

### 14. Notification & Alert System

| Alert Type | Channels | Content |
|-----------|----------|---------|
| New Signal | Push + TG + In-App | Pair, Direction, Entry, SL, TPs, Confidence, Rationale |
| TP Hit | Push + In-App | TP level hit, P&L, suggestion for remaining position |
| SL Hit | Push + In-App | P&L, auto-generated post-mortem (see 14.2) |
| News Alert | Push + In-App | Event, impact, countdown, pairs affected |
| Daily Rundown | Push + Telegram | Day events summary, active signals, market bias |
| Conflict Warning | In-App | Both directions with HTF/LTF analysis |
| Cooldown Mode | Push + In-App | Encouragement to step away, daily stats |

#### 14.2 Signal Failure Post-Mortem (auto-generated on SL hit)

Every stopped-out signal generates a structured post-mortem:
- **Which module was wrong:** Identify the strongest module that voted in the signal direction but was invalidated (e.g., "Order Block was mitigated — price swept through the zone")
- **What happened:** Was it a news event? A structural break on HTF? A liquidity grab? Cross-reference with economic calendar and HTF market structure changes.
- **Lesson:** One-sentence takeaway for the user (e.g., "This OB buy was invalidated by a bearish CHoCH on the 4H timeframe 30 minutes after entry — HTF structure shifted against the trade.")
- Post-mortems are logged in the journal and accessible from the signal history card.

#### 14.3 Telegram Bot

Built from scratch via Telegram Bot API. Features: dedicated signal channel, personal DM alerts, inline buttons (View in App, Skip), rich formatting with pair, direction, levels, confidence.

### 15. UI/UX Design System: Dark Glassmorphism

#### 15.1 Design Philosophy

made. rejects the typical trading terminal aesthetic. It uses Dark Glassmorphism — warm dark backgrounds with frosted glass card layers, gold/amber accents, and soft ambient gradients — creating an interface that feels premium and calming. The goal: a luxury fintech product, not a 2010 forex dashboard.

#### 15.2 Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Background Deep | #0A0A1A | App base, deepest layer |
| Background Card | #1A1A2E / rgba(26,26,46,0.7) | Glass card surfaces with backdrop-blur |
| Ambient Gradient | #2D1B4E to #1A0A2E | Deep purple orbs behind glass |
| Gold Primary | #D4A843 | Logo, active states, CTA buttons |
| Gold Light | #E8C874 | Hover states, highlights, confidence bars |
| Buy Signal | #22C55E | Green for buy, profit indicators |
| Sell Signal | #EF4444 | Red for sell, loss indicators |
| Text Primary | #F5F5F5 | Main content (high contrast) |
| Text Secondary | #9CA3AF | Labels, timestamps |
| Glass Border | rgba(212,168,67,0.15) | Subtle gold-tinted card borders |

#### 15.3 Glass Card CSS

```css
background: rgba(26,26,46,0.6);
backdrop-filter: blur(20px) saturate(150%);
border: 1px solid rgba(212,168,67,0.12);
border-radius: 20px;
box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05);
```

#### 15.4 Key Screens

**Home / Signal Dashboard:** Active signals as glass cards with pair, direction, confidence bubble (animated gold ring), entry/SL/TP, and expandable View Analysis section.

**Signal Detail:** Each indicator contribution as horizontal bar chart in glass panel, color-coded: green for modules aligned with signal direction, red for modules opposing, amber for neutral. A "Dissent" section highlights opposing modules (e.g., "RSI (8% weight) opposes this signal — asset is in overbought territory"). Mini chart showing setup. TP/SL visually marked. Contextual tooltips on every element. Confidence decay indicator shows time remaining before signal fades.

**Economic Calendar:** Timeline with glass event cards. High-impact events pulse with gold glow. Countdown as circular progress rings. Color-coded by impact.

**Trade Journal:** Card-based history with P&L color coding. Tap to expand. Analytics with glass-panel charts.

**Risk Calculator:** Interactive sliders for balance and risk %. Real-time lot size. Prominent display of dollar risk amount.

### 16. Education & Contextual Tooltips

made. teaches as it signals. Every element has a contextual tooltip triggered by long-press or ? icon.

#### 16.1 Tooltip Examples

**On Order Block:** An Order Block is a zone where big institutions placed large orders before a strong price move. Price often returns to these zones. Learn more on Investopedia.

**On RSI: 28.5:** RSI below 30 means the asset is oversold - sellers are exhausted and buyers may step in. This supports a potential buy.

**On Confidence Score:** This shows how many of our 9 analysis modules agree on this direction. 82% means strong alignment across methods.

#### 16.2 External Links

Each tooltip links to relevant Investopedia articles. For ICT concepts without Investopedia coverage, links go to curated YouTube explanations or Babypips.

### 17. Backtesting Framework & Expected Performance

#### 17.1 Methodology

Period: January 2021 - March 2026. Data: 1-minute OHLCV from Dukascopy (primary) validated against OANDA (secondary) for price accuracy. Higher TFs resampled from 1-min with documented timezone alignment (4H candles start at 00:00, 04:00, 08:00... UTC — must match HFM MT4/MT5 server time for candle boundaries; misalignment silently corrupts all HTF analysis).

**Execution Model (critical):** All backtests use NEXT-BAR-OPEN execution — signals generated at bar close are executed at the OPEN of the following bar + spread. This prevents look-ahead bias and typically reduces performance by 5-10% vs signal-bar execution, but gives honest results that match live trading.

**Dynamic Spread Model (replaces flat spread):**

| Condition | XAUUSD Spread | GBPJPY Spread |
|-----------|--------------|--------------|
| London/NY active hours | 2 pips | 3 pips |
| Asian session | 4 pips | 4 pips |
| First 5 min of high-impact news (NFP, FOMC, CPI) | 15 pips | 10 pips |
| Low liquidity (holidays, rollovers) | 6 pips | 5 pips |

Additional realistic assumptions: 50ms latency, 1-pip slippage, 0 commission. Each signal also logs price-at-signal-time vs price-at-execution-time to measure realized slippage.

#### 17.2 Realistic Performance Targets

| Metric | XAUUSD Target | GBPJPY Target |
|--------|--------------|--------------|
| Win Rate (TP1 hit) | 62-68% | 58-65% |
| Win Rate (TP2 hit) | 45-55% | 42-50% |
| Win Rate (TP3 hit) | 30-40% | 28-35% |
| Average R:R Achieved | 1:1.8 - 1:2.2 | 1:1.6 - 1:2.0 |
| Profit Factor | 1.4 - 1.8 | 1.3 - 1.6 |
| Max Drawdown | 8-15% | 10-18% |
| Signals/week (Day Trading) | 8-15 | 6-12 |
| Monthly return (1% risk) | 4-8% | 3-7% |

#### 17.3 Why These Numbers Are Honest

The best quant funds operate with 50-65% win rates and 1.3-2.0 profit factors. A retail system with 62-68% TP1 win rate and 1.4-1.8 profit factor is genuinely excellent. This honesty separates made. from scam services claiming 90%+ win rates.

#### 17.4 Backtest Report Format

Each run produces: total trades, win/loss/BE counts, equity curve, monthly P&L table, drawdown chart, best/worst trades, average hold time, performance by session, and performance during news vs normal. Reports published in-app for transparency.

### 18. Regulatory Compliance & Disclaimers

made. is an informational/educational tool, not a licensed financial advisor or broker.

#### 18.1 Required Disclaimers

*Trading foreign exchange and CFDs carries a high level of risk and may not be suitable for all investors. Past performance is not indicative of future results. made. provides algorithmic analysis and educational information only. It does not constitute financial advice. Never trade with money you cannot afford to lose.*

#### 18.2 Regulatory Considerations

Review compliance with: MAS (Singapore), FCA (UK), and global fintech regulations before Phase 3 launch. The execution feature may require registration in certain jurisdictions.

### 19. Monetization Strategy

#### 19.1 Unit Economics (must validate before launch)

| Cost Category | Estimated Monthly Cost | Notes |
|--------------|----------------------|-------|
| AWS infrastructure (compute, DB, Redis) | $200-500 | Scales with users; baseline for engine + API |
| OANDA market data API | $0-100 | Free tier may suffice initially |
| TradingEconomics API | $50-100 | Calendar data |
| MetaApi (broker connections) | $5-15 per connected account | Scales linearly with Pro users |
| APNS + Telegram | ~$0 | Minimal per-message cost |
| Total fixed costs | ~$350-700/month | Before any users |
| Per-user variable cost | ~$1-3/month (Free/Premium), $6-18/month (Pro with MetaApi) | |

**Break-even analysis:** At $49/month Premium and $99/month Pro, break-even at ~15-20 paid users. At 500 paid users (12-month target), monthly revenue of $25K-50K with healthy margins.

**Comparable pricing:** Signal services typically charge $30-100/month. made. differentiates on transparency and education, justifying mid-to-upper range.

#### 19.2 Tier Structure

| Tier | Features | Price |
|------|----------|-------|
| Free | Limited confluence ideas (score shown but no entry/TP/SL levels), calendar, tooltips, 1H only, paper trading | Free |
| Premium | Full signals all TFs, 3 TP/SL, push + TG alerts, journal with post-mortems, risk calc, news data, Focus Mode, paper trading | $49/month or $399/year |
| Pro | Premium + broker execution, EA, API access, priority signal delivery (<500ms), advanced analytics, historical backtest reports | $99/month or $799/year |

Annual pricing at ~32% discount incentivizes commitment and reduces churn.

#### 19.3 Churn Prevention & Retention Strategy

Signal services have notoriously high churn — users subscribe during hot streaks and cancel after drawdowns. made. builds retention into the product:

- **Long-term equity curve:** Prominently displayed on dashboard (not just recent P&L) so users see the full picture during losing streaks
- **Education stickiness:** Users stay for learning, not just signals. Contextual tooltips, post-mortems, and module dissent analysis build skills over time
- **Monthly performance reports:** Automated email/push showing how the system recovered from historical drawdowns similar to the current one
- **Streak gamification:** Longest winning streak, best R:R achieved, journal consistency badge, monthly learning milestones
- **Drawdown communication:** When system enters drawdown, proactively message users: "This is normal. Here's how similar periods resolved historically." Transparency builds trust.

### 20. Development Roadmap

Phase 1: Signal Engine MVP (Months 1-3) — Build confluence scoring engine in Python. Implement all 9 modules + regime detection. Backtest against 5 years of data with next-bar-open execution and dynamic spreads. Optimize weights with Optuna. Walk-forward validation per trading style.

Phase 1.5: Shadow Mode Validation (Month 4) — Deploy engine on live data for 4 weeks. Log all signals but show them to nobody. Compare shadow signals against actual market outcomes. This catches look-ahead bias, data snooping, and regime changes that backtesting cannot. GO/NO-GO for Phase 2 based on shadow mode results within 15% of backtest performance.

Phase 2: iOS App + Telegram (Months 5-8) — Build React Native iOS app with glassmorphism design. Signal display with module dissent visualization, calendar, risk calc, journal with auto post-mortems. Telegram bot. TradingEconomics integration. Paper Trading mode (simulated execution). Beginner Focus Mode.

Phase 3: Broker Integration (Months 7-10) — MetaApi for HFM MT4/MT5. Confirmation execution flow with validity windows and slippage tolerance. Custom EA. Correlation warnings, net exposure tracking, and context-aware cooldown mode.

Phase 4: Polish + Launch (Months 10-13) — Beta testing with 50-100 users. Live performance tracking. UI refinements. App Store submission. Public launch.

Phase 5: Expansion (13+ months) — Additional pairs (EURUSD, USDJPY, BTC/USD, indices). Android. More broker integrations. Community features. LLM-powered conflict analysis and sentiment layer.

### 21. Success Metrics & KPIs

| Metric | 6-Month Target | 12-Month Target |
|--------|---------------|----------------|
| Backtest win rate (TP1) | >=60% | Maintained >=60% live |
| Profit factor | >=1.4 | Maintained >=1.3 live |
| Beta retention (30-day) | >=40% | >=50% |
| App Store rating | N/A | >=4.5 stars |
| Paid subscribers | N/A | 500+ |
| Signal latency | <2 seconds | <1 second |

### 22. Appendix: Indicator Parameter Reference

| Indicator | Period | Key Levels | Notes |
|-----------|--------|-----------|-------|
| RSI | 14 | 70/30 (adj. per TF) | Divergence enabled |
| MACD | 12/26/9 | Zero line, signal cross | Histogram divergence |
| Bollinger Bands | 20, 2 SD | Band touch, squeeze | Squeeze breakout primary |
| EMA Short | 20 | Micro trend | Fastest in stack |
| EMA Medium | 50 | Short trend | Golden/Death cross |
| EMA Long | 100 | Medium trend | Intermediate filter |
| EMA Macro | 200 | Macro trend | Primary bias filter |
| ATR | 14 | Dynamic | SL/TP + displacement |
| Fib OTE | N/A | 61.8%, 70.5%, 78.6% | Applied to last swing |
| Fib Extensions | N/A | -27%, -61.8%, -100% | TP3 projection |

*— End of PRD —*

---

## DEVELOPMENT ROADMAP

**made.**

Detailed Sprint-Level Breakdown

Algorithms · Formulas · Acceptance Criteria

Phase 1 Focus: Signal Engine with Full Formula Specifications

Version 1.0 | March 2026 | Confidential

### Phase Overview & Timeline

This roadmap breaks the made. product development into 5 phases across 12+ months. Each phase is subdivided into 2-week sprints with specific deliverables, acceptance criteria, and dependencies. Phase 1 (Signal Engine) is expanded to maximum detail because it is the foundation everything else depends on.

| Phase | Duration | Months | Primary Deliverable |
|-------|----------|--------|-------------------|
| Phase 1: Signal Engine | 12 weeks | 1-3 | Backtested confluence engine with documented performance |
| Phase 1.5: Shadow Mode | 4 weeks | 4 | Live validation — engine on real data, no users, performance verified |
| Phase 2: iOS App + Telegram | 12 weeks | 5-8 | Functional app in TestFlight beta with paper trading |
| Phase 3: Broker Integration | 12 weeks | 7-10 | End-to-end HFM MT4/MT5 execution |
| Phase 4: Polish + Launch | 12 weeks | 10-13 | Public App Store release |
| Phase 5: Expansion | Ongoing | 13+ | Additional pairs, Android, community |

### PHASE 1: Signal Engine MVP (Weeks 1-12)

This is the most critical phase. Everything downstream depends on the accuracy and reliability of the signal engine. No UI work, no app work, no broker integration until this phase passes all acceptance criteria. Pure algorithm development, backtesting, and optimization.

**Exit Criteria for Phase 1:**

- XAUUSD TP1 win rate >= 60% across 5-year backtest (2021-2026)
- GBPJPY TP1 win rate >= 58% across 5-year backtest
- Profit factor >= 1.4 for XAUUSD, >= 1.3 for GBPJPY
- Max drawdown <= 15% with 1% risk per trade
- Minimum 500 trades per pair in backtest for statistical significance
- All 9 confluence modules independently validated
- Walk-forward optimization confirms no overfitting

#### Sprint 1 (Weeks 1-2): Infrastructure & Data Pipeline

**1.1 Development Environment Setup**

- Python 3.11+ virtual environment with: pandas, numpy, numba, ta-lib, vectorbt, backtrader, plotly, jupyter
- Git repository with branch strategy: main / develop / feature/* / backtest/*
- Folder structure: /engine (signal modules), /data (OHLCV storage), /backtest (test harness), /reports (output), /config (parameters)

**1.2 Historical Data Acquisition**

- Source: Dukascopy historical data (1-minute OHLCV candles), validated against OANDA for price accuracy on 200+ random samples
- Pairs: XAUUSD and GBPJPY, January 2021 through March 2026
- Total data points: ~2.6 million 1-minute candles per pair (5 years x 252 trading days x ~1440 minutes, minus weekends/holidays)
- Data validation: check for gaps, duplicates, outlier prices, weekend data leakage, daily rollover gaps
- **Timezone alignment (critical):** Dukascopy uses GMT+0. HFM MT4/MT5 typically uses GMT+2/+3 (EET). Document exact 4H candle boundaries for both and ensure resampled candles match HFM's alignment. A 2-3 hour shift means completely different 4H candles, different swing points, and different OBs. Validate by comparing 50+ resampled 4H candles against HFM's MT4 chart data.
- Storage: Parquet files (columnar, fast read, ~10x compression vs CSV)

**1.3 Timeframe Resampling Engine**

Build a candle resampling module that converts 1-minute data into all required timeframes:

- Input: 1-minute OHLCV DataFrame
- Output: 5m, 15m, 30m, 1H, 4H, 1D, 1W DataFrames
- Logic: Standard OHLCV resampling (Open = first, High = max, Low = min, Close = last, Volume = sum)
- Validation: Compare resampled candles against broker data for at least 50 random samples per timeframe

**1.4 Backtesting Harness (VectorBT)**

Build the core backtesting framework that all modules will plug into:

- Portfolio simulator with configurable: initial capital ($10,000 default), risk per trade (1%), dynamic spread model (see Section 17.1 — session/news-dependent: 2-15 pips XAU, 3-10 pips GJ), slippage (1 pip), commission (0), next-bar-open execution
- Trade executor: market entry, 3-tier partial close (40%/30%/30% at TP1/TP2/TP3), trailing SL after TP1
- Performance metrics: win rate (per TP level), profit factor, max drawdown, Sharpe ratio, Sortino ratio, average R:R, average hold time, trades per week
- Report generator: equity curve, monthly P&L heatmap, drawdown chart, trade distribution by day/hour

**Sprint 1 Deliverable: Fully operational data pipeline with validated 5-year dataset and working backtesting harness.**

#### Sprint 2 (Weeks 3-4): Market Structure Engine (Weight: 25%)

This is the highest-weighted module. It identifies the trend direction by tracking swing highs and swing lows, detecting Break of Structure (BOS) and Change of Character (CHoCH).

**2.1 Swing Point Detection Algorithm**

Formula: A swing high is confirmed when the candle has a higher high than the N candles on either side. A swing low is confirmed when the candle has a lower low than the N candles on either side.

- N (lookback) values per timeframe: 1m/5m = 3 candles, 15m/30m = 5, 1H/4H = 5, 1D = 7, 1W = 10
- Output: Array of swing_highs[] and swing_lows[] with timestamps and prices
- Validation: Visually verify 100 swing points across multiple market conditions (trending, ranging, volatile)

**2.2 Break of Structure (BOS) Detection**

Definition: Price closes beyond the most recent swing point in the direction of the existing trend.

- Bullish BOS: Current candle close > most recent swing high (while trend is already bullish)
- Bearish BOS: Current candle close < most recent swing low (while trend is already bearish)
- Output per BOS event: { type: 'bullish'|'bearish', price: float, timestamp: datetime, swing_ref: SwingPoint }
- BOS confirms trend continuation and scores +0.8 in the direction of the break

**2.3 Change of Character (CHoCH) Detection**

Definition: Price closes beyond a swing point AGAINST the prevailing trend, signaling a potential reversal.

- Bullish CHoCH: In a bearish trend (lower highs, lower lows), price closes above the most recent swing high
- Bearish CHoCH: In a bullish trend (higher highs, higher lows), price closes below the most recent swing low
- CHoCH is higher conviction than BOS for reversals and scores +1.0 in the new direction
- False CHoCH filter: Require the displacement candle to be >= 1.5x ATR to filter noise

**2.4 Market Structure State Machine**

The engine maintains a state for each timeframe:

- States: BULLISH_TREND, BEARISH_TREND, RANGING, TRANSITIONING
- Transitions: BOS keeps the current state (continuation), CHoCH triggers TRANSITIONING, a second CHoCH in the same direction confirms the new trend
- Ranging detection: 3 or more swing points within 1.5x ATR band = RANGING state

**2.5 Module Score Output**

Raw score range: -1.0 to +1.0 (pre-cap values; the aggregator applies the 0.85 cap before weighting — see §5.2).

- UNKNOWN (engine initialization, insufficient swing history): 0.0
- BULLISH_TREND + recent bullish BOS = +0.8
- BULLISH_TREND + bullish CHoCH confirmation = +1.0
- BEARISH_TREND + recent bearish BOS = -0.8
- BEARISH_TREND + bearish CHoCH confirmation = -1.0
- RANGING = 0.0 (no directional bias)
- TRANSITIONING = +/-0.3 (reduced confidence until confirmation)

**Sprint 2 Deliverable: Market Structure module with BOS/CHoCH detection, passing unit tests against 200+ manually labeled examples.**

#### Sprint 3 (Weeks 5-6): Order Blocks, FVGs & OTE (Weights: 20% + 15%)

**3.1 Order Block Detection Algorithm**

An Order Block is the last opposing candle before a displacement move.

- Step 1: Detect displacement candles (candle range >= 2x ATR(14))
- Step 2: Look back from displacement candle to find the last opposing candle (bearish candle before bullish displacement = bullish OB, and vice versa)
- Step 3: Define OB zone: High to Low of the OB candle (use body for precision, wicks for conservative zone)
- Validation filters: (a) OB must precede a BOS or CHoCH, (b) OB must have created an FVG, (c) OB must be unmitigated (price has not returned to fill >50% of the zone), (d) Displacement candle must have above-average tick volume (filters false OBs from low-participation moves)
- Mitigation tracking: Once price returns and trades through 50%+ of the OB zone, mark it as mitigated (no longer valid)
- Maximum active OBs per timeframe: 5 most recent (oldest expire)

**3.2 Fair Value Gap (FVG) Detection Algorithm**

An FVG is a three-candle pattern where price moved so fast it left a gap.

- Bullish FVG: Candle 3 low > Candle 1 high (gap between them is the FVG zone)
- Bearish FVG: Candle 3 high < Candle 1 low
- Minimum FVG size per timeframe: 0.5x ATR (1m/5m), 0.75x ATR (15m/30m), 1x ATR (1H/4H), 1.5x ATR (1D), 2x ATR (1W)
- FVG states: OPEN (unfilled), PARTIALLY_FILLED (price entered but didn't close through), FILLED (price closed through entire gap), INVERTED (breached and now acting as opposite S/R)
- Consequent Encroachment: Track when price reaches the 50% midpoint of the FVG (key reaction level)
- FVG + OB overlap detection: When an FVG zone overlaps with an OB zone = ICT Unicorn Setup (highest probability, 1.10x confluence multiplier)

**3.3 Optimal Trade Entry (OTE) Fibonacci Module**

Applied to the most recent dealing range (swing high to swing low or vice versa).

- Fibonacci levels calculated: 0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0
- OTE Zone: 0.618 to 0.786 retracement (the discount zone for buys, premium zone for sells)
- Sweet Spot: 0.705 level (highest probability single level)
- Extension levels for TP projection: -0.27, -0.618, -1.0 (measured from the dealing range)
- Score calculation: Price within OTE zone (0.618–0.786) = +0.8, price at 0.705 specifically = +1.0 (pre-cap), price in 0.5–0.618 zone = +0.4, price in 0.786–1.0 zone (beyond OTE, within range) = 0.0, price outside dealing range = 0.0
- Confluence boost: OTE + OB within zone = 1.08x multiplier, OTE + FVG within zone = 1.06x multiplier

**3.4 Combined ICT Module Score**

The Order Block + FVG module (20% weight) outputs:

- Price at unmitigated OB in trend direction = +0.9
- Price at unmitigated FVG in trend direction = +0.7
- Unicorn setup (OB + FVG overlap) = +1.0
- No active OB or FVG near current price = 0.0
- Price approaching mitigated zone = -0.2 (warning, not ideal)

**Sprint 3 Deliverable: OB, FVG, and OTE modules with overlap detection, validated against a balanced dataset:**
- 100 clear textbook setups (true positives — clean OBs/FVGs that held)
- 100 ambiguous/borderline cases (messy market data — overlapping OBs, tiny FVGs, borderline displacement)
- 100 false positive cases (OBs/FVGs that LOOKED valid but price blew through them)
- Measure both detection rate AND false positive rate. A module that detects 95% of setups but has a 40% false positive rate is worse than one that detects 80% with a 15% false positive rate.

#### Sprint 4 (Weeks 7-8): Classical TA Modules (Weights: 10%+8%+7%+5%)

**4.1 EMA Alignment Module (Weight: 10% XAU, 12% GJ)**

Calculates EMA 20, 50, 100, 200 on each timeframe.

- Perfect Bullish Stack: price > EMA20 > EMA50 > EMA100 > EMA200 → score = +1.0
- Partial Bullish: price > EMA200 but EMAs not perfectly stacked → score = +0.5
- Bearish equivalent: mirror logic → score = -1.0 / -0.5
- Ranging: price oscillating around EMAs, no clear order → score = 0.0
- Golden Cross (EMA50 crosses above EMA200): additional +0.3 bias boost for next 20 bars
- Death Cross: additional -0.3 bias for next 20 bars
- EMA formula: EMA_today = (Price_today x K) + (EMA_yesterday x (1 - K)), where K = 2 / (period + 1)

**4.2 RSI Module (Weight: 8%)**

Standard 14-period RSI with divergence detection.

- RSI formula: RSI = 100 - (100 / (1 + RS)), where RS = Average Gain / Average Loss over 14 periods
- Overbought/Oversold thresholds (timeframe-dependent): 1m/5m = 65/35, 15m-4H = 70/30, 1D = 75/25, 1W = 80/20
- Score when oversold (RSI < threshold): +0.6 to +1.0 (scaled by how extreme)
- Score when overbought (RSI > threshold): -0.6 to -1.0
- RSI in neutral zone (40-60): score = 0.0
- Bullish Divergence: Price makes lower low, RSI makes higher low → +0.8 buy signal
- Bearish Divergence: Price makes higher high, RSI makes lower high → -0.8 sell signal
- Divergence detection lookback per timeframe: 1m/5m = 5 bars, 15m/30m = 8 bars, 1H/4H = 10 bars, 1D = 15 bars, 1W = 20 bars
- Hidden Divergence (trend continuation): Price makes higher low but RSI makes lower low (bullish trend continues) = +0.5

**4.3 MACD Module (Weight: 7%)**

Standard MACD (12, 26, 9) with histogram analysis.

- MACD Line = EMA(12) - EMA(26)
- Signal Line = EMA(9) of MACD Line
- Histogram = MACD Line - Signal Line
- Bullish crossover (MACD crosses above Signal near zero line): +0.8
- Bullish crossover far from zero line: +0.4 (weaker signal)
- Histogram increasing (bars getting taller, positive): +0.3 momentum confirmation
- Histogram divergence: Price makes new high but histogram peak is lower → -0.6 (bearish warning)
- Bearish crossover: mirror of bullish scores
- No crossover, flat histogram: 0.0

**4.4 Bollinger Bands Module (Weight: 5%)**

20-period SMA with 2 standard deviations.

- Upper Band = SMA(20) + 2 x StdDev(20)
- Lower Band = SMA(20) - 2 x StdDev(20)
- Band Width = (Upper - Lower) / SMA(20)
- Squeeze detection: Band Width at 20-period low → flag SQUEEZE_ACTIVE
- Squeeze breakout above upper band + bullish MACD: +0.8
- Squeeze breakout below lower band + bearish MACD: -0.8
- Price touching lower band with RSI oversold: +0.5 (mean reversion support)
- No squeeze, price between bands: 0.0
- ATR multiplier adjustment: When ATR > 2x its 20-period average, widen BB interpretation zones by 20%

**Sprint 4 Deliverable: All 4 classical TA modules independently backtested with documented per-module accuracy rates.**

#### Sprint 5 (Weeks 9-10): Supporting Modules, TP/SL Engine & Confluence Aggregator

**5.1 Kill Zone Timing Module (Weight: 5%)**

UTC times are authoritative (see §6.6). All scores are directional: positive = in HTF trend direction, negative = counter-trend. Direction determined by HTF market structure state.

- Asian KZ (00:00–02:00 UTC, both pairs): score = +0.3 in trend direction (lower volatility, bias continuation)
- Shanghai Open KZ (00:15–02:15 UTC, XAUUSD only): score = +0.6 in trend direction (PBOC fixing, SGE physical demand). Takes precedence over generic Asian score during overlap window 00:15–02:00 UTC for XAUUSD.
- London KZ (07:00–10:00 UTC, both pairs): score = +0.8 in trend direction (highest probability for trend initiation)
- New York KZ (13:00–16:00 UTC, both pairs): score = +1.0 in trend direction (highest volatility, confirmation of London moves)
- London Close KZ (15:00–17:00 UTC, both pairs): score = +0.5 in counter-trend direction (retracement trades)
- Outside all KZs: score = -0.3 (penalty, not disqualification)
- Initial state (no trend established yet): score = 0.0 (neutral until market structure state machine confirms direction)

**5.2 Support & Resistance / Liquidity Module (Weight: 5%)**

- Identify swing high/low clusters: where 3+ swing points are within 0.5x ATR of each other = strong S/R level
- Equal highs/lows detection: consecutive swing points at nearly identical levels (within 5 pips for GJ, 0.03% of price for XAU — percentage-based to stay consistent across the $1800–$3000+ price range) = liquidity pool
- Score: Price approaching strong S/R in trade direction and bouncing = +0.7
- Score: Price broke through S/R (confirmation of momentum) = +0.5
- Score: Price near equal highs/lows (liquidity grab potential) = +0.4 (but flag as risky, institutions may sweep)

**5.3 TP/SL Hybrid Calculation Engine**

Executes after a signal passes confluence threshold. Calculates entry, SL, TP1, TP2, TP3.

**Stop Loss Algorithm:**

- Method 1 (Structural): Place SL beyond the nearest invalidation point (swing high/low that invalidates the trade thesis)
- Method 2 (ATR-based): SL = Entry +/- 1.5x ATR(14)
- Final SL = whichever is tighter, BUT minimum 1x ATR and maximum 3x ATR from entry
- Buffer: Add 5-10 pips (GJ) or 0.03%-0.07% of price (XAU, replaces fixed dollar buffer to handle $1800-$3000+ price range) beyond the raw level for stop hunt protection
- If calculated SL > 3x ATR: downgrade signal strength by 20% (excessive risk)

**Take Profit Algorithm:**

- TP1 (40% close): MIN(nearest opposing S/R level, 1.0x risk distance). Must be >= 1.0x risk (minimum 1:1 R:R)
- TP2 (30% close): MIN(next S/R level, opposing OB, 2.0x risk distance). Target: 1:2 R:R
- TP3 (30% close): MAX(major liquidity target, Fibonacci -0.618 extension, 3.0x risk). Target: 1:3 R:R
- Fallback: If no structural targets found, use pure ATR multiples (TP1 = 1.5x ATR, TP2 = 2.5x ATR, TP3 = 4x ATR)
- Validation: If TP1 cannot achieve 1:1 R:R, suppress the signal entirely

**5.4 Confluence Score Aggregator**

The master function that combines all module scores.

- Input: Array of 9 module scores, each between -1.0 and +1.0 (base scores capped at 0.85 to reserve headroom)
- **Step 1 — Regime gate:** Check market regime (ADX-based). If RANGING, increase thresholds and suppress trend-following signals (see Section 7.7).
- **Step 2 — Weighted sum:** Apply pair-specific weights (XAUUSD: 25/20/15/10/8/7/5/5/5, GBPJPY: 25/18/15/12/8/7/5/5/5). Weighted sum = SUM(score_i x weight_i) for all modules.
- **Step 3 — Multiplier bonuses:** Apply confluence multipliers (Unicorn 1.10x, OTE+OB 1.08x, OTE+FVG 1.06x, Kill Zone 1.05x/0.95x, day-of-week modifier). Multipliers stack multiplicatively.
- **Step 4 — Penalties:** HTF conflict: reduce score by 20%. News proximity (high-impact within 15 min): flag NEWS_RISK badge, reduce by 10%. Regime TRANSITIONAL: reduce by 10%.
- **Step 5 — Final score:** Clamped to [-1.0, +1.0] range.
- Signal generation threshold: |score| >= 0.50 (Moderate), >= 0.65 (Strong, triggers alerts), >= 0.80 (Very Strong)
- In RANGING regime: minimum threshold raised to |score| >= 0.70 for Moderate signals

**Sprint 5 Deliverable: Complete signal pipeline (all 9 modules + regime detection + aggregator + TP/SL engine) producing signals on historical data.**

#### Sprint 6 (Weeks 11-12): Full Backtesting, Optimization & Validation

**6.1 Full System Backtest**

Run the complete confluence engine against 5 years of data for both pairs, across all trading styles.

- Backtest configurations: Scalping (5m entry, 15m/1H HTF), Day Trading (15m entry, 1H/4H HTF), Swing Trading (4H entry, 1D/1W HTF)
- Per-configuration output: total trades, win rates (TP1/TP2/TP3), profit factor, max drawdown, Sharpe, Sortino, monthly returns
- **Minimum sample sizes:**
  - 500 trades per pair per trading style for aggregate metrics
  - 30-50 trades minimum per meaningful sub-segment (per Kill Zone, per day-of-week, per news/no-news)
  - Segments that don't meet minimums are explicitly flagged as "insufficient data — no claim made"
  - This prevents hiding performance collapse in specific conditions behind strong aggregate numbers

**6.2 Weight Optimization**

Use Bayesian optimization (Optuna) to find optimal weight combinations. Grid search is computationally infeasible (9 weights at 2% increments summing to 100% = millions of combinations).

- **Method:** Optuna with TPE sampler, budget of 1000-2000 iterations maximum
- Constraint: Weights must sum to 100%, no single module > 30%, no module < 3%
- Objective function: Maximize (win_rate_TP1 x profit_factor) while keeping max_drawdown < 15%
- Run on 80% of data (in-sample), validate on remaining 20% (out-of-sample)
- If out-of-sample performance drops > 15% vs in-sample: flag overfitting
- Alternative approach: coordinate descent — optimize 2-3 weights at a time while holding others fixed, cycle through all groups

**6.3 Walk-Forward Optimization**

The gold standard for avoiding overfitting. Walk-forward must be done PER TRADING STYLE since different styles have different trade frequencies.

**Day Trading / Scalping WFO:**
- Window size: 6 months (4 months IS, 2 months OOS)
- Step size: 2 months (sliding window)
- ~26 windows across 5 years, sufficient trade count in each OOS period (100+ trades)

**Swing Trading WFO:**
- Window size: 12 months (8 months IS, 4 months OOS)
- Step size: 4 months (sliding window)
- ~12 windows across 5 years, ensures 30+ trades per OOS period

**Acceptance criteria:**
- WFO efficiency ratio >= 0.6 (out-of-sample returns >= 60% of in-sample returns)
- No single OOS window has negative profit factor
- OOS max drawdown stays within 1.5x of IS max drawdown

**6.4 Stress Testing**

- Test against known extreme events in the data: COVID crash (March 2020 is before our window, but Feb 2022 Ukraine, SVB March 2023, Japan carry trade unwind Aug 2024)
- Test during high-impact news periods separately: How do signals perform during NFP, FOMC, CPI?
- Test during low-volatility consolidation periods: Does the system avoid overtrading?
- Test win rate by Kill Zone: Does London KZ really outperform Asian KZ as expected?

**6.5 Performance Report Generation**

Create the official backtest report for each pair and trading style:

- Equity curve with drawdown overlay
- Monthly P&L heatmap (months as columns, years as rows, color-coded green/red)
- Win rate breakdown by: TP level, Kill Zone, day of week, with/without news
- Module contribution analysis: Which modules contributed most to winning vs losing trades?
- Trade duration distribution (histogram)
- Consecutive loss analysis (longest losing streak, recovery time)
- Risk-adjusted metrics: Sharpe, Sortino, Calmar ratio

**Sprint 6 Deliverable: Complete backtest report proving performance targets are met. GO/NO-GO decision for Phase 2.**

| Go/No-Go Metric | XAUUSD Minimum | GBPJPY Minimum |
|-----------------|---------------|---------------|
| TP1 Win Rate | >= 60% | >= 58% |
| Profit Factor | >= 1.4 | >= 1.3 |
| Max Drawdown (1% risk) | <= 15% | <= 18% |
| WFO Efficiency | >= 0.6 | >= 0.6 |
| Total Backtest Trades | >= 500 | >= 500 |
| Monthly Return (avg) | >= 3% | >= 2% |

### PHASE 1.5: Shadow Mode Validation (Weeks 13-16)

The most honest validation step. The engine runs on live market data, generates signals in real-time, but shows them to nobody. All signals are logged with timestamps, and outcomes are tracked automatically.

**Shadow Mode Setup (Week 13):**
- Deploy signal engine to production infrastructure (Docker on AWS)
- Connect to live OANDA data feed with Twelve Data as failover
- Engine generates signals for all trading styles on both pairs
- All signals logged to database: timestamp, pair, direction, entry, SL, TP1/2/3, confluence score, module breakdown

**Shadow Mode Monitoring (Weeks 14-16):**
- Track signal outcomes as price hits TP1/2/3 or SL
- Compare shadow results against backtest expectations for the same time period
- Monitor: win rate, profit factor, signal frequency, average R:R, regime detection accuracy
- Check for systematic biases: Does the engine over-signal during certain sessions? Do signals cluster or spread naturally?

**Shadow Mode GO/NO-GO Criteria:**
- Shadow mode TP1 win rate within 15% of backtest TP1 win rate for same period
- Profit factor >= 1.2 (allowing degradation from backtest)
- No catastrophic failure patterns (e.g., 10+ consecutive losses, signals during data outages)
- Signal frequency matches backtest expectations (+/- 30%)
- If criteria not met: extend shadow mode by 2 weeks, diagnose issues, adjust parameters, re-run. Do NOT proceed to Phase 2 with an unvalidated engine.

### PHASE 2: iOS App + Telegram Bot (Weeks 17-28)

With a proven AND live-validated signal engine, Phase 2 wraps it in the made. user experience. The engine runs server-side; the app is a real-time consumer of signal events.

#### Sprint 7 (Weeks 17-18): Backend API & Real-Time Infrastructure

- FastAPI (Python) backend with WebSocket support for real-time signal push
- PostgreSQL schema: users, signals, trades, journal_entries, notification_prefs
- Redis pub/sub for signal broadcasting to connected clients
- REST endpoints: GET /signals (active), GET /signals/history, GET /calendar, POST /journal, GET /analytics
- Authentication: JWT-based auth with Apple Sign In
- Rate limiting and API security hardening

#### Sprint 8 (Weeks 19-20): Signal Engine Deployment

- Containerize signal engine (Docker) with health monitoring
- Deploy to AWS/GCP with auto-scaling for data processing
- Scheduled jobs: bar-close signal calculation for each active timeframe
- Signal lifecycle management: creation, update (trailing SL), expiry, outcome logging
- Market data feed integration: OANDA or Twelve Data API for live OHLCV

#### Sprint 9 (Weeks 21-22): iOS App - Core Screens

- React Native project setup with dark glassmorphism design system
- Signal Dashboard: glass cards with pair, direction, confidence ring (with decay indicator), entry/SL/TP levels
- Signal Detail view: indicator contribution bars with color-coded module dissent (green=aligned, red=opposing, amber=neutral), mini chart, contextual tooltips
- Economic Calendar: timeline with glass event cards, countdown rings, impact color coding
- TradingEconomics API integration for calendar data with SGT timezone default
- **UI Complexity Modes (§8.3):** Implement Simple / Pro / Max mode selector in Settings. Default to Simple on first launch with onboarding quiz. Simple = top 1-2 signals, plain-English labels, no module breakdown. Pro = full signal detail with dissent bars and regime badge. Max = raw scores, decay timer, advanced analytics, CSV export. Gate Pro/Max behind Premium/Pro subscriptions respectively.

#### Sprint 10 (Weeks 23-24): iOS App - Risk, Journal & Paper Trading

- Risk Calculator screen: interactive sliders, real-time lot size calculation, USD risk display
- Trade Journal: auto-log from signals, manual entry option, card-based history, auto-generated post-mortems on SL hits
- Analytics Dashboard: win rate donuts, equity curve (prominently displayed for retention), monthly P&L, filters by pair/style/timeframe
- **Paper Trading Mode:** Virtual account with simulated execution, full P&L tracking, clearly marked in journal. Serves as safe onboarding for beginners and live engine validation.
- Settings: timezone switcher (SGT/EST/GMT/auto), trading style selector, notification prefs, Focus Mode toggle

#### Sprint 11 (Weeks 25-26): Telegram Bot

- Telegram Bot API setup from scratch: register bot, set up webhook endpoint
- Signal broadcast channel: rich message formatting with pair, direction, levels, confidence
- Personal DM alerts: account-specific based on user's selected pairs and trading style
- Inline buttons: View in App (deep link), Skip, Acknowledge
- Daily Rundown message: automated 6:00 AM SGT push of day's economic events

#### Sprint 12 (Weeks 27-28): Notifications, Polish & TestFlight

- Apple Push Notifications (APNS) integration for: new signals, TP/SL hits, news alerts, daily rundown
- Notification scheduling: cascading news countdowns (1h, 30m, 15m, 5m, 1m)
- News signal suppression: 15-min pre and 5-min post high-impact events
- Education tooltips: implement long-press tooltip system with Investopedia links
- QA pass: test all flows on iPhone 13-16 range, iPad compatibility check
- TestFlight deployment for internal and early beta testers (10-20 users)

**Phase 2 Exit Criteria: Functional iOS app on TestFlight with paper trading + working Telegram bot, receiving live signals from deployed engine, with calendar, journal (incl. post-mortems), Focus Mode, and paper trading operational.**

### PHASE 3: Broker Integration & Execution (Weeks 29-40)

#### Sprint 13-14 (Weeks 29-32): MetaApi Integration

- MetaApi cloud REST API account setup and HFM server connection
- Account linking flow in-app: user enters MT4/MT5 credentials, validated via MetaApi
- Read-only mode: display account balance, equity, open positions, trade history
- Execution mode: place market orders, set SL/TP, modify orders via MetaApi
- Confirmation-based flow: Signal → User reviews → Taps Confirm → Order placed → Confirmation screen

#### Sprint 15-16 (Weeks 33-36): Custom Expert Advisor & Trade Management

- MQL4 EA for MT4: receive webhook signals, validate price, execute with slippage tolerance
- MQL5 EA for MT5: same functionality, adapted for MT5 architecture
- Partial close management: auto-close 40% at TP1, 30% at TP2, trail SL for remaining 30%
- Trailing SL logic: after TP1 hit, move SL to breakeven; after TP2, trail SL to TP1 level
- Error handling: rejected orders, insufficient margin, price deviation alerts
- Execution confirmation callback: EA reports fill price, actual lot, slippage back to app

#### Sprint 17-18 (Weeks 37-40): Risk Safeguards & Correlation Engine

- Daily exposure limit enforcement: max 3 simultaneous signals per pair, max 3% daily risk
- Context-Aware Cooldown Mode (§11.4): news-attributed losses → no cooldown (suppress signals for news window only); setup-pattern losses → suppress that specific Kill Zone + setup type for 24h; rolling loss rate > 50% on last 10 signals → 4-hour cooldown with encouragement UX. No simple "2 consecutive = 2 hour" rule.
- Correlation warning engine: DXY strength monitor, XAUUSD vs GBPJPY sentiment conflict detection
- Historical news reaction data: pre-compute and store average price moves for top 10 events per pair
- Conflict analysis generator: AI-powered brief explaining HTF vs LTF divergence
- Full integration testing: signal → app display → user confirm → MT4/MT5 execution → journal log

**Phase 3 Exit Criteria: End-to-end trade execution from signal to HFM MT4/MT5, with partial closes, trailing SL, validity windows, slippage tolerance, risk limits (including weekly/monthly drawdown breakers), net exposure tracking, context-aware cooldown, and journal logging.**

### PHASE 4: Polish, Beta Testing & Launch (Weeks 41-52)

#### Sprint 19-20 (Weeks 41-44): Closed Beta

- Recruit 50-100 beta testers: mix of beginners, intermediates, and experienced traders
- Beta tracking dashboard: aggregate signal performance in live market conditions
- Compare live performance against backtest expectations (accept up to 15% degradation)
- User feedback collection: in-app feedback form, weekly survey, 1-on-1 interviews with 10 users
- Bug tracking and priority resolution pipeline

#### Sprint 21-22 (Weeks 45-48): Refinement

- UI/UX refinements based on beta feedback (navigation pain points, information hierarchy)
- Signal engine parameter adjustments based on live vs backtest comparison
- Performance optimization: app load time < 2s, signal latency < 2s end-to-end
- Accessibility audit: contrast ratios on glassmorphism (minimum 4.5:1 for body text)
- Legal review: disclaimers, terms of service, privacy policy, regulatory compliance check

#### Sprint 23-24 (Weeks 49-52): App Store Launch

- App Store submission: screenshots, description, keywords, privacy labels
- App Store review preparation: ensure all financial disclaimers meet Apple guidelines
- Marketing landing page: made.app or similar domain with product overview
- Launch announcement: Telegram channel, social media, trading communities
- Monitoring: crash analytics, signal performance tracking, user retention dashboards
- Payment integration: Apple In-App Subscriptions for Free/Premium/Pro tiers

**Phase 4 Exit Criteria: App live on App Store with payment processing (Free/Premium/Pro tiers at $0/$49/$99), achieving >= 4.5 star rating in first 30 days. Churn prevention systems active.**

### PHASE 5: Expansion (Month 12+)

Phase 5 is ongoing and prioritized based on user demand and business metrics.

#### 5.1 Additional Pairs

- Priority 1: EURUSD (most liquid forex pair, validates engine on low-volatility major)
- Priority 2: USDJPY (complements GBPJPY, tests JPY correlation logic)
- Priority 3: BTC/USD (crypto, tests engine on 24/7 market with different volatility profile)
- Priority 4: NAS100/US30 (indices, broadens market coverage)
- Each new pair requires: weight re-optimization, 3-year backtest, 1-month paper trading validation

#### 5.2 Android App

- React Native shared codebase (if used in Phase 2) enables faster Android development
- Material Design adaptation of glassmorphism design system
- Estimated timeline: 8-12 weeks from Phase 5 start

#### 5.3 Additional Broker Support

- IC Markets, Exness, Pepperstone via MetaApi (most support MT4/MT5 already)
- cTrader integration for brokers offering that platform
- FIX API support for institutional-grade execution

#### 5.4 Community Features

- Signal leaderboard: anonymized performance ranking of different trading styles
- User-shared journal insights (opt-in): aggregate learning from community trades
- Weekly market analysis newsletter powered by the signal engine data

#### 5.5 Advanced AI Layer

- Sentiment analysis: parse news headlines and social media for directional bias
- Pattern recognition: CNN-based chart pattern detection to complement rule-based analysis
- Adaptive weighting: ML model that adjusts module weights based on recent market regime

### Dependency Map & Critical Path

The critical path runs through Phase 1. If the signal engine does not meet performance targets, all downstream phases are blocked until it does.

| Dependency | Blocks | Risk Mitigation |
|-----------|--------|----------------|
| 5-year OHLCV data quality | All Phase 1 work | Validate against 2+ data sources before starting Sprint 2 |
| Module accuracy (each) | Confluence aggregator | Unit test each module independently before integration |
| Backtest performance targets | Phase 2 start | If targets not met: adjust weights, add/remove modules, extend Phase 1 by 2-4 weeks |
| TradingEconomics API access | Calendar feature | JBlanked API as fallback; manual calendar as last resort |
| MetaApi HFM connectivity | Broker execution | Test with HFM demo account in Sprint 13 (Week 29) before building full flow |
| Shadow mode performance | Phase 2 start | If shadow results degrade >15% from backtest: extend shadow by 2 weeks, diagnose, re-run |
| Apple App Store approval | Public launch | Ensure financial disclaimers meet guidelines; submit 2 weeks early |

*— End of Roadmap —*

made. Development Roadmap v1.0 | March 2026
