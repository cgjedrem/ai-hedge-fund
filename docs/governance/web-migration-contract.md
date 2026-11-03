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

**Current implementation boundary (not an A3 waiver).** Root enrollment, root/build
binding, inventory drift checks and OS lanes fence cooperating participants only.
`migrate-existing` records an exact operator attestation; it does not independently
prove that an old executable, writable container or arbitrary filesystem writer has
lost access. A successful attestation or lock probe is therefore not production
handover acceptance. If exclusion cannot be established outside this protocol, keep
the desk read-only. T015/T021/T138 remain incomplete on that criterion.

**Write-authority classification (implemented).** `handover.write_authority(root)`
separates enrollment from write authority. Only `fresh` and `relocated` roots that the
legacy-reachability checks below do not flag are `protocol-native` (the checks cover the
legacy home itself and aliases at its `<top>` and `<top>/<item>` levels; deeper per-file
symlinks/hardlinks are left to inventory/head drift detection); every other enrolled root is
`ownership-unknown` (or `unavailable` when enrollment is invalid) and read-only:

- `migrate-existing` (attested in-place) roots → `attested-migration-read-only`.
- Root path containing a `.hedge-fund` component (case-insensitive), a nested `.hedge-fund`
  entry, or a root that is, contains, or sits inside `<HOME>/.hedge-fund`, or that any
  `<HOME>/.hedge-fund/<top>` or `<top>/<item>` alias resolves into (junction/symlink, by
  device/inode and resolved path; bounded scan) → `legacy-layout-*` / `legacy-home-alias`.
- Any `paper/*/runner.pid` → `legacy-runner-present`; unverifiable or over-bound probes →
  `legacy-reachability-unverified`.

`RootOwnerLease.acquire`/`matches`, `root_registry_writer`, `require_paper_write_lanes` and
stale-reservation recovery enforce it, so web, CLI, owned-runner child, research/mandate and
emergency Halt writers all fail closed once authority is lost, including writers already
holding lanes. The web desk re-classifies on every capabilities read and write attempt,
reports `write_authority`, and drops its mutation token and owner lease on denial.
`aihf --root SOURCE handover inspect-source` (read-only) plus
`aihf --root TARGET handover relocate-from SOURCE --content-digest D` copies engine data
(`mandates`, `paper`, `research`) into an empty, disjoint, legacy-unreachable target. The
top-level `.env`, `cache` and `runtime` are never copied, and any `.env`/`.env.*` file under
the copied trees refuses relocation before its bytes are read. The copy is digest-pinned and verified per file, the
source is re-snapshotted unchanged, and target heads must equal source heads. The source
is never written. A failed copy leaves the target `invalid` and read-only.
Raw-write audit (this slice, source grep of non-test modules for file write/replace/unlink
calls): enrolled-root writes in `paths.py`, `backtesting/research.py`, `fund/storage.py`,
`paper/ledger.py` and `web/services.py` sit behind the owner-lease lanes,
`require_paper_write_lanes` or `root_registry_writer`; TUI wipe always denies via
`paper_write_denial`; the legacy paper runner entrypoint is disabled. This is a static audit
plus the tests above, not the T021 exhaustive interleaving matrix.
T021 source-based writer map (supersedes the grep audit as the inventory, still partial):
`hedge_fund\runtime\test_writer_map.py` AST-scans every non-test production module for raw
write primitives (`write_text`/`write_bytes`/`open` write modes/`mkdir`/`rename`/`replace`/
`unlink`/`remove`/`rmtree`/`write_atomic` and the root `rename_file`/`rename_directory`/
`unlink_file` primitives). Each `(module, qualname, primitive)` is mapped to its seam
(root no-follow, paper inventory transition, bound-root `write_atomic`, paths helper,
unenrolled legacy branch, denied entrypoint, primitive, bootstrap or residual), an evidence
level (`race`, `denial`, `primitive`, `none`) and existing test nodes. The test fails on
unmapped or stale callsites and on missing test nodes, and pins the residual set.
Deterministic barrier tests in `hedge_fund\runtime\test_writer_race_matrix.py` cover an
authority flip (legacy home alias or `runner.pid`) inside paper append/rewind/deploy/
approval-clear/audit transitions, between successive deploy effects, after a completed rewind effect, after a lifecycle
journal and before a lifecycle head transition, and between web mandate rename and write.
They also cover a junction/link swap of `ledger/superseded`, the ledger directory or the
approval parent mid-transaction, same-fund `WriterConflict` while a transaction is paused,
independent-fund progress, and crash after the rewind rename followed by restart.
Fixes from these tests: paper ledger/deploy effects on enrolled roots go through
`PaperInventoryTransition` effect methods or the new no-follow `RootContext.unlink_file`,
which recheck write authority immediately before each effect. Ledger-head records are
published only after a final authority recheck. Lifecycle `_move`/`_write_index` recheck
root ownership. The web mandate update returns 409, naming the partial state when authority
changes after the rename. A failed emergency Halt after a failed redo raises
`PaperReconciliationRequired` chained to the original error.
Cooperative protocol writers are serialized with OS locks; authority and inventory are
revalidated at defined effect/publication boundaries; supported no-follow primitives
prevent reparse traversal. Same-account out-of-band writers are not fenced, and mutations
completed before detected authority loss may require reconciliation.
Residuals named by the map (open):
- the raw `events.jsonl` append follows links (detected by drift, not prevented);
- `paths.write_atomic` falls back to raw `os.replace` when no root is bound; for paths under an
  enrolled root the admission slice below now routes that fallback through the enclosing root's
  `RootContext` and admission, so the raw replace remains only for unenrolled paths;
