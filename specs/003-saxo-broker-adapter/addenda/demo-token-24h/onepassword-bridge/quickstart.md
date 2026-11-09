# Quickstart: Attended in-app Saxo SIM inspection

**Status**: Source implementation and final parent code review PASS, including
the publication race fix. Focused offline fake coverage, all 16 changed/new Python
files' style checks, full frontend tests and build pass. Full Python suite NOT RUN;
Linux IPC verification is blocked by the helper's unsupported tmpfs root under
normal admission, not by an unreviewed code change. Actual host SB-A08/T026
acceptance remains blocked on operator-local inputs and deployment smoke. This runbook
is not credentialed or Docker-host acceptance evidence. No real reference or
account is known, inferred, listed or resolved here.

## 1. Preconditions and stop conditions

- Consult [tasks.md](tasks.md): focused tests, static checks and final parent code
  review have passed; full-suite and Linux IPC acceptance remain incomplete.
  The dedicated deployment profile and host preflight are implemented, but no
  host/browser/SIM acceptance has been run.
- Use only the dedicated `saxo-inspection` service and a separate, already
  admitted inspection root/volume containing no fund state, plus exact reviewed
  image/source pins. Do not use a shared fund root or initialize/enroll/trust a
  root for this inspection.
- Provide the exact local field reference and conservative UTC expiry yourself.
  The value remains in 1Password. No secrets in command history, files, browser,
  clipboard/chat, environment or build configuration.
- Authenticate attended host `op` in the operator's terminal through the existing
  desktop integration. No service-account/Connect/session-token authority enters
  the container. Stop on ambiguous authentication; do not dump environment variables.
- Enable the separate non-secret backend capability
  `HEDGE_FUND_RUNTIME_CAPABILITIES=saxo-demo-token` in an approved deployment.
  `HEDGE_FUND_RUNTIME_PROVIDERS` remains application-only, empty unless separately
  selected. Do not set Saxo token/reference environment variables inside Docker.
- Stop if observer-only, root owner unavailable, stale target, wrong destination,
  expired mapping, unsupported topology or unavailable browser/network capability.
  Do not "repair" any of these by bypassing admission or opening a shared fund root.

### Current implementation and deployment boundary

The current `docker-compose.op-runtime.yml` is `network_mode: none` with no
published browser port. Preserve it and its validator unchanged. The general
`web-operator` bridge profile and Linux host-network override are not approved
targets for this feature.

The implemented, opt-in topology is a separate
`docker-compose.saxo-inspection.yml` service `saxo-inspection-operator` under
profile `saxo-inspection`: private dedicated bridge, one separate pre-existing
admitted inspection root/volume with no fund state, and host-only publishing
`127.0.0.1:8877:8876`. No fund root, `webdesk` network, host networking, extra
mount/network/port or running-container mutation is permitted. Docker bridge
networking does not filter internet destinations; only the app's fixed,
TLS-verified SIM origin, exact GET-path allowlist, redirect/proxy denial and
per-action consent are asserted as SIM restrictions. Do not claim domain-level
firewall enforcement.

The profile and fake-only host preflight/negative tests exist, and final
code/static/focused review passed. However, full-suite and Linux IPC verification,
exact operator-local mapping values, deployment provenance and claimed-platform
loopback/browser smoke are not complete. **Do
not perform delivery or inspection; report SB-A08 BLOCKED** until those gates
are independently satisfied. The intended browser URL is
`http://127.0.0.1:8877`, but it is not approved for use yet. Do not use
`docker network connect`, host-network overrides, port changes on an existing
container, root trust commands, proxy tricks or `docker exec` to read a vault.
The host-delivery command must remain the attended `aihf-op-deliver` private-stdin
flow and preflight the exact dedicated service before resolving any field. Verify
Docker Desktop and Linux Engine independently; Linux host networking is not a
proxy for Windows support.

## 2. Prepare non-secret mapping locally

Only after the feature and deployment gates pass, create a local, untracked
`operator-local\saxo-inspection-mapping.json`. Use the following schema, replacing
every bracketed placeholder using your approved deployment record and known field
reference. Never add a `value` or `token` property. No token file is created.
The example is intentionally not accepted until all placeholders are replaced.
Keep operator-local metadata out of commits, public logs and shared evidence.

```json
{
  "schema": 1,
  "mappings": [
    {
      "provider_id": "saxo-demo-token",
      "reference": "op://<operator-supplied-vault>/<operator-supplied-item>/<operator-supplied-field>",
      "destination": "saxo-sim-readonly",
      "topology_profile": "saxo-inspection",
      "root_id": "<64-hex-approved-root-identity>",
      "container_id": "<64-hex-approved-container-id>",
      "image_id": "sha256:<64-hex-approved-image-id>",
      "revision": "<approved-source-git-revision>",
      "source_sha256": "<64-hex-approved-source-hash>",
      "volume_name": "<approved-existing-named-volume>",
      "expires_at": "<future-UTC-RFC3339-expiry>"
    }
  ]
}
```

`topology_profile` is a strict mapping field; the implementation rejects unknown
profiles and preserves legacy application mappings. Expiry must be
future, no more than 24 hours from delivery and no later than the
operator-known credential expiry. An issuer may reject the bearer sooner.
Do not inspect/decode the bearer to guess a lifetime. Do not read the user's
default mapping file or `.env` to construct this example.

## 3. Deliver from the attended host terminal

From the checked-out project with its installed Poetry environment:

```powershell
poetry run aihf-op-deliver --config .\operator-local\saxo-inspection-mapping.json --provider saxo-demo-token
```

