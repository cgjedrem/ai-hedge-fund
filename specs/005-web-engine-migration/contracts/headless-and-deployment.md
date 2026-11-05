# Headless and deployment contract

**Proposed CLI changes; not executable acceptance evidence today.** Existing command meanings
remain canonical except the expressly documented safety incompatibilities. No scripts,
compose, entrypoints or provider defaults are changed by the planning PR.

**Release 1 scope (user-directed, 2026-11-04 and 2026-11-05):** Release 1 keeps the TUI
entrypoint as a fallback and retains all headless commands. The selected Docker path is one
writable, single-user paper desk, published only on host loopback, reusing canonical root
trust and cooperating-writer admission. The final image was exercised on disposable
synthetic ext4 volumes; observed results and evidence limits are in
`implementation-evidence.md`. The exact runtime timestamp and full invocation were not
retained, so formal runtime acceptance remains INCONCLUSIVE. The separate observer-snapshot
architecture, TUI/ttyd retirement and dual-platform packaged distributions remain deferred.
The real funds' move from the legacy home root uses the offline handover below and is
performed only by the operator.

## Launch and command compatibility

The target console accepts explicit global `--root PATH` before every command. A no-command
interactive invocation opens packaged React desk, never Textual. A missing bundle fails
actionably. `aihf-web --root PATH` is retained; writable mode/network capability require
explicit launch arguments. No default-root/CWD/environment fallback after migration.

Retain backtest and paper create/tick/run/stop/status/list/scorecard/halt/resume/approve/reject/
redo, canonical JSON/stdout/output-file reports, dates/cadence and SIM headless semantics.
Every writing entry uses the same root/deployment admission, versioned protocol, expected
identity/head and idempotent request ID as web; an old nonparticipating command is not exempt.
Noninteractive headless work must supply reviewed expected head/due-set/capture digest and
finite bounds, not "yes to anything". Add preview mode that outputs safe canonical review
identity without execution; acceptance consumes exact reviewed preview. Never ask a script
to confirm an unspecified future head.

Proposed explicit per-invocation policy flags:

| Flag | Meaning |
| --- | --- |
| `--root PATH` | Required fixed root; passed identically to all children before sensitive imports. |
| `--request-id ID`, `--preview-id ID`, `--preview-digest DIGEST` | Durable duplicate-safe submission of the exact reviewed work; token delivered privately, not retained global authorization. |
| `--allow-network` | Enable reviewed allowed providers only for this operation; does not authorize paid usage. |
| `--authorize-paid`, `--max-cost AMOUNT`, `--max-calls COUNT` | Explicit one-shot/backtest provider/cost authorization; never permitted for scheduled paid/cloud work, never env-implied. |
| `--expires-at TIME`, `--max-sessions COUNT`, `--max-calls COUNT` | Finite free/local scheduled authorization bound to reviewed deployment/capture/provider set. |
| `--allow-writes` | Explicit web capability; Docker inspection omits it, and operator mode still requires enrolled root trust. No container-bind flag exists. |

Exact argparse spelling remains implementation work; normative semantics above must be
preserved and published commands must be tested, not copied unverified from this proposal.
No paid invocation example is supplied for this planning execution.

## Deliberate migration incompatibilities

- Provider default changes paid `fd` → credential-free yfinance; install/package the free
  dependency for every entry advertising this default. A key/provider env override is not
  paid/network authorization. All cloud-labelled/keyless hosted inference is paid/cloud class.
- Explicit root is mandatory; prior home/CWD/dotenv/global path behavior is rejected.
- Shared admission/ownership protocol requires controlled offline handover. Old CLI/cron/
  service ownership is unknown until excluded; no automatic upgrade/start/restart/adoption.
- Web execution/lifecycle is local-paper only. SIM readiness is inspectable; retain documented
  non-TUI headless SIM reference/OAuth provisioning and operations under exclusive account
  binding. No ordinary web SIM parity claimed, no live brokerage configuration offered.
  This is target behavior, not shipped provisioning acceptance; the implemented SIM boundary
  below deliberately blocks production provisioning and execution.
- TUI/default terminal entry and Docker ttyd/TUI services retire only after assertion/packaged
  platform acceptance. Noninteractive Rich console reports are not a TUI dependency.
