# Validation runbook: proposed 1Password Docker connection

**Synthetic validation guide.** No real credential read, provider call or existing-fund
change is authorized. The initial provider allowlist is empty.

## Prerequisites for later synthetic validation

1. Implementation authorization and runtime-only source compatibility recorded.
2. Supported Python/Poetry tools and final built image identity recorded by the execution owner.
3. Separate synthetic Docker project, unused loopback port and ext4 named volume; isolated
   HOME/root and fake provider/resolver adapters. No protected/home project root mounts.
4. Actual Windows Docker Desktop Linux-container runtime evidence, including engine/context,
   OS versions, container/root identities and image digest. CLI presence alone is insufficient.
5. Operator and observer roles kept separate; no automatic runner start or host fund restart.

## Safe checks available now

From this worktree, the planning pointer selects the nested extension:

```powershell
& .\.specify\scripts\powershell\check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
git --no-pager diff --check
git --no-pager status --short
```

These are documentation checks, not secret-integration acceptance.

## Synthetic scenarios after implementation

| Step | Action | Required observation |
| --- | --- | --- |
| 1 | Run keyless fake operation with integration disabled and fake CLI missing/locked | Zero resolver/paid-provider calls; normal free/local behavior |
| 2 | Generate a unique harmless sentinel in the isolated test controller; deliver through fake resolver to one allowed backend | Selected fake consumer confirms equality internally; result records only boolean/count, never the value |
| 3 | Inspect exported image history and every layer, rendered Compose, container/image/exec config, process argv/environment, logs, browser traffic/storage and durable files | Zero sentinel occurrences; log only surface name/count; decode/reassemble archive/config formats rather than grep compressed bytes |
| 4 | Attempt observer, wrong-root, stale-boot, unauthorized provider/endpoint and unenrolled target delivery | Denial before resolution/effects; no authority gained |
| 5 | Run free/local runner and unrelated child with decoy keys/tokens in parent | Neither credential nor vault authority inherited; dotenv decoys ignored |
| 6 | Exercise missing CLI, denial, timeout, empty/large/control-character output, malformed/partial/replayed frames and stream loss | Sanitized errors, <=60-second bound, no fallback; ambiguous publication explicitly reported |
| 7 | Capture A, refresh B, revoke, attempt new and previously admitted dispatch | Immutable generation capture; revocation blocks new/next dispatch; no silent automatic restart |
| 8 | Restart/recreate only synthetic backend | Requires-auth; no value in ext4 data, writable layer or recovered snapshots; stale captures denied |
| 9 | Re-run observer, root authority and W07 endpoint/network denial regressions | Existing boundaries unchanged; credential delivery never validates/calls a provider |

Attach outcomes to [acceptance-evidence.md](acceptance-evidence.md). Runtime suites use
fake `op` and fake providers; never real LLM/data/Saxo calls. Existing tests from the
reconciled Spec005 implementation should be selected with the new co-located tests in a
single pytest run, then escalated according to repository acceptance obligations. Exact new
test node IDs must be added by OP001, not invented as executable commands in this draft.

## Local authentication, only after separate authorization

The installed CLI is 2.34.1. The user must confirm subscription/desktop app, Windows Hello
and CLI integration locally if approving attended mode. No account/vault content needs
to be pasted into chat. A service-account token is not required for the recommended slice.
If an unattended mode is requested later, provision its token privately and revise this plan.

A real credential smoke is not necessary for synthetic acceptance and is not authorized by
this runbook. Provider IDs remain unset; do not configure a real mapping, authenticate Saxo,
import existing `.env`, restart the current TUI or connect this flow to an existing fund.
