# Feature Specification: Complete Web Engine Migration

**Feature Branch**: `cgjedrem-vigilant-robot`

**Created**: 2026-10-31

**Status**: Draft specification; requirements-quality reviewed, not implementation accepted

**Input**: Complete the migration from the terminal UI so the existing React/shadcn desk is the sole supported interactive engine driver, preserving its terminal-inspired appearance, domain behavior and supported headless deployments. Deliver actual runner control, manual execution, live valuation, fund lifecycle, approvals, backtests, reports and complete supported configuration, including providers, models and credentials. Follow specify, assumptions clarification, adversarial red team, plan, open plan-review PR, tasks, implementation/convergence and multiple QA gates; create a new main-targeting PR and never merge it. This execution stops after specification.

**Baseline and scope**: `main` at `6443490db64056742fbbe6a18abf92c903c10861`, merged PR #7, is an additive web desk and explicitly not retirement-ready. [Discovery and complete capability disposition](discovery.md) form the scope inventory. Framework names here are user-selected product constraints, not an architecture proposal. No engine algorithm, ledger-schema redesign, real brokerage, historical intraday engine, remote/public web exposure or unrelated defect repair is included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operate the paper engine from the desk (Priority: P1)

An operator inspects a deployed fund, understands readiness and effective configuration, deliberately starts or stops its scheduler, or runs the next session manually, without opening the terminal UI.

**Why this priority**: A viewer cannot replace the operator interface until it safely drives the real engine.

**Independent Test**: Use a synthetic deployment, fake clock and fake providers to start a runner, observe a completed canonical session, stop it and separately run a due session manually. Verify recorded state and ownership without real funds or external calls.

**Acceptance Scenarios**:

1. **Given** a stopped, verified, due deployment and valid offline configuration, **When** the operator confirms runner start, **Then** readiness is acknowledged, exactly one owned runner starts and subsequent status and session progress are visible.
2. **Given** competing browser and headless starts/manual runs, **When** both seek admission for the same deployment, **Then** only one conflicting writer is admitted and denial causes no fill or append; independent funds remain operable.
3. **Given** an in-flight session, **When** Stop is requested, **Then** the desk distinguishes requested from completed stop, admits no new session and does not claim rollback of completed effects.
4. **Given** a due, nothing-due, halted or invalid fund, **When** manual execution is requested, **Then** canonical execution, no-work completion or a specific preflight denial is reported respectively.
5. **Given** a submitted operation or active runner, **When** the page reloads or closes, **Then** monitoring can recover without repeating the mutation and browser closure alone does not stop the runner.
6. **Given** stale or forged process metadata, **When** status or stop is requested, **Then** ownership is unknown/denied and no unrelated process is signalled.

---

### User Story 2 - Configure a complete reproducible fund (Priority: P1)

An operator creates, edits or clones a mandate and selects market data, LLM provider/model and credentials with clear provenance and application timing.

**Why this priority**: Safe operation requires complete validated configuration rather than an incomplete form or hidden environment changes.

**Independent Test**: Round-trip every supported mandate field and runtime setting through the desk using synthetic files and credential sentinels; compare validated results and frozen operation snapshots.

**Acceptance Scenarios**:

1. **Given** a valid supported mandate containing non-default model parameters, weights, costs and schedule settings, **When** opened and saved unchanged, **Then** no supported value is dropped and historical default omissions remain compatible.
2. **Given** a library strategy or custom roster, **When** analysts, sleeve/model weights, blend policy, dollar neutrality, risk, benchmark or order threshold are edited, **Then** registry and domain validation apply and custom composition cannot impersonate an unchanged canonical library.
3. **Given** a deployed snapshot, **When** its template is revised, renamed or cloned, **Then** the deployed rules, pending decision and history remain unchanged.
4. **Given** no cloud credentials, **When** free data and a supported local model are selected, **Then** readiness does not require a cloud key and validating settings makes no external call.
5. **Given** active work with captured configuration, **When** new model/provider/key settings are saved, **Then** active work keeps its frozen configuration, new settings persist for the next operation and a runner restart is explicitly required to adopt them.
6. **Given** invalid identifiers, unknown parameters or a credential-bearing endpoint URL, **When** submitted, **Then** validation rejects them without exposing secret contents or invoking providers.

