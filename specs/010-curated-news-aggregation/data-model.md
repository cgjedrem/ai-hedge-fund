# Phase 1 Data Model

**Specification**: [spec.md](spec.md)
**Research**: [research.md](research.md)

All runtime models are immutable Pydantic 2 models except the explicitly mutable refresh coordinator and store transaction. Strings have bounded lengths; timestamps are UTC at the storage boundary. JSON uses canonical key ordering and UTF-8 without a BOM.

## Catalog models

### `CuratedCatalog`

| Field | Type | Validation |
|---|---|---|
| `schema_version` | integer | Exactly `1` |
| `catalog_id` | string | Stable safe identifier |
| `registry` | `RegistryProvenance` | Required even when no current entry came from the registry |
| `sources` | tuple[`SourceDefinition`, ...] | Unique IDs; no duplicate enabled `(kind, canonical URL, ticker/form binding)`; at most 100 enabled in a refresh plan |
| `digest` | derived SHA-256 | Hash canonical content excluding no security-relevant fields; never supplied by the file |

The catalog is packaged read-only data at `hedge_fund/news/catalog.json`, not root-editable runtime state. A source or redirect host is authorized only when represented in the validated selected plan and its frozen provider targets.

### `RegistryProvenance`

- `name`: literal `plenaryapp/awesome-rss-feeds`.
- `commit`: full lowercase Git commit SHA; initially `9ab2482cae9031a5a39635c887fcfc8ece7e130a`.
- `license`: literal `CC0-1.0`.
- `repository_url`: canonical HTTPS repository URL.
- `reviewed_on`: ISO calendar date.

Changing the commit requires reviewing changed candidate ownership, topics, URLs, hosts, and rights descriptions. Updating this metadata does not itself enable candidates.

### `SourceDefinition`

| Field | Type | Validation |
|---|---|---|
| `source_id` | string | Lowercase stable ID, unique across catalog |
| `kind` | enum | `feed` or `sec-edgar` |
| `publisher` | string | Human-readable reviewed authority/publisher |
| `category` | enum | `editorial`, `investor-relations`, `sec-filing`, `regulatory`, `macro` |
| `url` | HTTPS URL | Canonical feed or official source location; no credentials, fragment, secret query, or non-443 port |
| `enabled` | boolean | Only enabled sources enter a default refresh |
| `allowed_hosts` | tuple[hostname, ...] | Contains the URL host and every separately reviewed redirect origin; no wildcard, IP literal, or Yahoo host |
| `scope` | enum | `company` or `market` |
| `tickers` | tuple[string, ...] | Required nonempty for company scope, empty for market; uppercase canonical tickers |
| `cik` | ten-digit string or null | Required for `sec-edgar`; must agree with the single bound company |
| `forms` | tuple[string, ...] | `sec-edgar` only; bounded explicit SEC form allowlist, including `8-K` where configured; no `*` |
| `company_aliases` | tuple[string, ...] | Reviewed deterministic relevance aliases for editorial feeds; not arbitrary regex |
| `freshness_seconds` | positive integer | Drives stale evaluation; does not schedule polling |
| `limits` | `SourceLimits` or null | May only tighten global `RefreshLimits` |
| `curation` | `CurationEvidence` | Required approval and verification evidence |
| `summary_policy` | enum | `none` or `feed-supplied`; the latter requires summary-use evidence |

A company source is not inferred from a current portfolio at runtime. Operators add/enable its reviewed binding. Removing a ticker disables future selection but does not delete history.

### `CurationEvidence`

- `basis`: `registry-reviewed` or `independently-verified`.
- `registry_opml_path`, `registry_xml_url`: required for registry-derived entries; otherwise absent.
- `discovery_url`: official page or feed index supporting authenticity.
- `verified_on`: review date, not a claim of continuous liveness.
- `purpose`: bounded reviewed relevance statement.
- `rights_note`: bounded evidence for metadata/summary use; no assertion of article-body rights.
- `approved_by`: review identity or change reference supplied by the project, not a secret.

Catalog loading rejects unknown fields, malformed IDs/URLs, placeholder verification values, Yahoo hosts, invalid company/CIK/form combinations, redirect hosts not listed, and less restrictive per-source limits.

## Normalized news models

### `NewsItem`

