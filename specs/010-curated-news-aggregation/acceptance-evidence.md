# Acceptance Evidence — Curated Financial News Aggregation

## Scope and execution boundaries

Gate 1 was approved by the user on 2026-11-25. Validation uses committed offline fixtures, controlled clocks/DNS/transports, and synthetic temporary roots. No live publisher/SEC retrieval, paid-provider call, real desk-root access, real sleep in deterministic tests, deployment check, push, or pull request is part of this evidence.

The production SEC filing path is configurable but the shipped catalog has no enabled `sec-edgar` source. AMD and NVIDIA investor-relations candidates remain disabled pending operator selection. The US2 integration test uses the real pinned EDGAR Tools 6.4.0 isolated parser with a test-only 300-second timeout to tolerate cold native imports; this does not establish production compliance with the contractual 30-second source deadline in this environment.

## Verified focused results

| Command or scenario | Result |
| --- | --- |
| `pytest hedge_fund/news/test_refresh.py -q` after deterministic-ordering changes | 18 passed in 52.98s |
| `pytest hedge_fund/news/test_integration.py::test_sec_filings_and_macro_releases_survive_restart_and_repeat_refresh -q` | 1 passed in 31.75s; two real isolated-parser invocations, six persisted items after repeat refresh |
| `pytest hedge_fund/news/test_composition.py -q` | 5 passed in 7.59s |
| US1 100-refresh/restart analyst integration | 1 passed in 402.53s |
| Earlier focused news/analyst run before the final ordering and real-parser integration edits | 135 passed in 405.27s; superseded by the final focused run below |
| Focused `pytest -q hedge_fund/news hedge_fund/features/test_news.py hedge_fund/data/test_cached.py` before independent-review remediations | 136 passed in 338.99s |
| Catalog regression | 21 passed in 2.42s |
| Production catalog against `catalog-v1.schema.json` using the already-installed system `jsonschema` | Valid under `Draft202012Validator`; schema self-check passed |
| `poetry check --lock` | Passed; only pre-existing Poetry deprecation warnings |
| Transport regression | 19 passed in 3.10s |
| CLI regression | 9 passed in 50.48s |
| EDGAR offline worker regression | 8 passed in 27.39s |
| EDGAR scratch collision | 1 passed in 30.34s |
| EDGAR malformed output, timeout, and output-limit cases | 3 passed in 30.50s |
| EDGAR refresh reason allowlist | 2 passed in 22.34s |
| Mixed-success deadline persistence | 1 passed in 17.11s |
| Redirect source limit | 1 passed in 16.69s |
| Compressed/decompressed source limits | 2 passed in 35.21s |
| Valid empty RSS/Atom feeds | 2 passed in 22.00s |
| Feed parsing module | 6 passed |

Historical results above are not represented as a single clean final suite. Fresh post-remediation evidence observed on 2026-11-25 UTC:

| Final-tree command or scenario | Result |
| --- | --- |
| Cleanup sanitization, real isolated EDGAR parsing, and merge-counter saturation | 3 passed in 24.29s |
| Transport/store/refresh/filings/worker/root-path regression selection | 93 passed, 2 skipped in 115.37s |
| Exact catalog/normalization/parsing/worker/root remediation selection | 55 passed in 7.38s |
| Seven original independent-review regressions | 7 passed in 7.42s |
| Production composition | 5 passed in 6.47s |
| Fresh US1/US2 offline integration, including the real isolated EDGAR parser | 2 passed, 416 feedparser deprecation warnings in 159.02s |
| Focused news/analyst suite before M1 | 160 passed, 506 feedparser deprecation warnings in 284.58s |
| M1 deadline regression | RED: worker timeout 30 rather than 10 after a controlled 20-second download under a 30-second source deadline; GREEN: 1 passed in 4.85s |
| Direct refresh/filings/integration selection before per-invocation `_resolved_timeout` refinement | 31 passed, 434 warnings in 181.20s |
| Runtime selection after M1 refinement | 10 failed, 141 passed, 2 skipped in 641.60s; all ten failures were unchanged owned-runner timing/contention cases at lines 292, 483, and 671 |
| Final post-refinement `poetry run pytest hedge_fund/news -q --tb=short` | **142 passed, 506 feedparser deprecation warnings in 226.59s**; includes the direct refresh/filings/integration coverage after `_resolved_timeout` refinement |
| Full `poetry run pytest hedge_fund -q --tb=short` | **47 failed, 3,239 passed, 62 skipped, 506 warnings in 13,290.23s (3:41:30)**; feature writer-map omissions were subsequently corrected as detailed below |
| Focused `pytest hedge_fund/runtime/test_writer_map.py -q --tb=short` after registration fix | **125 passed in 8.23s** |
| Focused writer inventory/map run after registration fix | **1 failed, 126 passed in 13.79s**; the sole inventory failure contains only six unchanged build-identity/credential-delivery omissions, with every feature-owned write now classified |