- there is no durable rewind intent, so a crash after the rename leaves root-wide drift
  that blocks every fund until offline reconciliation;
- the mandate rename+rewrite is not journaled;
- the POSIX `lstat`→`unlinkat` delete is not identity-fenced;
- Saxo token refresh locks and explicit credential files live outside root admission;
- demo/bootstrap directory creation precedes enrollment.
**A3 decision (2026-11-03, conservative default).** Cooperative registry/OS locks,
enrollment, attestation and inventory/head drift detection do **not** prove exclusion of
unaware or out-of-band same-account writers, and no surface may claim they do. Write
authority therefore additionally requires an out-of-band exclusion basis
(`runtime/exclusion.py::out_of_band_exclusion_basis`). No production basis exists yet: a
protocol-native root without one is `ownership-unknown` with reason
`out-of-band-exclusion-unproven`, so every enrolled production root is read-only for the
owner lease, registry writer, paper lanes, web desk, CLI and owned runner. Enabling
production mutation requires a new, explicitly evidenced basis (dedicated OS account,
ACL or sandbox that unaware writers cannot reach); none is implemented. The only basis
today is `synthetic-test-owned`: test mode plus a root strictly inside the harness-created
`<checkout>/outputs/spec005-test-*` directory carrying its regular `.test-owned` marker,
with no reparse points on the chain. It exists so synthetic tests can exercise controlled
flows; it is not production evidence.

**T021 admission slice: writer inventory and admission race matrix (2026-11-03).** Complements the writer map and barrier matrix above. A hidden bypass was fixed: the owned
runner child never bound its root, so unbound `paths.write_bytes`/`ensure_directory`/
`write_atomic` fallbacks wrote into the enrolled root without admission. Unbound writes now
detect an enrolled ancestor on both the lexical path and the parent-alias-resolved path
(`runtime/private/v1/handover.json`; any or unreadable marker entry counts as enrolled, and
admission state without a marker fails closed) and route through that root's `RootContext`
and admission, and the runner child binds its root. Saxo refresh-lock directories inside an
enrolled root are rejected. Lane acquisition re-verifies owner/authority after the OS
lock is granted. `runtime/test_writer_inventory.py` is an AST ratchet over every raw
write/replace/unlink/mkdir/open-for-write site in `hedge_fund/` production modules
(including any `os`/`shutil`/`tempfile` writer call, names imported from them, and `open`
with a non-literal mode; `hedge_fund/test_support/` is not scanned even though it ships in
the wheel — its synthetic enrollment helper refuses any root without the
`synthetic-test-owned` basis), classified as
paths-routed, registry, paper-lanes, deployment, web-gated, bootstrap, lock-file, root
primitive, disabled, outside-root or test-harness; an unclassified, stale or recounted
site fails. `runtime/test_writer_admission_race_matrix.py` drives the central primitives with a real
second interpreter: same-object contention for every lane, independent-object progress,
authority flip while a lane is held (legacy `runner.pid`, legacy home alias, loss of the
exclusion basis) and during OS-lock wait, registry snapshot versus in-flight commit,
crash/kill then retry, cooperative release then retry, production read-only denial,
exclusion-basis negatives and enrolled-root path routing.

