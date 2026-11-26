# Analyst Retrieval and Compatibility Contract

## DataClient adapter

```python
class CuratedNewsDataClient:
    def __init__(self, client: DataClient, store: NewsStore): ...

    def get_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
    ) -> list[CompanyNews]: ...
```

Every other `DataClient` method delegates directly to `client`; method arguments, return types, exception behavior, context-manager lifetime, and raw-provider identity are unchanged. The adapter is installed outside `CachedDataClient` in production composition:

```text
raw provider -> CachedDataClient (existing non-news behavior)
             -> CuratedNewsDataClient (local get_news override)
```

`get_news` never calls the wrapped client's `get_news` or legacy response cache. Consequently Yahoo/yfinance cannot contribute items through this path. Non-news yfinance methods are not replaced. Store/validation failures raise `DataClientError`; valid empty selections return `[]`.

Explicitly injected web/test/custom factories keep their current behavior to avoid breaking fixtures and authority guards. Production CLI, owned scheduled-runner, and web composition each construct the outer adapter with the same root-local store. The scheduled runner gains no network target and performs no refresh.

## Additive `CompanyNews` projection

Existing fields retain their types and meanings:

```json
{
  "ticker": "EXAMPLE",
  "title": "Example headline",
  "source": "Example Company Investor Relations",
  "date": "2026-11-25T12:00:00+00:00",
  "url": "https://ir.example.com/news/example"
}
```

New optional fields are:

| Field | Type/default | Meaning |
|---|---|---|
| `news_id` | string or `None` | Stable logical item identity |
| `fetched_at` | ISO UTC string or `None` | Latest committed fetch, distinct from `date` |
| `category` | string or `None` | Reviewed editorial/IR/SEC/regulatory/macro category |
| `attributions` | list[`NewsAttribution`], default empty | All known sources, original IDs/links, publication/fetch observations |
| `source_state` | string or `None` | Canonical source outcome plus freshness, e.g. `healthy:current`, `failed:stale`, `healthy-empty:unknown` |

`NewsAttribution` is a small shared Pydantic model in `data/models.py`, not a storage dictionary. It contains `source_id`, `publisher`, `original_id`, `original_url`, `published_at`, and `fetched_at`, all optional except source ID/publisher. It carries no raw markup, response body, contact identity, or query credentials.

Old JSON lacking all new fields and old Python callers constructing five-field `CompanyNews` remain valid. The adapter's requested ticker appears in `ticker`; complete original associations remain available from `NewsStore.query`. Rich queries use `NewsItem` directly.

## Filtering and ordering

1. Select items explicitly associated with the requested uppercase ticker and, by default, market-scope items. No article-body or LLM ticker inference occurs.
2. Include only known publication values in `[start_date, end_date]` when dates are known. `date=None` represents unknown publication and remains visible at the data boundary; existing `NewsContext` drops it before rendering.
3. Reject invalid query dates and non-positive/excessive limits with `DataClientError` rather than silently changing the query.
4. Sort by normalized publication timestamp/date descending, normalized canonical URL ascending, and `news_id` ascending; unknown publication is last. Apply the bounded limit after deterministic sorting.
5. Map canonical publisher/title/link/category and all attributions without mutating stored records. Freshness is computed using the reader's injected clock.

The rich `NewsQuery` supports explicit `include_undated=False` and category/source filters. `NewsPage.health` is the authoritative way to interpret an empty result. Retrieval does not claim freshness from item recency alone.

## Analyst prompt compatibility

`features/news.py` remains the sole prompt-rendering boundary for this feature. It continues to:

- Request the seven-day window ending at the session and at most eight headlines.
- Exclude items after the session and undated items.
- Render newest last with absolute publication days and deterministic tie-breaking.
- Hash only the rendered news context; fetch timestamps, health, and attribution metadata do not create unrelated prompt changes.

No analyst agent, decision schema, ledger schema, broker interface, price provider, or fundamentals provider is rewritten. Existing regression fixtures using injected five-field `CompanyNews` objects remain valid. A new normalized headline can change the news prompt; metadata-only refreshes of the same logical headlines cannot.

## Health views

`SourceHealthView` adds derived `freshness` (`current`, `stale`, or `unknown`) and `is_stale` convenience boolean/null to persisted `SourceHealth`; it does not rewrite the terminal attempt status. Views are sorted by source ID. The relationship is:

| Latest committed status | Freshness can be | Interpretation |
|---|---|---|
| `never-run` | `unknown` | No successful or failed observation yet |
| `healthy` | `current`, `stale` | Valid nonempty or previously populated source; not a transport failure |
| `healthy-empty` | `current`, `stale` | Last valid response contained zero entries; not malformed |
| `degraded` | `current`, `stale` | Some valid entries committed and some rejected |
| `failed` | `current`, `stale`, `unknown` | Last attempt failed; old items remain and prior success controls age |
| `disabled` | inherited or `unknown` | No new retrieval; history remains queryable |

No health state fabricates publication time or converts fetch time into publication time.
