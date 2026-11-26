# Offline Validation Quickstart

This guide applies after Gate 1 approval and implementation. Gate 1 itself changes no dependencies or production code. These commands must not be converted into live-feed smoke tests.

## Prerequisites

- Python 3.11 and Poetry, using the repository's normal environment.
- After the approved dependency-manifest change: `poetry install`.
- A pytest temporary root created by repository root fixtures. Never pass a real desk root or reuse `HEDGE_FUND_ROOT` from the operator environment.
- No SEC identity is needed for tests. Any identity-like fixture value is a reserved invalid example used only to prove placeholder rejection; valid identity tests use a clearly synthetic non-deliverable value through a fake config object.
- Network, DNS, wall-clock sleeping, and paid-provider calls are forbidden. The test suite installs socket/DNS denial guards and uses fake transports, resolvers, clocks, and waiters.

Contracts: [catalog](contracts/catalog-contract.md), [refresh/transport/store](contracts/refresh-contract.md), [retrieval](contracts/retrieval-contract.md). Entities and invariants: [data-model.md](data-model.md).

## Focused verification

Run the smallest relevant suites first:

```powershell
poetry run pytest -q hedge_fund/news hedge_fund/features/test_news.py hedge_fund/data/test_cached.py
poetry run pytest -q hedge_fund/runtime/test_dispatch.py hedge_fund/runtime/test_policy.py hedge_fund/runtime/test_owned_runner_child.py hedge_fund/runtime/test_admission.py hedge_fund/runtime/test_writer_inventory.py
```

Then run the full offline suite to prove unrelated provider, ledger, runner, web, and broker behavior is preserved:

```powershell
poetry run pytest -q
```

Formatting/static checks for changed Python files:

```powershell
poetry run black --check --line-length 420 hedge_fund/news hedge_fund/data/models.py hedge_fund/run.py hedge_fund/runtime hedge_fund/web/services.py
poetry run isort --check-only --profile black hedge_fund/news hedge_fund/data/models.py hedge_fund/run.py hedge_fund/runtime hedge_fund/web/services.py
poetry run flake8 --max-line-length 420 --extend-ignore=E203 hedge_fund/news hedge_fund/data/models.py hedge_fund/run.py hedge_fund/runtime hedge_fund/web/services.py
```

If `black` or `isort` reports unrelated pre-existing files in a broad directory, narrow the command to the files changed by this feature and record that baseline separately; do not reformat unrelated code.

## Acceptance scenarios

### 1. Representative end-to-end fixture refresh and restart

1. Load a synthetic catalog with one official IR feed, editorial feeds, SEC EDGAR filings/8-Ks, and Fed, SEC, BLS, and BEA feeds. Point every URL at reserved test names; map them to committed response fixtures.
2. Run `NewsRefresher.refresh` with fake transport/EDGAR provider and fixed clocks, then construct a new store and `CuratedNewsDataClient` against the same temporary root.
3. Query existing `get_news` and rich `NewsStore.query` for company and market scopes.
4. Assert every admitted item has title, approved canonical link, attribution, category, fetch timestamp, and either precise publication timestamp/date or explicit unknown. Check 8-K accession/form/items and official macro/regulatory classification.
5. Assert wrapped price/fundamental fakes receive exactly the same calls as an unwrapped client and no raw/Yahoo `get_news` call occurs.

**Expected**: all committed items survive restart, map to additive `CompanyNews`, and render through existing `NewsContext` with undated/future entries excluded. Metadata-only refresh does not change an unchanged prompt hash.

### 2. URL/title normalization and 100 idempotent refreshes

Use table-driven cases for Unicode/IDNA host and scheme casing, default ports, fragments, tracking parameters, encoded unreserved characters, dot segments, root trailing slash, meaningful query/path differences, HTML entities, whitespace, and missing/ambiguous zones.

1. Refresh the same representative fixtures 100 times, alternating process reader instances and equivalent URLs/titles.
2. Include same-title/different-event and same-title/conflicting-GUID records, a legitimate title edit on one URL, one story under several sources, and a filing repeated through two official routes.
3. Include an item with no publication time and an ambiguous-zone item; verify fetch time never replaces either.

**Expected**: one logical item per intended duplicate cluster, all attributions preserved, stable IDs/aliases, no distinct-event merge, byte-identical canonical state for identical ordered inputs, and no duplicate analyst results.

### 3. Partial failure and health transitions

Create at least 20 items across two independent sources. Script one source through success, healthy-empty, malformed response, timeout, and failure; keep the other healthy. Repeat with a write failure before atomic replacement and after a completed commit.

