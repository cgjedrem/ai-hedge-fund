# Research and risk model: 1Password Docker extension

Date: 2026-11-09. Planning evidence only. No secret resolution or runtime acceptance.

## Repository evidence and provenance

Read-only code-explorer report produced in this session against Git objects, not other
checkout files. Current baseline B is `3f7bea8ea2106670264b34520e0d2e6a6588fe20`.
Latest discovered local Spec005 continuation F is
`62c1dc46303eb98e73ba81375cb7848508bb0266` (`cgjedrem-fantastic-succotash` at discovery).
Moving branch names are not evidence pins.

Common ancestor: `6443490db64056742fbbe6a18abf92c903c10861`; B has 3 unique commits and
F has 96. B is not an ancestor of F. No merge, cherry-pick, branch switch, source copy or
other checkout access was performed. No freshness claim against a live remote is made.
The existing child was based on main rather than F; this is an explicit execution dependency,
not silently repaired by merging unapproved source history.

| Evidence at pinned F | Finding |
| --- | --- |
| `specs/005-web-engine-migration/tasks.md:805-809,820-821` | W05 provider/secret safety; W06 ext4; W07 Ollama networking; W08 synthetic artifact; W09 separately gated real local model smoke; retained W units, not new numbered spec tasks |
| `specs/005-web-engine-migration/spec.md:73-75` | Separate read-only observer and Windows operator deployment roles |
| `specs/005-web-engine-migration/tasks.md:258-279` | Existing credential store/capture/status task lineage |
| `hedge_fund/runtime/credentials.py:40-145,272-287` | Root-private versioned durable values and compare-and-swap semantics |
| `hedge_fund/runtime/configuration.py:392-443` | Minimal owned-child environment; no ambient API-key/token inheritance |
| `hedge_fund/web/services.py:4145-4159` | Captured explicit provider key, environment fallback disabled |
| `hedge_fund/data/client.py:57-84` | Explicit key; no ambient fallback |
| `hedge_fund/runtime/owned_runner_child.py:623-662` | Free/local scheduler; no credential handles |
| `hedge_fund/paths.py:32-37,92-118` | Selected-root dotenv opt-in; model/provider configuration allowlist, not API keys |
| `docker-compose.yml:103-107`, `docker-compose.linux.yml:39-42` | Checked-in older bind/Linux topology is not proof of implemented Windows R1 |
| `docs/governance/web-migration-contract.md:151-162` | No extra credential mount / Windows topology boundary |
| `specs/003-saxo-broker-adapter/quickstart.md:8-38` | Separate SIM OAuth provisioning/refresh prior art |
| `hedge_fund/secrets/provider.py:16-72` | Fakeable bounded `op` adapter; sanitized errors; Saxo write-back uses stdin |

At B, `hedge_fund/tui/keys.py:33-68` loads/saves dotenv and process environment; B's CLI
imports it. F's guarded consumers are different. A legacy environment recipe cannot be
claimed to implement F's capture rules. TUI source residue in F does not grant an alternative
credential path. Saxo resolution/rotation must not be repurposed as general app authentication.

## Installed product evidence

`Get-Command op` located the Windows `op.exe` WinGet link.
`op --version` returned **2.34.1**. Docker CLI executable is present.
No account/vault/item command, environment dump, credential file or `.env` read occurred.
Desktop app state, account plan, integration toggle, CLI authentication and Docker daemon
state remain unverified. No CLI installation or upgrade was performed.

## Official product documentation

Fetched publicly on 2026-11-09 without repository content or credentials in requests.
The developer site redirects to `www.1password.dev`. A guessed Docker shell-plugin URL
returned 404; it provides no basis for a Docker authentication claim.