Uncovered surface (open): (1) production mutation is disabled pending an exclusion basis;
(2) the matrix exercises the shared admission primitives each writer class uses, not every
domain writer end-to-end under every interleaving; (3) deeper per-file symlink/hardlink
aliases inside a root rely on inventory/head drift; (4) legacy unenrolled `~/.hedge-fund`
use without `--root` keeps legacy behavior outside this protocol; (5) the ratchet is static:
dynamic dispatch (`getattr`, writer callables passed as values) and scripts outside
`hedge_fund/` (for example `check_stock.py`) are not scanned; (6) the synthetic basis trusts
test-mode environment variables a same-account process could set — that grants nothing the
process could not already write directly, but it is not an isolation proof; (7) `aihf-web
--demo` seeding is a mutation, so outside the synthetic harness it exits before enrollment
with an A3 explanation (the 2026-11-01 wheel demo smoke predates A3 and no longer
reproduces); (8) owned-runner record writes now recheck root write authority immediately
before publication, but that helper does not itself verify a matching held owner lease and the
check does not exclude an uncooperative writer racing after it. Runner provider dispatch also
revalidates the held owner before each new transport, and an unpublishable terminal status
causes the child to fail rather than report success. T015/T021 stay open
until a production basis is implemented and evidenced.

Scoped archive/restore uses registry-before-object admission and a retained
`archive-prepared`/`restore-prepared` journal outside the active stores. After a
move, inventory changes compare-and-set the reviewed deployment entry, retain the
live enrolled entries of independent funds, and verify the full resulting inventory.
Explicit recovery reconciles only a matching journal/content transition; it never
rebases arbitrary drift or repeats unknown financial effects. Completed or abandoned
journals retain the exact reconciled operation IDs, so later legitimate ledger progress
does not invalidate a previously proven result.
These checks detect unsupported states, not hostile writes that ignore OS lanes.

The desk separates template, local-paper deployment and research-report archive scopes;
it offers no permanent deletion or implicit linked replacement. Review binds source
bytes, references, runner observations and enrollment heads to an expiring single-use
confirmation. Restores preserve the original identity, reject exact/canonical collisions
and leave the fund stopped. List/detail pages expose retained archives and explicit
recovery; an unsupported record shows a manual-review error without hiding independent
archives or granting permission.

Headless `aihf --root ROOT lifecycle list|inspect`, `lifecycle preview --action
archive --kind template|deployment|research --identity ID`, `lifecycle archive KIND ID
--expected-head HASH --request-id ID`, and `lifecycle restore|recover ARCHIVE_ID
--expected-head HASH --request-id ID` use the same reviewed protocol without TUI or
provider loading. Restore/recover previews use `--action restore|recover --archive-id ID`.
No network/model/dotenv option is accepted by these offline commands. A drifted root
stays web-read-only; bounded explicit headless journal recovery does not enable other
mutations. An explicit-root paper CLI command never falls back to an unenrolled writer.

An accepted archive interrupted before journal creation is not automatically retried.
Recovery requires the durable operation, absent exact archive destination, verified
enrollment and the original source bytes. Only a deployment may have advanced: its
fund-file digest must be unchanged, session count nondecreasing and prior session hash
retained; the operator reviews the full current source digest/head again before a
no-effect reconciliation. A restore interrupted before its write-ahead move may likewise
be explicitly reconciled against the intact archived bytes and archived journal state,
even if a new destination now collides; that never authorizes overwrite or a real restore.
Changed templates/reports, changed deployment snapshots/history and unknown destinations
remain manual-review states. Missing records alone never establish safe recovery.

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