## Acceptance scenario coverage

- **Analyst retrieval and restart:** US1 refreshes representative general/company fixtures 100 times with reader reconstruction, verifies deduplication, stable attribution/publication/fetch timestamps, analyst projection, and unchanged non-news delegation. US2 retrieves guarded SEC submissions and macro fixtures, invokes the real isolated parser, reconstructs readers, and verifies filing/macro order, dates, links, and repeat-refresh deduplication without `filings.files` retrieval.
- **Determinism:** refresh outcomes are sorted by source ID and duplicate dispositions are assigned from entries sorted by source ID/original ID/normalized URL/deduplication keys. The added regression failed with `['zeta', 'alpha']` before the production fix and passes afterward.
- **Health and partial failure:** focused store/refresh tests cover healthy-empty, degraded/failed/stale state, older-run fencing, retry idempotency, atomic replacement interruptions, mixed-success deadlines, and persistence of successful sources beside failures.
- **Bounded execution:** recorded-event tests cover 50 sources, worker/per-host limits, request and redirect budgets, shared cadence, deadlines, no late starts, compressed/decompressed byte caps, and entry caps without real sleeps.
- **Transport and SSRF:** offline matrices cover exact origins, every redirect hop, DNS pinning/rebinding and non-public/mixed answers, scheme/userinfo/port/query restrictions, SEC identity validation, bounded streams, and sanitized failures.
- **Content and rights:** parser tests cover inert markup, embedded-resource non-retrieval, malformed/false-empty feeds, excess entries, feed-supplied summary policy, and bytes-backed `BytesIO` input so feedparser cannot reinterpret raw bytes as a path or URL.
- **EDGAR containment:** audit probes cover denied network/child-process behavior, scratch-confined import effects, typed metadata, forbidden document APIs, malformed/oversize worker output, timeouts, and sanitized worker reasons.
- **CLI and composition:** tests cover offline status, network authorization, SEC preflight, selectors/no-op/partial failure/corrupt state, JSON and sanitized exits, plus backtest, owned-runner, and web adapter composition with injected-factory preservation.

## Repository-wide regression and triage

An earlier broad run completed with **42 failed, 145 passed in 8705.30s**. It was not a clean full-suite result and did not establish that every failure predates this feature.

Focused Saxo reproduction:

```text
pytest hedge_fund/test_run.py -k "saxo_demo_execution_refuses_before_ledger_or_execution" -q
4 failed, 114 deselected in 2.89s
```

All four fail at unchanged `hedge_fund/test_run.py:3013` because `hedge_fund.run` has no `apply_credentials`. `HEAD:hedge_fund/run.py` also lacks that attribute; the implementation is in `hedge_fund/tui/keys.py`. This is static evidence of a pre-existing test/code mismatch, not evidence for unrelated timeout failures.

Focused timing reproduction:

```text
pytest "hedge_fund/runtime/test_owned_runner_child.py::test_stop_during_inflight_session_finishes_once_then_stops[none]" "hedge_fund/test_run.py::test_cli_halt_does_not_wait_for_a_busy_control_lane" -q
1 failed, 1 passed in 48.92s
```

The owned-runner test did not reach its injected offline data client within ten seconds. Its injected-factory branch is unchanged by this feature. This reproduction is not claimed as a verified pre-change baseline failure. The CLI control-lane test passed in isolation.

## Style and review

After all implementation, review, and writer-registration refinements, Black `--check --line-length 420` reported all 38 changed Python files unchanged; isort `--check-only --profile black`, flake8 `--max-line-length 420 --extend-ignore=E203`, `git diff --check HEAD`, and `poetry check --lock` exited zero. `E203` is excluded for Black slice-formatting compatibility. Poetry emitted only existing metadata deprecation warnings. Isort intentionally uses repository configuration without a 420-column import override. An earlier style command's PowerShell status 1 came solely from unsupported informational `Get-Date -AsUTC` after its linters had passed; the final compatible invocation has no such wrapper failure.

The first independent Standards/Spec and OWASP review returned FAIL with four Important findings: missing production manual-redirect opt-in, accidental shared atomic-write changes, EDGAR writer admission spanning subprocess execution, and cross-source GUIDs defeating title merging. Those findings and the reported Minor transport, persistence, catalog, timestamp, editorial-alias, worker-containment, and diagnostic issues were remediated with focused regressions. The bounded independent re-review returned **PASS-WITH-CAVEATS** on Standards and Spec and verified all four Important fixes. Its final M1 deadline finding was remediated test-first and independently accepted: no Critical or Important issue was introduced. N1 was resolved by documenting informational SEC request metadata and per-hop host-based identity selection; N2's private root-admission helper use was deliberately accepted to avoid unrelated shared API churn. Complete findings and security dispositions are in `review-report.md`.

