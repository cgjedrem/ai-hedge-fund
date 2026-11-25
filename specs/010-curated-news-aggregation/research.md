# Phase 0 Research: Curated Financial News Aggregation

**Date**: 2026-11-25
**Specification**: [spec.md](spec.md)

## Source and dependency decisions

### Curated registry baseline

- **Decision**: Use `plenaryapp/awesome-rss-feeds` only as a review queue. Pin the initial review to commit `9ab2482cae9031a5a39635c887fcfc8ece7e130a`; record the source OPML path and original `xmlUrl` on every catalog entry derived from it. Registry membership never enables a source.
- **Rationale**: The repository and its `LICENSE` identify CC0-1.0, and its OPML files provide a useful candidate inventory. The Business & Economy and Personal finance lists also contain Yahoo, podcasts, YouTube, consumer blogs, aggregators, and feeds with restrictive descriptions, so bulk import is incompatible with the specification.
- **Alternatives considered**: Wholesale OPML import and runtime discovery were rejected because they bypass editorial, rights, and host review. Vendoring the registry was rejected as unnecessary; stable provenance and per-entry evidence are sufficient.
- **References**: [repository metadata](https://api.github.com/repos/plenaryapp/awesome-rss-feeds), [CC0 license](https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/LICENSE), [recommended categories](https://api.github.com/repos/plenaryapp/awesome-rss-feeds/contents/recommended/with_category), [pinned review commit](https://github.com/plenaryapp/awesome-rss-feeds/commit/9ab2482cae9031a5a39635c887fcfc8ece7e130a).

### Initial official-source seed

- **Decision**: Ship a small JSON catalog with reviewed Federal Reserve, BLS, BEA, and SEC releases enabled, plus official AMD and NVIDIA investor-relations candidates disabled until an operator selects their tickers. Tests use separate synthetic company fixtures. The implementation may add independently reviewed editorial entries only with their own evidence and rights review.
- **Rationale**: These sources cover all required official authorities without pretending that example companies are the user's portfolio. Company enablement is an explicit catalog change with ticker and CIK binding. No Yahoo, podcast, consumer blog, or unreviewed registry entry is present.
- **Alternatives considered**: Enabling arbitrary popular tickers or importing all official feeds would create irrelevant traffic and results. Autonomous IR discovery was rejected because it becomes crawling and cannot establish approval.
- **Initial endpoints**:
  - Federal Reserve: `https://www.federalreserve.gov/feeds/press_all.xml` and `press_monetary.xml`; optional reviewed `speeches.xml`, `testimony.xml`, `h15.xml`, `h41.xml`, and `prates.xml` remain disabled unless needed.
  - BLS: `https://www.bls.gov/feed/bls_latest.rss`, with focused `empsit.rss`, `cpi.rss`, `ppi.rss`, `jolts.rss`, `eci.rss`, `ximpim.rss`, and `realer.rss` candidates.
  - BEA: `https://www.bea.gov/rss`, discovered from the official BEA site; its response was identified as RSS, but future live liveness verification is not an acceptance-test requirement.
  - SEC releases: `https://www.sec.gov/news/pressreleases.rss` and `https://www.sec.gov/news/speeches-statements.rss`.
  - Company candidates: AMD `https://ir.amd.com/news-events/press-releases/rss`, declared by an official RSS alternate link; NVIDIA `https://investor.nvidia.com/rss/pressrelease.aspx` and the officially linked `https://nvidianews.nvidia.com/cats/press_release.xml`, all disabled by default.
- **References**: [Fed feed index](https://www.federalreserve.gov/feeds/feeds.htm), [BLS feed index](https://www.bls.gov/feed/), [BEA RSS](https://www.bea.gov/rss), [SEC feed index](https://www.sec.gov/about/rss-feeds), [AMD IR](https://ir.amd.com/), [NVIDIA IR feed index](https://investor.nvidia.com/investor-resources/rss/default.aspx).

### Feed parsing

- **Decision**: Add exact direct dependency `feedparser==6.0.14`. Fetch bytes with the guarded application transport and call `feedparser.parse(response_bytes)` only. Parse no URL, path, file object, or article link through feedparser.
- **Rationale**: Version 6.0.14 supports Python 3.11, is BSD-2-Clause licensed, accepts raw response bytes, and sanitizes common HTML fields. Application-level byte and entry bounds are still required. Plain-text declarations and sanitizer gaps mean parsed fields remain untrusted.
- **Alternatives considered**: Feedparser's URL-loading behavior was rejected because it bypasses dispatch, DNS pinning, timeouts, and size controls. A second XML parser was rejected as unnecessary. Blind acceptance of `bozo=1` was rejected: recoverable entry errors may be counted, but a feed-level malformed document is failed rather than called healthy-empty.
- **References**: [PyPI](https://pypi.org/pypi/feedparser/json), [parse inputs](https://feedparser.readthedocs.io/en/latest/introduction/), [sanitization](https://feedparser.readthedocs.io/en/latest/html-sanitization/), [bozo behavior](https://feedparser.readthedocs.io/en/latest/bozo/).

### SEC filings and 8-K releases

- **Decision**: Add exact direct dependency `edgartools==6.4.0` and lock its transitive dependencies. The parent retrieves the official `https://data.sec.gov/submissions/CIK##########.json` document through `GuardedNewsTransport`, with the validated SEC `User-Agent`. A short-lived isolated worker then uses EDGAR Tools' offline `extract_company_filings_table` / `create_company_filings` path to project `filings.recent` into `EntityFilings` / `EntityFiling` metadata. Only application-owned frozen `FilingRecord` values leave the worker. Configured forms, including `8-K`, are filtered from metadata; 8-K `items` labels come from the submissions metadata, not a downloaded current report.
- **Rationale**: This uses the user-selected EDGAR Tools normalization while preserving application-owned DNS pinning, redirect authorization, throttling, and byte limits. Pinned source inspection found no supported synchronous client/transport injection in 6.4.0: its import-time `HTTP_MGR` builds its own `httpx` client, reads ambient proxy configuration, and creates cache/migration directories. Its `Company.get_filings` path can load further submissions, and `CurrentReport`/`filing.obj()` downloads and parses the filing document. Therefore package networking is not used at all.
- **Worker containment**: Before importing `edgar`, a `python -I -B` worker installs a non-removable Python audit hook denying socket name resolution/connect/bind/send operations, child-process creation, and file/directory creation, mutation, deletion, or rename events outside its allocated run scratch directory. It receives a minimal proxy-free environment with `EDGAR_LOCAL_DATA_DIR`, `EDGAR_CACHE_DIR`, and `EDGAR_IDENTITY` set to root-local values before import; local storage remains disabled. The parent supplies bounded JSON on stdin, applies source/deadline limits, bounds stdout/stderr, and accepts only typed normalized output. Package import may create its known cache/migration directories only under that scratch root. A contract test must prove the pinned offline parser path and denial hooks; any mismatch fails that SEC source closed.
- **Metadata limits**: Process only `filings.recent`; do not fetch `filings.files` pagination in v1. Never call `EntityData.get_filings` with full loading, `filing.obj()`, `CurrentReport`, `text()`, `markdown()`, `html()`, `header`, or `attachments`. Build the official filing-index link from CIK/accession without fetching it. Treat `acceptanceDateTime` as precise only when it has an explicit valid zone/offset; otherwise retain `filingDate` as date-only and leave precise publication unknown. EDGAR Tools notes that legacy 1999–2011 `items` metadata can be inaccurate, so no document-based repair is attempted.
- **Alternatives considered**: Replacing `HTTP_MGR` or `_get_transport` was rejected because these are private APIs and cannot guarantee that every cached import, redirect, proxy, DNS connection, and disk writer is covered. In-process global socket/environment monkeypatching was rejected because it could affect unrelated providers. Application-only field mapping without EDGAR Tools was rejected because the user explicitly required EDGAR Tools. Scraping filing documents and unbounded historical pagination are outside content and run scope. A latest-floating dependency was rejected because the parser/import boundary must be reproducible.
- **References**: [PyPI](https://pypi.org/pypi/edgartools/json), [pinned v6.4.0 source](https://github.com/dgunning/edgartools/tree/v6.4.0), [offline submissions table/filings construction](https://github.com/dgunning/edgartools/blob/v6.4.0/edgar/entity/data.py#L63-L138), [offline submissions parser](https://github.com/dgunning/edgartools/blob/v6.4.0/edgar/entity/data.py#L141-L200), [filing metadata objects](https://github.com/dgunning/edgartools/blob/v6.4.0/edgar/entity/filings.py#L34-L96), [import-time HTTP manager](https://github.com/dgunning/edgartools/blob/v6.4.0/edgar/httpclient.py#L545), [SEC submissions API](https://www.sec.gov/edgar/sec-api-documentation), [SEC fair-access policy](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

## Architecture decisions

### Refresh is a separate finite operation

- **Decision**: Add `aihf --root <root> --enable-network news refresh` for a one-shot refresh and offline `aihf --root <root> news status`. Analyst `get_news` never performs network I/O. Initial scope has no automatic scheduler; scheduled paper runners only read committed local news.
- **Rationale**: This prevents an analyst prompt or backtest from unexpectedly triggering many publishers and avoids an unattended loop. Existing `--enable-network` and one-shot dispatch remain meaningful. A manual selection may include source IDs and configured tickers; an empty selection is a successful no-op with zero calls.
- **Alternatives considered**: Fetch-on-read and per-runner background refresh were rejected because they conflate analysis with retrieval and multiply network calls. A new daemon was explicitly excluded by the specification.

### Operation-bound provider authorization

- **Decision**: Introduce free-data provider identity `curated-news`. Materialize one immutable `ProviderTarget(kind="data", provider="curated-news", endpoint="https://<host>")` per explicitly approved origin, including every permitted redirect origin. Bind the complete sorted source plan, catalog digest, deadlines, and call/resource limits into a one-shot operation. Each redirect hop must consume authorization for its own matching target.
- **Rationale**: Existing target identity already includes the normalized endpoint. Extending endpoint validation for this provider to require an explicit origin-only endpoint lets the fixed target set act as the host allowlist without a mutable global bypass. `ProviderDispatch` still reserves every call, disables ambient proxies, and binds DNS validation to the connection.
- **Alternatives considered**: A wildcard `curated-news` remote-host rule was rejected because it would authorize arbitrary hosts. Bypassing dispatch for feedparser or EDGAR Tools was rejected. Adding scheduled refresh to the paper-runner authority was deferred because no scheduler is required for the initial capability.

### Guarded transport and bounded execution

- **Decision**: Reuse `ProviderDispatch.authorize_transport`, `validate_request_url`, `resolve_destination`, and the DNS-pinned `httpx` client. Use manual redirects (`follow_redirects=False`, `trust_env=False`), streaming byte limits, injected clocks/waiters/resolvers, a shared global semaphore and per-host scheduler, and finite per-source/run request budgets.
- **Rationale**: These are the repository's existing enforcement points. Revalidation at each hop closes redirect and DNS-rebinding gaps. A single host key shares cadence across all its sources. The refresh coordinator sorts source IDs before submission and commit so completion timing cannot change persisted output.
- **Alternatives considered**: A new raw `requests`/HTTP client was rejected. Automatic redirects and `httpx` defaults were rejected because proxy use and redirect reauthorization would be ambiguous. Unbounded retries were rejected; initial scope performs no automatic retry after a failure.

### Default limits

- **Decision**: Centralize immutable `RefreshLimits` defaults and permit only stricter operator overrides: at most 100 selected sources, 4 global concurrent sources, 1 concurrent request per host, 1.0 second between request starts on a host, 5-second connect, 15-second read, 30 seconds per source, 120 seconds per run, 3 redirects, 500 requests and 500 resources per run, 2 MiB compressed response bytes, 5 MiB decompressed bytes, and 500 entries per feed. SEC sources also remain below SEC's published 10-requests-per-second maximum; the shared 1-second default is deliberately more conservative.
- **Rationale**: Finite defaults make the workload reviewable and testable. Redirects count against both the per-source and aggregate request limits. An overall deadline prevents new work; in-flight work retains its slot until its guarded operation has actually stopped.
- **Alternatives considered**: Unlimited or per-source independent throttles were rejected. Parallel requests to one host were rejected as the default. Conditional requests using persisted ETag/Last-Modified are a later optimization, not required for correctness.

### SEC identity

- **Decision**: Read `HEDGE_FUND_NEWS_SEC_IDENTITY` only for an SEC-bearing refresh. Require a descriptive organization/application name plus a syntactically valid contact email or URL, reject known placeholders and generic library defaults, and never commit a real operator identity. Do not print the value in status, errors, or run reports. Validate the outgoing SEC `User-Agent` at the transport boundary.
- **Rationale**: SEC fair access requires a declared `User-Agent`, exemplified as `Sample Company Name AdminContact@example.com`, and publishes a maximum of 10 requests per second. Missing identity fails before any SEC request; non-SEC sources may still run only when the selected plan contains no SEC source.
- **Alternatives considered**: Anonymous requests, a repository-owned fake contact, or per-source conflicting identities were rejected. Secrets are neither required nor accepted for public feeds.

### Root-local durable store

- **Decision**: Persist one canonical UTF-8 JSON document at `cache/news/state.json`, with schema version, monotonically increasing local revision, items, identity aliases, per-source health, and a bounded tail of the latest 100 run summaries. Writes go through `paths.write_atomic` and the existing root/writer admission path. Readers validate the whole document and never modify it during retrieval.
- **Rationale**: A single small state commit gives all-or-nothing item/health transitions and straightforward interruption/retry behavior. It avoids a new database service and un-routed SQLite writes. Item history remains; run-summary trimming prevents unrelated operational growth. The existing `CachedDataClient` response cache is not a news store.
- **Alternatives considered**: Per-source files were rejected because cross-source dedupe and health would need multi-file transactions. Direct writes and an unintegrated SQLite database were rejected because they bypass root governance. In-memory-only state failed the restart requirement.

### Legacy analyst integration

- **Decision**: Add `CuratedNewsDataClient` as the outermost decorator: `CuratedNewsDataClient(CachedDataClient(raw), store)`. Override only `get_news`; delegate every other method unchanged. Apply it at production CLI, owned-runner, and web composition points. Explicitly injected test/custom data-client factories retain their existing behavior unless they opt into the wrapper.
- **Rationale**: Placing the decorator outside the legacy cache prevents its wall-clock ten-minute TTL from hiding source health or duplicating curated records. The narrow adapter preserves price, fundamentals, filings, earnings, and all non-news behavior. Scheduled runners no longer call Yahoo through `get_news`; they read the local store without adding refresh calls to runner authorization.
- **Alternatives considered**: Extending `CachedDataClient` with durable merging was rejected because its provider/method/parameter cache has different semantics. Replacing the raw provider factory was rejected because it would affect unrelated market data. Rewriting downstream analyst agents was rejected; they continue to consume `NewsContext`.

### Compatibility and relevance

- **Decision**: Preserve the existing `CompanyNews` fields and their meanings. Add only optional metadata (`news_id`, `fetched_at`, `category`, `attributions`, and `source_state`) with backward-compatible defaults. Keep richer health/run queries on the curated client/store. Existing `NewsContext` still filters undated/future items, takes eight headlines, sorts deterministically, and renders only title/date/source/link.
- **Rationale**: Existing serialized records and injected clients remain valid. Provenance is available at the data boundary without changing ledger contracts or adding fetch timestamps to prompts. Additive news results may change a prompt only when the actual headline set changes.
- **Alternatives considered**: Replacing `CompanyNews` with the storage model was rejected. Putting health prose into every prompt was rejected because it would create unrelated model and cache churn. Returning storage dictionaries was rejected in favor of typed models.
- **Relevance rule**: A source entry declares either explicit ticker/CIK bindings or `market` scope. General editorial entries are associated only through reviewed company aliases matched against feed title/summary; no LLM or article-body enrichment is used. Market-scoped macro/regulatory items are available to company queries through the adapter and through a rich macro query. Ties sort by UTC publication time, normalized canonical URL, then stable news ID; undated records sort last in rich retrieval and are still dropped by existing prompt rendering.

## Normalization and health decisions

### Canonicalization and deduplication

- **Decision**: Normalize HTTPS scheme and IDNA host casing, remove fragments, user information and default port 443, normalize percent-encoding of unreserved characters and dot segments, and remove only known tracking parameters (`utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, `igshid`). Preserve non-tracking query names, values, order-sensitive paths, and trailing slashes except the empty/root form. Normalize titles with HTML-to-text, Unicode NFKC, whitespace collapsing, and casefolding for comparison; retain the cleaned display title.
- **Rationale**: These transformations remove common syndication noise without disguising a different endpoint. The original approved link remains available in each attribution. No link is fetched during normalization.
- **Alternatives considered**: Aggressive removal of all queries, trailing slashes, punctuation, or stop words was rejected as semantic loss. Similarity/LLM matching was rejected as non-deterministic and prone to false merges.

### Stable identity and conservative merging

- **Decision**: Prefer SEC accession identity, then normalized URL. Merge equal normalized URLs. A title match may merge distinct links only when normalized title, UTC publication minute, and at least one explicit ticker/market association match and neither side supplies a conflicting SEC accession or source-native GUID. Missing/ambiguous timestamps cannot support cross-link title merging. Sort refresh results before matching; retain an existing item ID on repeat, choose the lexicographically smallest existing ID when clusters join, and retain aliases to absorbed IDs.
- **Rationale**: URL identity handles ordinary duplicates; the additional evidence makes title-based syndication merging useful without merging same-titled distinct events. Persistent aliases make retries and cluster joins idempotent.
- **Alternatives considered**: Title-only matching was rejected because different stories share headlines. Never merging distinct URLs failed the cross-source dedupe requirement. Random UUIDs and completion-order IDs were rejected as non-deterministic.

### Content rights and safety

- **Decision**: Store feed-supplied title, sanitized plain-text summary, timestamps, metadata, attribution, and links only. Strip markup/entities to text, cap display fields, render summaries as inert text, and never retrieve images, scripts, iframes, enclosures, article bodies, or links discovered inside content. Record the evidence for using summaries per source; absent rights evidence disables summary retention while title/link metadata remains.
- **Rationale**: Feed sanitization is not a rendering or rights boundary. The feature does not assume that CC0 registry metadata licenses publisher articles.
- **Alternatives considered**: Full-text extraction, HTML persistence, and active preview generation were rejected. Treating registry CC0 as publisher-content rights was explicitly rejected.

### Health and failure semantics

- **Decision**: Health states are `disabled`, `never-run`, `healthy`, `healthy-empty`, `degraded`, and `failed`. `stale` is a separate age evaluation using the source's declared freshness interval and injected query clock; it never erases the last committed outcome. Record last attempt/success, last publication, accepted/rejected counts, consecutive failures, and a bounded sanitized reason code. Failed refresh leaves old items queryable; successful empty is distinct from malformed zero-entry output.
- **Rationale**: One enum cannot faithfully express both the latest transport result and freshness. Partial success is visible per source and in the run's aggregate status. Secrets, URLs with queries, response bodies, and operator contact values are excluded from diagnostics.
- **Alternatives considered**: Deleting items on failure, treating every exception as empty, and using wall-clock reads inside tests were rejected.

## Test strategy

- **Decision**: Use pytest with committed RSS/Atom/EDGAR fixture bytes, fake guarded transports, scripted redirects/DNS answers, fake monotonic/wall clocks and waiters, a recording executor, and temporary synthetic roots. No test performs DNS, socket HTTP, real sleep, paid calls, or reads a real desk root.
- **Rationale**: Every acceptance criterion can be exercised through deterministic contracts: parser/normalizer unit tests, store interruption/retry tests, refresh event-log tests, security denial tests before a fake connection, composition tests, and existing feature/ledger regression tests.
- **Alternatives considered**: Live feed smoke tests and timing-based `sleep` tests are not acceptance evidence. Any future operator-requested live check is a separate manual action with explicit SEC identity and bounded source selection.

## Gate 1 conclusion

All specification-level choices are resolved. Implementation remains gated on explicit approval. The parent owns every SEC HTTP request; EDGAR Tools 6.4.0 is confined to the audited offline parser worker. The pinned parser, socket/process denial, and root-local import-side-effect contracts must pass before SEC fixture refresh is enabled. Any mismatch is a blocking implementation defect, not permission to enable package networking or bypass policy.
