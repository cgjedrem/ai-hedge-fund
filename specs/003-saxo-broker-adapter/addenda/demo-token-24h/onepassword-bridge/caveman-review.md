# Caveman Review

**Scope**: Documentation only — `spec.md`, `plan.md`, `tasks.md`,
`contracts/inspection.md`, `research.md`, `data-model.md` and `quickstart.md`.
No source, test, Compose or running-container changes were made.

| Finding | Resolution |
|---|---|
| `tasks.md:L19` (before this update): T002 only documented the `network_mode: none`/browser blocker and deferred topology to a later review. It had no selected design or implementation/acceptance criteria, so SB-A08 could not be completed. | T002 now records a concrete `saxo-inspection` profile design and required checks. `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/inspection.md` and `quickstart.md` specify a new isolated service, dedicated already-admitted no-fund-state root/volume, `127.0.0.1:8877:8876`, capability-specific pinned host delivery, exact application-layer SIM GET restrictions, and explicit limits of Docker bridge isolation. T024-T026 add offline negative topology tests, profile/validator implementation and operator-local smoke/provenance acceptance. |

**Design boundary**: Preserve the existing `op-runtime` network-none profile and
its validator. Do not reuse the general `web-operator` bridge or Linux host-network
override, mutate a running container, share a fund root, or claim that Docker
network membership filters domains. Existing root-owner, role, loopback
session/origin/CSRF checks and SIM mutation protections remain required. The
planned desk uses the existing explicit in-app discovery/inspection actions and
separate settings card; no additional route or credential surface is approved.

**Disposition**: Finding addressed in documentation. T024-T026 are pending; the
profile does not exist and SB-A08 remains BLOCKED. No Docker/Saxo/1Password smoke,
tests, or runtime action was performed. No real vault reference, root identity or
expiry was inferred.
