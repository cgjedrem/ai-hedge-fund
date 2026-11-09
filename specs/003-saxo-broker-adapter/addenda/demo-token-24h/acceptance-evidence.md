# Acceptance Evidence: Saxo SIM Demo Connection

## Rebase integration verification (2026-11-09)

- **Target**: PR #8 head `ca434fdb91730d036d11da3a91667173bbf90a6a`; this session's local rebase also includes the existing `edc79eb` data-recovery commit. The original task checkpoint is `de5884511e36c7979834d8202d1a59bbe1d3604c`; rebase conflict resolution is in progress.
- **Runtime boundary**: no Saxo request, order, fund deployment/mutation, shared-root write, schedule, or container/runner change was made.
- **Focused offline results**:
  - `uv tool run --from poetry poetry run pytest hedge_fund/test_run.py -k 'saxo_inspect or cli_requires_explicit_root' -q --basetemp=.pytest-pr8-saxo-cli2` — **7 passed, 91 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/brokers/test_saxo_tokens.py hedge_fund/brokers/test_saxo_client.py hedge_fund/brokers/test_factory.py hedge_fund/fund/test_spec.py -k 'saxo or demo or account_key' -q --basetemp=.pytest-pr8-saxo-targeted` — **78 passed, 92 deselected**.
  - `uv tool run --from poetry poetry run pytest hedge_fund/test_run.py -k 'cli_sim_create_denies or cli_sim_execution_denies' hedge_fund/brokers/test_factory.py -k sim_ownership_denial hedge_fund/brokers/test_account_binding_guards.py -k sim -q --basetemp=.pytest-pr8-saxo-ownership` — **5 passed, 4 failed, 2 errors, 112 deselected**. The selected CLI synthetic-root tests cannot enroll these pytest temporary roots because they are outside the harness-created `.test-owned` root; this is a fixture/environment boundary, not a bypass or permission to weaken admission. The factory ownership denial itself passed.
- **Credentialed SIM inspection: BLOCKED**. The process has no `SAXO_DEMO_ACCESS_TOKEN_REF`; `op` is installed but `op whoami --format=json` is unauthenticated. No vault item was listed or read, and no token value or `.env` was accessed. The existing 1Password path cannot be used from this process without its authorized local reference and authenticated session; no login/refresh was attempted.
- **Target behavior**: read-only `aihf saxo inspect --enable-network` runs without opening a fund root and requires explicit network consent. Fund/SIM mutation remains blocked by the separate `require_sim_account_ownership()` gate (`ownership-unknown`) even where local root admission passes. Do not weaken either gate.
- The full suite and style checks are still pending in this rebase worktree; results must not be inferred from prior baseline evidence below.

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
