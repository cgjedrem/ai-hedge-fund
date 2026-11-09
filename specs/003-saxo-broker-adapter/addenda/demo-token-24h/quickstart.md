# Quickstart: Saxo SIM Demo Connection

The inspection command is SIM-only and read-only. It does not create a fund or place an order.
The existing Saxo OAuth credential path is also SIM-only; this application has no live-account support.

## Prerequisites

- A Saxo SIM account and a valid demo token held in the local secrets vault.
- `op` CLI installed, authenticated, and permitted to read the referenced vault field.
- Current Python/Poetry environment installed.
- Explicit `--enable-network` consent for the inspection request.
- Fund preparation requires an explicitly selected root accepted by normal write admission and a separately verified SIM account-ownership capability. Both controls must pass; neither can be bypassed.

## Configure a local token reference

Set `SAXO_DEMO_ACCESS_TOKEN_REF` to the `op://` field reference for the 24-hour Saxo SIM token, for example `op://<vault>/<item>/<field>`. The setting contains only the reference; the token stays in 1Password and is resolved into memory when inspection starts.

Keep the existing SIM OAuth references (`SAXO_APP_KEY_REF`, `SAXO_APP_SECRET_REF`, and `SAXO_REFRESH_TOKEN_REF`) separate. The demo reference cannot be configured with any OAuth reference. SIM OAuth mode remains available to the Saxo broker factory; the read-only inspection command requires demo-token mode. Neither credential mode supports live-account endpoints.

Do not put the token value in chat, source code, a command argument, `.env`, or fund files. Demo-token mode does not refresh, write back, or assume a lifetime for the token. If Saxo rejects it or reports expiry, refresh the token in the authorized local workflow and update the referenced field; the command fails closed.

## Read-only connection check

Run (this command does not require or open a fund root):

```text
aihf saxo inspect --enable-network
```

Success prints sanitized SIM account summaries: account key, currency, cash balance, position count, and position UIC/amount rows. With multiple eligible accounts, no account is silently selected; the output sets `selection_required` and leaves `selected_account_key` empty.

To inspect one eligible account explicitly, pass its account key from the candidate summary:

```text
aihf saxo inspect --enable-network --account-key <account-key>
```

The explicit key limits inspection to that account; inspection does not persist a fund binding. Missing or invalid references produce an actionable validation error. Rejected/expired tokens produce a redacted re-authentication error. Incomplete account, balance, or position responses fail closed. The HTTP request timeout is 15 seconds. The command does not create a fund, initialize the shared user root, or submit an order.

Inspection is read-only: it uses the SIM `/users/me`, `/accounts/me`, `/balances`, and `/positions` endpoints. The demo-token client rejects every non-GET request before token resolution or transport. A rejected demo token is cleared from memory and is not retried. The command does not persist the selected account key.

## Docker credential bridge: narrow scope authorized; implementation pending

On 2026-11-09 the user explicitly authorized a narrow OP-FR-002 supersession for a
standalone `saxo-demo-token` -> `saxo-sim-readonly` in-app inspection capability.
See [onepassword-bridge\quickstart.md](onepassword-bridge/quickstart.md) for the
future operator runbook and [onepassword-bridge\plan.md](onepassword-bridge/plan.md)
for the design awaiting caveman review. The bridge is not yet implemented.
The existing Docker delivery profile has no network/browser access and remains a
platform blocker until a supported topology is reviewed. No real delivery is run
by this documentation phase.

Do not install `op`, add service-account authority to a container, alias a Saxo token
as an LLM/data key, create a token file, or change a running operator's allowlist.
There is still no generic `aihf-op-deliver --provider saxo` authority. The purpose
mapping is a proposed extension, not currently supported source behavior. The
application provider catalogs stay unchanged; OP-FR-007 still forbids values in
files or durable storage. A non-secret mapping alone grants no broker authority.

The supported alternative is host-only inspection from the same attended terminal
where 1Password authentication succeeds. Replace the placeholder with the exact
field reference supplied by the operator; no vault/item path is inferred:

