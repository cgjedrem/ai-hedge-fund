# Data model: Web migration

**Design only.** Existing domain schemas, ordered/default-off serialization and hash-chain
bytes remain unchanged. New state is root-private/versioned sidecar state under the fixed
root; it is not a replacement financial ledger. Authority is the [forward contract](../../docs/governance/web-migration-contract.md).

| Entity | Fields / relationships | Validation and immutability |
| --- | --- | --- |
| RootContext | canonical path, filesystem/device identity, host/boot/namespace identity, protocol/build, launch capabilities, handover evidence | Explicit launch argument before imports; local supported filesystem, protected/path guards; no env/browser redirection/elevation. |
| MandateTemplate | canonical name, revision/content digest, validated existing FundSpec | All supported fields/default omissions round-trip; YAML/YML/case collisions reject; edits/clone/rename expect revision. |
| Deployment | stable ID, root ID, immutable mandate snapshot/digest, universe, broker, ledger head, lifecycle, predecessor/archive links | No snapshot mutation; local-paper web mutations only; halt/replay/quiescence checks. |
| SIMAccountBinding | SIM environment/account identity, deployment/root owner, status, transfer provenance | Single active binding across deployments/roots; unverifiable exclusivity denies mutation; no real-broker option. |
| RuntimeSettings | monotonic version, normalized provider/model/endpoint/parameters, provenance per field | Launch/env non-secret settings > persisted > default; never authorizes network/paid or selects root. |
| CredentialVersion | private provider-host-bound material, monotonic version, presence/deletion metadata, ACL proof | Root-private atomic set/delete; no material in public schemas; deletion affects new captures only. |
| FrozenCapture | ID/digest, mandate/universe/config/credential versions, endpoints/provider/model/broker, code stamp | Private credential references/material remain stable for active work; public redacted view shows effective/source/restart-needed status. |
| RunnerAuthorization | deployment/root/capture digest, allowed free/local providers, initial due-set, expiry, session/call/resource counters | No cloud/paid loops; finite bounds, explicit action; first bound denies next work. |
| Ownership | root/deployment/protocol/build, PID namespace/boot, PID/incarnation, handshake nonce, process group/control channel, auth/capture IDs | PID alone insufficient; unknown/stale/legacy fails closed; nonce private, no cross-namespace signal. |
| AdmissionReservation | resource identity, owner/operation, runner lifetime or bounded lease, journal phase, recovery evidence | Kernel locks coordinate all processes; release on crash does not authorize recovery; control lane remains bounded/responsive. |
| ConfirmationPreview | action/subject, expected revision/head, ordered exact due-set/range, universe/capture, budget/consequences, operator session, expiry, digest | Immutable preview; digest canonical bytes, single-use consumption; admission revalidates head/due-set and fixed root. |
| Operation | durable request ID, payload digest, confirmation ID, capture/authorization, owner, stage/events/result, status/ambiguity | Persist before effects; same ID/payload returns status, changed payload conflicts; no browser-only evidence. |
| ReconciliationProvenance | operation/head identities, broker book/fill evidence, captured version, operator/time/decision, residual uncertainty | Required for ambiguous post-fill Resume in addition to replay; cannot fabricate ledger success. |
| ArchiveJournal | scope/identity/head/revision, references, source/retained destination, phases, replacement/restore link | Exact reversible move, no broad wipe; interruption recoverable; restore stopped/collision-checked. |
| Decision/Verdict | existing timestamp, source hash, pending/matching/stale/consumed/expired status | Canonical replacement/source-redo invalidation/consumed-execution replay unchanged; approval does not start. |
| ValuationEstimate | request/deployment/head, source/time, per-ticker marks/freshness, coverage, signed precise estimates | Observational only; partial/stale not complete current NAV; obsolete identity discarded. |
| ResearchResult/Report | existing canonical result identity/provenance, bounded pagination cursor, proposed/executed/risk/cost/NAV/scorecards | Preserve precision/inert text; minute label daily replay; malformed entries visible; no credentials. |
| AcceptanceEvidence | criterion/source, expected/observed, revision/build/time/environment, fixture/exclusions, status, superseded evidence link | Fresh actual observation only; required blocked/inconclusive prevents retirement; fixes reopen affected rows. |

## State transitions

- Runner: starting → running after handshake/readiness; running → stopping on owned request/
  authorization exhaustion/Halt → stopped only at verified quiescence. Failure → failed or
  unknown depending on evidence. Unknown is never adopted/signalled by PID liveness.
  Restart observes only verified live owners; never automatically starts stopped/failed owners.
- Bounded job: accepted (durable) → running → completed/failed; cancel-requested → cancelled
  at safe boundary. Restart leaves unfinished interrupted, preserving ambiguity/result links.
  Surviving workers are fenced/reconciled; interrupted cannot transition to running without a
  new reviewed request that independently proves it cannot repeat effects.
- Confirmation: issued → consumed atomically with request; issued → expired/stale. Consumed
  never issues a new mutation; original request ID retrieves its durable status.
- Deployment: active/stopped → archiving → archived; restore journal → active/stopped.
  Replacement archives prior then creates distinct linked deployment. Unknown/interrupted
  journal remains recovery-required; no implicit overwrite/run/catch-up.
- Halt: clear → operator halt/control error/replay error/ambiguous effects. Resume clears only
  after required validation; ambiguous effects additionally require reconciliation provenance.
  Resume is not execution or runner-start authorization.
- Credential: present version N → replaced/deleted version N+1 for new capture; captured N
  may remain active privately. Status distinguishes stored/effective/active, not secret value.

## Consistency rules

Registry precedes sorted deployment locks; session lease rechecks root, ownership, Halt,
head/due-set and capture authorization before provider construction. Runner reservation
denies manual work even between sessions; verdict/emergency marker uses separate short lane.
Duplicate request and token consumption share a durable transaction/journal: recovery never
interprets an incomplete marker as permission to repeat financial effects.
Read-only observer cannot create sidecars; paired immutable snapshots either verify or
return observation conflict. Journal/credential ACL failure blocks privileged capability.
