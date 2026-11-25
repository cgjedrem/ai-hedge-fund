# Feature Specification: Curated Financial News Aggregation

**Feature Branch**: `cgjedrem-news-aggregation-speckit` (app-managed worktree; branch creation skipped, numbering applied)

**Created**: 2026-11-25

**Status**: Approved for implementation (2026-11-25)

**Input**: User description: "Build a curated financial-news aggregation capability using the CC0 `plenaryapp/awesome-rss-feeds` registry as a curated baseline plus independently discovered official RSS/Atom feeds; EDGAR Tools for SEC filings and 8-K releases; Python feedparser for configured feeds; official portfolio-company investor-relations feeds and Fed/SEC/BLS/BEA macro feeds. Exclude Yahoo and irrelevant blogs/podcasts. Normalize into existing news structures, persist locally, deduplicate by normalized URL/title, retain attribution and publication/fetch timestamps and source health. Enforce bounded concurrency, per-host throttling, timeouts, a descriptive SEC user agent, allowlisted hosts, redirect controls, and private-network/SSRF protections. Integrate with analyst news retrieval. Do not assume republication rights for third-party article bodies. Use deterministic offline tests without real sleeps/network. Price and fundamentals provider replacement is separate scope. Follow repository conventions, read memory.md if present, and never test against a real desk root. Do not create a PR unless explicitly requested by the user. Run the Speckit specification and planning phases and produce a Gate 1 summary for user approval. Do NOT implement before explicit approval."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analysts receive curated company and market news (Priority: P1)

An analyst runs existing news retrieval for a portfolio or ticker and receives relevant items from approved general financial feeds and official portfolio-company investor-relations feeds. Items use the existing news shape, survive local restart, and carry enough provenance and timing information for the analyst to assess them. Repeated or cross-source copies do not crowd out distinct reporting.

**Why this priority**: This is the core user value: broader, more trustworthy news reaches the existing analyst workflow without requiring the analyst to visit each publisher.

**Independent Test**: Seed a synthetic local workspace with approved company and general-news fixtures, run the refresh and existing analyst retrieval, restart the local reader, and verify relevant normalized items, stable deduplication, timestamps, and attribution without accessing a network or a real desk root.

**Acceptance Scenarios**:

1. **Given** enabled approved general-news and portfolio-company sources contain new relevant items, **When** an analyst requests news through the existing workflow, **Then** the response includes those items in the existing news structure with title, canonical link, source attribution, publication time when supplied, and fetch time.
2. **Given** the same item appears repeatedly in one source or under equivalent normalized links or titles across approved sources, **When** refreshes and analyst retrieval run, **Then** one logical news item is returned and all known source attributions remain available.
3. **Given** previously fetched items and no successful new response from a source, **When** analyst retrieval runs, **Then** the previously persisted items remain available and the source's stale or failed state is distinguishable from a successful empty refresh.
4. **Given** a source is Yahoo, an irrelevant blog, a podcast, or not explicitly approved, **When** sources are selected or refreshed, **Then** its items are not admitted even if discovered in a third-party registry.

---

### User Story 2 - Analysts receive filings and macro releases alongside news (Priority: P2)

An analyst sees SEC company filings, including 8-K releases, and relevant Federal Reserve, SEC, BLS, and BEA releases in the same normalized retrieval experience. The analyst can distinguish a filing or official statistical release from editorial reporting and follow its canonical source link.

**Why this priority**: Official filings and macro releases are primary evidence that complements curated reporting and reduces dependence on delayed secondary coverage.

**Independent Test**: Load representative filing, 8-K, and macro-release fixtures for configured companies and agencies, refresh only those sources, and verify that existing analyst retrieval returns correctly classified, attributed, timestamped, deduplicated items with working canonical source references.

**Acceptance Scenarios**:

1. **Given** an approved SEC source publishes a filing or 8-K for a requested company, **When** retrieval runs after refresh, **Then** the analyst receives a normalized item identifying the official source, company, filing or release type, publication time, fetch time, and canonical link.
2. **Given** an enabled Fed, SEC, BLS, or BEA source publishes a release, **When** retrieval runs after refresh, **Then** the item appears as an official macro or regulatory release rather than being attributed to an editorial publisher.
3. **Given** a filing is exposed through more than one approved route or is fetched again unchanged, **When** normalization and persistence complete, **Then** retrieval returns one logical item without losing its official attribution.

---

### User Story 3 - Operators refresh sources safely and can diagnose health (Priority: P3)