```powershell
$env:SAXO_DEMO_ACCESS_TOKEN_REF = 'op://<vault>/<item>/<field>'
uv tool run --from poetry poetry run aihf saxo inspect --enable-network
```

This is an operator-run command, not executed as part of offline verification.
It resolves one real secret and makes read-only SIM GET requests when explicitly
run; it does not use either Docker operator or a fund root. The host shell must
not also configure any of the three Saxo OAuth references. Do not copy identity,
token or account output into public evidence.

The scope amendment is now recorded; remaining steps are parent review/comment
resolution, offline implementation/acceptance and a reviewed operational topology.
The consumer uses an existing eligible backend permission context without creating
or mutating a fund root for inspection. Memory-only generation pinning, expiry/
rejection/revoke/restart fences and explicit action consent are mandatory; no
refresh/write-back or broker mutation. A one-shot CLI process cannot consume the
backend lease merely through `docker exec`. File-backed delivery remains forbidden,
not an alternative implicitly permitted by this amendment.

## Fund deployment and execution status: BLOCKED

PR #8 adds explicit root selection and normal root write-admission controls. Those controls govern local fund files, but do not establish exclusive control of a Saxo SIM account. The separate `require_sim_account_ownership()` gate fails closed with `ownership-unknown` because account-wide custody cannot be verified; Saxo broker construction and SIM mutation are therefore unsupported. The TUI also denies paper writes on enrolled roots. Do not change `HOME`, edit root constants, or call internal deployment/run functions to get around either gate.

`aihf saxo inspect --enable-network` is the supported read-only Saxo SIM operation in this addendum. It does not initialize the shared user root, load root `.env` files, or create a fund. No fund was deployed, no runner was started or changed, and no Saxo order was placed. This task did not attempt fund creation or execution.

Unblocking requires a supported, verified account-wide SIM ownership/custody capability in addition to passing root write admission. Do not infer SIM mutation authorization from root admission alone.

## Timeouts and stop behavior

- Each Saxo HTTP request has a 15-second timeout.
- The existing SIM OAuth Saxo order-fill inspection is bounded by a 120-second deadline. The demo-token client rejects every non-GET request, so this deadline is not a demo-order capability or evidence of demo execution.
- The demo-token path does not refresh or assume a token lifetime. A rejected token is invalidated and fails closed without retry; update the referenced 1Password field through the authorized local workflow.
- Expiry/rejection during inspection stops the request without retry or SIM OAuth fallback. Demo execution, first-order confirmation, bounded-run shutdown, and interruption recovery remain blocked by the SIM ownership gate; do not infer those behaviors from the existing OAuth fill deadline.

## Offline validation

Use fake transports and synthetic roots only:

```text
poetry run pytest hedge_fund/brokers/test_saxo_tokens.py hedge_fund/brokers/test_factory.py hedge_fund/brokers/test_saxo_client.py hedge_fund/brokers/test_saxo_orders.py hedge_fund/fund/test_spec.py hedge_fund/fund/test_spec_broker.py hedge_fund/paper/test_deployed_broker.py hedge_fund/paper/test_saxo_e2e.py hedge_fund/secrets/test_saxo_secrets.py -q
poetry run pytest hedge_fund/test_run.py -k saxo -q
poetry run pytest hedge_fund/paper/test_runner.py -k saxo -q
poetry run pytest hedge_fund/tui/test_builder.py hedge_fund/tui/test_builder_broker.py -q
poetry run pytest hedge_fund/tui/test_paper_view.py -k minute_fund_rows_are_pure -q
poetry run pytest hedge_fund/tui/test_paper.py -k saxo -q
```

These selections verify token-source exclusivity/redaction, SIM-only behavior, account ambiguity, read-only inspection, invalid/expired-token failure, account binding, and fail-closed deployment/execution guards. Root admission is separate from Saxo account ownership; cash reconciliation, approval, first-order authorization, bounded-run stop, and interruption behavior remain blocked and are not inferred from these tests.

No test in this guide makes a network request, consumes paid data/model credits, reads the user's token value, or submits a demo order.
