# Review Report

## Status: pass-with-caveats

## Scope

- Merge-base review: HEAD `50497a4ad09c56d1ec56406a8d7608ce95219459` plus the complete curated-news working-tree diff, including intent-to-add files.
- Implementation: `hedge_fund/news/`, additive news metadata in `hedge_fund/data/models.py`, production composition in `hedge_fund/run.py`, `hedge_fund/runtime/owned_runner_child.py`, and `hedge_fund/web/services.py`.
- Runtime/security integration: `hedge_fund/runtime/dispatch.py`, `endpoints.py`, `policy.py`, and `root.py`.
- Contracts and evidence: `specs/010-curated-news-aggregation/`, `README.md`, `pyproject.toml`, `poetry.lock`, and `memory.md`.
- Test scope: all news tests, offline integration fixtures, affected runtime tests, analyst/cached-data tests, and repository-wide regression triage. No live network or real desk root was used.
- No out-of-scope provider replacement was made. `RootContext.replace_file` is the required confined replacement primitive for news-local persistence; legacy `paths.write_atomic` is unchanged from HEAD.
- Review axes: Standards and Spec, followed by the complete OWASP LLM and general-security checklists.
- Independent QA: initial FAIL, bounded remediation re-review PASS-WITH-CAVEATS, then a narrow M1/N1/N2 follow-up confirming no new Critical or Important issue. Independent review was static; local execution evidence is recorded separately in `specs/010-curated-news-aggregation/acceptance-evidence.md`.

## Critical

None open.

## Important

All four original Important findings were resolved and independently verified:

- `hedge_fund/news/transport.py:111` — production transport now explicitly permits guarded manual redirect responses. Automatic redirects remain disabled and every hop is reauthorized. **Resolved.**
- `hedge_fund/runtime/root.py:596`, `hedge_fund/news/store.py:127,186` — legacy shared atomic writes were restored to HEAD behavior; news uses confined replacement under news-local writer admission. **Resolved.**
- `hedge_fund/news/filings.py:181-219` — root writer admission covers scratch creation/cleanup, not subprocess execution. **Resolved.**
- `hedge_fund/news/store.py:212-214` — only conflicting nonempty native IDs from the same source block title-only merging; publisher-native GUIDs from different sources no longer prevent merges. **Resolved.**

The final Minor deadline finding was also remediated:

- `hedge_fund/news/refresh.py:304-320`, `hedge_fund/news/filings.py:163-170,339` — EDGAR worker timeout is now resolved after the SEC submissions download from the remaining source/run deadline, capped at 30 seconds, with no-budget and invalid-budget failure handling. The public-refresh regression failed with `[30.0] != [10.0]` before the fix and passed afterward. Independent narrow follow-up: **M1 fixed; no Critical or Important issue introduced.**

No open Important findings remain from the independent review.

## PR #18 Copilot review remediation

Four additional Copilot findings were confirmed against the implementation and corrected on the PR branch:

- `news/normalize.py` preserves the directory trailing slash implied by final literal or percent-decoded `.`/`..` path segments; `/a` and `/a/` remain distinct.
- `news/store.py` rejects ambiguous title-only candidates when retained clusters have conflicting SEC identities or same-source native IDs. Strong-key matches remain authoritative, and an ambiguous third-publisher observation becomes a separate item instead of bridging incompatible clusters.
- `news/refresh.py` checks the deadline again after feed parsing and before retaining entries or accepted/rejected counts.
- `NewsStore.commit()` now derives per-source and run-level new/merged counts from actual merge decisions before constructing health and history. `NewsRefresher.refresh()` returns the normalized committed run, removing the separate approximate disposition algorithm.

Each finding has a public-seam regression that reproduced the defect before its fix and passes afterward. The tests use synthetic roots, injected clocks/transports, and no network or real sleeps. Final suite and style evidence is recorded in `specs/010-curated-news-aggregation/acceptance-evidence.md`.

## Minor

- `hedge_fund/news/filings.py:163-219` — the post-download budget is resolved before scratch-directory admission, which can wait up to five seconds; cleanup can add further time. The later refresh deadline check prevents late results from being stored, and no `sec-edgar` source is enabled in the shipped catalog. This is a documented residual timing limitation, not a claim of a hard wall-clock bound. [Confidence: 70%]
- `hedge_fund/news/client.py:24` — analyst reads revalidate the complete retained state on every call to preserve cross-process visibility. Large-state read performance is unbenchmarked; no unsafe in-process cache was introduced. [Confidence: 80%]

## Nitpick

- `hedge_fund/news/store.py:127`, `hedge_fund/news/filings.py:181,215` — these modules use the private `paths._root_write_admission` helper. The behavior is reviewed and tested; introducing a broader public shared API was deliberately deferred to avoid unrelated churn. [Opinion; accepted]
- Resolved: `hedge_fund/news/transport.py:41-42` documents that `sec_identity_required` is informational and actual SEC identity selection is host-based on every redirect hop.
- Resolved: the EDGAR parser retains its timeout callback and stores each resolved value separately, so a second parse does not reuse a stale budget. Current refresh composition constructs one parser per source invocation.

## Security Checklist (OWASP LLM Top 10)

