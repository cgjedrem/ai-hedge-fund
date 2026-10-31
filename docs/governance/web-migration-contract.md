# Web migration contract

**Effective planning decision:** 2026-10-31, user-directed autonomy.
**Scope:** spec005 web-only engine migration; implementation is pending.
**Authority:** amended [constitution](../../.specify/memory/constitution.md).
Historical [spec005](../../specs/005-web-engine-migration/spec.md) and discovery remain
point-in-time records. This forward contract resolves ambiguities and explicitly supersedes
the contradictions listed in §1. It does not certify runtime safety.

## 1. Governance and deliberate scope changes

**G1 — HM1.** React replaces the TUI configuration surface in governance now; removal
still waits for complete retirement acceptance. Paper-only, ledger integrity, evidence
and no-paid-tests principles remain binding. The user authorized a documentation-only
amendment exception to the old amendment/full-suite dependency; no runtime suite was
run or deemed passed. Every future baseline failure needs individual pre-change reproduction
and source-bound evidence. Linux-required blocked rows remain blocked. This supersedes
historical FR-061 and Assumption 11 only concerning amendment authority.

**G2 — HM2.** Free credential-free market data is the default for every supported entry.
This intentionally changes compatibility with the old paid `fd` default. An environment
provider override or stored key may select/configure a provider but never authorize a call.
Paid headless operations need explicit per-invocation authorization; saved settings and
environment cannot retain it. All cloud LLMs, including cloud-labelled/keyless Ollama
models, are paid/cloud policy class even if an account reports no charge. Genuinely local
inference requires approved model identity and loopback endpoint, not key absence or a
brand label. Cloud models are prohibited in runners. This is an explicit safety exception
to FR-004's unchanged-default compatibility.

**G3 — HM3.** Scheduled local-paper work may use free data and genuinely local models only.
Authorization binds root/deployment, broker, mandate/universe/configuration digest, permitted
providers/endpoints, finite expiry, maximum sessions and call/resource bounds. The first
reached bound stops new admission; expiry during a session does not claim rollback. Network
enablement is necessary but insufficient. Paid/cloud scheduled loops, arbitrary background
loops and actual brokerage remain prohibited. Paid one-shot manual, valuation and backtest
actions require reviewed per-operation authorization and budget. Review shows call/cost
estimate, dates, universe and assumptions; estimate is advisory and enforced cap authoritative.
Unknown upper-bound cost denies paid admission. Reserve worst-case budget before dispatch;
spending/call/resource caps prevent the next call rather than alerting after overspend.
No automatic paid retries. Historical FR-026/Assumption 4's conflict is resolved for design only.

**G4 — LM5.** Web mutation/execution/lifecycle is local-paper only. The web may inspect
redacted SIM readiness and records, but denies SIM start/stop/tick/redo/halt/resume/verdict/
deploy/archive/restore/replace. Retain non-TUI headless SIM provisioning and canonical
supported headless SIM operations with fakes in tests, never real brokerage. One SIM
account/environment binding belongs to exactly one active deployment under a root-wide
exclusive registry. Reject duplicate binding at deploy/restore/replace. Also reject bindings
across roots: absent verifiable exclusive account control, deny headless SIM mutation;
a root-local file alone cannot establish global exclusivity. Binding transfer requires
verified stopped/quiescent old owner and explicit release/transfer provenance. Provisioning
alone grants no execution. This expressly supersedes US6 scenario 5, FR-027's browser-operation
reading and Assumption 9: SIM browser control is an intentional parity exemption, not accepted
web-control coverage. Discovery B12/C09/D07 and all affected SIM rows must record the exemption
in future trace evidence; never silently claim all 74 capabilities are migrated.

## 2. Launch, root and exposure boundary

**R1 — LB1.** The writable driver requires an explicit launch root argument fixed before
imports touching configuration/providers/storage. Every headless invocation/child receives
that exact argument. Missing/invalid root fails; no HOME/USERPROFILE/CWD/environment root
or upward fallback. Canonical identity includes filesystem identity, not only a normalized
string. Reject traversal, protected/reserved aliases, symlink/reparse escape, case collision,
trailing-dot/space and path races before access; revalidate identity at use through supported
handle-relative operations. Read-only discovery cannot bypass protected-path guards.

**R2 — LB1.** Dotenv is disabled in tests. If explicitly enabled in production, read only
the exact configured-root dotenv file; no CWD/parent/home discovery. Non-secret setting
precedence: explicit launch/environment override, root-persisted setting, safe default.
Root, writable/read-only mode, network capability, paid authorization, container mode and
budgets cannot be elevated by environment/browser input. Children get minimal allowlisted
environment (required OS launch variables and validated non-secret provider settings), not
ambient credentials/root/capability variables. Credentials use a root-private snapshot/handle
available only to the owned process, never arguments/logs. Root-specific cache/plot/config
paths and isolated child HOME/USERPROFILE prevent third-party library fallbacks.