---

### User Story 3 - Approve and recover without unsafe retries (Priority: P1)

An operator reviews pending decisions, approves or rejects the exact decision, halts unsafe execution and deliberately recovers or redoes an eligible paper session.

**Why this priority**: Removal of the terminal recovery surface must not weaken decision identity, ledger integrity or operator control.

**Independent Test**: Exercise matching, stale, consumed and redone approvals, corrupted controls and failed appends against synthetic ledger fixtures.

**Acceptance Scenarios**:

1. **Given** a pending decision, **When** the operator submits a verdict bound to its timestamp and source hash, **Then** only that decision is affected; approval alone never starts execution.
2. **Given** a changed source/head or expired verdict, **When** a stale confirmation is submitted, **Then** the desk reports conflict and refreshes rather than retargeting it.
3. **Given** unreadable controls or a corrupt ledger, **When** recovery Halt is requested, **Then** new execution can be stopped safely without trusting corrupt execution state; Resume remains denied until verified replay succeeds.
4. **Given** an eligible latest local-paper session and quiescent writers, **When** identity/head-bound redo is confirmed, **Then** superseded history is retained, source redo invalidates stale votes and execution redo preserves matching consumed-verdict semantics.
5. **Given** fills followed by append failure or lost response, **When** monitoring resumes, **Then** the desk exposes halted/ambiguous outcome and never automatically repeats execution.

---

### User Story 4 - Manage a reversible fund lifecycle (Priority: P2)

An operator deploys, archives, restores or replaces a fund and archives research without accidentally wiping shared history.

**Why this priority**: Lifecycle parity is required for retirement, but depends on proven admission and ownership.

**Independent Test**: Use synthetic templates, deployments and research with decoy sibling identities; test collisions, concurrent writers and archive/restore transitions.

**Acceptance Scenarios**:

1. **Given** a valid template and universe, **When** deployed, **Then** a new immutable snapshot is created and readiness leads to deliberate run/backtest actions.
2. **Given** an active or queued writer, **When** archive or replacement is requested, **Then** the operation is denied until owned work is stopped and quiescent.
3. **Given** a reviewed exact identity and head, **When** archival is confirmed, **Then** only the selected template, deployment or research object is archived according to the stated scope; no broad wipe occurs and retained history is recoverable.
4. **Given** an archived deployment, **When** restored or replaced, **Then** restore is collision-checked and stopped; replacement creates a distinct deployment identity linked to retained history, never overwriting old rules.

---

### User Story 5 - Observe honest valuation and research (Priority: P2)

An operator explicitly refreshes estimated live value, follows backtest progress and reads complete decision, execution, risk and performance reports.

**Why this priority**: Operational decisions need timely but clearly labelled information, not misleading live/recorded equivalence.

**Independent Test**: Use fake quotes, backtest callbacks and known report fixtures with fractional/signed holdings, missing prices and malicious text.

**Acceptance Scenarios**:

1. **Given** network disabled, **When** valuation refresh is requested, **Then** denial occurs before provider invocation; page mount, refresh, reconnect and monitoring never authorize paid calls.
2. **Given** an authorized refresh with complete, partial or stale quotes, **When** the result arrives, **Then** source/time/coverage are shown; incomplete current NAV is not presented as complete and recorded series remain unchanged.
3. **Given** a reviewed backtest request, **When** submitted and monitored across navigation/reload, **Then** progress and captured mandate/provider/model remain visible, one job runs and results can be reopened.
4. **Given** cancelled or interrupted work, **When** inspected, **Then** cancellation boundaries or interrupted state are explicit; a server restart never automatically resumes a bounded job.
5. **Given** a saved report, **When** inspected or exported, **Then** proposed and executed actions, clamps, weights, orders, fills, costs, tape, theses, NAV, benchmark and scorecards agree with canonical records.
6. **Given** a minute mandate backtest, **When** reviewed or reported, **Then** it is labelled daily replay, not historical intraday validation.

