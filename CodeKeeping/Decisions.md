# Decisions Log

Architecture choices, design decisions, and technical trade-offs — with rationale so future-you understands why.

## Format
```
### [DATE] — Decision title
**Context:** What problem prompted this decision
**Decision:** What was chosen
**Why:** Reasoning and trade-offs considered
**Alternatives rejected:** What else was considered and why it lost
**Impact:** What this affects downstream
```

---

## Log

### 2026-03-26 — Supabase for PostgreSQL layer
**Context:** Need managed Postgres with auth, real-time, and REST API generation
**Decision:** Use Supabase instead of raw self-hosted PostgreSQL
**Why:** Provides managed Postgres + built-in auth (Apple Sign In compatible), row-level security, real-time subscriptions for client push, and auto-generated REST API — significantly reduces Phase 2 backend boilerplate
**Alternatives rejected:** Raw PostgreSQL on AWS RDS (more ops overhead, no built-in auth); Firebase (NoSQL, wrong fit for relational trade journal)
**Impact:** Sprint 7 backend setup; Redis still required for engine state checkpointing (<10ms requirement exceeds Supabase real-time latency)

### 2026-03-26 — Next-bar-open execution for backtesting
**Context:** Need honest backtest results that match live trading
**Decision:** All backtests execute signals at the OPEN of the bar following signal generation
**Why:** Prevents look-ahead bias; signal-bar execution is impossible in live trading. Typically reduces performance by 5-10% vs signal-bar but produces results that match real fills
**Alternatives rejected:** Signal-bar execution (look-ahead bias, inflated results); VWAP fill (too complex, not meaningful for short-hold trades)
**Impact:** Sprint 6 backtest harness; accept 5-10% performance haircut as cost of honesty

### 2026-03-26 — Multiplicative confluence bonuses (not additive)
**Context:** Need to handle multiple ICT setup overlaps (OB + FVG + OTE + Kill Zone)
**Decision:** Bonus multipliers stack multiplicatively (1.10x × 1.08x × 1.05x = 1.25x), applied to pre-clamp score
**Why:** Additive bonuses can push scores above 1.0 in unpredictable ways; multiplicative stacking preserves score distribution integrity and is easier to reason about
**Alternatives rejected:** Additive bonuses (score distribution breaks down with 3+ bonuses active)
**Impact:** §5.4 Confluence Aggregator Step 3; max multiplier stack ~1.25x on a 0.85 capped score = 1.06, clamped to 1.0