- Archive replaces broad deletion; replacement is new linked identity; restored work is
  stopped and catch-up must be separately reviewed/bounded.
- Headless network/provider work now needs explicit operation policy; compatibility does
  not preserve previously unsafe implicit paid calls or unfenced writers.

## Trusted single-writer handover

Existing roots remain read-only by default, including fresh enrollment, `migrate-existing`
and `relocate-from` results. The offline handover path is:

1. `aihf --root ROOT handover inspect` verifies root/build/protocol and inventory, then
   prints the current inventory digest and an exact root-specific operator acknowledgement.
2. The operator confirms all other programs that can reach the root are stopped or excluded,
   including old CLI versions, cron, services, writable containers and scripts.
3. `aihf --root ROOT handover trust-single-writer --inventory-digest DIGEST
   --operator-acknowledgement TEXT` accepts only the exact current acknowledgement and
   inventory. It rechecks root identity, enrollment/build, legacy reachability and inventory
   under offline exclusive admission before recording trust.
4. `aihf --root ROOT handover revoke-single-writer` removes the trust record; absent,
   invalid, mismatched or revoked trust returns the root to read-only mode.

No environment default, enrollment, migration attestation, relocation, PID/TTL, marker,
cooperative lock or web endpoint substitutes for this acknowledgement. The operator's
exclusion is a declared trust assumption, not OS-enforced protection; protocol locks fence
only cooperating participants. An unaware or malicious same-account writer remains
unfenced. Known or unverified active legacy participants, unsafe roots and inventory/build
mismatches still deny trust. This path does not touch real deployments unless an operator
deliberately invokes it for the selected root.

## Supported topology

One Windows or Linux host owns local supported root and all writable processes. Host local
model endpoint is literal loopback. Host desk binds loopback. CLI/runner share the same
OS/namespace/device/root identity and admission. Process lifetime is detached from server/
browser; verified graceful stop only. No system/compose auto-restart for upgraded runners.

Selected Release 1 topology is one writable, single-user paper desk in Docker. Mount only the
selected root at `/data`; that mount is writable for canonical ledger, operation and private
runtime state. Keep the image filesystem read-only, drop capabilities, and publish only to
host loopback. The Compose `web` profile is read-only inspection; `web-operator` explicitly
enables writes and network capability. Supported browser access uses the Linux host-network
overlay: app binds literal `127.0.0.1`, and the overlay clears bridge ports/networks. Do not
accept Docker gateway peers or add a `host.docker.internal` exception. Windows bridge/browser
and Ollama access remain unsupported. Do not mount the host home or unrelated credential paths. Credentials already
stored inside the selected root remain private to the service and must never appear in API
responses, logs or browser state. Root enrollment, offline trust, immutable capabilities and
the existing RootOwnerLease, operation-service lease and per-fund admission remain mandatory.
The operator excludes every other writer while trust is enabled. A TUI fallback does not
permit a second concurrent writer. No cross-namespace runner stop/adoption, automatic
enrollment or identity rebind is supported. Image labels and the package code-version stamp
bind a full source revision and package-source digest; runtime environment values cannot
override them.

The Windows Docker Desktop bind filesystem is not currently supported: a synthetic host
directory mounted at `/data` reports `9p`, and `RootContext.open` rejects it because only
local NTFS/ext4 are admitted. A Docker Desktop ext4 named volume is permitted for disposable
synthetic runtime validation only; it does not support NTFS-to-ext4 relocation. On the final
image, same-container restart retained PID/mount namespace identity and trusted write
capability; a replacement container changed namespace identity and remained read-only.
These observations do not approve rebind, cross-filesystem copy or upgrade. Host-network/
browser/Ollama runtime remains untested. FR-044 protected names remain globally denied, so
the R1 `watchtower` targets are blocked pending a user decision. Never remove the protected-
name guards or add fixture/agent-specific bypasses.