**Expected**: healthy items always commit; prior failed-source items remain; `healthy-empty`, `degraded`, `failed`, `stale`, and `never-run` are distinguishable; accepted/rejected/stored counts and sanitized reasons are accurate; a source never claims success for uncommitted work; retrying a committed run ID is idempotent; revision conflict cannot overwrite newer state.

### 4. Fifty-source bounded scheduling

Use 50 synthetic sources with multiple sources per host, scripted response completions, fake monotonic/wall clocks, and a waiter that advances recorded time without sleeping. Include slow, malformed, and empty sources and several EDGAR calls.

**Expected**: event logs prove at most the configured global and per-host concurrency, shared minimum request-start interval per host, finite connect/read/source/run deadlines, no late request starts, request/redirect/entry/byte caps, deterministic source-ID commit order, and a correct partial/success/failure aggregate. No real sleep occurs.

### 5. SSRF and redirect denial matrix

Before fake connection, attempt HTTP/non-HTTP schemes, URL userinfo, fragments, non-443 ports, credential-like query fields, unapproved hosts, wildcard/case/trailing-dot variants, IPv4/IPv6 literals and alternate notations, mapped addresses, private/loopback/link-local/multicast/reserved/unspecified addresses, mixed public/private DNS answers, DNS rebinding, and redirect changes to each variant.

Use redirect fixtures for allowed same-origin, separately approved cross-origin, missing target authorization, excessive hops, invalid Location, and unsupported status. Verify SEC header construction independently for missing, placeholder, malformed, valid synthetic, and transport-dropped identities.

**Expected**: every disallowed case is denied before content retrieval; every allowed hop gets a new reservation/DNS pin; no fallback client or ambient proxy is used; diagnostics contain no response body, contact identity, credential, or sensitive query.

### 6. Parser/content-rights boundaries

Use RSS and Atom fixtures containing valid entries, recoverable bad entries, malformed XML, `bozo` results, plain-text/HTML summaries, script/iframe/image/enclosure links, compressed bombs/oversize streams, excess entries, future/old dates, and false zero-entry responses. Wrap feedparser with a spy that records its input type.

**Expected**: feedparser receives a bytes-backed `BytesIO` stream, never a URL, filesystem path, or raw bytes it could reinterpret as a path; bad entries are isolated where safe; malformed/oversize/excess responses fail explicitly; output is bounded inert text; summary omission follows catalog policy; zero article/embedded-resource requests occur; no full filing text/markdown method is invoked.

### 7. EDGAR Tools 6.4.0 offline integration contract

Install the pinned package in the development environment. Supply committed submissions/8-K JSON through the recording guarded parent transport, then invoke the real isolated parser worker against a temporary synthetic root. Assert the parent applies the validated synthetic SEC identity and the worker receives bytes only. Exercise the worker's audit hook with denied socket-resolution/connect and child-process attempts that never reach a destination. Snapshot files before/after import and parsing, verify configured form/entry filtering, and exercise ambiguous acceptance timestamps and legacy `items` metadata without document retrieval.

**Expected**: EDGAR Tools returns the expected frozen filing metadata from `filings.recent`; no package HTTP method, raw socket, child process, home-cache write, `filings.files` pagination, or article/exhibit/full-document fetch occurs. Every package-created cache/migration path remains under the allocated synthetic run directory. A parser/API/audit mismatch fails that SEC source closed and blocks acceptance rather than enabling a package network fallback.

### 8. CLI and composition

Invoke the CLI `main` in-process with monkeypatched production factories and a temporary root:

- `news status` without network authority reads health and performs zero network construction.
- `news refresh` without `--enable-network` exits `2` before retrieval.
- An SEC plan without identity exits `2` before any selected non-SEC request.
- Valid fake refresh, no-op, partial failure, unknown source, corrupt store, and `--json` produce the documented exit codes and sanitized output.
- CLI, owned runner, and web production composition place the curated adapter outside the legacy cache. Injected custom clients retain their guard and current behavior.

**Expected**: scheduled-runner dispatch has no additional news call/target; analyst reads are offline; all non-news data methods delegate unchanged.

## Manual demonstration (still offline)

After the tests, an implementer may run the two CLI commands against a newly created synthetic root using fake provider factories in a test harness. Do not substitute a real root, real SEC contact, or actual publisher URL to make the demonstration more realistic. A separately approved live smoke test is outside this quickstart and not required for acceptance.