---

### User Story 6 - Retire the terminal UI without losing deployment support (Priority: P1)

An operator launches the supported desk, uses its dense terminal-inspired keyboard-friendly presentation and retains automation/recovery commands without installing the old terminal UI.

**Why this priority**: Sole-driver status is an accepted operational outcome, not merely removing screens.

**Independent Test**: In clean isolated installations, exercise packaged desk launch and every supported headless entry without Textual installed, then audit capability acceptance on Windows and Linux.

**Acceptance Scenarios**:

1. **Given** a packaged installation without frontend build tooling or Textual, **When** the default interactive entry launches, **Then** the supported desk opens; missing assets produce actionable failure, never terminal fallback.
2. **Given** the same installation, **When** supported headless paper/backtest/report commands run on fake data, **Then** command meaning, outputs and canonical records remain compatible and import no terminal-UI helpers.
3. **Given** desktop, narrow-screen and keyboard-only operation, **When** each primary journey is exercised, **Then** navigation, focus, confirmations and status remain usable with the existing terminal-inspired visual language.
4. **Given** any mandatory parity or platform row is blocked/inconclusive, **When** retirement readiness is evaluated, **Then** it fails closed; unavailable Linux evidence is blocked, not passed.
5. **Given** SIM provisioning is required, **When** its documented headless non-TUI setup is used with fakes, **Then** the desk can inspect readiness and operate the deployed SIM fund without accepting real-brokerage configuration.

### Edge Cases

- Wrong configured root, decoy home, case aliases, trailing spaces/dots, reserved device names, symlink/reparse paths and path races: deny unsafe access; never fall back to real user roots.
- Concurrent CLI/browser writes, duplicate starts, stale PID reuse, forged ownership and crash-held admission: fail closed without killing unknown processes; unrelated funds and emergency Halt remain responsive.
- Daily backlog, explicit date/backfill, weekly/monthly cadence, one-second minimum, minute gaps/holidays/lateness and SIM regular-hours cutoff: preserve existing engine outcomes and display skips/backlog honestly.
- Repeated confirmations, delayed monitoring responses, server/browser restart and missing job identifiers: recover observation, never repeat mutations automatically.
- Invalid controls, malformed records, failed append after fills and stale approvals: separate corruption, halted and unknown outcomes; require explicit safe recovery.
- Unknown models/parameters, local endpoint failures, mixed environment/persisted configuration and credential rotation: deny invalid readiness without network validation or secret disclosure.
- Partial/stale/missing quotes, short/fractional positions and late valuation responses: label coverage, preserve signed precision and discard obsolete responses without changing recorded values.
- Archive interruption, name collision, stale head and active research references: leave an intelligible recoverable state, never partial broad deletion.
- Malicious model/report text, foreign Host/Origin, missing/expired CSRF token and untrusted endpoint URLs: reject privileged actions and render text without privileged execution.
- Missing static bundle, unavailable Linux runtime and historical-only evidence: actionable failure or blocked evidence, never fallback or inferred acceptance.

## Requirements *(mandatory)*

Each requirement is normative. Story scenarios supply primary acceptance; the discovery disposition table gives complete baseline coverage. Denial requirements are accepted only when fakes beneath production guards prove zero unauthorized side effects.

### Functional Requirements

#### Supported surface and runtime

