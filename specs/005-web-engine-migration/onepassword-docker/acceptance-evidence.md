# Acceptance evidence: 1Password Docker extension

**State**: NOT RUN. No image built, no container changed, no secret resolved.
Draft acceptance definitions are not evidence of runtime success.

Each later row must bind: revision + dirty-diff digest, build/image digest, loaded artifact,
timestamp/timezone, host/engine/CLI versions, synthetic root/container identity, scenario,
execution owner, check mode, command/test node, exact counts/duration, raw-artifact location
and redaction provenance. Review/build/unit/fake/runtime/user reports are separate evidence.
Any relevant source change invalidates affected rows. BLOCKED/INCONCLUSIVE is not PASS.

Do not save secret-bearing inspect/config/log/browser data as evidence. Scan synthetic values
inside a controlled harness and retain only sanitized counts/booleans and artifact identities.
Include plain/escaped/encoded representations for exposure checks; do not claim these exhaust
all covert channels or prove memory zeroization.

| Row | Requirements | Scenario and measurable acceptance | Mode | Status |
| --- | --- | --- | --- | --- |
| OP-A01 | OP-FR-001, OP-FR-014 | Keyless disabled/missing/locked states: 0 resolver/paid-provider calls; normal free/local work | Unit/fake + runtime fake | NOT RUN |
| OP-A02 | OP-FR-004 | Export final image; examine history/config and every decompressed/reassembled layer: 0 sentinel occurrences | Built artifact | NOT RUN |
| OP-A03 | OP-FR-004, OP-FR-010 | Rendered Compose, Docker image/container/exec config, argv/env, logs/errors, browser network/storage and exports: 0 sentinel occurrences | Artifact/runtime/browser | NOT RUN |
| OP-A04 | OP-FR-005, OP-FR-012 | Only intended fake consumer holds value; observer, TUI path, runner, unrelated child and vault authority inheritance denied | Unit/fake + runtime fake | NOT RUN |
| OP-A05 | OP-FR-002, OP-FR-003, OP-FR-012 | Wrong root/target/role/provider/endpoint, lost authority: 0 resolver calls before initial denial, 0 publication/dispatch/effects after recheck denial | Unit/fake + runtime fake | NOT RUN |
| OP-A06 | OP-FR-008, OP-FR-011 | CAS conflict, wrong boot, replay, malformed/partial/oversized frame: 0 partial publication; ambiguous ack explicit | Unit/fake + runtime fake | NOT RUN |
| OP-A07 | OP-FR-006, OP-FR-010, OP-FR-011 | Locked/absent/denied/timeout/malformed CLI; <=60s; 0 fallback/dispatch; sanitized errors, no raw stderr | Unit/fake + runtime fake | NOT RUN |
| OP-A08 | OP-FR-007, OP-FR-013 | Synthetic backend stop/recreate and interrupted work: 0 durable sentinel occurrences, stale handles denied, requires-auth | Windows runtime fake | NOT RUN |
| OP-A09 | OP-FR-008, OP-FR-009 | A-to-B refresh, failed refresh, concurrent revoke/admit/dispatch: fixed capture, correct CAS, next dispatch denied after revoke, no auto restart | Unit/fake + runtime fake | NOT RUN |
| OP-A10 | OP-FR-012, OP-FR-013 | Actual Windows LinuxKit/ext4 topology; final artifact authority/private IPC/W07 adjacent denials and supported negative platform states | Windows runtime fake | NOT RUN |

Linux/native auth behavior is not inferred from Windows. Existing Spec005 Linux regressions
remain applicable; no new host-Linux 1Password authentication support is claimed by this slice.
Windows containers, remote daemon contexts, missing peer-auth primitives and old images must
fail closed. An unavailable Windows test host leaves OP-A08/OP-A10 BLOCKED.