**R3 — LB5.** Supported writable roots: local NTFS on Windows and local ext4 on Linux with
tested locks, atomic replacement and identity primitives. Other filesystems are unsupported
until separately evidenced. Deny UNC, SMB/NFS, mapped network drives, cloud-synced roots and
remote mounts. Unknown filesystem/identity is unsupported. Namespace and filesystem/device
identity are part of admissibility.

**R4 — LM2/LB2.** One host PID namespace holds write authority per root. Host desk/CLI/
owned children share admission. Container desk is a read-only observer: read-only state
mount, no credentials mount/provider calls/root writes (including job/config/cache sidecars),
workers/runners/lifecycle control or mutation proxy. It reads immutable snapshots, validates
paired head/snapshot and returns observation conflict rather than an inconsistent view.
Remove Docker ttyd download, `tui`/`tui-web`, automatic runner services/restart policies
from supported images/compose examples during implementation. No automatic upgraded-runner
start/restart. Separate isolated headless container deployments are outside this writable
topology. Cross-namespace stop/adoption/mutation is unsupported and denied.

**R5 — LB2.** Host writable desk is loopback-only. Sole bind carveout: explicitly read-only
container observer binding an internal interface while published exclusively to host loopback.
Non-loopback publication/host networking and remote/public exposure are unsupported.
Host/Origin/CSRF checks remain enforced on added routes/channels as applicable. Browser
protection does not create container write authority. Ordinary examples never use protected
deployment names, real home mounts or creator port 8765.

**R6 — LB3.** Remote endpoints require HTTPS, no userinfo/query/fragment secrets, validated
ports and approved provider host identity. Credentials bind to exact scheme/host/port and
never follow redirects/changed endpoints. Deny metadata, link-local, private, multicast,
unspecified and other non-global destinations including IPv4-mapped IPv6. Only local-model
literal loopback on the host with approved port/model is a private-address exception;
`host.docker.internal` is not local-model permission. Validation makes no calls. Authorized
dispatch resolves/revalidates all destination addresses, pins the checked destination,
verifies TLS and denies redirect/DNS rebinding escapes. String validation alone is insufficient.
A model possibly proxying cloud inference is denied the scheduled-local exception.

## 3. Shared admission and runner ownership

**A1 — LM1.** Every writer participates: CLI/web manual execution, runners, redo, verdict/
control, template/config/credential, deploy/archive/restore/replace, research results and
account binding. Web-local mutexes are insufficient. A versioned root admission protocol
uses OS-released cross-process locks plus durable journals: short root registry lock for
shared names/accounts/config; deployment runner reservation; deployment execution/lifecycle
lease; short control/decision lock. Multi-resource acquisition order: registry, then sorted
deployment identities. No blocking runner lock on emergency-control paths. Independent
deployments remain independent; bounded research capacity is separate from runner lifetime.

**A2 — LM1/HM5.** Runner reservation lasts verified owned lifetime; each session takes/
rechecks a short execution lease. Start/manual/redo/archive/replace/restore deny conflicts
or unknown owners before effects. Manual execution is denied, never queued, while a runner
reservation is active, even between sessions. Lifecycle requires no queued/in-flight writer.
Verdict/Halt use bounded short control lane; root-safe emergency Halt publishes an atomic
fail-closed marker even when ordinary controls are corrupt. Check Halt at admission and
safe provider/execution boundaries; already-issued effects may complete. Configuration/
template edits freeze versions and never modify deployments or active captures.

**A3 — LM1.** Legacy/nonparticipating writer presence or uncertain ownership blocks all
mutation/admission, not only stop/adoption. A protocol marker cannot fence an old binary
that ignores it. Upgrade requires controlled offline handover with evidence old CLI/cron/
services/writable containers cannot reach the root. Unverified handover is ownership-unknown,
read-only. Never auto-adopt/start to test ownership. Locks do not defend against arbitrary
out-of-band file writers; inability to exclude those writers denies mutation.

**A4 — LM1/LM2/HM4.** Ownership binds root/deployment, protocol/build, namespace/host boot,
PID/process incarnation, private handshake nonce, authorization and capture digest. PID
liveness is insufficient. POSIX session/process group and Windows owned process group/
control channel detach runner lifetime from browser/server and enable verified graceful stop.
Never signal unrelated PIDs/unknown descendants. Stop revokes new admission and waits for
safe boundary; stopping differs from confirmed stopped. Browser closure does nothing.
Server restart may observe/reattach only a verified live upgraded owner, never start/restart
stopped/failed/legacy/unknown runners. No OS/compose autorestart.

**A5 — LM1.** Kernel crash release does not prove financial safety. Recovery requires explicit
identity/head-bound review, verified owner death/quiescence in the same namespace, legacy
exclusion, replay and operation journal inspection under registry/deployment locks. Never
displace live/unknown owners on timeout/TTL/PID reuse. Record recovery provenance before
releasing stale reservation; potential post-fill effects remain ambiguous under §4.
Unsupported incarnation/lock/ACL primitives deny mutation and block platform acceptance.

## 4. Confirmation, recovery and durable operations

