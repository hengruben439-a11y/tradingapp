# Changelog

Version history, spec changes, engine parameter updates, and notable modifications — with dates.

## Format
```
### [DATE] vX.X — Title
**Type:** Spec | Engine | App | API | Config | Hotfix
**Changed:** What was modified
**Why:** Reason for change
**Affects:** Which components / sprints are impacted
```

---

## Log

### 2026-03-26 v1.0 — Initial CLAUDE.md specification
**Type:** Spec
**Changed:** PRD and Roadmap created in CLAUDE.md. Covers signal engine, ICT modules, classical TA, backtesting methodology, risk management, broker integration, UI/UX, monetization, and 5-phase development roadmap.
**Why:** Foundation document for the made. trading platform build
**Affects:** All phases

### 2026-03-26 v1.1 — Specification audit and 11-issue fix pass
**Type:** Spec
**Changed:**
1. Confidence decay formula defined as `base_score × (1 - 0.25 × elapsed_fraction)` — fixes broken 0.80→0.70 example
2. Kill Zone Asian UTC corrected from 23:00 to 00:00; new §6.6 UTC reference table added
3. Shanghai Open Kill Zone (00:15–02:15 UTC, XAUUSD only) added to Sprint 5.1 module spec
4. Module score cap clarification: +1.0 raw scores are pre-cap; aggregator applies 0.85 cap
5. Fibonacci standardized to 78.6% (0.786) everywhere — removed all instances of "79%"
6. Phase 2 timeline corrected from "Months 4–7" to "Months 5–8" (was overlapping Phase 1.5)
7. Sprint 17-18 cooldown updated to reference §11.4 context-aware model (removed old "2 losses → 2h" reference)
8. Equal highs/lows XAU tolerance: "$1" → "0.03% of price" (consistent with ATR normalization)
9. Day-of-week modifier: added operational spec — default 1.0x, stored in config YAML, recalibrate quarterly
10. RSI divergence lookback: explicit per-TF values added (5/8/10/15/20 bars)
11. Pip value table added to §11.1: XAUUSD $1/pip/lot, GBPJPY dynamic (USDJPY-dependent, $9.50 fallback)
**Why:** Pre-build spec audit to catch implementation-breaking inconsistencies before Sprint 1
**Affects:** Sprint 2 (market structure scoring), Sprint 3 (OTE levels), Sprint 5 (Kill Zone module, S&R module, aggregator), Sprint 10 (risk calculator), Sprint 17-18 (cooldown)

### 2026-03-26 v1.1 — Architecture: Supabase added
**Type:** Spec / Config
**Changed:** §4.1 System Overview updated — PostgreSQL row replaced with Supabase (managed Postgres with auth, RLS, real-time, REST API). Redis retained for engine state checkpointing.
**Why:** Supabase reduces Phase 2 backend boilerplate significantly; built-in auth supports Apple Sign In; real-time subscriptions available for client push (non-critical path)
**Affects:** Sprint 7 backend setup

