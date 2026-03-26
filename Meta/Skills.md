# Skills

Active Claude Code skills in use for this project. Invoke with `/skill-name` in the Claude Code prompt.

---

## Project Skills

### /upkeep
**File:** `~/.claude/commands/upkeep.md`
**Purpose:** Manual session sync — updates all CodeKeeping .md logs for the current session, then commits and pushes everything to GitHub.
**When to invoke:** At the end of a build session, or anytime you want a clean checkpoint committed and pushed.
**What it does:**
1. Updates Progress.md (sprint status + milestone log)
2. Updates Changelog.md (spec/code changes)
3. Updates Debug.md (open/resolved bugs)
4. Updates Performance.md (if backtest results exist)
5. Updates Decisions.md (if new decisions made)
6. Updates Integrations.md (if API status changed)
7. Commits all changes and pushes to GitHub

---

## System Skills (Claude Code Built-in)

### /commit
**Purpose:** Smart git commit with auto-generated message from staged diff.
**When to invoke:** After completing a meaningful unit of work you want in git history.

### /review-pr
**Purpose:** Code review a pull request.
**When to invoke:** Before merging any feature branch to main.

### update-config
**Purpose:** Modify Claude Code settings.json — hooks, permissions, env vars, MCP servers.
**When to invoke:** To add hooks, change permission rules, or update project config.

### feature-dev
**Purpose:** Guided feature development with codebase understanding and architecture focus.
**When to invoke:** When starting a new sprint feature that requires understanding existing patterns first.

### claude-mem:make-plan
**Purpose:** Create a phased implementation plan with documentation discovery.
**When to invoke:** Before starting a multi-step implementation task.

### claude-mem:mem-search
**Purpose:** Search persistent cross-session memory for past decisions and solutions.
**When to invoke:** When you want to recall how something was previously solved or decided.

### frontend-design
**Purpose:** Create production-grade frontend components with high design quality.
**When to invoke:** Phase 2+ when building React Native UI components.

### simplify
**Purpose:** Review and simplify recently changed code for clarity and efficiency.
**When to invoke:** After writing a complex module to clean it up before committing.

### code-review
**Purpose:** Review code for bugs, logic errors, and security issues.
**When to invoke:** Before committing any completed Sprint deliverable.

---

## Phase-Specific Skill Usage

| Phase | Key Skills |
|-------|-----------|
| Phase 1 (Signal Engine) | feature-dev, code-review, simplify, /upkeep |
| Phase 2 (iOS App) | frontend-design, feature-dev, code-review, /upkeep |
| Phase 3 (Broker) | feature-dev, code-review, /upkeep |
| Phase 4 (Launch) | review-pr, code-review, /upkeep |
| All Phases | /upkeep (end of every session) |