**O1 — HM5/LM4.** Expiring single-use confirmation binds action/root/object identity,
revision/head, exact ordered due-session set, dates/backfill, universe, frozen configuration/
broker/provider versions, budgets and consequences. Digest canonical preview bytes and bind
token to local operator session. Consume token atomically with durable request admission.
Expiry/mismatch/head/due-set/time-window changes or reuse conflict; refresh/review, never
retarget. Identical admitted request ID/payload returns existing status after consumption;
same ID/different payload conflicts. New requests cannot reuse the token.

**O2 — LM4.** Restore remains stopped and collision-checked, never auto-catches up. Before
manual/backfill/start after restore/delay, review exact oldest-first backlog, count/resource
bound and explicit bounded selection/skip decision consistent with canonical cadence; never
fabricate bars or silently discard due work. Admission recomputes head/exact due-set.
Clock-induced staleness requires new review. Runner preview binds initial due-set separately
from finite future-schedule authorization; all bounds apply to catch-up and future work.

**O3 — HM5.** Verdict remains timestamp/source-hash bound with canonical consumed/replacement
semantics. Approval is not Run/Resume/start. Active-runner approval confirmation warns existing
scoped schedule authorization may execute the approved decision later. Settings/Resume/
approval never start work. Redo is local-paper-only, latest/head-bound and quiescent, retains
superseded history, invalidates source votes and preserves matching consumed execution votes.

**O4 — LM3.** Distinguish corrupt controls/replay and ambiguous post-fill halts. Replay alone
cannot clear ambiguity. Require durable reconciliation provenance: request/operation ID,
expected/current head, broker book/fill identities and evidence, captured version, operator
decision, recorded time and residual uncertainty. Use canonical broker reconciliation;
never fabricate success records. Irreconcilable remains halted/unknown. Resume requires
both reconciliation and replay, never repeats the old job or starts a runner.

**O5 — HM4/HM5.** Root-private sidecars persist request/idempotency identity, preview/
configuration digest, authorization, progress/status and reconciliation/confirmation
provenance without changing old ledger fields. Accepted is durable before spawn/effects.
Atomic journaling associates token consumption and admission. States: accepted → running →
completed/failed; cancel-requested → cancelled at safe boundary. Restart marks unfinished
bounded work interrupted, with ambiguity if effects may exist; no auto-resume/retry.
Surviving bounded workers must be fenced from new effects and safely reconciled/stopped
before conflicting admission. Lost response/reload queries status only. Completed results
remain discoverable; cancellation/stop never claims rollback.

## 5. Configuration, credentials and observation

**C1 — LB4.** Private credentials support atomic surgical set/delete and monotonic versions.
Deletion makes the key absent for new captures; it cannot erase privately captured active
material. Expose presence/source/effectiveness/version only, with absent/present/overridden/
deleted-after-capture/restart-required distinguishing stored/effective/active versions.
Warn about active captures; stopping is separate. Never echo keys in responses/errors/
logs/exports/browser storage/arguments. Apply/verify POSIX owner-only modes and restrictive
Windows ACL inheritance/owner SID. If protection cannot be established, deny mutation/use;
if validation tooling cannot evidence it, acceptance is blocked, not passed by POSIX analogy.

**C2.** Full validated JSON advanced editing plus ordinary controls must round-trip all
domain weights/parameters/risk/cost/schedule/broker/default omissions and canonical library-
to-custom identity. No arbitrary code construction. Revision-bound edit/rename/clone does
not change deployment. Universe and lifecycle are separate resources. Archive by exact
identity/head/references; journal interrupted moves/restores; replacement creates a distinct
linked identity with retained history, never overwrites deployed rules.

**C3.** Observation never authorizes calls. Explicit authorized refresh yields estimated
valuation with source/time/per-ticker freshness/coverage separate from recorded NAV.
Partial/stale marks never claim complete current NAV or overwrite records. Reports/exports
preserve canonical signed/fractional precision, proposed/executed/risk/cost/scorecards and
inert untrusted text. Minute backtests are daily replay; free data is not asserted point-in-time.
Research uses stable bounded pagination/search, malformed errors and scoped archive.

## 6. Evidence and remaining risk

Resolutions are design commitments, not implemented fixes. Retirement is blocked until
every required capability/platform/lifecycle row has fresh evidence. Map all 74 discovery
IDs to FRs, tests and status including explicit SIM exemption. Move each retired UI assertion
before deleting tests/dependencies; include Docker ttyd/TUI/compose/Make/README and helper imports.

Record exact criterion/source, expected/observed result, actual source/build/time/environment,
synthetic fixture provenance and exclusions. Reopen affected rows after fixes; no invented
clocks/runtime passes/historical counts. Baseline exceptions need individual paired reproduction.
No paid tests. Synthetic protected-name fixtures may contain forbidden names only inside
an isolated test root to prove denial before access; ordinary examples never do. Do not
fingerprint real protected roots for evidence.

Remaining implementation risks: OS locks/incarnation/Windows ACLs; legacy handover; DNS
enforcement; cost estimation; post-fill reconciliation; worker stop/restart; packaging/browser
accessibility. None is accepted runtime-safe merely because specified here. Network filesystems,
cross-namespace mutation and SIM browser control are intentionally unsupported, not hidden passes.
