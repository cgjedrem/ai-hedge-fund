# Acceptance Evidence: Saxo SIM Demo Connection

## User-authorized publication and bounded container start (2026-11-09)

The user subsequently authorized committing/pushing the reviewed changes to
existing **cgjedrem/ai-hedge-fund PR #8** and starting a new dedicated inspection
container. This supersedes historical statements below that no commit, push or
container start was authorized; it does not waive normal root admission or
authorize initialization/enrollment/trust, shared-root use, orders, live-account
traffic or changes to existing containers.

- Verified the correct PR was **OPEN**, head
  `ca434fdb91730d036d11da3a91667173bbf90a6a`, branch
  `cgjedrem-vigilant-robot`. Explicit `--repo cgjedrem/ai-hedge-fund` is required:
  unqualified `gh pr view 8` selects the upstream fork's unrelated closed PR.
- Fetched that branch and verified it is an ancestor of this session's HEAD.
  Staged only the explicit reviewed file manifest, passed staged `git diff
  --check`, and committed implementation
  `499fc83b288d08e2ca2902620ca4d762c7736058` with the required coauthor trailer.
  Normal `git push origin HEAD:cgjedrem-vigilant-robot` succeeded
  (`ca434fd..499fc83`); the live PR head matched afterward. No checkout, force
  push, squash, main merge or other-worktree operation occurred.
- Built `aihf-saxo-inspection:499fc83` using `Dockerfile.web`, revision
  `499fc83b288d08e2ca2902620ca4d762c7736058`, package-source SHA-256
  `397520f03f1bea92c92eb4158fc4b341f9ab4e938f82c5c74f7150fa099827f7`.
  Build succeeded, immutable image
  `sha256:204f643d4c21b916cfd93d5d112f90a5ec9edf6f7a161942c3376cdbe2acf459`;
  both OCI identity labels matched. Build included frontend compilation and
  source-identity verification; no credentials were supplied to the build.
- Docker Engine **29.9.2**, Compose **5.6.1**, context **desktop-linux**,
  Linux/x86_64 kernel **6.6.87.2-microsoft-standard-WSL2**. Compose configuration
  validation for `docker-compose.saxo-inspection.yml --profile saxo-inspection`
  passed using non-secret pin values and an explicitly unresolved external-volume
  placeholder. This was syntax validation, not deployment approval.
- No approved pre-existing, dedicated, no-fund-state admitted inspection volume
  was supplied or found in the named-volume metadata. The only AIHF data volume
  belongs to the existing cycle-two service; it was not mounted, read or changed.
  The approved plan expressly excludes creating/enrolling/trusting a production
  root for inspection, so no production inspection volume or counterfeit
  test-owned production root was created.
- To test the supported entrypoint without changing any root, started a bounded,
  uncredentialed **readiness probe**, not an admitted deployment, from that image
  on its own disposable bridge, published only
  `127.0.0.1:8877:8876`, read-only filesystem, all capabilities dropped,
  no-new-privileges, no restart policy and **no data mounts**. Requested role
  `web-operator`, empty application-provider allowlist and separate
  `saxo-demo-token` capability; immutable image `/data` was the only root candidate.
  Probe container:
  `8db9cf272303d785f620aaaadf7e9a631ccb458c1a65aa3ed6dd2712834c6f0f`.
  Normal `aihf-web-supervisor`/`aihf-web` startup exited **2** with
  `aihf-web: error: root requires local NTFS or ext4`. Its unmounted image root
  is not an eligible ext4 data root. No enrollment/trust was attempted.
- Bounded host GET of `http://127.0.0.1:8877/api/saxo/sim/status` observed
  **unreachable**, container **exited**, not running/restarting; the readiness
  probe took **2.12 seconds**. No health/HTTP response, observer role, available
  capability, authenticated session or browser reachability was observed.
  **There is no listening inspection service.** Removed exactly that exited
  container and its created network
  `97cc598e65a7eb664c596988bab7c84d9c3640ac2e9540186e5c7c4f6f74405d`;
  no restart loop or detached helper was left.
- Presence-only host checks found `op` installed, no
  `SAXO_DEMO_ACCESS_TOKEN_REF`, no `OP_SERVICE_ACCOUNT_TOKEN` or
  `OP_CONNECT_TOKEN`; bounded captured `op whoami --format=json` reported
  authentication unavailable. Raw output was neither emitted nor persisted.
  No vault reference, item, field, token or `.env` was read or guessed. The
  ambiguous description of a latest token does not supply an exact field
  reference or conservative UTC expiry.
- Existing user containers `bb35e1e52ba8` and `ff767e9ab4cf` remained running;
  neither was restarted, reconfigured, inspected for secrets or attached to the
  new network. No real Saxo/provider/model request, OAuth refresh, lease
  publication, account result, fund mutation or order occurred.

**Disposition:** image build and bounded startup attempt are complete, but
T026/SB-A08 and credentialed SIM acceptance remain **BLOCKED**. An already
approved dedicated admitted inspection root/volume is required first; there is
no supported bootstrap under this inspection-only authorization. An exact
operator-local `op://...` field reference and conservative UTC expiry, plus
attended host authentication, are also required before delivery. Ask for these
non-secret inputs only, never the token value. The runbook now includes a
token-free status curl and a Python `requests.Session` example retaining
CSRF/session in process memory with explicit consent/selection/generation/revoke.
That Python example passed syntax parsing only; it was not executed against a
service. Full Python suite was not rerun or claimed.

### Additional isolated Linux/ext4 fake verification