If Poetry is managed through the already installed uv tool, the equivalent is:

```powershell
uv tool run --from poetry poetry run aihf-op-deliver --config .\operator-local\saxo-inspection-mapping.json --provider saxo-demo-token
```

Run one form only. The command performs a real field read only after target/
purpose/authority checks and sends the value over private stdin, not HTTP.
Expected success: `delivery=available provider=saxo-demo-token generation=<n>`.
This means delivered, not connected. Safe denial gives a fixed reason code.
Outcome unknown means stop and inspect value-free status; do not auto-repeat.
Do not run `op read` yourself, pipe a bearer, echo it, or enable subprocess logging.

## 4. Use the desk

1. After SB-A08 passes, open the dedicated service at
   `http://127.0.0.1:8877` in the local operator browser. Never expose the desk on
   a non-loopback interface.
2. Settings -> **Saxo SIM account inspection** must show capability, state,
   generation and conservative expiry, with no token/reference form.
3. Explicitly confirm **Discover SIM accounts**. The browser sends network
   consent and expected generation only. No broker request happens merely on load.
4. Choose one returned account, including when only one choice exists. Explicitly
   confirm **Inspect selected account**. Review currency, accounting cash and
   position summary. Display must say SIM/read-only, no fund connected, trading
   blocked. No model/data selection, mandate or fund is changed.
5. To stop access, select **Revoke inspection credential**. State becomes revoked
   and displayed choices/results clear. Nothing automatically reconnects.

Do not export account output into public evidence. Each action stops within
30 seconds; request/paging/size bounds are in [contracts\inspection.md](contracts/inspection.md).
An invalid/expired/rejected token requires updating the actual field through the
operator's normal authorized local workflow and fresh deliberate delivery. There
is no refresh endpoint, OAuth fallback or automatic retry.

## 5. Rotate, restart and troubleshoot

- Rotate deliberately with a new expiry/mapping and one new delivery. New actions
  use the new generation; old choices must be rediscovered.
- Revoke during an action prevents subsequent dispatch/publication; an already
  transmitted GET cannot be recalled.
- Backend/container restart loses all leases and choices; refresh the operator
  session and deliver again. Never copy a token into durable storage to survive it.
- `consent-required`/`network-disabled`: use explicit supported action/capability;
  credential presence is not consent.
- `stale-generation`/`stale-selection`: clear and rediscover deliberately; never
  substitute the newest secret under an old handle.
- `inspection-limit`/`invalid-broker-response`: no partial success, automatic
  continuation or order. Investigate using fixed reason codes, not raw token-bearing
  response dumps.
- `deployment-unavailable`: topology gate remains blocked; do not alter existing
  containers or use another profile as a workaround.

The existing host-only `aihf saxo inspect --enable-network` remains a separate
source path described in the parent quickstart. It cannot consume the backend
lease and is not proof of this in-app bridge. SIM fund deployment/order execution
remains denied by `require_sim_account_ownership()` regardless of root admission.

## 6. Offline verification after implementation

Use the existing test-owned synthetic-root harness, fakes and project-local
scratch paths. Do not read any actual local secrets/configuration or run Docker/
broker requests. Use the existing Poetry Python 3.11 environment (the `uv tool run`
prefix also works when `poetry` is not on PATH). Let the repository conftest
allocate its marked test-owned root; do not override `--basetemp` outside it or
disable conftest/admission merely to obtain passing HTTP tests:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
uv tool run --from poetry poetry run python -m pytest hedge_fund\secrets\test_docker_delivery.py hedge_fund\runtime\test_external_credentials.py hedge_fund\runtime\test_credential_delivery.py hedge_fund\brokers\test_saxo_tokens.py hedge_fund\brokers\test_saxo_client.py hedge_fund\brokers\test_factory.py hedge_fund\web\test_saxo_inspection.py -q --tb=short -p no:cacheprovider
```

Frontend from its directory, then full-suite source acceptance:

```powershell
Push-Location .\frontend
try {
    npx vitest run src\pages\settings-saxo.test.tsx
    if ($LASTEXITCODE -ne 0) { throw 'Saxo settings tests failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally {
    Pop-Location
}
uv tool run --from poetry poetry run python -m pytest hedge_fund -q -p no:cacheprovider
git --no-pager diff --check
```

Run the smallest targeted selections during TDD; run the full suite before claiming
full-suite acceptance. Source implementation and final code review are complete,
but do not imply full-suite or platform acceptance. No dependencies are installed merely to draft this plan.
Use existing Black/isort/Flake8 configuration on changed Python files. Retain
exact test IDs, clocks, revision/fingerprint/platform and synthetic provenance in
the parent `acceptance-evidence.md`; do not store secret-bearing traces.
Any failure needs fresh per-test baseline evidence, not broad historic exemptions.
SB-A08 real Docker evidence remains BLOCKED despite the implemented/reviewed
dedicated topology and isolated fake-only helper attempt. After exact operator-local
inputs and deployment gates are satisfied, the operator-run local smoke must record:
UTC time and host OS; Docker Engine/Desktop and Compose versions/context; exact
source revision/hash, image digest and dedicated container identity; the approved
dedicated root/volume identity (no fund contents); selected Compose profile and
port/network inspection results; host-local browser reachability and a
non-loopback exposure-denial check; exact test IDs/commands; and fixed outcome
codes for successful explicit discovery/selection/inspection/revoke. Keep
credential references, bearer material, account details and raw upstream/secret
traces out of repository evidence. The smoke must use only manual SIM GET actions:
no orders, live endpoints, schedules, fund-state writes, container/network
mutation or secret persistence.