- [x] **LLM01: Prompt Injection — PASS WITH RESIDUAL RISK.** Feed titles/summaries are cleaned, bounded, inert data; no dynamic evaluation occurs. They can still reach analyst prompts, so semantic instruction-like text is not comprehensively filtered. Analysts must treat it as untrusted evidence, not instructions.
- [x] **LLM02: Insecure Output Handling — PASS.** No feed or LLM output is rendered as raw HTML, used as SQL, or passed to a shell. EDGAR worker arguments use a fixed argument vector without `shell=True`.
- [x] **LLM03: Training Data Poisoning — PASS FOR THIS FEATURE.** No training pipeline is changed. Sources are explicitly reviewed, attributed, and cataloged; registry membership alone never enables a source.
- [x] **LLM04: Model Denial of Service — PASS WITH DOCUMENTED TIMING CAVEATS.** Request, redirect, byte, entry, concurrency, cadence, source/run, and worker limits are enforced. Blocking-socket, scratch-lock, cleanup, cold-import, and large-state limits are not represented as proven hard bounds.
- [x] **LLM05: Supply Chain Vulnerabilities — PASS.** `feedparser` 6.0.14 and `edgartools` 6.4.0 are exactly pinned; `poetry.lock` is consistent. The registry is pinned to commit `9ab2482cae9031a5a39635c887fcfc8ece7e130a` and treated only as a review queue.
- [x] **LLM06: Sensitive Information Disclosure — PASS.** No credentials or real desk data were added. Synthetic SEC identities are used in tests. Provider, transport, store, CLI, and worker failures use sanitized reason codes; SEC identity never follows a redirect to a non-SEC host.
- [x] **LLM07: Insecure Plugin Design — PASS WITH CONTAINMENT CAVEAT.** Curated endpoints are explicitly classified and authorized. The isolated EDGAR worker denies network/process execution, restricts scratch effects, and permits trusted native initialization only during imports. Python audit hooks are not an OS sandbox against malicious native code.
- [x] **LLM08: Excessive Agency — PASS.** Refresh is manually selected, bounded, allowlisted, and confined to an enrolled synthetic/operator root. There is no automatic scheduler, arbitrary document retrieval, or out-of-root write capability. No destructive operation is introduced.
- [x] **LLM09: Overreliance — PASS WITH LIVE-ACCEPTANCE GAP.** Generated code received independent Standards/Spec and security review plus deterministic tests. Live publisher/SEC behavior, production cold start, deployment, and POSIX replacement remain unverified and are not claimed.
- [x] **LLM10: Model Theft — PASS / NOT APPLICABLE.** No model weights, proprietary models, or model endpoints are added or exposed; no AI credentials are committed.

## General Security Checks

- [x] Input type, length, and format are validated at catalog, transport, parser, store, CLI, and provider boundaries.
- [x] No SQL injection vectors: no SQL queries are introduced.
- [x] No XSS vectors: feed content is inert metadata and no raw-HTML rendering path is introduced.
- [x] No command injection vectors: worker execution uses a fixed argument list and never `shell=True`; untrusted feed content is not a command argument.
- [x] Authorization is explicit for curated endpoints and each request/redirect hop; destination allowlists and public-IP checks fail closed.
- [x] Least privilege is preserved: only configured hosts, SEC submissions metadata, and root-confined news/scratch paths are used. Filing documents, exhibits, and `filings.files` are not retrieved.
- [x] No IDOR vector is introduced: source IDs select only reviewed catalog entries; arbitrary URLs and roots are not accepted by the public CLI path.
- [x] Client-facing errors use generic sanitized reason codes without response bodies, stack traces, environment values, or credentials.
- [x] No secrets, API keys, tokens, real credentials, or private article bodies are present in source or fixtures.
- [x] Password hashing and sensitive-data-at-rest encryption are not applicable; no passwords or new sensitive datastore are introduced.
- [x] HTTPS is required for remote sources; DNS pinning, non-public-address denial, exact-origin controls, and redirect reauthorization mitigate SSRF and rebinding.
- [x] No sensitive data is placed in query parameters; SEC identity is sent only in the appropriate request header to an authorized SEC host.

## Test Coverage Assessment

- Happy paths: covered for feed/IR/macro normalization, SEC metadata projection, deduplication, persistence/restart, analyst retrieval, CLI status/refresh, and production composition.
- Error paths: covered for denied destinations, DNS rebinding, redirects, timeouts, byte/entry limits, malformed content/state, partial failure, corrupt worker output, worker timeout/cleanup, and sanitized CLI failures.
- Edge cases: covered for Atom/RSS variants, false-empty feeds, ambiguous filing timestamps, same-source GUID conflicts, cross-source title merges, merge-counter saturation, older-run fencing, retry idempotency, and 50-source bounded scheduling.
- M1 regression: `NewsRefresher.refresh` with a controlled clock and offline transport/worker proves that a 20-second download under a 30-second source deadline leaves a 10-second worker timeout.
- Final exact test counts, runtime failures, style evidence, and full-suite triage are maintained in `acceptance-evidence.md`; no clean repository-wide result is inferred from focused passes.
- Overall: sufficient for offline feature delivery with the documented caveats; live/production and POSIX runtime acceptance remain outstanding.

## Summary

- Open findings: 3 total — 0 Critical, 0 Important, 2 Minor, 1 Nitpick.
- Four original Important findings and the final M1 Minor deadline issue are resolved. N1 is documented; N2 is deliberately accepted.
- Recommendation: **approve with caveats** for the requested offline implementation and local commit. Do not interpret this as live-production certification.
- Delivery constraints: no live-network acceptance, real desk root, push, or pull request. No provider replacement is included.