This follow-up used **only a disposable test artifact**, not a production
inspection volume or bootstrap. It supersedes the older "zero tests collected"
Linux finding below for this exact three-module selection, not the remaining
deployment/IPC acceptance.

Created named volume `aihf-saxo-linux-tests-bf812617` with labels
`aihf.runtime.purpose=disposable-test-only` and
`aihf.runtime.provenance=synthetic-test-harness`. Mounted it only at checkout
`/workspace/outputs`, with the checkout read-only at `/workspace`, image root
read-only, network **none**, all capabilities dropped and no-new-privileges.
Unchanged `hedge_fund/conftest.py` allocated/marked its test-owned root and normal
`RootContext` admission succeeded on the volume's ext4 filesystem. No admission
API, test-owned marker, owner authority or environment was fabricated for a
production service.

Archived only installed existing Poetry-environment Python sources for
`pytest`, `_pytest`, `pluggy`, `iniconfig`, `packaging`, `pygments` and the `py.py`
shim into project-relative `.saxo-linux-pytest-tools.zip` (**1,604,788 bytes**).
Extracted these tooling sources under the disposable volume's
`/workspace/outputs/verification-tools`. No package install, manifest change,
internet/provider request or dependency download occurred.

An initial tooling attempt exited before conftest loading because pytest
capture had no writable default scratch directory. The retry explicitly kept
pytest's pre-conftest scratch inside `/workspace/outputs`; conftest then
configured its normal marked test-owned environment. No outside scratch path
was made writable. Environment:
`PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; Linux CPython **3.11.18**, pytest **7.4.4**.
Exact executed pytest selection:

```text
pytest.main([
  "hedge_fund/runtime/test_credential_delivery.py",
  "hedge_fund/runtime/test_external_credentials.py",
  "hedge_fund/web/test_saxo_inspection.py",
  "-q", "--tb=short", "-r", "s", "-p", "no:cacheprovider"
])
```

**Observed: 120 passed, 9 failed, zero skipped; exit 1; pytest 81.55 seconds,
90.75 seconds around pytest.main. This selection did not pass.** All HTTP
inspection tests and other frame/store cases passed. The nine Unix socket
cases use pre-existing `_short_test_socket_path()` hardcoded to `/tmp`; that path
remained read-only and was not mounted or made writable. Seven fail at direct
socket-directory creation with `Errno 30: Read-only file system`, and two fail
server creation with `private local IPC is unavailable`. Failing cases:

- `test_delivery_server_does_not_unlink_an_unowned_socket`
- `test_delivery_server_survives_deep_frame_and_handles_next_status`
- `test_delivery_server_survives_huge_integer_frame_and_handles_next_status`
- `test_delivery_server_recovers_only_owned_stale_socket`
- `test_delivery_server_preserves_untrusted_existing_socket_directory` for
  `active`, `wrong-mode`, `wrong-socket-mode`, `wrong-owner`, `extra-entry`

This identifies a concrete test-path/runtime-boundary mismatch, not successful
IPC acceptance. No source was changed to suppress failures, patch admission,
redirect test socket paths, skip tests or weaken the container. The earlier
Windows skips are no longer the only Linux evidence; these nine actual failures
must remain visible.

At `2026-11-09T17:25:50+01:00`, cleanup verified: initial helper
`6d422638d478180067e99f40e4eae8a2610127b615e45358098886704b2f8217`
and retry helper
`a03cf1ff0623a30ed486cd1908d7d114a3e499b73e80fd1ed0d0afff0699d60a`
were removed, only their disposable test volume was removed, tooling archive
was absent, and no `aihf-saxo` helper container/volume remained. The verified
source-pinned image was retained. No production-root lifecycle operation,
real credential or broker traffic occurred.

## Final review and bounded Linux verification (2026-11-09)

**Current result: final parent code/static/focused review PASS**, as confirmed by
the parent/user after the publication race fix. This supersedes older pending-QA
statements below without changing their historical test results. T023 is complete.
T022 remains partial: full Python suite **NOT RUN**; Linux IPC/HTTP execution
**BLOCKED before collection by normal root admission**, not a test assertion
failure. T026/SB-A08 actual host/browser/SIM acceptance remains **BLOCKED**:
exact approved local reference/expiry are missing and no live acceptance was
authorized. No reference or expiry was inferred.

At `2026-11-09T16:16:28.662945+00:00`, HEAD remains
`53bb1fcf731cd31fbc476710cef9ced2a2a255f4`. Recomputed using the 21-path
algorithm below, implementation manifest SHA-256 is
`4e6f9fc7fa6673d2a9b37c774d2ad832ba9439f8856ab08a46979ca2aa305683`;
implementation dirty-diff SHA-256 is
`33b400c3714f0cc0ec41647b27943de3c330b19a87c439e20993c6b2d8fee847`.
No application/test source changed during this verification.

**Actual platform/image**: Docker Linux/amd64, kernel
`6.6.87.2-microsoft-standard-WSL2`, glibc 2.41; existing local image
`aihf-op-cycle2-user-test:dc2bed3`, image ID and reported repository digest
`sha256:f10303e775fb9f926ebd71bfbc9b321a39024d22752c49516b7772dde4eb06a4`.
Image CPython **3.11.18**. No image was built or pulled. Presence-only probes
found pytest missing in this image and in the two existing alternatives
`aihf-web:2b4cbed2a20c6f9877cbbc762e6df378c960d3f8-3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`
and `cgjedrem-legendary-umbrella-runner:latest`.

**Bounded offline bootstrap**: archived only installed host pure-Python sources
for pytest, `_pytest`, pluggy, iniconfig, packaging, pygments, plus the installed
`py.py` compatibility shim. The first bootstrap import reported missing `py`;
adding that existing shim produced successful pytest **9.1.1** imports under
Linux Python 3.11.18. No package install, dependency/manifest change or network
access occurred. Application dependencies came from the existing image, not a
Windows virtual environment.

The named test helper used `docker run --rm --network none --read-only`,
repository read-only bind at `/workspace`, archive read-only at
`/verification-tools.zip`, and isolated tmpfs mounts at `/verification-tools`
(32 MiB), `/workspace/outputs` (128 MiB), `/tmp` (64 MiB).
`PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` were set. Python extracted only the tooling
archive into its helper tmpfs, added `/verification-tools` and `/workspace` to
the import path, changed to `/workspace`, then called the exact pytest selection:

```text
pytest.main([
  "hedge_fund/runtime/test_credential_delivery.py",
  "hedge_fund/runtime/test_external_credentials.py",
  "hedge_fund/web/test_saxo_inspection.py",
  "-q", "--tb=short", "-r", "s", "-p", "no:cacheprovider"
])
```

**Observed result: exit 4, zero tests executed, 0.92 seconds** measured around
`pytest.main`. Normal `hedge_fund/conftest.py` created its marked synthetic root
but `RootContext.open` -> `validate_filesystem` rejected tmpfs with
`UnsupportedFilesystemError: root requires local NTFS or ext4`.
No `--confcutdir`, `--noconftest`, patched admission, alternative filesystem
claim or weakened root gate was used. This is a concrete platform/harness
prerequisite blocker, not evidence of a source bug. Linux deny/revoke/restart
behavior was **not observed**, and the nine Windows-skipped socket cases remain
unverified. Their previously passing Windows fake/frame/CAS/revoke/restart and
HTTP results remain separate evidence (306 passed/9 skips; adjacent 136/1 skip).

**Cleanup confirmed** at the timestamp above: `docker ps -a --filter
name=aihf-saxo-verify- --format '{{.ID}} {{.Names}} {{.Status}}'` returned no rows.
Created helper names were `aihf-saxo-verify-probe-bf812617`,
`aihf-saxo-verify-option-bf812617` (reused sequentially for two probes),
`aihf-saxo-verify-tooling-bf812617` (sequential bootstrap attempts), and
`aihf-saxo-verify-linux-bf812617`; all ran with `--rm` and were absent afterward.
Transient container IDs were not captured; no IDs are invented. The only host
scratch file, repository-relative `.saxo-linux-pytest-tools.zip` (1,659,722 bytes),
was explicitly removed and its absence checked. Helper tmpfs contents disappeared
with their containers; no helper, archive or test output remains on the host.
No existing user container, volume or network was attached or modified, no user
container logs or environment were read, and no real credentials, `.env`, `op`,
vault, Saxo/provider requests, fund/order actions, commit or push were used.

## Final-QA publication race correction (2026-11-09)

**Result: fixed and freshly validated offline; QA recheck remains pending.**
This follow-up supersedes the earlier bridge source fingerprints and affected
Python test counts below. The branch/HEAD and existing Poetry Python 3.11
environment are unchanged. No commit, dependency/configuration change,
credential access, real network call, Docker operation or shared-root mutation.
All roots, leases, clocks and broker responses used by tests are synthetic and
the repository conftest/network guard remained loaded.

**Reproduction / diagnosis**: the prior final-position-GET test revoked before
the final lease/authority checks, so it did not cover construction/reflection
work after those checks. New
`test_http_loss_during_result_redaction_prevents_publication` blocks the
reflection-check seam after the prepared discovery/inspection projection has
passed its earlier checks. Complete revoke/cancel/owner/root/permission loss,
expiry or generation invalidation, then unblock. Before the fix all **14 cases
failed in 22.08s**: HTTP 200 returned choices or the financial summary. With the
fix the same targeted command passed **14 cases, 48 deselected in 21.35s** before
the additional lock-order/boundary tests were added. Failure is now a sanitized
non-200 response, without choices/account/cash/positions; captures are released.

**Patch manifest / linearization**:

- `hedge_fund\runtime\external_credentials.py`: add
  `commit_capability_publication`; retain the store's reentrant lock through
  captured-handle validation and the local publication callback. This is shared
  with revoke/invalidation/close, not merely an extra unlocked check. Rotation
  still permits pinned A to complete; late A invalidation never revokes B.
- `hedge_fund\web\saxo_inspection.py`: discovery and inspection commit their
  complete reflection-checked projections through `_publish_result`.
  Coordinator lock first (same order as `_begin`), recheck local authority, then
  store lock. Commit marks cancellation inactive and returns the prepared result.
  Cancellation and `clear_all` use the coordinator lock. Revoke releases the
  store lock before `clear_all`; `_end` releases the store lock before acquiring
  the coordinator lock. No store-to-coordinator nested acquisition was added.
  No broker call, projection construction or reflection traversal is performed
  while holding the publication locks. The store callback performs no I/O,
  authority check or further lock acquisition.
- `hedge_fund\runtime\test_external_credentials.py`: four additional cases verify
  validation/commit share the revocation lock under actual contention and that
  revoke/invalidate/close winning first never invokes the commit callback.
- `hedge_fund\web\test_saxo_inspection.py`: 17 additional cases: the 14 red-first
  post-redaction loss cases; a cancellation-lock contention case; two HTTP
  publication-wins cases delaying cleanup/transport handoff while revoke/cancel
  completes. These distinguish a serialized commit from an unchecked extra
  validation and define the allowed opposite ordering.
- Related docs: `onepassword-bridge\contracts\inspection.md`, `spec.md`,
  `tasks.md`, and this evidence section record the scenario, acceptance rows and
  exact boundary.

The **publication boundary is the local prepared-result commit, before FastAPI
serialization/HTTP transmission**, not a socket-send gate. Revoke/cancel winning
before commit suppresses the result; publication winning first may still be
delivered after revoke. Cancel after commit reports `cancelled: false`.
Neither committed results nor already sent HTTP bytes can be recalled.
Root/owner/private-storage/network authority is rechecked at the local boundary,
not made immutable against external changes through transport. No absolute
post-revoke transport-suppression claim is made.

**Fresh exact validation commands/results**, with
`PYTHON_DOTENV_DISABLED=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONDONTWRITEBYTECODE=1`:

1. Red-first reproduction:
   `uv tool run --from poetry poetry run python -m pytest hedge_fund\web\test_saxo_inspection.py -k loss_during_result_redaction -q --tb=short -p no:cacheprovider`
   — **14 failed, 48 deselected in 22.08s** before implementation, then
   **14 passed, 48 deselected in 21.35s**.
2. Fresh complete bridge selection:
   `uv tool run --from poetry poetry run python -m pytest hedge_fund\runtime\test_credential_delivery.py hedge_fund\runtime\test_external_credentials.py hedge_fund\secrets\test_docker_delivery.py hedge_fund\web\test_saxo_inspection.py hedge_fund\brokers\test_factory.py hedge_fund\brokers\test_saxo_client.py hedge_fund\brokers\test_saxo_tokens.py -q --tb=short -r s -p no:cacheprovider`
   — **306 passed, 9 skipped in 54.55s**. Includes **65 inspector tests**.
   The nine skips remain existing Unix-socket/platform tests on Windows.
   Pinned A/B rotation, late A rejection preserving B, generation-CAS revoke,
   cancel/authority loss, release and restart cases all pass.
3. Fresh adjacent HTTP/runtime-authority selection:
   `uv tool run --from poetry poetry run python -m pytest hedge_fund\web\test_app.py hedge_fund\web\test_services.py hedge_fund\web\test_settings.py hedge_fund\web\test_settings_provenance.py hedge_fund\web\test_write_authority.py hedge_fund\brokers\test_account_binding_guards.py -q --tb=short -p no:cacheprovider`
   — **136 passed, 1 skipped in 107.78s**.
4. On exactly the four Python files in this follow-up manifest, the commands
   below **all passed**; Black reports four files unchanged, no ignored error
   codes. `git diff --check` passed (existing LF/CRLF advisories only).

   ```powershell
   $files = @('hedge_fund\runtime\external_credentials.py', 'hedge_fund\runtime\test_external_credentials.py', 'hedge_fund\web\saxo_inspection.py', 'hedge_fund\web\test_saxo_inspection.py')
   uv tool run --from poetry poetry run black --check @files
   uv tool run --from poetry poetry run isort --check-only @files
   uv tool run --from poetry poetry run flake8 --max-line-length=420 @files
   git diff --check
   ```

**Updated source fingerprints**, using the same 21 implementation paths and
NUL-delimited hashing algorithms documented below:

- Manifest SHA-256:
  `4e6f9fc7fa6673d2a9b37c774d2ad832ba9439f8856ab08a46979ca2aa305683`.
- Implementation dirty-diff SHA-256:
  `33b400c3714f0cc0ec41647b27943de3c330b19a87c439e20993c6b2d8fee847`.

The full Python suite, frontend tests/build, credentialed host acceptance and
Linux/socket smoke were **not rerun** in this follow-up. Earlier frontend
results are historical and frontend files were not changed by this correction.
T022 remains partial, T023 requires QA recheck, and T026/SB-A08 remain blocked.

## In-app inspection bridge implementation status (2026-11-09)

**Result: Expanded governed offline validation passed; final QA, full Python suite
and host acceptance remain outstanding.** Evidence refreshed
`2026-11-09T16:00:17.9218897Z`. The current working branch
remains `cgjedrem-verbose-winner` at
`53bb1fcf731cd31fbc476710cef9ced2a2a255f4`. All changes are local and
uncommitted. Source-manifest fingerprint (SHA-256, listed implementation files
only; documentation and ignored build output excluded):
`81d734eeb65896e8173b0ec59e2c7d2e8b69d7582f76486cbe2a2214bb848846`
(SHA-256 over sorted repository-relative implementation paths and file bytes,
with NUL separators; docs excluded).

The implementation adds a distinct `saxo-demo-token` capability namespace and
purpose-bound in-memory lease; compatible private stdin delivery with explicit
expiry; strict dedicated host/topology validation and opt-in
`docker-compose.saxo-inspection.yml`; a lease-backed Saxo SIM GET client with
proxy/redirect denial, response/paging/request/time bounds and no token cache;
authenticated, consented, actor/generation-scoped discovery and selected-account
inspection routes; and a separate transient settings card. The existing
`op-runtime` network-none profile, application-provider catalog and Saxo
fund/order ownership gates remain separate. The bridge makes no claim that a
Docker bridge filters domain egress.

**Recovered environment**: Windows; existing project Poetry environment
`aihf-4l3vIF0x-py3.11`, CPython **3.11.15**, pytest **7.4.4**, pandas **2.3.3**,
Black **23.12.1**, isort **5.13.2**, Flake8 **6.1.0**; Node **22.13.1**,
npm **10.9.2**, Vitest **4.1.12**, Vite **6.4.5**. Poetry was recovered with
`uv tool run --from poetry poetry env info`; no dependency restoration or manifest
change was needed. Earlier system-Python-3.13/missing-pandas/style claims are
superseded, not current blockers.

**Final exact commands/results** (all Python tests loaded the repository conftest,
marked synthetic-root enrollment and network guard; no `--noconftest`,
`--confcutdir`, or external `--basetemp`):

- `uv tool run --from poetry poetry run python -m pytest hedge_fund\runtime\test_credential_delivery.py hedge_fund\runtime\test_external_credentials.py hedge_fund\secrets\test_docker_delivery.py hedge_fund\web\test_saxo_inspection.py hedge_fund\brokers\test_factory.py hedge_fund\brokers\test_saxo_client.py hedge_fund\brokers\test_saxo_tokens.py -q --tb=short -r s` — **285 passed, 9 skipped in 27.43s**. All nine skips are existing Unix-socket ownership/server tests on Windows; private stdin/frame and host/topology fakes ran. The web inspection file contains **48 passing tests**, including real FastAPI middleware/routes/services with only synthetic leases, clock and fake Saxo transport injected.
- `uv tool run --from poetry poetry run python -m pytest hedge_fund\web\test_app.py hedge_fund\web\test_services.py hedge_fund\web\test_settings.py hedge_fund\web\test_settings_provenance.py hedge_fund\web\test_write_authority.py hedge_fund\brokers\test_account_binding_guards.py -q --tb=short` — **136 passed, 1 skipped in 109.29s**. The pre-addition HTTP baseline also passed **52 tests in 8.37s** without fixture exceptions.
- From `frontend`: `npx vitest run src\pages\settings-saxo.test.tsx --reporter=dot` — **9 passed in 59.30s**; then final `npm test -- --reporter=dot` — **232 passed, 14 files in 45.20s**.
- From `frontend`: `npm run build` — **TypeScript and Vite build passed**, **2317 modules**, **32.25s** Vite duration. Existing large-chunk advisory remains nonfatal; generated static assets are ignored build output.
- All **16 changed/new Python files**: `black --check`, `isort --check-only`, `flake8 --max-line-length=420`, each via `uv tool run --from poetry poetry run`, **passed**. No warning-ignore flags were used. Fixed new unused-variable/spacing/import/formatting issues rather than hiding them. `git diff --check` passed.
- **Full Python suite: NOT RUN** in this bounded specialist phase (the parent reports approximately 40 minutes). No full-suite pass or current environment/fixture blocker is claimed.

**Genuine missing behavior fixed**: a successful late inspect response restored
the summary after cancellation. New UI tests first reproduced this (**1 failed,
227 passed** across the then-current frontend suite). A transient action epoch
now fences publication on cancel, revoke, reconnect, authority/status change and
unmount; stale completions cannot overwrite a newer action's state. Revoke is
available while a GET is in flight. Removed discovery's unnecessary status reload,
which could clear fresh choices when status responses were slow. Added HTTP
session/origin/token/peer/owner/root/permission/network/consent denial,
selection scoping, disk-quiet typed inspection, bounded resource limits, busy and
foreign cancel, final-GET revoke, A/B late rejection and restart tests. These HTTP
tests extend an already-implemented seam; no retrospective red-first claim is made.
Runtime tests now explicitly cover multi-capture A/B retention/release, CAS revoke,
close/restart and stale pins. Broker tests exercise the DemoTokenManager subtype
fence for lease-backed order and live-path denial.

**Implementation manifest** (all fake/offline source artifacts fingerprinted
separately from docs): `docker-compose.saxo-inspection.yml`;
`frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`,
`frontend/src/pages/settings.tsx`, `frontend/src/pages/settings-saxo.test.tsx`;
`hedge_fund/brokers/factory.py`, `saxo.py`, `test_factory.py`,
`test_saxo_client.py`, `test_saxo_tokens.py`;
`hedge_fund/runtime/credential_delivery.py`, `external_credentials.py`,
`test_credential_delivery.py`, `test_external_credentials.py`;
`hedge_fund/secrets/docker_delivery.py`, `test_docker_delivery.py`;
`hedge_fund/web/app.py`, `schemas.py`, `services.py`, `saxo_inspection.py`,
`test_saxo_inspection.py`.

**Final implementation diff SHA-256** (`git diff --binary HEAD` for the
implementation manifest above, followed by the sorted bytes of untracked
implementation artifacts; documentation and the pre-existing
`.pytest-saxo-delivery-tests/` directory excluded):
`d1c8cfd2cf78467f50dffeed11c272ca69b79c50fd054d7aeda7833c794f55b7`.

Both hashes cover exactly the **21 implementation files** listed above. For the
manifest hash, sort canonical repository-relative paths and append
`path + NUL + file bytes + NUL` for each. For the dirty diff hash, hash
`git diff --binary HEAD -- <manifest paths>` followed by those same delimited
paths/bytes for untracked implementation files only. Documentation, ignored
build output and task-owned pytest scratch directories are excluded.

**Not performed / blockers**: no 1Password reference or token was read or
resolved; no Saxo request, Docker command, container/network change, shared-root
mutation, order or fund operation was performed. No host/browser smoke was run.
The operator has not supplied the locally approved field reference and expiry,
so T026 and SB-A08 remain **BLOCKED**. T022 is partial solely because the full
Python suite has not run; focused validation, frontend and style are complete.
T023's parent QA review remains pending. Windows cannot exercise the nine
Unix-socket tests; no Linux/container validation is inferred. No commit, push,
branch change or PR was made.

At `2026-11-09T16:01:50.1286484Z`, only the inspected synthetic pytest directories
`.pytest-saxo-delivery-tests` and `.pytest-saxo-validation` were removed. Their
file-name allowlist and link targets were checked before cleanup; no unknown
files or other worktree/output directories were deleted. Final `git diff --check`
passed after documentation updates.

## Documentation-only bridge scope supersession (2026-11-09)

The user subsequently approved the narrow in-app inspection bridge. The dated
Spec005 OP-FR-002 scope amendment now permits only `saxo-demo-token` ->
`saxo-sim-readonly`; OP-FR-007 memory-only retention, all other broker/OAuth
delivery denial, application-provider separation and SIM mutation/ownership
denial remain intact. Specification, plan, tasks, research, data model, interface
contract, runbook and author quality checklist are in `onepassword-bridge\`.

This phase performed source/document reads and documentation edits only. No
source/test script, credentials/configuration/environment/token read, Docker,
network, broker or order operation occurred. No commit/push/branch/PR change.
The prior dirty test file is preserved for the parent's later implementation.
Parent caveman review and comment resolution are pending, not reported as passed.
No new test or runtime acceptance result is claimed.

The actual eligible `docker-compose.op-runtime.yml` target is network-none with
no published browser port. Source implementation may proceed offline after review;
real Docker in-app acceptance stays BLOCKED until a supported source-pinned
browser/SIM egress topology is reviewed. Exact source reference, expiry and
eligible target remain operator-local inputs; none were discovered or guessed.

The following policy-denial record remains historical evidence for pre-amendment
source behavior. It is not the current approved scope or bridge acceptance.

## Docker bridge policy assessment (2026-11-09, baseline `53bb1fc`)

**Result: BLOCKED by the approved architecture; no broker bridge implemented.**
Read-only source inspection found that the Spec005 1Password extension explicitly
excludes Saxo tokens and SIM authentication. OP-FR-002 requires broker-credential
denial; OP-FR-007 prohibits persisted values. Contrary to the proposed file-backed
premise, its delivery destination is a process-local memory lease, not a secret
file. `SourceMapping`, `APPLICATION_PROVIDER_IDS`, `runtime_provider_destinations`
and `RuntimeCredentialLeaseStore` independently enforce this application-provider
scope. A separate CLI process cannot consume that backend's memory lease.

The user instruction requires stopping rather than overriding deliberate
governance. No provider registry, allowlist, delivery protocol, token source,
ownership gate or runtime consumer was changed. The quickstart records the
specific policy amendment needed and an exact operator-run host inspection command
requiring the operator's known `op://` field reference and authenticated terminal.
No actual vault/item path was inferred or written.