- **FR-001**: At retirement, the existing web desk MUST be the sole supported interactive engine interface; the no-argument interactive entry MUST launch it and direct supported TUI entrypoints/dependencies MUST be removed only after FR-062 passes. No terminal fallback is permitted.
- **FR-002**: The desk MUST preserve its terminal-inspired dark, dense, monospaced financial presentation while keeping labelled status, visible focus, readable contrast and numeric precision; new controls MUST work on desktop, narrow screens and keyboard-only navigation with a command palette, back navigation and accessible confirmations.
- **FR-003**: Overview, paper detail and operational resources MUST support explicit refresh and update active status without navigation away/back. Recorded/offline/live/error labels MUST distinguish data provenance; delayed responses MUST NOT overwrite newer operation identity.
- **FR-004**: Supported headless backtest, paper create/tick/run/stop/status/list/scorecard/halt/resume/approve/reject/redo and output-file/stdout workflows MUST remain compatible without importing or installing Textual. Existing console report rendering MAY remain non-interactive.
- **FR-005**: Clean packaged installations MUST include desk assets and serve them without Node/build tools at runtime. Supported launch, container, deployment and Make/documented entrypoints MUST agree; unavailable assets MUST fail with actionable instructions, not import the old UI.
- **FR-006**: User-selected roots MUST govern every server, headless command, child, ledger, cache, configuration and credential access. No CWD, implicit home or root alias MAY redirect operations to another workspace; denied paths MUST NOT be accessed.

#### Admission, ownership and jobs

- **FR-007**: All participating cross-process browser/headless runner-start, manual tick, redo and lifecycle paths MUST share admission and identity checks. Verdict and halt/resume writes MUST coordinate with these operations without blocking emergency controls indefinitely. Conflicting actions on one deployment MUST NOT produce duplicate fills/appends or overwrite each other's work; independent deployments MUST remain independent.
- **FR-008**: Runner ownership MUST verify deployment/root identity and process incarnation, not PID liveness alone. Unknown, legacy, stale or forged ownership MUST fail closed for stop/adoption; no stale-PID process may be killed.
- **FR-009**: The desk MUST distinguish starting/running/stopping/stopped/failed/unknown, show readiness acknowledgement, configured-root identity, captured configuration, last/next session and redacted bounded diagnostic events.
- **FR-010**: Runner start MUST require an explicit operator action and passing frozen preflight. A read, page mount, approval, Resume or server startup MUST NOT start a runner.
- **FR-011**: Stop MUST target only verified owned runners, cease admission of new sessions and allow in-flight work to reach its documented safe boundary; requested stop MUST be distinguished from confirmed quiescence.
- **FR-012**: Closing/reloading the browser MUST leave an admitted runner unchanged. On server restart, a separately running runner MAY be reattached only with verified ownership; stopped/failed runners MUST NOT be automatically started. Unknown ownership MUST be displayed, not adopted.
- **FR-013**: Long-lived runners MUST NOT monopolize bounded job execution or block emergency Halt and verdict entry indefinitely. Once received, Halt MUST prevent admission of new execution; existing execution boundaries MUST be displayed honestly.
- **FR-014**: Manual execution MUST use canonical engine semantics for due/nothing-due, recorded-session idempotence, explicit reviewed dates/backfill, daily/weekly/monthly/minute cadence, catch-up oldest-first, market closure/gaps/lateness and SIM submission cutoff; no new trading algorithm is introduced.
- **FR-015**: Manual sessions and backtests MUST expose accepted/running/completed/failed/cancel-requested/cancelled/interrupted outcomes, stage/agent progress, captured request identity and final report where available.
- **FR-016**: Accepted bounded jobs MUST have recoverable identity/status. After server restart unfinished jobs MUST be marked interrupted and MUST NOT automatically resume; completed persisted results MUST remain discoverable. Browser storage alone is not durable execution evidence.
- **FR-017**: Double-clicks, lost responses, reloads, reconnects and stale confirmations MUST NOT cause repeated mutations. Ambiguous side effects MUST require explicit reconciliation rather than automatic retry; stop/cancel MUST NOT claim rollback.

#### Runtime configuration and credentials