| Field | Type | Rules |
|---|---|---|
| `news_id` | string | `news_` plus lowercase SHA-256; stable through aliases |
| `title` | string | Clean inert text, nonempty, bounded; no markup |
| `summary` | string or null | Clean inert feed-supplied text only; bounded and omitted when rights policy is `none` |
| `canonical_url` | HTTPS URL | Selected by stable attribution precedence; must remain on an approved host for at least one attribution |
| `category` | enum | Copied from canonical attribution's reviewed source |
| `tickers` | tuple[string, ...] | Sorted unique explicit associations; never inferred by an LLM |
| `market_scope` | boolean | True for configured market-wide relevance |
| `published_at` | UTC datetime or null | Set only when date/time and zone/offset are known |
| `published_on` | date or null | Set for date-only values; may accompany a precise timestamp for grouping |
| `publication_precision` | enum | `second`, `minute`, `day`, or `unknown` |
| `first_fetched_at` | UTC datetime | Earliest committed observation; immutable thereafter |
| `last_fetched_at` | UTC datetime | Latest committed observation; never substituted for publication time |
| `attributions` | tuple[`Attribution`, ...] | At least one; sorted and unique by source/native ID/normalized URL |
| `dedupe_keys` | tuple[string, ...] | Sorted URL/title/accession evidence used for future idempotent matches |

Raw source timestamps may be retained only as bounded attribution metadata for diagnosis; they are not parsed again during rendering and never enter active content. Future-dated entries beyond the allowed clock-skew bound are rejected. Extremely old entries may be retained but do not displace bounded current query results.

### `Attribution`

- `source_id`, `publisher`, and `category`: copied from the reviewed source, not feed-supplied identity claims.
- `original_id`: optional bounded source GUID or SEC accession; absence is explicit.
- `original_url`: optional original approved HTTPS link; never fetched as an article.
- `normalized_url`: optional canonical comparison form.
- `original_title`: cleaned title supplied by this source.
- `published_at`, `published_on`, `publication_precision`: source-specific observation, using the same rules as the item.
- `first_seen_at`, `last_seen_at`: distinct committed fetch timestamps.
- `sequence`: deterministic catalog precedence used for canonical selection.

Canonical attribution precedence is: exact official SEC accession record first for a filing; otherwise lowest reviewed `sequence`, then earliest source publication timestamp with unknown last, then normalized URL, then source ID. Existing canonical selection remains unless a higher-precedence attribution arrives. Every source remains visible even when not selected.

### Identity and merge rules

1. A normalized SEC accession is a strong key; conflicting accessions cannot be merged by title.
2. Equal normalized URLs merge regardless of title edits, preserving all titles as attribution evidence.
3. Different non-empty normalized URLs with no strong-key match merge by title only when normalized title, UTC publication minute, and at least one ticker or market association all match, and neither attribution has a conflicting source-native GUID.
4. A title fallback involving a missing URL uses the same timestamp/scope/conflict rules. Unknown or date-only publication does not support title-only merging.
5. Existing items are matched before new items. Refresh outputs are sorted by source ID, original ID, and normalized URL before matching.
6. Repeated matches retain the existing `news_id`. Joining two existing clusters chooses the lexicographically smallest ID and maps the other through `aliases`; no attributions are dropped.
7. `news_id` for a wholly new cluster is SHA-256 over the canonical strongest key of its deterministically first attribution. A later merge never renumbers retained history.

A merge conflict leaves records separate and increments a bounded diagnostic counter; it is not silently forced.

## Health and run models

### `SourceHealth`

| Field | Type | Meaning |
|---|---|---|
| `source_id` | string | Catalog identity |
| `enabled` | boolean | Snapshot of latest catalog/attempt state |
| `status` | enum | `disabled`, `never-run`, `healthy`, `healthy-empty`, `degraded`, `failed` |
| `last_attempt_at` | UTC datetime or null | Start of latest committed attempt |
| `last_success_at` | UTC datetime or null | Only committed successful work |
| `last_publication_at` | UTC datetime or null | Latest known source publication, not fetch time |
| `last_run_id` | string or null | Attempt that produced this health |
| `accepted_count` | nonnegative integer | Valid entries accepted in latest attempt, before dedupe |
| `rejected_count` | nonnegative integer | Invalid/unsafe entries rejected in latest attempt |
| `stored_count` | nonnegative integer | New logical items committed by latest attempt |
| `consecutive_failures` | nonnegative integer | Reset only by committed valid success |
| `reason_code` | bounded enum/string or null | Sanitized category such as `timeout`, `malformed-feed`, `destination-denied`, `response-too-large`; no body, contact, query, credential, or arbitrary exception text |
| `freshness_seconds` | positive integer | Current catalog threshold used by projection |