An operator configures an explicit approved-source catalog and performs a bounded refresh. The system isolates slow, malformed, redirected, or hostile sources, respects per-host courtesy limits, and reports per-source outcomes without hiding partial failures. Every outbound destination remains subject to the same network policy.

**Why this priority**: Broadening ingestion must not create an unbounded background workload, a silent freshness failure, or a path into private network services.

**Independent Test**: Use fake transports, recorded clocks, synthetic DNS results, hostile redirect/address fixtures, and a temporary local workspace to prove concurrency and throttle bounds, deadlines, destination rejection, descriptive SEC identification, partial-result preservation, and accurate health transitions without real sleeps or network access.

**Acceptance Scenarios**:

1. **Given** more enabled sources than the configured concurrency limit, **When** a refresh runs, **Then** no more than the permitted number fetches run concurrently and no host exceeds its configured request cadence.
2. **Given** a source exceeds its deadline, returns malformed content, or fails, **When** the bounded refresh ends, **Then** other sources still complete, previously persisted items remain intact, and the affected source records the failure and attempt/fetch times.
3. **Given** a URL, redirect target, or resolved address is not allowlisted or refers to a private, loopback, link-local, or otherwise non-public destination, **When** retrieval is attempted, **Then** the request is refused before connection and the refusal is recorded without fetching content.
4. **Given** a redirect chain, **When** each target is evaluated, **Then** scheme, host, address, and redirect-count policy is reapplied and no redirect can bypass the original allowlist.
5. **Given** an SEC request is permitted, **When** it is sent, **Then** it carries the configured descriptive identity and contact information required for responsible SEC access.
6. **Given** an item links to a third-party article, **When** it is normalized, persisted, and shown to analysts, **Then** only permitted feed metadata, supplied summary text, attribution, and the source link are used; no article body is scraped or republished without documented rights.

### Edge Cases