- **FR-018**: The desk MUST list supported LLM providers/models, validate selection, show selected/effective model and source, and persist non-secret choices for subsequent operations and restarts.
- **FR-019**: The desk MUST separately select and persist a normalized market-data provider. Free credential-free data MUST be the default; paid providers MUST require explicit selection and operation-specific authorization.
- **FR-020**: Supported runtime settings MUST include local LLM endpoint, context size and timeout, plus supported remote endpoint overrides. Values MUST be validated without network access; credential-bearing URLs and unsupported schemes/parameters MUST be rejected.
- **FR-021**: API-key entry MUST be write-only, surgically persisted in private root-scoped credential storage and atomically updated with applicable owner-only protection. Status MAY reveal presence/source/effectiveness but never values; secrets MUST NOT appear in responses, logs, errors, exports, browser persistence, URLs or subprocess arguments.
- **FR-022**: Effective configuration MUST use explicit launch/environment overrides ahead of root-persisted settings ahead of safe defaults; the desk MUST expose non-secret provenance and any override preventing a saved value from taking effect.
- **FR-023**: Every admitted operation MUST freeze its mandate, universe, provider/model and relevant credential/configuration version before execution. Saved changes apply to the next operation, never hot-swap active work; an existing runner MUST require explicit stop/start to adopt new settings. Active credential material MUST remain private and stable for that operation.
- **FR-024**: Preflight MUST reject missing required credentials, unknown model/provider, invalid mandate/root, unauthorized network, conflicting owner, halt or replay error before provider construction or side effects. Local models and free data MUST NOT require unrelated cloud keys.
- **FR-025**: External calls MUST require explicit operator network enablement bounded to reviewed operations and provider/cost policy. Page mount, observation polling, validation and reconnect MUST never enable network; paid valuation auto-polling and silent paid defaults are prohibited.
- **FR-026**: Runner authorization MUST identify its continuing scheduled paper activity and providers; it MUST NOT authorize actual brokerage or arbitrary background data loops. Until the Principle II governance conflict is resolved, network-backed unattended runner acceptance is blocked; offline/fake scheduled operation remains testable.
- **FR-027**: Local paper and Saxo SIM MUST remain supported broker choices with clear readiness. Existing headless non-TUI SIM reference/OAuth provisioning is the only interactive provisioning exception; the desk MUST explain it and inspect redacted readiness, not persist rotated tokens as ordinary API keys or offer real brokerage.

#### Mandate configuration

- **FR-028**: The desk MUST list/read/create/edit/clone/rename all supported mandate configurations with canonical identity discovery across YAML/YML, case-aware collisions and protected-name/path validation. Edit/rename confirmations MUST bind the expected template revision and reject stale changes; malformed entries MUST remain visible as errors rather than silently vanish.
- **FR-029**: The editor MUST cover every supported validated mandate field: capital, deployment universe, strategy/analyst roster, sleeves and model weights/constructor parameters, blend gross target/mode, dollar neutrality, all risk limits, transaction spread/per-share/notional/minimum commissions, minimum order equity threshold, benchmark, approval gate, broker, cadence and intraday interval/window.
- **FR-030**: A validated structured JSON advanced editor MAY satisfy complete coverage; every field need not have an individual widget. Ordinary and advanced views MUST agree and round-trip supported values without dropping non-defaults; registry/parameter validation MUST reject arbitrary executable content.
- **FR-031**: Library strategies MUST retain canonical rosters/identity unless deliberately edited into an identified custom composition. Supported analyst subsets/weights/parameters MUST be editable and validated; dollar neutrality MUST NOT be silently inferred.
- **FR-032**: Schedule editing MUST preserve daily/weekly/monthly/minute rules, one-second minimum and window/timezone/SIM restrictions. Day-grid conversion MUST remove minute-only fields before validation; returning to minute cadence MUST restore valid defaults.
- **FR-033**: Saving/editing MUST preserve historical field ordering/default-off omissions, approval/cost defaults and replayable serialization. A deployed mandate MUST be immutable; template editing MUST NOT rewrite its snapshot or pending decision.
- **FR-034**: Successful creation/edit MUST lead to inspect, deploy or reviewed backtest/manual-run actions; universe selection MUST be distinct from immutable template identity and revalidated at operation admission.

#### Approvals, recovery and lifecycle