`stale` is derived as `now - last_success_at > freshness_seconds`; absent success is freshness `unknown`. It is exposed separately as `freshness = current | stale | unknown`, so a stale healthy-empty result is not confused with failure. `degraded` means a valid response committed some entries while rejecting others. An older-finishing run cannot overwrite health committed by a newer `last_attempt_at` for the same source.

### `SourceOutcome`

Contains `source_id`, terminal `status`, `started_at`, `finished_at`, request/redirect/byte/entry counts, accepted/rejected/new/merged counts, and the same bounded `reason_code`. These values are diagnostics only and carry no response content.

### `RefreshRun`

- `run_id`: random operation identifier for authority, persisted as the unique commit idempotency key; it is not used as a news identity or ordering key.
- `catalog_digest`, `source_ids`: exact frozen input.
- `started_at`, `ended_at`: injected wall-clock values; `ended_at` is null while uncommitted.
- `limits`: immutable resolved `RefreshLimits` snapshot.
- `status`: `running` in memory; committed as `succeeded`, `partial`, `failed`, or `no-op`.
- `outcomes`: tuple of `SourceOutcome`, sorted by source ID.
- `total_requests`, `total_new_items`, `total_merged_items`: checked sums of outcomes/commit results.

A failed independent source permits other selected sources to finish. Exhausting aggregate budget or the overall deadline stops new work and produces `partial` when anything committed, otherwise `failed`; cancellation is not reported as healthy-empty.

## Persisted state

### `NewsState`

Stored atomically at root-relative `cache/news/state.json`:

- `schema_version`: exactly `1`.
- `revision`: positive integer, incremented once per committed mutation.
- `catalog_digest`: digest that produced the latest commit; old items remain readable when the catalog changes.
- `items`: mapping from `news_id` to `NewsItem`, serialized in sorted ID order.
- `aliases`: mapping from absorbed or prior stable IDs/keys to current `news_id`; cycles and dangling targets are invalid.
- `health`: mapping from source ID to `SourceHealth`, sorted by ID; unknown catalog sources remain historical but cannot trigger network activity.
- `recent_runs`: latest 100 `RefreshRun` records sorted by `(started_at, run_id)`, with unique run IDs.

The reader rejects malformed versions, invalid UTF-8, unexpected fields, non-finite or out-of-range values, alias cycles, and inconsistent counts rather than silently returning fabricated empty state. A missing state file is a valid empty `never-run` store; a corrupt existing file raises `DataClientError`.

### Commit invariants

1. A transaction carries `expected_revision`, frozen run, merged items, and health updates.
2. Writer admission and root revalidation occur before atomic replacement. The commit re-reads the current state under the writer boundary; a different revision causes `NewsStoreConflict`, never a blind overwrite.
3. Repeating an already committed `run_id` returns that committed result without incrementing revision. Older attempts cannot replace newer source health.
4. Items, aliases, health, and run summary become visible together. Health cannot claim success for an uncommitted item batch.
5. Existing items survive source failure, disabled sources, and catalog changes. Only an explicit future retention feature may delete them.
6. Query projections compute `source_state`/freshness at read time and never write back to the store.

## Analyst projection

`CuratedNewsDataClient.get_news(ticker, end_date, start_date=None, limit=1000)`:

- Selects explicit ticker matches plus market-scope items. Editorial ticker association must have been established by reviewed source bindings or deterministic company aliases in feed metadata.
- Excludes known publications after `end_date` and before an optional `start_date`; undated records remain representable with `date=None`, and existing `NewsContext` continues to drop them from prompts.
- Sorts rich results deterministically by publication time/date (unknown last), normalized canonical URL, then `news_id`, applies `limit`, and returns existing `CompanyNews` objects.
- Preserves `ticker`, `title`, `source`, `date`, and `url`; adds optional `news_id`, `fetched_at`, `category`, `attributions`, and `source_state`. The projected `ticker` is the requested ticker; original associations remain in the rich item.
- Performs no network or legacy response-cache access. All other `DataClient` methods delegate unchanged to the wrapped client. Infrastructure/store failures raise `DataClientError`; valid absence returns an empty list.
