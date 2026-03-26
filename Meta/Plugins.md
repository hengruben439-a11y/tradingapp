# Plugins & MCP Servers

Active MCP (Model Context Protocol) plugins and servers available in this Claude Code session.

---

## Core Build Plugins

### Supabase MCP
**Purpose:** Direct database management — run SQL migrations, query entities, deploy edge functions, manage branches.
**Relevant sprints:** Sprint 7 (backend schema), Sprint 8 (signal lifecycle), Phase 3 (trade journal queries)
**Key tools:** `execute_sql`, `apply_migration`, `list_tables`, `get_logs`, `deploy_edge_function`
**When to use:** Creating the PostgreSQL schema for users/signals/trades/journal, running migrations, checking query performance.

### Context7 MCP
**Purpose:** Fetch up-to-date library documentation and code examples.
**Relevant sprints:** All Phase 1 sprints (vectorbt, pandas, ta-lib docs), Phase 2 (React Native, FastAPI docs)
**Key tools:** `resolve-library-id`, `query-docs`
**When to use:** Before implementing a module — fetch the current vectorbt or ta-lib API to avoid using deprecated patterns.

### Playwright MCP
**Purpose:** Browser automation for testing web-facing features.
**Relevant sprints:** Phase 2 web dashboard (Phase 5), Phase 4 QA.
**Key tools:** `browser_navigate`, `browser_snapshot`, `browser_fill_form`, `browser_take_screenshot`
**When to use:** E2E testing the web app, screenshot capture for QA reports.

### Figma MCP
**Purpose:** Read design context from Figma files, export assets, manage Code Connect.
**Relevant sprints:** Phase 2 (iOS glassmorphism UI components), Phase 4 (App Store assets)
**Key tools:** `get_design_context`, `get_screenshot`, `get_metadata`
**When to use:** When implementing a UI component — pull the design context to get exact colors, spacing, and structure from the Figma file.

### Notion MCP
**Purpose:** Create/update Notion pages — useful for external documentation and stakeholder reports.
**Relevant sprints:** Phase 4 (beta user onboarding docs), Phase 5 (team docs)
**Key tools:** `notion-create-pages`, `notion-update-page`, `notion-search`
**When to use:** Publishing backtest reports or user guides externally.

### Google Calendar MCP
**Purpose:** Sprint scheduling, deadline tracking, milestone reminders.
**Relevant sprints:** All phases — sprint planning and deadline management.
**Key tools:** `gcal_create_event`, `gcal_list_events`, `gcal_find_free_time`
**When to use:** Scheduling sprint reviews, setting GO/NO-GO review dates.

---

## Marketing & Launch Plugins (Phase 4+)

### Canva MCP
**Purpose:** Design creation for App Store screenshots, marketing materials.
**Relevant sprints:** Phase 4 (App Store submission)
**Key tools:** `generate-design`, `export-design`

### Gamma MCP
**Purpose:** AI-powered presentations for investor/user demo decks.
**Relevant sprints:** Phase 4 launch, Phase 5 expansion
**Key tools:** `generate`

### Bitly MCP
**Purpose:** Shortened URLs for marketing links, QR codes.
**Relevant sprints:** Phase 4 marketing landing page
**Key tools:** `create_short_link`, `create_qr_code`

### Make MCP
**Purpose:** Workflow automation — Telegram notification pipelines, alert automation.
**Relevant sprints:** Phase 2 Telegram bot (alternative to custom code for simple notification flows)
**Key tools:** `scenarios_create`, `scenarios_run`

### Vercel MCP
**Purpose:** Deploy the marketing landing page and web dashboard.
**Relevant sprints:** Phase 4 (landing page), Phase 5 (web app)
**Key tools:** `deploy_to_vercel`, `list_deployments`, `get_runtime_logs`

---

## Plugin Status

| Plugin | Status | First Used Sprint |
|--------|--------|-----------------|
| Supabase | Available | Sprint 7 |
| Context7 | Available | Sprint 1 |
| Playwright | Available | Phase 2 QA |
| Figma | Available | Sprint 9 |
| Notion | Available | Phase 4 |
| Google Calendar | Available | Sprint 1 (planning) |
| Canva | Available | Phase 4 |
| Gamma | Available | Phase 4 |
| Bitly | Available | Phase 4 |
| Make | Available | Phase 2 |
| Vercel | Available | Phase 4 |
