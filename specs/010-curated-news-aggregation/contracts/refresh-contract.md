# Refresh, Transport, and Persistence Contracts

These are internal Python and CLI contracts. The feature exposes no new web API and creates no background service.

## CLI

### Bounded refresh

```text
aihf --root <synthetic-root> --enable-network news refresh
    [--source <source-id>]... [--ticker <ticker>]... [--json]
```

- `--enable-network` and the repository's existing operation-bound dispatch are mandatory. The command does not authorize paid providers.
- No selectors means all enabled sources. Repeated `--source` selects exact enabled source IDs. `--ticker` selects enabled company sources bound to that ticker, including its configured SEC EDGAR source; it does not discover sources or expand the catalog.
- Unknown/disabled explicit selections fail validation rather than silently fetching an unreviewed source. Selecting no enabled sources is a `no-op` with zero provider calls.
- A plan containing any SEC source requires `HEDGE_FUND_NEWS_SEC_IDENTITY` before dispatch construction. Identity failure aborts the entire selected plan before any request, including non-SEC requests.
- The resolved plan, catalog digest, source URLs and approved origins, exact limits, operation ID, and expiry are frozen before work. Calls/resources have zero monetary cost and finite upper bounds.
- Output is a sanitized run summary or per-source table. `--json` is stable, sorted JSON suitable for automation. Neither output contains the SEC identity, response body, arbitrary exception text, URL credentials, or query strings.
- Exit `0`: all selected sources succeeded (including healthy-empty) or the plan was a no-op. Exit `1`: any selected source failed, the run was partial, or persistence conflicted. Exit `2`: invalid invocation, catalog, identity, or authorization before retrieval.

### Offline health

```text
aihf --root <synthetic-root> news status [--source <source-id>]... [--json]
```

Reads only `cache/news/state.json`; it neither requires nor consumes dispatch authority and never opens a network client, even if a caller supplied `--enable-network`. It reports enabled/disabled state, last attempt/success/publication, accepted/rejected/stored counts, freshness, and sanitized reason. Unknown sources are reported as absent, not fetched. Exit `0` for a readable store even when a source is failed/stale; exit `1` for corrupt/unreadable state; exit `2` for an invalid selector or invocation.

## Refresh service

```python
class NewsRefresher(Protocol):
    def refresh(self, request: RefreshRequest) -> RefreshRun: ...
```

`RefreshRequest` contains the selected immutable catalog/source IDs, `RootContext`, a preauthorized `ProviderDispatch`, resolved `RefreshLimits`, UTC wall clock, monotonic clock, waiter, resolver, and transport/filing-provider factories. Production defaults are finite; tests supply all time and I/O fakes. The SEC identity is supplied to the adapter through a redacting configuration object and is never part of `RefreshRun`.

`RefreshLimits` fields and defaults:

| Field | Default | Hard boundary |
|---|---:|---:|
| `max_sources` | 100 | 100 selected per run |
| `global_concurrency` | 4 | May be lowered, not raised above 4 |
| `per_host_concurrency` | 1 | May be lowered only; initial implementation therefore always 1 |
| `minimum_host_interval_seconds` | 1.0 | May be increased; no source can lower below 1.0 |
| `connect_timeout_seconds` | 5 | Finite; maximum 5 |
| `read_timeout_seconds` | 15 | Finite; maximum 15 |
| `source_deadline_seconds` | 30 | Finite; maximum 30 |
| `run_deadline_seconds` | 120 | Finite; maximum 120 |
| `max_redirects` | 3 | Per request chain, maximum 3 |
| `max_source_requests` | 20 | Includes redirects and EDGAR requests |
| `max_run_requests` | 500 | Shared dispatch reservation maximum |
| `max_compressed_bytes` | 2 MiB | Per response, actual streamed bytes |
| `max_decompressed_bytes` | 5 MiB | Per response, actual decoded bytes |
| `max_entries` | 500 | Per parsed feed/filing response |

The sum of selected per-source maxima must fit aggregate dispatch reservations before starting. EDGAR pagination/request counts are included. No automatic retries occur in v1. An explicit new invocation is required.

Concurrency and cadence are controlled by shared scheduler state, not independent per-source sleeps. All request starts and ends append to an event record in tests. The deadline gate is checked before scheduling, before each redirect/request, after resolution, and before persistence. A worker slot is not released until its transport call has stopped. The coordinator never begins late work.

## Guarded feed transport

```python
@dataclass(frozen=True)
class FetchRequest:
    source_id: str
    url: str
    accepted_media_types: tuple[str, ...]
    sec_identity_required: bool

@dataclass(frozen=True)
class FetchResponse:
    final_url: str
    status_code: int
    media_type: str | None
    content: bytes
    redirect_count: int

class GuardedNewsTransport(Protocol):
    def fetch(self, request: FetchRequest) -> FetchResponse: ...
```

Contract:

1. Only GET is used. Headers are bounded; ambient proxy configuration and environment credentials are ignored.
2. Every URL/hop must match an exact frozen provider target, HTTPS and port 443, with no credentials, fragment, secret query, or unapproved host/port.
3. Every DNS answer must be a valid global unicast address; mixed public/private answers fail. The selected validated address is pinned to the actual socket. Re-resolution or redirect invalidates the old pin.
4. Redirects are manual, bounded, and limited to 301/302/303/307/308 with a valid Location. Each hop consumes call/resource authority, uses the same host scheduler, and repeats all checks. Other 3xx responses fail.
5. SEC requests carry the validated descriptive identity. The adapter checks the actual outgoing header, not merely a configuration value.
6. Timeouts cover connection and reads; the request cannot outlive its source/run authority. Content-Length and actual streamed compressed/decompressed counts are bounded. Oversize or invalid compressed content fails before parser invocation.
7. Only expected RSS/Atom/XML or SEC adapter media types are accepted. A successful HTTP status alone is not a healthy parse.
8. `FeedSource` passes returned content through a bytes-backed `BytesIO` stream to `feedparser.parse`; no parser call receives a URL, filesystem path, or raw bytes that feedparser could reinterpret as a path. Article, enclosure, image, and embedded-content URLs are never passed back to transport.

Typed failures include `DestinationDenied`, `RequestTimeout`, `ResponseLimitExceeded`, `InvalidResponse`, and `AuthorizationDenied`. They map to bounded reason codes without raw response text.

## EDGAR Tools offline adapter

```python
class EdgarFilingProvider(Protocol):
    def get_filings(self, source: SourceDefinition, *, limit: int) -> Sequence[FilingRecord]: ...

class EdgarSubmissionParser(Protocol):
    def parse(self, source: SourceDefinition, document: bytes, *, limit: int) -> Sequence[FilingRecord]: ...
```

`EdgarFilingProvider` fetches exactly the source's reviewed `data.sec.gov/submissions/CIK##########.json` URL through `GuardedNewsTransport`, then gives those bounded bytes to `EdgarSubmissionParser`. The parent transport applies the validated descriptive SEC `User-Agent`; the package is never asked to retrieve a URL.

The concrete parser pins `edgartools==6.4.0` and runs in a fresh `python -I -B` worker. Before importing `edgar`, it installs a Python audit hook that denies socket resolution/connect/bind/send operations, child-process creation, and file/directory creation, mutation, deletion, or rename events outside the allocated root-local run scratch directory. A minimal environment has no proxies and sets `EDGAR_LOCAL_DATA_DIR`, `EDGAR_CACHE_DIR`, and `EDGAR_IDENTITY` before import so package initialization cannot prompt or write to a home cache. Local storage remains disabled. The parent holds writer admission for the scratch directory, bounds input/output and lifetime, and maps worker errors to sanitized reason codes without echoing its environment or contact identity.

The worker passes a defensive copy of `filings.recent` through the pinned `extract_company_filings_table` and `create_company_filings` functions, reads `EntityFiling` metadata, filters the source's explicit forms and bounds, and returns plain frozen `FilingRecord` JSON. It does not call `Company.get_filings`, `EntityData.get_filings`, `filing.obj()`, `CurrentReport`, or any text/markdown/HTML/header/attachment property. Only `filings.recent` is in scope; `filings.files` pagination is not fetched. Exceeding configured matching-entry limits fails the source explicitly rather than silently dropping filings.

A `FilingRecord` carries accession, form, filing date, optional explicitly zoned acceptance timestamp, report date, metadata `items` labels, primary-document description, file number, size, and an official filing-index URL constructed without retrieval. Ambiguous acceptance time remains date-only; legacy metadata is not repaired from documents. No raw EDGAR object, response body, contact value, or environment crosses the interface.

Pinned-version contract tests use committed submissions fixtures and prove parser output, blocked Python socket/child-process events, and confinement of import-time cache/migration writes to a temporary synthetic run directory. Any raw package network attempt, external write, unbounded pagination call, API mismatch, or malformed worker result fails that SEC source closed. No fallback package HTTP client is introduced.

## Persistence

```python
class NewsStore(Protocol):
    def load(self) -> NewsState: ...
    def query(self, query: NewsQuery) -> NewsPage: ...
    def health(self, source_ids: Sequence[str] | None = None) -> tuple[SourceHealthView, ...]: ...
    def commit(self, transaction: NewsTransaction) -> NewsState: ...
```

- Construction requires an open `RootContext`; all paths derive from `root.resolve("cache/news")`.
- `load` treats only a missing state file as empty. Corruption or unsupported schema raises `DataClientError`.
- `query` and `health` are read-only and need no dispatch. Freshness uses an injected clock.
- `commit` validates expected revision, run/source fences, canonical JSON, item invariants, and writer admission, then calls `paths.write_atomic` for `state.json`.
- One atomic replacement commits items, aliases, health, and run summary. The previous valid file remains on serialization/write/replace failure.
- Repeating a committed run ID is idempotent. Revision mismatch raises `NewsStoreConflict`; there is no silent lost update or automatic unbounded retry.

`NewsQuery` supports ticker, market inclusion, start/end dates, categories, source IDs, include-undated, and positive bounded limit. `NewsPage` contains deterministic items and distinct per-source health/freshness views, so an empty page can still distinguish `never-run`, `healthy-empty`, `failed`, and `stale`.
