# Implementation Plan: Curated Financial News Aggregation

**Branch**: `cgjedrem-news-aggregation-speckit` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-curated-news-aggregation/spec.md`

## Summary

Deliver a manually refreshed, curated financial-news capability using a reviewed CC0-registry baseline, official company IR and Fed/SEC/BLS/BEA feeds, and EDGAR Tools filings/8-K metadata. A guarded bounded transport and feedparser normalize inert metadata into one atomic root-local store with stable deduplication, all-source attribution, publication/fetch timestamps, and explicit source health. An outer `CuratedNewsDataClient` replaces only analyst `get_news` with deterministic persisted retrieval; all other providers and ledger/broker behavior remain unchanged.

Gate 1 received explicit user approval on 2026-11-25. Implementation and dependency edits may proceed under the approved contracts and deterministic offline test plan. Live retrieval remains outside acceptance testing, and PR creation still requires a separate explicit request.

## Technical Context

**Language/Version**: Python 3.11, Pydantic 2, existing Windows PowerShell/Poetry tooling.

**Primary Dependencies**: Existing `httpx`, root/runtime dispatch, and Rich CLI; new exact direct dependencies `feedparser==6.0.14` and `edgartools==6.4.0`, with Poetry lock updates only during approved implementation.

**Storage**: Canonical UTF-8 JSON at root-relative `cache/news/state.json`, atomically committed through `RootContext`, writer admission, and `paths.write_atomic`; versioned packaged source catalog at `hedge_fund/news/catalog.json`.

**Testing**: pytest with committed RSS/Atom/EDGAR fixtures, fake transports/parser workers, controlled DNS and clocks, no real sleep/network/paid calls, and temporary synthetic roots only.

**Target Platform**: Existing supported local NTFS Windows and ext4 Linux roots; CLI, paper scheduled runner, and web-service composition. No new hosted service or UI.

**Project Type**: Library/service capability integrated into the existing Python CLI, analyst data client, scheduled runner, and web backend.

**Performance Goals**: Bound a run to 100 sources, 4 concurrent sources, 1 request per host at a time, 500 requests, and a 120-second overall deadline; complete 50-source scheduling tests using recorded time with no actual delay.

**Constraints**: Explicit reviewed HTTPS hosts and redirect origins; global-address DNS validation pinned to each actual connection; descriptive SEC identity; no ambient proxies/automatic redirects; compressed/decompressed/entry limits; no Yahoo, irrelevant blogs/podcasts, article-body retrieval, runtime crawler, paid credentials, unattended loop, or real-root tests.

**Scale/Scope**: Small reviewable source catalog, durable item history, latest 100 run summaries, existing eight-headline analyst context. Price/fundamental-provider replacement, source-management UI, automatic scheduling, retention deletion, and full-text archival are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-research gate

**PASS — ratified constitution 1.1.0.** Initial design identified root-local atomic persistence, synthetic-root offline tests, deterministic normalization/rendering, and explicit SEC/network controls. No ledger or live-trading change, real external test request, or unbounded refresh was proposed. Research was limited to primary-source documentation and did not modify production code.

### Post-design gate

**PASS — Principle I: ledger and live-trading integrity.** No ledger schema, writer, migration, trading decision, or broker/live path is changed. News is read-only analyst context. Existing ledger and behavior suites remain required regression evidence.

**PASS — Principle II: paper-only operations and root containment.** News state lives below the selected root and uses existing root identity, writer admission, and atomic replace. The new refresh is a finite free-data operation with operation-bound authority; no daemon or live broker access is added. Only synthetic temporary roots are valid test targets.

**PASS — Principle III: test-first evidence and controlled tests.** The quickstart defines catalog/parser/normalizer, security, scheduling, persistence, composition, and end-to-end acceptance tests before implementation. All are deterministic and offline. No real sleeps, DNS, sockets, paid calls, or real desk-root access are permitted.

**PASS — Principle IV: deterministic pipeline and point-in-time behavior.** Sorted source plans, stable identity/aliases, explicit merge rules, canonical JSON, and injected clocks are specified. Existing seven-day/eight-headline rendering and future/undated filtering remain intact. Price/fundamentals/raw-provider behavior is delegated unchanged.

**PASS — Principle V: multi-surface configuration and scheduled governance.** The two new commands share the same service and catalog. No mandate/fund configuration divergence or new web configuration is introduced. Production CLI, owned-runner, and web analyst composition use the same local reader; scheduled runners perform no additional news network calls and retain free/local provider constraints.

**PASS — Principle VI: maintainability and security discipline.** The feature is isolated in `hedge_fund/news`, reuses existing dispatch/root boundaries, pins new dependencies, and includes focused offline tests. Python changes must use Black line length 420, isort Black profile, flake8, and UTF-8 without BOM. No complex gate exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/010-curated-news-aggregation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── contracts/
    ├── catalog-v1.schema.json
    ├── catalog-contract.md
    ├── refresh-contract.md
    └── retrieval-contract.md
```

`tasks.md` is deliberately not created by Gate 1 planning.

### Source Code (planned changes, repository root)

```text
hedge_fund/
├── news/
│   ├── __init__.py              # Narrow public exports
│   ├── catalog.json             # Reviewed source definitions/provenance
│   ├── models.py                # Catalog/item/health/run/limit models
│   ├── catalog.py               # Strict loading, semantic approval, digest
│   ├── normalize.py             # Inert text, timestamps, URL/title keys
│   ├── parsing.py               # Bytes-only feedparser adapter
│   ├── filings.py               # Guarded SEC retrieval/offline metadata adapter
│   ├── edgar_worker.py          # Audited root-confined EDGAR parser process
│   ├── transport.py             # Guarded SEC JSON and feed retrieval
│   ├── refresh.py               # Finite scheduler/coordinator and outcomes
│   ├── store.py                 # Root-local query and atomic transactions
│   ├── client.py                # DataClient news overlay/delegation
│   ├── fixtures/                # Committed synthetic RSS/Atom/EDGAR bytes
│   └── test_*.py                # Focused offline tests beside modules
├── data/
│   └── models.py                # Additive optional CompanyNews provenance
├── runtime/
│   ├── endpoints.py             # Exact-origin curated-news target validation
│   ├── policy.py                # Free-data curated-news classification
│   └── owned_runner_child.py    # Offline reader composition only
├── web/
│   └── services.py              # Production local-news adapter composition
└── run.py                       # News commands and CLI composition

pyproject.toml                  # Approved pinned dependencies/package data only
poetry.lock                     # Reproducible transitive lock update
```

**Structure Decision**: Use one `hedge_fund/news` package to isolate source curation, untrusted parsing, secure retrieval, durable state, and the analyst adapter. Extend existing composition and security enforcement points rather than create a parallel network or persistence stack. Test fixtures and tests remain beside the package, consistent with repository convention. No frontend, API route, separate application, database service, or task artifact is added.

## Design References

- [Phase 0 research](research.md): source evidence, dependency versions, decisions, alternatives, and defaults.
- [Phase 1 data model](data-model.md): entities, validation, merge rules, health transitions, persistence invariants.
- [Catalog contract](contracts/catalog-contract.md) and [JSON Schema](contracts/catalog-v1.schema.json): reviewable source approval boundary.
- [Refresh contract](contracts/refresh-contract.md): CLI, limits, transport, EDGAR, and store interfaces.
- [Retrieval contract](contracts/retrieval-contract.md): additive `CompanyNews`, composition, point-in-time and health semantics.
- [Offline quickstart](quickstart.md): focused and full verification with acceptance scenarios.

## Complexity Tracking

None. The post-design constitution check has no violations requiring justification.
