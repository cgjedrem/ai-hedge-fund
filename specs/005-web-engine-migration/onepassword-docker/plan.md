# Implementation Plan: 1Password runtime secrets for the Docker desk

**Branch**: `cgjedrem-ubiquitous-sniffle` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)
**State**: Runtime-only scaffolding implemented and fake-tested; operational configuration,
final artifact acceptance, independent review and platform proof remain pending.

## Summary

Propose an attended Windows host delivery tool: resolve exactly one allowlisted reference
using installed `op`; capture its output privately; carry the value through non-terminal
stdin to a target-checked container helper; publish an instance-bound memory lease to the
operator backend using private local IPC. No plaintext files, configured container environment,
vault authority inside the container, browser secret submission or scheduled paid work.

This bridge is application code to design and verify, not a feature supplied by 1Password
or Docker. Private IPC feasibility, Docker stream confidentiality under the stated local
administrator trust boundary and same-root admission must be demonstrated before acceptance.
The host launcher may use the host Docker CLI; the Docker daemon socket must not be mounted
inside a service.

The existing versioned credential store is prior art for admission and immutable captures,
not the destination for imported values. An additive external-source handle contract needs
user approval because existing durable captures cannot simply be populated with API-key
environment variables. Existing saved-credential mode remains unchanged; selecting this
source must never fall back to it.

## Technical Context

**Language/Version**: Existing Python ^3.11/Poetry; Windows PowerShell orchestration only
where necessary. No new dependency/version selected in this design.
**Primary Dependencies**: Installed host `op` 2.34.1; host Docker CLI; authoritative Spec005
runtime admission/configuration/capture/credentials and guarded backend dispatch.
**Storage**: Runtime value in target-backend memory only. Non-secret mapping/generation
metadata follows root-private admission. No new plaintext root store, dotenv or cache.
**Testing**: Co-located pytest with subprocess/resolver/provider fakes; existing frontend
tests if status changes; final synthetic Docker artifact acceptance; existing style tools.
**Target Platform**: Windows host with Docker Desktop Linux containers/LinuxKit and ext4
named-volume operator root. WSL/native Windows containers/remote Docker are not inferred.
**Project Type**: Local single-operator Python backend/CLI and existing React desk.
**Performance Goals**: One credential per delivery; 16 KiB maximum; overall 60-second
resolution/authentication deadline; no retry or polling.

## Implementation checkpoint — 2026-11-09

The local pinned Spec005 history is merged at `19b4913`; the main-only Yahoo news fix and
planning documents are preserved. Runtime implementation was committed locally as
`15fc2d9c62c73e5eb40aec3c0a3a46022a82287c`; its binary source diff SHA-256 is
`b9c005969127a269aeb70470cdcab4946f915cf166396817c2863450ec9d58b3`. Runtime work includes
an empty-by-default lease store,
source-typed capture metadata, bounded private IPC, a fakeable host Docker target checker,
a public `aihf-op-deliver` command and a strict local JSON mapping loader. Operator provider
allowlisting accepts provider IDs only through `HEDGE_FUND_RUNTIME_PROVIDERS`; unset remains
empty. Durable credential storage remains unchanged. The path is not a supported live
workflow because the checked-in Compose operator still uses a bind mount rejected by the
launcher; no ext4 named-volume acceptance has occurred.

The first user-approved `op whoami` check ran at 2026-11-09 11:27:18 +01:00 and returned
unauthenticated in 0.093 seconds with CLI 2.34.1; sanitized reason:
`desktop-integration-unavailable`. Connect/service-account auth variables were absent.
No prompt activity was recorded. No vault/item or provider value was read.

After the user reported desktop CLI integration was on, one more bounded `op whoami` ran
at 2026-11-09 12:19:34 +01:00. It returned unauthenticated in 1.070 seconds with sanitized
reason `desktop-account-not-signed-in`. The executable resolved under user-local AppData;
Authenticode was valid, while file-version metadata was unavailable (earlier CLI report:
2.34.1). The parent shell was interactive, but the CLI child was hidden with stdout/stderr
redirected. Nine 1Password processes shared Windows session 5. Connect/service-account/
session-token presence checks were false. Prompt activity is unverified; no app settings,
raw identity data, stderr or vault content was read.

Read-only Path of Practice prior art documents `op whoami` with biometric unlock in an
attached terminal (`docs/secrets.md:33-38`) and host `op run` environment injection
(`scripts/dev-backend.ps1:62-85`, `docker-compose.yml:1-7,35-41`). Hidden invocation is a
plausible prompt-related difference, not confirmed cause. Its Compose environment flow
conflicts with this plan's no-secret-environment boundary and is not reused. Smallest local
diagnostic: run `op whoami` directly in attached PowerShell/Windows Terminal; no further
check was run by this implementation.

Final integrated fake selection: 255 passed, 1 skipped in 178.94 seconds, wall time
181.461 seconds, at 2026-11-09T11:27:31.7859045Z; earlier config/allowlist/status selection:
83 passed, 1 skipped in 6.81 seconds. Docker
artifact/runtime acceptance is not run; current Compose uses a bind mount and the host
launcher fails closed on that topology. Provider mappings stay empty by default. See
`acceptance-evidence.md` for exact command/evidence, unresolved broad regression failures
and blocked rows.
**Constraints**: No secret values in Docker config/environment/argv/logs/images/browser;
no real providers, vault reads, funds, credential provisioning or container changes now.
**Scale/Scope**: One selected target instance/root and provider per delivery. Provider
allowlist initially empty; bounded explicitly authorized backend work only.
**Unverified capabilities**: Desktop app installation/unlock/integration/account entitlement,
Docker daemon readiness/context/engine version, Windows topology, private IPC and loaded
artifact identity. CLI version alone proves none of these.