- A registry entry changes ownership, topic, feed URL, or host after initial curation: prior registry membership alone does not authorize continued retrieval; the source requires current approval and host allowlisting.
- A portfolio changes: newly relevant official company sources may be enabled, while removed companies' persisted items remain historically available but do not trigger new discovery or fetches solely from the old portfolio.
- A source omits publication time or supplies ambiguous timezone data: absence or ambiguity is preserved explicitly; fetch time is not presented as publication time.
- Equivalent URLs differ by tracking parameters, fragments, default ports, or scheme casing: normalization removes only semantics-preserving variation and never rewrites a link into an unapproved destination. Trailing punctuation is retained because generic removal can change resource identity; the research decision supersedes any interpretation that punctuation must be stripped.
- Different stories share a title, or one story legitimately changes its title: title-only evidence must not merge clearly distinct links or publication events; conflicting identities remain separate and reviewable.
- One publisher supplies the same story under several URLs: deterministic normalized URL/title matching collapses the duplicates while retaining all observed attribution and canonical-link candidates according to a stable precedence rule.
- A feed contains future-dated, extremely old, oversized, compressed, malformed, or partial entries: validation bounds resource use and bad entries do not invalidate unrelated valid items or existing history.
- A source returns success with zero valid entries: this is a healthy empty result only when the response is genuinely valid; parse and validation failures remain failures.
- A host has multiple configured sources: all requests to that host share the same throttle and failure accounting remains per source.
- A redirect changes host, scheme, port, user-info, or resolved address: every hop is treated as a new untrusted destination and can be refused independently.
- DNS resolution returns both public and non-public addresses or changes between validation and connection: any disallowed destination fails closed; validation is bound to the actual connection attempt.
- The process is interrupted during persistence: completed items are not duplicated on retry, partially written batches do not corrupt prior state, and source health does not claim uncommitted work succeeded.
- Third-party feed summaries contain markup or embedded remote content: analyst output treats them as untrusted text and does not fetch embedded resources or interpret active content.
- All sources fail or none are enabled: analyst retrieval can still use existing persisted items and reports freshness honestly rather than fabricating current news.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support an explicitly approved catalog composed of relevant entries curated from the CC0 `plenaryapp/awesome-rss-feeds` baseline, independently verified official RSS/Atom feeds, official portfolio-company investor-relations feeds, SEC filing and 8-K sources, and Fed, SEC, BLS, and BEA macro sources.
- **FR-002**: Registry membership or automated discovery MUST NOT by itself enable a source. Each enabled source MUST have a reviewed purpose, source attribution, canonical feed or release location, and explicit host approval; irrelevant blogs, podcasts, and all Yahoo sources MUST be excluded.
- **FR-003**: The system MUST refresh only configured and enabled sources and MUST NOT perform unrestricted web crawling or follow article links to discover additional content.
- **FR-004**: The system MUST ingest SEC filings and 8-K releases and normalize official macro and regulatory releases into the same analyst-facing news model as curated feeds while retaining their official-source classification.
- **FR-005**: Every normalized item MUST map into the existing news structure without changing unrelated market-data behavior and MUST retain a stable item identity, title, canonical source link, source attribution, source category, observed publication time when available, and fetch time.
- **FR-006**: Normalized items and source-health observations MUST be persisted locally so items and freshness state survive application restart and remain available when later refreshes fail.
- **FR-007**: Deduplication MUST be deterministic across repeated refreshes and restarts using normalized URLs and normalized titles, with conservative conflict handling that avoids merging clearly distinct stories; all attributions for a merged item MUST be retained.
- **FR-008**: URL and title normalization MUST be stable and semantics-preserving. Tracking-only URL variation MAY be removed, but normalization MUST NOT conceal a changed host, port, scheme, or non-tracking path that identifies different content.
- **FR-009**: Publication and fetch timestamps MUST remain distinct and use explicit timezone semantics. Missing or invalid publication timestamps MUST remain unknown rather than being replaced silently with fetch time.
- **FR-010**: Analyst news retrieval MUST include persisted items relevant to the requested portfolio, ticker, company, or macro scope, apply deterministic freshness/recency ordering, and expose source and freshness information needed to interpret the result.
- **FR-011**: A failure or timeout in one source MUST NOT discard items already persisted from that source or prevent independent sources from completing; partial success and stale data MUST be distinguishable in source health.
- **FR-012**: Source health MUST record at least enabled/disabled state, last attempt, last successful fetch, last observed item publication where known, success/failure/stale status, item counts, and a sanitized failure reason suitable for diagnosis without secrets or response-body leakage.
- **FR-013**: Refresh execution MUST enforce configurable finite global concurrency and per-host concurrency limits, a configurable minimum interval between requests to each host shared across all its sources, and finite connection/read/overall deadlines.
- **FR-014**: A refresh MUST have a finite overall work bound, including source count, redirect count, response size, decompressed size, and parsed-entry limits; exceeding a bound MUST fail or truncate that source explicitly without affecting other sources.
- **FR-015**: All outbound requests MUST be limited to approved HTTPS destinations and explicitly allowlisted hosts. URL credentials, unexpected ports, non-HTTP(S) schemes, embedded remote resources, and unapproved proxy use MUST NOT provide a bypass.
- **FR-016**: Redirect handling MUST be bounded and MUST revalidate every target against scheme, host, port, and resolved-address policy before connecting; approval of the initial URL MUST NOT imply approval of its targets.
- **FR-017**: The system MUST prevent requests to private, loopback, link-local, multicast, reserved, unspecified, and other non-public addresses, including address literals, alternate numeric notations, DNS rebinding, mixed public/private DNS answers, and redirect-based variants. Destination validation MUST apply to the actual connection, not only an earlier string or DNS check.
- **FR-018**: SEC-bound requests MUST use an operator-configured descriptive user agent identifying the application or operator and providing a contact channel. Missing or placeholder identity MUST prevent SEC fetching rather than substituting an anonymous or generic client identity.
- **FR-019**: The system MUST NOT require paid-provider credentials or spend paid-provider credits for this capability, and it MUST NOT create an unbounded unattended retrieval loop. Any scheduled use MUST remain within the repository's existing free-data scheduling governance and finite run bounds.
- **FR-020**: Third-party article bodies MUST NOT be scraped, stored, or republished by default. The system MAY retain feed-provided titles, summaries, metadata, attribution, and links only to the extent permitted by the source; absence of documented republication rights MUST be respected.
- **FR-021**: Feed-provided markup, links, and summaries MUST be treated as untrusted input. Rendering or analyst use MUST NOT execute active content or trigger secondary remote fetches.
- **FR-022**: Persistence MUST be safe under retry and interruption: committed existing records remain readable, repeated items do not create duplicates, and a source is marked successful only for work actually committed.
- **FR-023**: Source configuration and curated-catalog changes MUST be reviewable and reproducible, including baseline-registry provenance/version and the verification basis for independently discovered official sources.
- **FR-024**: Tests for this capability MUST be deterministic and offline, using fake transports, controlled name resolution and clocks, and temporary synthetic workspaces; they MUST NOT access a real desk root, real external feeds, or rely on real sleeps.
- **FR-025**: Existing price and fundamentals providers, ledger behavior, and broker behavior MUST remain unchanged; replacement of price or fundamentals providers is explicitly out of scope.