- **FR-035**: Verdicts MUST bind both decision timestamp and source-record hash, preserve canonical replacement semantics and visibly distinguish pending/matching/stale/consumed/expired state. A stale confirmation MUST conflict, never retarget.
- **FR-036**: Approval and Run now MUST be separate authorizations even when offered in one journey. Resume MUST only clear a verified halt; it MUST NOT start a runner, execute immediately or bypass replay checks.
- **FR-037**: Emergency Halt MUST remain available through a root/identity-safe recovery path when controls are unreadable; halt/control corruption and ledger corruption MUST remain distinct. No execution or Resume is allowed until required verification succeeds.
- **FR-038**: Latest-session redo MUST require explicit expected identity/head confirmation, quiescent shared admission and local-paper eligibility. Source redo MUST invalidate stale verdicts; execution redo MUST preserve matching consumed-vote replay. Superseded records MUST remain available and SIM redo MUST be denied.
- **FR-039**: Failure after fills but before append MUST preserve canonical halt/audit behavior and expose ambiguous state. Neither browser recovery nor job restart MAY repeat effects automatically or fabricate a successful record.
- **FR-040**: Deployment MUST create an immutable snapshot under a distinct canonical identity, with collision/protected-root checks and verified readiness before any execution.
- **FR-041**: Template, deployment and research removal MUST be separately scoped reversible archival, not broad permanent deletion. Review MUST show exact identity, consequences, references and expected revision/head; stale or mismatched confirmations MUST fail.
- **FR-042**: Deployment archive/replacement MUST require stopped, verified owned runners and no queued/in-flight conflicting writer. Archive/restore MUST preserve history and recover intelligibly after interruption; restore MUST collision-check and remain stopped.
- **FR-043**: Replacement/redeployment MUST archive the prior deployment and create a new identity linked to retained history; it MUST NOT overwrite deployed rules or implicitly replay pending decisions. Research archive MUST coordinate active jobs/references and leave unrelated results intact.
- **FR-044**: Real `watchtower`, `watchtower-weekly`, `umbrella`, their runners and creator preview `8765` MUST NOT be accessed, started, stopped, modified or used as acceptance fixtures. Alternate path/name aliases MUST NOT bypass protection.

#### Valuation, research and reporting

- **FR-045**: Live valuation MUST require explicit authorized refresh and show estimate versus recorded values separately, including quote source, valuation timestamp, per-ticker print/freshness and missing/stale coverage.
- **FR-046**: Partial/stale quotes MUST NOT appear as complete current NAV or overwrite recorded NAV, benchmark, performance or scorecards. Signed/fractional positions and cash precision MUST be preserved; obsolete responses MUST be discarded.
- **FR-047**: Backtest review MUST show validated dates/universe, defaults, mandate identity/revision, provider/model and network/cost authorization; execution MUST reuse canonical domain backtesting and captured settings. Credential-free data that is not point-in-time MUST carry an explicit research limitation, not imply point-in-time validity.
- **FR-048**: Backtest warming/stage/analyst progress, theses and cancellation boundaries MUST be observable without terminal widgets. Cancelling MUST prevent further work at the documented boundary and retain clear status, not claim completed work was rolled back.
- **FR-049**: Saved research MUST be browsable beyond the current 100-row bound through bounded pagination/search, with stable identities, malformed-record errors and reopenable reports.
- **FR-050**: Paper session/day history and report drilldowns MUST show proposed versus executed allocations, risk/clamps, orders/fills, weights, tape, theses, costs, signed/fractional shares, cash/NAV, benchmark, metrics and canonical analyst/strategy scorecards.
- **FR-051**: Browser downloads and supported headless JSON/stdout/output files MUST preserve canonical result/provenance and precision, without secrets. Browser formatting MUST NOT round-trip into authoritative records.
- **FR-052**: Minute-mandate backtests MUST be labelled daily-grid replay in review, progress and reports. True historical intraday backtesting is explicitly out of scope, not a hidden parity claim.

#### Boundaries, acceptance and governance

