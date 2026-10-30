# Quickstart: Validating the T212 Broker Adapter

**Feature**: 003-t212-broker-adapter

Two validation layers: (A) offline tests — no network, no credentials, run anywhere; (B) a manual demo smoke test against the user's T212 demo account.

## A. Offline validation (CI-grade)

Prerequisites: `poetry install` (no extras needed beyond the existing environment).

```powershell
# adapter + secrets + wiring tests (network-free by design)
poetry run pytest hedge_fund/brokers/test_t212.py hedge_fund/secrets -q

# full suite must stay green apart from the 6 documented Windows baseline failures
poetry run pytest hedge_fund -q
```

Expected outcomes:

- `test_t212.py`: order placement → poll → fill mapping; rejection and timeout paths; 429 handling; quantity rounding (4dp, sell-down); ticker mapping and universe refusal; demo-only base URL assertion; no-secret-in-errors assertions.
- `hedge_fund/secrets`: `op://` resolution via a stubbed `op` subprocess; plaintext passthrough; missing-variable error; no secret material in messages.
- Wiring: `FundSpec` accepts `broker: t212`, pops the default on serialization (byte-compat), factory builds the right broker, redo refuses t212 funds, TUI/status show the broker name.

## B. Manual demo smoke test (user in the loop)

Prerequisites (user-side, one-time):

1. T212 **demo** account (Invest product) — done.
2. Demo API credentials: T212 app → Settings → API (Beta) → generate; the secret is shown once.
3. Store in 1Password item `T212` with fields `api_key` and `api_secret`.
4. 1Password CLI (`op`) installed and signed in — desktop unlock for host runs; `OP_SERVICE_ACCOUNT_TOKEN` set for Docker runs.

Then set (PowerShell, host):

```powershell
$env:HEDGE_FUND_T212_API_KEY   = "op://<vault>/T212/api_key"
$env:HEDGE_FUND_T212_API_SECRET = "op://<vault>/T212/api_secret"
```

Deploy a tiny probe fund (mandate with `broker: t212`, 1 ticker, small capital, manual cadence) and run one session:

```powershell
poetry run aihf    # TUI → deploy fund → run session (watch it)
```

Pass criteria:

- Startup resolves credentials via `op` (no plaintext anywhere).
- Pre-session reconciliation reports the demo account's real positions/cash.
- The session's order appears in the T212 demo app (History → Orders) with a matching ticker/quantity.
- The ledger records the fill with the broker's actual price; NAV reflects it.
- A deliberately bad ticker in the universe → session refuses before any order.
- `redo` on the t212 fund → refused with a clear message.

## Failure modes to watch (from research)

- 401 → wrong environment's key (demo key required) or malformed Basic auth.
- 403 `Scope( X ) missing for API key` → regenerate the key with `orders:execute` + `portfolio` + `account` + `metadata` scopes.
- 429 → pacer should prevent; if seen, note the endpoint and reset header.
- `quantity-precision-mismatch` → quantity had >4 decimals (adapter should prevent; report if seen).
- `SellingEquityNotOwned` → sell exceeded `quantityAvailableForTrading` (pies/pending orders lock shares).