### Key Entities

- **Source definition**: An operator-approved origin with stable source ID, publisher/authority, category, canonical retrieval location, enabled state, portfolio or macro relevance, allowlisted host, curation/verification evidence, and per-source limits where specialized policy is needed.
- **Source health**: The latest observable refresh state for a source, including attempt and success times, freshness/staleness, accepted and rejected item counts, and sanitized diagnostic state.
- **News item**: A normalized analyst-facing record with stable logical identity, headline, permitted summary or metadata, canonical link, category, company/ticker or macro associations, publication time when known, and fetch time.
- **Attribution**: The publisher, agency, filing authority, source ID, original item identifier, and original link associated with a news item; multiple attributions may support one deduplicated logical item.
- **Refresh run**: One finite retrieval attempt across selected sources, with recorded start/end, scope, policy limits, per-source outcomes, and partial-success status.
- **Curated catalog snapshot**: The reviewable baseline and independently verified additions used to define eligible sources, including registry provenance and approval status; it is distinct from the set currently enabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a representative approved catalog containing general news, at least one portfolio-company investor-relations source, SEC filings/8-Ks, and all four named macro authorities, 100% of valid fixture items admitted for analyst retrieval retain attribution, canonical link, category, fetch time, and publication time or an explicit unknown marker.
- **SC-002**: Across 100 repeated refreshes of the same representative fixture set, including process restarts and alternate equivalent URLs/titles, analysts receive zero duplicate logical items and no loss of distinct source attributions.
- **SC-003**: In a fixture set with at least 20 items from two independent sources where one source is malformed, slow, or unavailable, 100% of valid items from the healthy source remain retrievable and 100% of prior items from the failed source remain available with visibly stale/failed health.
- **SC-004**: In deterministic adversarial tests, 100% of attempted requests to unapproved hosts, non-public addresses, disallowed redirect targets, credential-bearing URLs, and DNS-rebinding variants are refused before content retrieval; zero requests reach a non-public or unapproved destination.
- **SC-005**: A refresh containing at least 50 sources and multiple sources per host never exceeds its configured global concurrency, per-host concurrency, per-host request cadence, or overall deadline in recorded-clock tests, and it performs no real sleep.
- **SC-006**: Analyst retrieval after restart returns 100% of committed fixture items in deterministic order, with current, stale, healthy-empty, and failed source states distinguishable in every case.
- **SC-007**: No acceptance or development test performs real network I/O, sleeps on a wall clock, reads or writes a real desk root, or spends paid-provider credits; all new behavioral tests complete using recorded fixtures and controlled clocks.
- **SC-008**: Zero Yahoo, irrelevant blog/podcast, or unapproved discovered sources appear in enabled-source or analyst-result fixtures, and zero third-party article-body retrievals occur when only feed metadata and links are authorized.
- **SC-009**: Existing analyst workflows can consume the new items without changes to their downstream decision inputs other than receiving the additional normalized news records; existing price, fundamentals, ledger, and broker behavior remains unchanged in regression tests.

## Assumptions

- Initial source selection is a small, reviewable, relevant allowlist rather than wholesale import of the third-party registry. Registry provenance and the basis for independently discovered official sources are recorded for review.
- Official-source discovery is a bounded curation activity, not an autonomous crawler. An operator can approve additional company investor-relations sources as portfolio coverage requires.
- Sources are publicly accessible without paid credentials. Operators provide descriptive SEC contact identity through configuration; no actual contact value is embedded in shared fixtures or committed secrets.
- Analysts consume persisted results through the existing news-retrieval path. This feature adds bounded refresh and local persistence but does not introduce a new continuously running background service.
- Local history is retained by default; deletion, retention-policy management, and a new source-management web interface are not required for the initial capability. Configuration may use existing supported operator surfaces where practical.
- Only feed-supplied metadata and summaries are used for third-party content. Full-text extraction, article-body archival, and republication are excluded unless separately reviewed for rights and scope.
- SEC filings and official agency releases retain their official attribution and canonical references; their inclusion does not imply permission to mirror unrelated publisher content.
- All development and acceptance tests use synthetic temporary roots and deterministic fakes. Any later live smoke test is a separate, explicit operator decision and is not evidence required for Gate 1 approval.
- Price and fundamentals provider replacement, changes to trading decisions or broker execution, and modifications to ledger serialization are outside this feature.
- Gate 1 approves specification and implementation planning only. Production code, dependency changes, task execution, live retrieval, and pull-request creation require separate explicit authorization.