## Constitution Check

Read current constitution before discovery. The reference continuation has a different
constitution; its free/local scheduled exception is not imported or used to widen authority.

| Principle/gate | Before research | After conditional design |
| --- | --- | --- |
| I Ledger integrity | No ledger work | Sidecars/leases only; no serialization/history changes |
| II Paper/provider safety | Keyless default; no paid calls | Preserved; no credential implies spending authorization |
| III Tests co-located | Docs-only now | Future code needs targeted then required suite/platform evidence |
| IV Determinism | Immutable capture required | Generation-bound memory leases; no latest-under-old-handle lookup |
| V Surface consistency | Existing surfaces traced by specialist | Status only; no new TUI/runner credential path |
| VI Style | ASCII/no BOM docs | Existing black 420/isort/flake8 for future code |
| Existing Spec005 contract | Separate divergent history | Runtime-only external-source compatibility approved; preserve durable mode |
| Plan review / user approval | User authorized autonomous implementation | Provider allowlist intentionally empty; no IDs inferred |
| Platform/runtime evidence | Not executed | BLOCKED: synthetic Windows artifact evidence required |

No constitution waiver or gate bypass is claimed. Phase 0 research and Phase 1 design are
approved for implementation; source-history reconciliation remains a required first gate.
No target-branch plan-review-gate configuration exists in this checkout; no push is authorized.

## Project Structure

### Documentation

`specs\005-web-engine-migration\onepassword-docker\` contains spec, plan, research,
data-model, contracts/runtime-delivery, quickstart, tasks, analysis, requirements checklist
and acceptance evidence template. Parent Spec005 artifacts are not rewritten.

### Proposed source seams

| Location in pinned Spec005 continuation | Purpose |
| --- | --- |
| `hedge_fund\secrets\provider.py` | Reuse fakeable resolver/sanitized failure patterns; preserve Saxo semantics |
| `hedge_fund\runtime\credentials.py`, `capture.py`, `configuration.py` | Add source-typed runtime lease handles, admission, capture and child filtering |
| `hedge_fund\run.py` | Explicit-root, non-echoing host/target command integration |
| `hedge_fund\web\services.py`, `schemas.py` | Lease consumption and value-free status; no secret delivery through browser |
| `hedge_fund\runtime\owned_runner_child.py` | Regression coverage only: free/local policy unchanged |
| `Dockerfile.web`, `docker-compose*.yml` | Narrow operator helper/IPC packaging and secret-free deployment |
| Co-located tests and existing frontend tests | Negative boundaries, frozen generation and exposure tests |

Exact new filenames are left to the implementation specialist after baseline reconciliation;
do not implement against absent runtime modules in the current main-derived tree.

## Phase 0: Research decisions

See [research.md](research.md) for official sources, alternatives and threat model.
Recommended default is attended host desktop auth, no Connect/service account deployment,
no container `op`, no plaintext store import, no automatic refresh.
Unattended authentication is a separate scope decision, not an unresolved implicit fallback.

## Phase 1: Conditional design

1. Validate explicit local Docker context, target build/instance/root/operator role and
   existing write/admission eligibility before invoking a resolver. Container identity must
   be pinned by immutable ID and expected image/build identity, not just a reusable name.
2. Resolve one strict reference privately, with sanitized errors and bounded memory/timeout.
   Do not use shell command substitution, terminal pipelines or secret-bearing argv.
3. Use host Docker exec attached stdin without TTY and without secret environment settings.
   Helper performs a second target/admission check and sends one framed request via private
   local IPC to the backend owning the lease. Public Docker exec arguments contain no value.
4. Require backend generation/version compare-and-swap and single-use delivery identity.
   Publish atomically only after complete validation; stream loss never produces partial success.
5. Backend captures a source-typed lease identity into authorized bounded work. Values never
   enter durable job/config snapshots or child environments. Cross-process consumers without
   the owning lease are rejected, not silently granted new access.
6. Expose status only. Refresh/revoke serialize with admission and dispatch fencing.
   Process/container restart invalidates all external leases; explicit redelivery is required.

The private IPC transport is a proposed Unix-domain endpoint inside the operator's private
runtime namespace, not a mounted host/1Password/Docker socket. Its path, peer credentials,
permissions, framing and ownership must be verified in local task T008. If peer authentication or
authority cannot be proved, stop and revise this design rather than broaden privileges.

## Compatibility and task gate

Map to Spec005 FR-021-FR-024, FR-058; W05/W06/W08 with W07 adjacency; historical
T045/T050/T051/T053/T057/T059/T060/T085/T086/T134. Do not mark those tasks complete.
There are **12 proposed implementation/acceptance tasks**, all unchecked, in [tasks.md](tasks.md).
They may be refined after user choices; no task is authorized by this count.

Runtime-only external-source mode and attended host auth are approved. No provider IDs were
provided, so the allowlist starts empty. No actual provider access is needed to implement or
accept the synthetic slice. A real-key smoke would require separate explicit authorization.

## Complexity Tracking

No constitution violation is proposed. Private IPC and source-typed leases are the minimum
additional mechanisms suggested to meet the no-persistence/no-Docker-environment boundary.
If the user instead accepts durable root-store import, revise spec, retention acceptance and
security disclosure before choosing that smaller but materially different design.
