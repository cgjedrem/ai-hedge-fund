# Headless and deployment contract

**Proposed CLI changes; not executable acceptance evidence today.** Existing command meanings
remain canonical except the expressly documented safety incompatibilities. No scripts,
compose, entrypoints or provider defaults are changed by the planning PR.

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
| `--read-only`, `--container-bind` | Observer-only role and tightly scoped internal-bind carveout; cannot be promoted to writable. |

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
- TUI/default terminal entry and Docker ttyd/TUI services retire only after assertion/packaged
  platform acceptance. Noninteractive Rich console reports are not a TUI dependency.
- Archive replaces broad deletion; replacement is new linked identity; restored work is
  stopped and catch-up must be separately reviewed/bounded.
- Headless network/provider work now needs explicit operation policy; compatibility does
  not preserve previously unsafe implicit paid calls or unfenced writers.

## Supported topology

One Windows or Linux host owns local supported root and all writable processes. Host local
model endpoint is literal loopback. Host desk binds loopback. CLI/runner share the same
OS/namespace/device/root identity and admission. Process lifetime is detached from server/
browser; verified graceful stop only. No system/compose auto-restart for upgraded runners.

Optional container serves packaged read-only observer. Mount only a sanitized observation
subtree/snapshots read-only, never root credentials/config secrets; if a safe projection cannot
be exposed, deny observer startup. No providers, mutations or proxy. Internal interface bind
is allowed only with explicit observer mode and exclusively loopback-published host port.
No host network mode or remote/public publication. Cross-namespace mutation unsupported.
Separate writable container deployments are not supported by this migration topology.

Implementation docs/compose must remove hard-coded real/protected deployment names, ttyd
downloads and `tui`/`tui-web` services, writable runner examples and `restart: unless-stopped`.
Use only synthetic names such as `demo-alpha` and isolated project-owned roots/ports.
Do not operate existing compose services to validate the migration: current examples remain
nonconforming until rewritten. Container/Linux runtime is accepted only with actual evidence.

## Filesystem/ownership recovery contract

Local tested NTFS/ext4 only; network/mapped/cloud-synced/unknown root unsupported.
No namespace/PID/TTL shortcut for a stale runner. Prove owned incarnation dead/quiescent,
exclude old writers, verify root/head/replay/journals and reconciliation when needed, then
explicitly record/release reservation. If platform primitives unavailable, capability denied/
acceptance blocked. PID liveness cannot authorize a signal.

SIM account/environment binding must exclude active duplicates even across roots. Operator
account exclusivity/handover evidence is required; root-local bookkeeping alone is insufficient.
Fakes validate policy without contacting Saxo or creating/rotating real credentials.