| Official source | What it establishes / does not establish |
| --- | --- |
| [Desktop app integration](https://www.1password.dev/cli/app-integration) | Windows desktop app/subscription, Windows Hello and CLI integration are documented; does not establish they are enabled locally or forwarded into LinuxKit |
| [Service accounts with CLI](https://www.1password.dev/service-accounts/use-with-1password-cli) | CLI >=2.18.0; token-based auth and supported read/run commands; Connect environment settings take precedence; installed version meets documented minimum, not proof of an account |
| [CLI run](https://www.1password.dev/cli/reference/commands/run) | Supplies child environment and masks CLI output by default; no promise of absence from Docker metadata, process environment, logs outside that command or root snapshots |
| [CLI read](https://www.1password.dev/cli/reference/commands/read) | Field reference resolution and no-newline flag; stdout contains a value, so future launcher must capture privately, never display it |
| [Secure deployment](https://www.1password.dev/get-started/secure-deployment.md) | Documents CLI/SDK/service-account/Connect options for containers; not a verified Docker Desktop desktop-auth socket bridge |
| [Connect](https://www.1password.dev/connect) | Separate private REST service with local cached secrets and token/bootstrap operations; not needed by default |
| [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) | Explicit per-service file mounts; Linux containers; not automatic application `_FILE` support or encrypted ephemeral storage |

No documentation example that prints a secret, embeds it in command arguments or writes a
plaintext file is an approved command in this workflow.

## Decisions and alternatives

**Decision: Keep this under Spec005 as `onepassword-docker`, with OP-prefixed local IDs.**
Rationale: Existing provider/capture/deployment requirements encompass it. W07 is not a
generic secrets connection task. Alternative: a new numbered feature; rejected without
evidence of an independently authorized product scope.

**Decision: Attended host-side Windows CLI authentication first.**
Rationale: A documented local workflow exists without providing the container vault authority.
User unlock/approval must happen locally, not through chat. The host agent does not authenticate
on the user's behalf. Cancellation/timeout is a normal denied state.
Alternative: dedicated least-privilege service account for unattended resolution; valid official
product path but unapproved scope. A user would provision a read-only dedicated-vault token
locally; never paste it into chat, repo, Compose or command history. Desktop user auth is not
vault-scoped like a service account: the launcher allowlist limits this tool, not other commands
in the authorized host session. This residual risk must be accepted or the auth choice revised.

**Decision: Runtime-only private delivery and source-typed memory leases.**
Rationale: Meets the requested value-only-at-runtime boundary without root-store persistence.
Alternative: explicit host-to-root credential-store import; simpler existing capture integration,
but durable plaintext version retention conflicts with the proposed runtime-only goal.
Alternative: `op run` plus Compose environment; documented generally, but configured values
would violate no-inspect/environment acceptance and still miss F's captured-key semantics.
Alternative: Compose secret files; per-service isolation is useful but would add a credential
mount and retention semantics; not approved by current Spec005 topology or current consumers.
Alternative: install `op` plus a token inside application containers; expands authority and
requires token provisioning/rotation, not chosen.
Alternative: host desktop/daemon socket mount or WSL forwarding; no supported working path
verified, not chosen. No privileged container or Docker-socket mount workaround is allowed.
Alternative: Connect; adds server/cache/bootstrap secrets and operational burden, not chosen.

**Decision: Explicit refresh/revoke; no automatic restart or vault polling.**
Rationale: Preserve operation immutability and fund isolation. A new generation is used only
for new admissions; revoked work cannot cross a new dispatch boundary. Restart loses leases.
Python/process memory release is not a claim of cryptographic zeroization.

## Risk model

| Threat / failure | Required control | Acceptance |
| --- | --- | --- |
| Docker inspect/Compose metadata exposure | No secret configured env, build arg, label, argv or interpolation | OP-A02, OP-A03 |
| Browser/script/log disclosure | Value-free status, no browser import; sanitized error codes; no raw resolver stderr | OP-A03, OP-A07 |
| Wrong container/root or stale instance | Pin instance/image/root/role; recheck before publish and dispatch | OP-A05 |
| Vault overreach | One allowlisted reference; no list/export; only host resolver has auth | OP-A01, OP-A05 |
| Partial/replayed delivery | Bounded framing, unique delivery ID, generation CAS, atomic publication | OP-A06 |
| Leaks to children/observer/runner | Private IPC; consumer source binding; existing child allowlist; observer denial | OP-A04 |
| Cached/old credential resurrection | No plaintext persistence; boot nonce; generation fences; no ambient fallback | OP-A08, OP-A09 |
| Locked CLI, prompt hang or unavailable Docker | Bounded failure/cancellation, no partial success, no auto retry | OP-A07 |
| Paid or broker side effect | Empty initial allowlist; fake adapters; no provider dispatch authorized by delivery | OP-A01, OP-A05 |
| Unsupported LinuxKit filesystem/auth assumptions | Final synthetic ext4 artifact on actual Windows Docker Desktop; fail closed | OP-A10 |
| Host admin / Docker admin / compromised backend | Explicit trusted-local-operator boundary; cannot protect memory from administrator | Residual risk; not claimed solved |

## User authorization and remaining dependencies

The user authorized autonomous implementation and approved the stated runtime-only,
host-CLI-to-private-backend design. Attended desktop auth is the conservative implementation
assumption; no provider IDs were supplied, so the initial allowlist stays empty. No key values
are needed. Local reconciliation of the pinned Spec005 basis is authorized and must preserve
main's Yahoo news fix. No push or merge-to-main is authorized. Windows runtime feasibility
remains a future evidence gate.