**Manifest**:

- `hedge_fund\secrets\test_docker_delivery.py`: six fake-only cases cover Saxo and
  purpose-named demo destination CLI denial before mapping/Docker/resolver access,
  mapping/backend-configuration denial, and status/publication denial while
  leaving an empty application lease store unchanged (`requires-auth`, generation
  zero). These cases do not establish preservation of an active lease.
- This addendum's `plan.md`, `quickstart.md`, `tasks.md`, and
  `acceptance-evidence.md`: architectural stop condition, safe host alternative,
  proposed policy review and validation evidence.

**Verification**: Windows, existing Poetry Python environment; dotenv loading and
pytest plugin autoload disabled, bytecode/cache output disabled, existing guarded
test harness and project-local pytest basetemp used. No dependency change/install.

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
uv tool run --from poetry poetry run python -m pytest hedge_fund\secrets\test_docker_delivery.py hedge_fund\runtime\test_external_credentials.py hedge_fund\brokers\test_saxo_tokens.py hedge_fund\brokers\test_saxo_client.py hedge_fund\brokers\test_factory.py hedge_fund\test_run.py -k '(saxo or demo or delivery or mapping or operator_provider or sim_ownership_denial) and not saxo_demo_execution_refuses_before_ledger_or_execution and not saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals' -q --tb=short -p no:cacheprovider --basetemp=.pytest-saxo-delivery-policy-final-20261109
```

Result: **166 passed, 9 skipped, 111 deselected** (final rerun 1.16 s). Includes new policy
regressions, allowed fake application delivery, standalone GET-only SIM inspection,
demo-token rejection/no-write-back and factory SIM ownership denial.
Black (`--line-length 420`), isort, Flake8 (`--max-line-length=420
--extend-ignore=E306`) on the changed test file and `git diff --check` all passed.

The initial selection without the two exclusions produced **166 passed, 9 skipped,
10 failed, 101 deselected** (1.80 s). All ten failures are existing CLI fixture
patches of removed `run.apply_credentials`, in the two excluded test functions.
`run.py` and `test_run.py` have no changes against `53bb1fc`; these pre-existing
rebase-adjacent fixture failures were not repaired or represented as a passing
suite. No full-suite or credentialed SIM acceptance is claimed.

**Safety**: No Docker command, container inspection/restart/mutation, shared-root
access, `.env`, raw environment, log or secret-value read, `op` invocation, real
broker/network call, token mutation, fund deployment, runner or order. Both
existing containers were left untouched. Production behavior and the
`require_sim_account_ownership()` denial are unchanged. Changes remain local and
uncommitted; no push.

## Rebase integration verification (2026-11-09)

- **Branch/revision**: `cgjedrem-verbose-winner`; rebased onto PR #8 head `ca434fdb91730d036d11da3a91667173bbf90a6a`. Rebase integration commit `99eda23131338cef96468dd1afea6a3a66009700`; lint follow-up `fa5845c` (source revision under test). The rebase also preserves the existing `edc79eb` data-recovery commit. Original checkpoint: `de5884511e36c7979834d8202d1a59bbe1d3604c`.
- **Workspace fingerprint**: tracked worktree clean after the source commits; only task-created pytest basetemp directories were removed. The evidence-only documentation update is not included in the tested source revision.
- **Environment**: Windows, project Poetry environment, Python 3.11. `SAXO_DEMO_ACCESS_TOKEN_REF` absent; `op` CLI installed; `op whoami --format=json` unauthenticated.
- **Runtime boundary**: no Saxo request, order, fund deployment/mutation, shared-root write, schedule, or container/runner change was made.
- **Focused offline results**:
  - `uv tool run --from poetry poetry run pytest hedge_fund/test_run.py -k 'saxo_inspect or cli_requires_explicit_root' -q --basetemp=.pytest-pr8-saxo-cli-final` — **7 passed, 91 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/brokers/test_saxo_tokens.py hedge_fund/brokers/test_saxo_client.py hedge_fund/brokers/test_factory.py hedge_fund/fund/test_spec.py -k 'saxo or demo or account_key' -q --basetemp=.pytest-pr8-saxo-core-final` — **78 passed, 92 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/brokers/test_factory.py -k sim_ownership_denial -q --basetemp=.pytest-pr8-saxo-factory` — **2 passed, 4 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/tui/test_builder.py hedge_fund/tui/test_builder_broker.py -k saxo -q --basetemp=.pytest-pr8-saxo-tui-final` — **2 passed, 15 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/test_run.py -k 'cli_sim_create_denies or cli_sim_execution_denies' hedge_fund/brokers/test_factory.py -k sim_ownership_denial hedge_fund/brokers/test_account_binding_guards.py -k sim -q --basetemp=.pytest-pr8-saxo-ownership` — **5 passed, 4 failed, 2 errors, 112 deselected**. The selected CLI synthetic-root tests cannot enroll these pytest temporary roots because they are outside the harness-created `.test-owned` root; this is a fixture/environment boundary, not a bypass or permission to weaken admission. The factory ownership denial itself passed.
- **Style**: Flake8 (`--max-line-length=420 --extend-ignore=E306`), isort `--check-only`, Black `--check` (22 files unchanged), and `git diff --check` all passed on changed Python/source files after the follow-up fix.
- **Full suite**: not run; no full-suite pass is claimed.
- **Credentialed SIM inspection: BLOCKED**. The process has no `SAXO_DEMO_ACCESS_TOKEN_REF`; `op` is installed but `op whoami --format=json` is unauthenticated. No vault item was listed or read, and no token value or `.env` was accessed. The existing 1Password path cannot be used from this process without its authorized local reference and authenticated session; no login/refresh was attempted.
- **Target behavior**: read-only `aihf saxo inspect --enable-network` runs without opening a fund root and requires explicit network consent. Fund/SIM mutation remains blocked by the separate `require_sim_account_ownership()` gate (`ownership-unknown`) even where local root admission passes. Do not weaken either gate.

## Historical pre-rebase evidence (baseline `3f7bea8`; superseded where it conflicts with PR #8)

The following records the original pre-rebase implementation and is not evidence that the same behavior is supported after rebasing. In particular, its claims about legacy SIM OAuth execution and the absence of root-admission machinery do not describe the PR #8 target.

## Scope and safety

- **Revision**: branch `cgjedrem-verbose-winner`, baseline `3f7bea8` (implementation remains uncommitted).
- **Environment**: Windows, project Poetry environment using locked dependencies, Python 3.11.
- **Credential/network boundary**: no `.env` or vault values were read; no real token was resolved; no Saxo/network request, paid data/model call, shared-root deployment, or actual order was made. Tests use fake transports, fake secret providers, and pytest synthetic roots only.
- **OAuth scope**: both the demo-token mode and the pre-existing OAuth credential path use Saxo SIM endpoints only. No live-account support is present or implied.
- **Compatibility**: only the new demo-token mode is blocked from shared-root deployment/execution. Existing unbound OAuth mandates retain the prior first-eligible SIM account selection and CLI/TUI deployment/run paths. Explicit account binding is required for demo-token mode only.

## Admission finding

At baseline `3f7bea8`, `hedge_fund/paths.py` fixes user data under `Path.home() / ".hedge-fund"` and exposes no isolated-root selector or write-admission API. No admission exception or alternate write path was introduced. The CLI and TUI reject deployment/execution only when `SAXO_DEMO_ACCESS_TOKEN_REF` selects the new demo-token mode; this keeps the new standalone token workflow from using the shared root without broadening the restriction to legacy SIM OAuth funds.

US3 remains **BLOCKED** pending an approved isolated-root admission capability. Fund initialization, cash/position reconciliation, approval, first-order authorization, bounded demo execution, and interruption recovery remain unimplemented.

## Focused offline verification

Each command used a project-local `--basetemp`; all Saxo interactions were synthetic.

| Selection | Result |
|---|---:|
| `uv tool run --from poetry poetry run pytest hedge_fund/brokers/test_saxo_tokens.py hedge_fund/brokers/test_saxo_client.py hedge_fund/brokers/test_factory.py hedge_fund/paper/test_deployed_broker.py hedge_fund/paper/test_saxo_e2e.py -q --basetemp=.pytest-saxo-review-broker-20261109` | 96 passed |
| `uv tool run --from poetry poetry run pytest hedge_fund/test_run.py -k saxo hedge_fund/paper/test_runner.py -k saxo -q --basetemp=.pytest-saxo-review-cli-20261109` | 14 passed, 39 deselected |
| `uv tool run --from poetry poetry run pytest hedge_fund/tui/test_builder.py hedge_fund/tui/test_builder_broker.py hedge_fund/tui/test_paper.py -k saxo -q --basetemp=.pytest-saxo-review-ui-20261109` | 6 passed, 41 deselected |

Coverage includes:

- Legacy SIM OAuth factory selection of the first eligible account when an old mandate has no account binding; OAuth CLI create/tick/run and TUI builder/runner paths remain available.
- Demo-token mode requires an explicit bound account and rejects deployment/execution from CLI/TUI while the token-mode setting is present.
- Demo-token rejection/expiry does not retry, refresh, or write back credentials.
- `RequestsTransport` is exercised through a patched `requests.request`: it receives `allow_redirects=False`; SaxoClient rejects 3xx responses to same-host non-SIM, same-host live-path, and cross-host `Location` targets without following any redirect.

## Style and remaining verification

- `git diff --check`: passed.
- Flake8 on all changed Python files with the repository's 420-character line length and existing E306 spacing warning excluded: passed.
- isort `--check-only` on changed Python files: passed.
- Black `--check` passes on changed Python files except `hedge_fund/test_run.py`, which has pre-existing formatting differences outside this change. A Black diff confirmed no formatting change in the added CLI regression region.
- The full suite was not run and is not claimed to pass. Earlier broad Windows runs recorded unrelated baseline issues: a console-encoding assertion in `hedge_fund/test_run.py`, a `Path.rename` collision in runner redo, and unsupported `strftime("%-d")` in a UI row test. The focused selections above pass.

## Completion status

US1 and the safe US2 inspection/account-binding subset are implemented and covered by focused offline tests. US3 deployment/execution remains blocked as described above; tasks T003 and T016–T022 remain **BLOCKED**, and T028 remains **NOT RUN**. No shared-root state, admission policy, ledger, or runner implementation was changed.

## Final review status (2026-11-09)

Read-only review passed after the legacy SIM OAuth compatibility, redirect refusal, and immediate-approval guard fixes. The final approval-path review confirmed the demo-token guard runs before ledger construction or approval writes, ordinary approve/reject and legacy SIM OAuth remain available, and documentation does not claim a real connection or full-suite result. This is static review plus offline test evidence, not live SIM acceptance. Implementation remains an uncommitted dirty diff against `3f7bea8`; no commit, push, or PR was requested or performed.

## Focused approval-bypass follow-up (2026-11-09)

- QA identified a demo-token execution bypass through `paper approve --now`: the command wrote an approval before calling tick, whose exception handling could log `tick_failed` and halt the fund after a rejected broker mutation.
- The CLI now rejects only immediate approval execution for a Saxo fund when demo-token mode is configured, before constructing the ledger. Legacy SIM OAuth, paper-fund approvals, and ordinary approve/reject verdicts retain existing behavior. No isolated-root admission capability was implemented.
- Red: `uv tool run --from poetry poetry run pytest hedge_fund\test_run.py -k saxo_demo_approve_now_refuses -q --basetemp=.pytest-saxo-approve-red-20261109` → **1 failed, 41 deselected**, as expected: the forbidden ledger constructor was reached before the fix. The regression was subsequently parameterized and renamed to cover all adjacent CLI execution entries.
- Green: `uv tool run --from poetry poetry run pytest hedge_fund\test_run.py -k 'saxo or approv or reject' -q --basetemp=.pytest-saxo-approve-green-20261109` → **35 passed, 16 deselected**. Fake CLI tests refuse `approve --now`, `tick`, `tick --again`, and `run` before ledger/provider/runner calls, with no fund directory, approval, event, or halt/control writes; the refusal emits only the fixed admission message. Compatibility cases exercise SIM OAuth immediate approvals, plain demo-token verdicts, and paper immediate approvals with/without demo-token mode. Existing synthetic paper tests exercise actual approval mailbox/event behavior.
- Adjacent-path inspection: CLI tick/redo/run already have token-mode guards; TUI session and runner actions have the same guards. TUI verdict recording does not execute tick; web approval only records a verdict and exposes no immediate tick execution. No further equivalent immediate-approval bypass was found in these entry paths. Internal engine APIs were not changed or represented as a new authorized execution surface.
- No credentials were read, no network/real broker calls were made, no shared fund root was changed, and no deployment/order occurred. The full suite was not run.
- Final recheck after code/test/document edits: `uv tool run --from poetry poetry run pytest hedge_fund\test_run.py -k 'saxo or approv or reject' -q --basetemp=.pytest-saxo-approve-final-20261109` → **35 passed, 16 deselected** (exit 0). `git diff --check`, Flake8 (`--max-line-length=420 --extend-ignore=E306`), and isort `--check-only` on `hedge_fund\run.py` and `hedge_fund\test_run.py` passed. Black `--check` passed on `run.py`; an in-memory Black check passed on the newly added test region. Whole-file Black on `test_run.py` still reports unrelated pre-existing formatting differences; those were not rewritten. Focused artifact assertions confirmed T003/T016–T022 remain blocked, T028 remains not run, T030 is recorded, and the quickstart preserves SIM OAuth/paper compatibility.