Keep the TUI and `tui-web` fallback services. A sequential TUI render was observed on a
separate synthetic volume after a graceful web-child stop; first TUI launch creates the
example mandate. This does not establish same-root cross-namespace rebind or writable
fallback on the trusted Docker root. Disable competing runner/TUI writers during any operator
session; fallback use begins only after the web writer stops. Compose examples use
synthetic names and isolated roots/ports. Do not operate existing compose services or actual
funds to validate migration. Container/Linux runtime acceptance requires final-image evidence.

## Filesystem/ownership recovery contract

Local tested NTFS/ext4 only; network/mapped/cloud-synced/unknown root unsupported.
No namespace/PID/TTL shortcut for a stale runner. Prove owned incarnation dead/quiescent,
exclude old writers, verify root/head/replay/journals and reconciliation when needed, then
explicitly record/release reservation. If platform primitives unavailable, capability denied/
acceptance blocked. PID liveness cannot authorize a signal.

SIM account/environment binding must exclude active duplicates even across roots. Operator
account exclusivity/handover evidence is required; root-local bookkeeping alone is insufficient.
Fakes validate policy without contacting Saxo or creating/rotating real credentials.

### Implemented SIM boundary (T096 fake policy; T099 partial)

The current build cannot establish complete cross-root account inventory or
exclusively mediated Saxo account control. A protocol-native root, private ACL,
cooperative lock, operator attestation, secret reference, or stopped runner is
not that proof. Manually configured and out-of-band account clients cannot be
excluded by the shipped root protocol.

`SIMAccountRegistry` in `brokers/account_binding.py` implements a permanently
unsupported, fail-closed production ownership seam. Inspection reports `ownership-unknown`, reason
`exclusive-account-control-unverifiable`, unverifiable cross-root inventory,
and no binding/provisioning/execution authority. Bind, release and transfer
always deny; they do not read or persist account identities, digests, keys,
registry files, or purported released/transfer provenance. No identity key is
provisioned by this production seam and no global account/network lookup is attempted.

The separate `AccountRegistry` is a fake-only policy simulation preserved from
PR8 commit `294f9db`: a private canonical HMAC store, root/deployment admission,
duplicate denial, owned-quiescent release and exact transfer provenance. Its
initialization, reads and mutations require the canonical checkout-owned synthetic
test namespace. An injected custody/quiescence callback cannot enable ordinary
production registry access. This test-mode confinement is not a global custody
proof; synthetic receipts always deny execution and cannot enable the production
ownership seam. Receipts/inspection explicitly report `policy_only: true` and
`global_custody: ownership-unknown`, even after a positive fake-policy bind.
No real account identity or provider configuration is used.
The simulation's namespace validation does not itself install or attest a socket
network guard; callbacks are trusted fake-policy inputs, not provider/account-control
proof. The test harness separately installs non-loopback denial. Historical adapter
fixture helpers additionally require its installed guard marker.

Headless SIM deployment, factory construction and OAuth entrypoints now deny
before deployment/ledger creation, environment/secret resolution, browser or
prompt access, refresh-lock creation, token rotation, or broker requests.
This intentionally rejects previously successful SIM setup even with valid
references. Local-paper behavior and readable historical SIM records remain.
CLI SIM create, tick/replay and approve-now deny with the ownership reason
before acquiring writer leases/lanes or constructing a ledger/provider authority.
The library tick path denies after confined deployment inspection,
under its existing admission, but before any ledger or provider access; it must
not journal approval consumption or Halt as a broker-initialization failure.
Low-level adapter algorithms are still exercised with network-denied test
doubles; that is neither provisioning nor global ownership acceptance.
Plain headless approve/reject still record admitted local verdicts on historical SIM
records; those verdicts grant no account authority and subsequent execution remains
denied. TUI verdict writes are denied by `paper_write_denial()` in every root state.
Complete ownership-gated SIM control parity remains
T070/T099 work. This slice changes no TUI code.

Any future supported binding needs an independently enforced account-control
authority, complete canonical cross-root inventory, private atomic registry
storage, and protocol-native authority for every relevant root. Release and
transfer additionally need verified prior ownership, stopped/quiescent
writers, exact replay-safe provenance, and root-registry then sorted deployment
admission. Until all of that is defensible, successful release/transfer and
headless SIM provisioning remain blocked in production. The incoming T096
fake-policy checkbox is retained; T099 and full account-control acceptance remain unchecked.