The M1 public-refresh regression uses a synthetic root, controlled monotonic clock, fake offline transport, and stubbed worker process. Before the fix, a 20-second SEC download under a 30-second source deadline produced `[30.0] != [10.0]`; afterward the worker received 10 seconds. `refresh.py` now supplies a deadline-checkpoint callback, and `filings.py` resolves it at parser entry after retrieval. The callback remains intact across invocations and each invocation's float is stored separately, avoiding stale-budget reuse. The final 142-test news run postdates that refinement.

The completed full-suite log is preserved at `C:\Users\ChristianGjedrem\.copilot\session-state\a2050198-89a8-4633-9c0c-9752ace71ab2\files\curated-news-full-suite-final.log`. Its two writer-ratchet failures exposed missing feature registrations for news persistence, EDGAR scratch creation/cleanup, and the POSIX replacement primitive. The focused RED reproduced both failures; registrations now classify these writes under root admission/no-follow primitives with existing behavioral evidence. The writer-map module passes all 125 tests. The inventory ratchet's remaining failure lists only `runtime/build_identity.py` and five `runtime/credential_delivery.py` entries, all unchanged by this feature. No unrelated production code was changed to obtain this result.

The other 45 full-suite failures are in unchanged Saxo/yfinance, paper, admission, owned-runner, writer-race, TUI, and web timing/contention areas; none is a news test. Historical baseline notes account for several Saxo/yfinance IDs, but this run does not independently prove every remaining failure pre-change. The full suite was not rerun after the test-only writer registrations, so no clean repository-wide result or zero-regression claim is made.

## Unperformed checks and limitations

- No live feed, SEC, EDGAR, publisher, deployment, or real-desk-root acceptance check was performed; these were explicitly excluded.
- No claim is made that cold EDGAR native imports meet the 30-second production source deadline on this Windows host. The production timeout was not weakened to hide that limitation.
- Independent JSON Schema validation used the already-installed system `jsonschema`; no project dependency was added. The production catalog also passes the strict application loader.
- Same-source native-GUID conflicts are counted by a persisted diagnostic that saturates at 1,000,000. Different publishers' native GUIDs do not block conservative title merging.
- URL trailing punctuation is deliberately retained. The specification edge-case wording was clarified because generic punctuation removal can change resource identity and conflicts with FR-008; `research.md` already rejected that unsafe transformation.
- `CuratedNewsDataClient.get_news` revalidates the complete retained state on every call so separate-process refreshes are not hidden by an in-process cache. Large-state read performance is unbenchmarked and remains a documented concern; no unsafe cache was added.
- Known placeholder `approved_by` and SEC identity values are rejected. Catalog review remains an operator responsibility: source reachability, rights, and disabled candidate suitability are not established by placeholder checks or offline tests.
- EDGAR scratch cleanup failures are fail-visible as sanitized `worker-cleanup-failed`; cleanup failure takes precedence over an earlier worker failure. No scratch failure is silently reported as success.
- The post-download EDGAR timeout is resolved before scratch-directory admission, which may wait up to five seconds, and cleanup can add elapsed time. This is not a strict end-to-end wall-clock bound; the refresh layer checks its deadline after provider completion and discards late results. No `sec-edgar` source is enabled in the shipped catalog.
- The final runtime selection's ten owned-runner timing/contention failures are recorded without a pre-change-baseline claim. The three variants at line 292 did not reach their injected client within ten seconds; two pre-effect control-contention variants at line 483 and five pre-effect observation-contention variants at line 671 retained worker threads. No unrelated runner test or production behavior was modified to hide these failures.
- Residual semantic prompt-injection risk remains because untrusted feed titles/summaries can reach analyst prompts. Text is cleaned and inert, but instruction-like semantics are not comprehensively filtered and must remain untrusted evidence.
- POSIX `RootContext.replace_file` has static independent review but no POSIX runtime verification on this Windows host. Live redirects, live SEC retrieval, production cold start, deployment, and full-state performance also remain unverified.
- The completed repository-wide suite is not clean: 47 failures were recorded before the two feature writer-ratchet omissions were fixed. Focused evidence verifies those registrations, while the other 45 unchanged-area failures are not all independently established as pre-change. Feature-focused results and repository-wide triage are reported separately above.
