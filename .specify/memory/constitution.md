<!-- Sync Impact Report
Version change: unversioned (de facto 1.0.0, ratified 2026-10-29, amended 2026-10-31) -> 2.0.0
Bump: MAJOR — product mission redefined by operator via grill session 2026-11-27.
Repo is now an advisory tool: investor personas (as prompts + data packets), stock
discovery, news archive (RSS + EDGAR), and a trade journal scored deterministically.
Reasoning happens in Claude Code (external, via MCP); the app contains zero LLM calls.
Paper-fund engine, backtesting, rebalancing, scheduler, TUI, paid providers, and all
in-app LLM provider code are CUT.
Principles (all operator-decided, grill transcript 2026-11-27):
- I Advisory only (operator: trades happen in live IBKR account, outside software)
- II LLM-free core (operator: "should we not have AI here at all" — confirmed)
- III Records append-only + single-writer (operator: journal via MCP, Nextcloud bind-mount)
- IV Data honesty, free sources only (operator: cut all paid — A)
- V Determinism + tested (operator: keep evidence rules, 10-min suite budget)
- VI Thin interfaces (operator: CLI keep, MCP build HTTP, React web keep+trim, TUI retire)
- VII Simplicity budget (operator: ratchet C during trim + spec-gate B forever)
- VIII Style (unchanged)
Removed: 2026-10-31 web-migration amendment (superseded — web stays but trimmed,
migration direction dead); paper-only Principle II (superseded by stronger I).
Follow-up TODOs:
- TODO(SPEC): big trim — remove paper/, backtesting/, portfolio/, risk/, strategies/,
  pipeline/, fund/, validation/, brokers/, secrets/, runtime/, tui/, llm/ + langchain deps;
  trim web/ routes; verify scorecard/, reporting/, features/ content first
- TODO(SPEC): MCP server (HTTP transport, loopback, tools: persona briefs, discovery,
  news, journal append/query, scorecard)
- TODO(SPEC): journal module (append-only store + deterministic scoring layer)
- TODO(SPEC): web desk page trim (cut paper/builder/mandates/saxo; add journal,
  scorecard, news, discovery; pnpm migration)
- TODO(DOCS): rewrite VISION.md and ROADMAP.md to match v2.0.0
-->

# AI Hedge Fund Constitution

## Core Principles

### I. Advisory only — the engine never trades (MUST)

- Software analyzes, discovers, archives, journals, scores. Human trades own live account, outside this repo.
- No broker code. No order routing. No trading APIs. No live-account credentials in repo, config, or root.
- Broker data arrives only as journal entries written through the MCP surface by an external operator agent.
- Why: operator trades live IBKR account via separate MCP. This software MUST NOT be able to create market risk — enforced by absence of capability, not by policy.

### II. LLM-free core (MUST)

- App contains zero LLM calls and zero LLM client dependencies. Reasoning happens in the operator's agent (Claude Code) over MCP.
- Personas = versioned prompt templates + deterministic data packets (fundamentals, news, filings) assembled by the app. The agent reasons; the app never does.
- All numbers (scores, screens, NAV, P&L) computed by deterministic code only.
- Why: operator already pays for the brain. In-app LLM code = cost, keys, guard machinery, and duplicate reasoning surface. Cut.

### III. Records append-only, single-writer (MUST)

- Trade journal, persona signals, news archive: append-only. Corrections = new records, never rewrites.
- Existing hash-chained serializations stay replayable byte-identically; format changes need documented migration.
- Exactly one writer (this app) owns the data root. Nextcloud syncs it read-only-everywhere-else; sync = backup, never a second writer.
- Why: journal + hash chain + sync conflicts = corruption unless writes are single-origin.

### IV. Data honesty, free sources only (MUST)

- Point-in-time only. No lookahead in any screen, brief, or score.
- Sources: yfinance (market), curated RSS catalog (news), SEC EDGAR (filings). All free, zero API keys.
- Paid providers and paid data are banned from the dependency tree. A future exception requires a constitution amendment.
- Why: operator decision — free stack covers the mission; paid guards were complexity without value.

### V. Determinism and tested (MUST)

- Recorded clocks, seeded randomness -> any session replayable.
- Tests co-located under `hedge_fund/`, run `poetry run pytest hedge_fund -q`.
- Change is done when full suite passes, or each remaining failure individually evidenced as unchanged baseline (test ID, expected/observed, platform, timestamp, repro on pre-change revision). Inconclusive suite != pass.
- Full suite MUST finish under 10 minutes on the dev machine. Any test file over 60s is marked slow and investigated. Targeted per-file runs = dev loop; full suite = merge gate.
- Why: evidence rule is scar tissue from real false-green claims. Budget stops suite re-bloat (was ~40 min).

### VI. Thin interfaces over one core (MUST)

- Three surfaces, all thin, zero duplicated logic:
  - CLI (`aihf`) — terminal use
  - MCP server — streamable HTTP transport, loopback, mounted on the FastAPI process; the operator-agent integration point
  - React web desk — journal, scorecard, news, discovery, persona briefs
- Textual TUI = RETIRED. Deleted via trim spec, no new investment.
- Why: operator uses CLI + MCP + web. Fourth surface = debt.

### VII. Simplicity budget (MUST)

- Ratchet until trim spec completes: dependency count and top-level package count may only go DOWN.
- Forever: any new top-level package, new dependency, or new infrastructure requires a spec section justifying its complexity; reviewer may block on it.
- Deleting code preferred over adding.
- Why: repo accumulated admission/handover/registry machinery outweighing product value. Operator: never again.

### VIII. Style (MUST)

- black line-length 420 (deliberate — do not reformat), isort black profile, flake8.
- Never write UTF-8 BOM into YAML or spec files.

## Technology Stack

- Python 3.11 + Poetry (`pyproject.toml` = single source of truth).
- Core libs: pandas, numpy, pydantic, pyyaml, rich, yfinance, feedparser, edgartools.
- No LLM client libraries (Principle II). No paid data clients (Principle IV).
- Frontend: React 19 + Vite + Tailwind + Radix/CVA (shadcn-pattern) + lucide; pnpm (migrated inside web-trim spec); Vitest + Playwright.
- Server: FastAPI + uvicorn — serves web static, REST API, and MCP endpoint on one loopback port.
- Deployment: single Docker container, explicit `/data` volume, loopback binding by default.
- Data root: operator-chosen dir (`--root` / `AIHF_ROOT`), bind-mounted from a Nextcloud-synced host folder (Principle III single-writer rule applies).
- OS: Windows-first dev (PowerShell scripts); Linux containers for deployment; suite evidence on both where feasible.

## Development Workflow

- Feature work follows spec-kit: specify -> plan -> tasks -> implement -> QA review.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, ...). PRs target `main`.
- Full-suite evidence per Principle V before merge, including the 10-minute budget.
- Constitution supersedes all other practices, templates, and habits. Conflict -> constitution wins.
- VISION.md and ROADMAP.md MUST be rewritten to match v2.0.0 (see Sync Impact Report TODOs).

## Governance

- Amendments need a spec under `specs/` plus Principle V evidence, or an explicit operator-directed governance amendment recorded in this section.
- Versioning semver: MAJOR = principle removal/redefinition; MINOR = new principle/section; PATCH = clarification.
- Every PR review verifies principle compliance; complexity challenged per Principle VII.
- Historical record: 2026-10-31 web-migration amendment SUPERSEDED (direction dead: web stays but trimmed; no engine migration).

**Version**: 2.0.0 | **Ratified**: 2026-11-27 | **Last Amended**: 2026-11-27