- **FR-053**: Existing loopback-only serving, Host and Origin validation, CSRF authorization and protected path checks MUST remain enforced on all added mutations and observation connections; startup capabilities MUST NOT be elevated by browser requests.
- **FR-054**: Untrusted model/report/configuration text MUST NOT execute privileged content. Redacted diagnostics and endpoint validation MUST preserve local-boundary protections across browser, exports and children.
- **FR-055**: Domain execution, broker reconciliation, sizing/cash invariants, ledger replay and approval semantics MUST remain authoritative and shared, not reimplemented in presentation. Historical records MUST replay byte-identically; cross-revision parity fixtures MUST pin the code-version stamp.
- **FR-056**: Existing reusable credential, defaults, console report/scorecard and schedule/progress behaviors MUST remain available outside TUI dependencies. Behavioral assertions from retired UI tests MUST be replaced before those tests/dependencies are removed.
- **FR-057**: Every discovery capability A01-F13 MUST have a linked requirement and acceptance disposition. A missing control MUST NOT be declared supported by a demo, documentation alone or a headless exception other than those explicitly stated here.
- **FR-058**: Future tests MUST use isolated synthetic HOME/USERPROFILE/root, dotenv disabled and credentials cleared before imports; fake network/data/LLM/broker/secrets/process/clock adapters MUST sit beneath production guards. No paid calls, real roots/runners, creator port or uncontrolled network/test loops are permitted.
- **FR-059**: Acceptance MUST record criterion, expected/observed outcome, source revision/build, time, environment, fixture provenance and exclusions. Affected evidence MUST reopen after fixes; historical PR7 counts MUST NOT be substituted for migration evidence.
- **FR-060**: The subsequent workflow MUST clarify recorded assumptions, resolve adversarial ledger/local-boundary/human-control findings before plan approval, publish an open main-targeting plan-review PR before tasks, implement test-first slices, converge every required gap and perform multiple independent QA passes including final re-review after fixes.
- **FR-061**: A proposed constitutional amendment MUST be addressed in the plan: replace TUI-specific surface wording with supported web/headless consistency and reconcile explicit authorized scheduled paper activity with Principle II. No amendment is made in this specify execution; existing MUST principles bind until governance requirements, including a passing full suite, are met.
- **FR-062**: Retirement MUST wait for implemented accepted parity, fresh TUI-free runtime/entrypoint/packaging evidence, protected-root isolation, shared-writer/ownership/restart tests and Windows/Linux lifecycle acceptance with no required blocked/inconclusive rows. Missing Linux evidence MUST block retirement. A new main-targeting PR MUST remain open for human review and MUST never be merged by this workflow.

### Key Entities *(include if feature involves data)*

- **Mandate template/revision**: Validated fund rules and canonical name; editable separately from deployments, with full supported field coverage.
- **Deployment**: Immutable mandate snapshot, universe, canonical identity, ledger/head and active/archived lifecycle; replacement links a new identity to retained history.
- **Effective configuration snapshot**: Non-secret provider/model/runtime choices, precedence/provenance and private credential version captured by an admitted operation.
- **Runner ownership/admission**: Verified workspace/deployment/process incarnation and conflicting-operation authority, separate from an untrusted PID.
- **Operation/job**: Stable request identity, frozen inputs, progress, cancellation/interruption outcome and links to results; observation does not authorize execution.
- **Decision/verdict**: Proposed action bound to timestamp/source hash, with pending, consumed and expired status.
- **Session record/report**: Canonical hash-chained facts and derived proposed/executed/risk/performance views.
- **Live valuation estimate**: Observational marks, source/time/coverage and stale state, never a replacement for a record.
- **Archive record**: Reversible scoped lifecycle action, expected identity/revision/head, retained provenance and restore/replacement links.
- **Acceptance evidence**: Source-bound result and environment/provenance; blocked is distinct from passed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the 74 discovery capabilities have accepted migrated coverage or the explicit supported exceptions recorded in discovery; zero required blocked/inconclusive rows remain at retirement.
- **SC-002**: All six operator journeys complete without the old terminal UI in isolated acceptance, with every supported configuration field round-tripping without loss.
- **SC-003**: In cross-process duplicate-start/manual/redo/archive and lost-response scenarios, zero duplicate fills, unauthorized appends, unrelated process signals or broad removals occur; independent funds remain usable.
- **SC-004**: All canonical fixture comparisons preserve historical replay, precision, approvals and sizing invariants; 100% of captured active-operation configurations remain unchanged after settings edits.
- **SC-005**: No page observation/reload/reconnect, configuration validation or denied action causes an external provider call; credential sentinel values appear zero times in returned/logged/exported/browser-persisted/subprocess-argument material.
- **SC-006**: In restart/reload acceptance, every admitted bounded job is recoverably completed/failed/cancelled/interrupted, every live runner is owned or explicitly unknown, and zero operations resume or repeat automatically.
- **SC-007**: Windows and Linux clean-install lifecycle, packaged launch and supported headless command acceptance all pass without the old terminal UI or runtime frontend build tools; missing-platform evidence produces a blocked gate.
- **SC-008**: Every primary action and confirmation is operable keyboard-only and at a 360-pixel-wide viewport; accepted mock-based screenshots preserve the existing terminal-inspired appearance without clipped critical status or numeric values.
- **SC-009**: With synthetic local workloads, local action acknowledgement and active status updates appear within two seconds in at least 95% of acceptance observations, excluding provider computation; Stop/Halt status never reports completion before its safe boundary.
- **SC-010**: Multiple independent QA passes and final source-bound review close every retirement-blocking finding, the required plan-review and new implementation PRs target main, and neither is merged by the autonomous workflow.

## Assumptions

1. The target is a trusted local operator desk plus retained headless deployment/automation, not a public multi-user trading service. Existing loopback guards remain mandatory.
2. React/shadcn and terminal-inspired appearance are explicit user choices. Architecture, protocols, storage mechanism for admission/configuration/jobs and component design are deferred to the plan.
3. Explicit operator network enablement is necessary but not sufficient for paid work: provider/cost and operation authorization are also required. Free data remains the default; offline viewing and free/local readiness need zero credentials.
4. Scheduled activity is explicitly started, paper-only, and never actual brokerage. Network-backed unattended runner operation is a proposed governance exception, not permission to violate the present constitution; plan approval must reconcile it.
5. Launch/environment overrides take precedence over persisted root settings, then safe defaults. Settings changes persist for the next operation; running jobs/runners keep frozen configuration. Adopting changes in a runner requires deliberate restart.
6. Deployed mandates remain immutable. Full supported editor coverage may use a validated structured JSON advanced view; partial widget coverage is not complete parity.
7. Irreversible broad deletion is excluded. Template/deployment/research removal means scoped reversible archival, with identity/head/revision confirmations and collision-checked stopped restoration.
8. Browser closure does not stop runners; server restart may reattach only verified still-live runners. Bounded jobs become interrupted, not auto-resumed. Reload never repeats mutations.
9. Saxo SIM reference/OAuth provisioning remains a documented headless non-TUI exception because it is a separate existing credential lifecycle; all ordinary desk operations/readiness must support SIM with fakes. No real-brokerage setup is added.
10. Explicit reviewed headless/manual backfill and JSON/console output remain supported. Minute backtests retain daily-grid semantics; historical intraday simulation is a separate future feature.
11. Autonomous gate decisions and remediation are explicitly user-directed; this does not authorize real-fund operations, secret disclosure, paid/network testing, merging, skipping mandatory evidence or amending the constitution now.
12. Windows baseline anomalies and unavailable Linux/browser tooling are evidence limitations, not passes or blanket exemptions for new defects. Current specification validation is documentation-only; runtime acceptance waits for authorized isolated implementation work.
13. Core spec identifiers remain FR-001 through FR-062. Later trace tooling must explicitly map FR identifiers rather than silently assume its default REQ prefix. Co-located tests are mandatory under the constitution despite generic task-template optional wording.
14. Dependency: domain seams and safety boundaries identified in discovery must remain authoritative; prior additive-desk acceptance is superseded only after the new retirement gate passes. No clarification markers remain, but the assumptions clarification and adversarial gates are still required before planning.
