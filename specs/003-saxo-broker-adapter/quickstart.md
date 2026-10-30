# Quickstart: Saxo OpenAPI Broker Adapter (SIM)

**Feature**: 003-saxo-broker-adapter | **Date**: 2026-10-30

## Prerequisites (one-time, user-driven)

1. **Saxo SIM account** — self-service, no funding: https://developer.saxo/accounts/sim/signup
2. **OpenAPI app (SIM environment)** — on the Developer Portal app management page, register an app with trading permission **Personal: Write**; note the AppKey + AppSecret (SIM-scoped — a SIM app cannot reach the live gateway).
3. **1Password CLI** (`op`) installed and unlocked (desktop app integration or service-account token).
4. **1Password item** `Saxo OpenAPI SIM` with fields `app-key`, `app-secret`, `refresh-token` (leave `refresh-token` empty until first auth).

## Configuration

```powershell
# non-secret references (op:// pointers, not values)
$env:SAXO_APP_KEY_REF      = "op://<vault>/Saxo OpenAPI SIM/app-key"
$env:SAXO_APP_SECRET_REF   = "op://<vault>/Saxo OpenAPI SIM/app-secret"
$env:SAXO_REFRESH_TOKEN_REF= "op://<vault>/Saxo OpenAPI SIM/refresh-token"
$env:SAXO_REDIRECT_URI     = "http://localhost"   # must exactly match the redirect URI registered for the app
# Optional: set to one absolute host/container-shared mount path for shared refresh coordination.
$env:SAXO_REFRESH_LOCK_DIR = "C:\shared\saxo-refresh-locks"
```

Mandate currency convention is fixed USD. The account currency is checked when the broker starts; no FX conversion is attempted. Without `SAXO_REFRESH_LOCK_DIR`, locks coordinate only processes using the same host temp directory. Lock acquisition times out after 90 seconds and reports its recorded owner; contention is retryable. A crash can leave a stale lock directory. Verify its recorded host/PID is inactive before removing it; the adapter never steals a lock.

## First authentication (interactive, ~1 min)

```powershell
poetry run python -m hedge_fund.brokers.saxo_auth
# → opens sim.logonvalidation.net/authorize (auth-code + PKCE) in your browser
# → log in with SIM credentials and approve the app
# → paste the redirected callback URL when prompted
# → exchanges the code and stores the refresh token using an item JSON template on stdin
```

From here the adapter self-refreshes (~every 15 min) and rotates the refresh token in 1Password. Expect an interactive re-auth roughly weekly (Saxo has no unattended retail login; CBA is institutional-only).

After interactive re-authentication, restart any running fund process. Its existing token manager remains in `REAUTH_REQUIRED` until process restart.

## Deploy a Saxo fund

```powershell
poetry run aihf
# fund setup → broker: saxo
# (mandate yaml: broker: saxo)
```

**Cadence matters**: Saxo mandates require minute cadence within regular US market hours (09:30–15:59 ET). The 16:00 closing bar is excluded. Omitted Saxo windows default to 09:30–15:59; explicit windows outside those limits are refused by mandate validation and the setup wizard. The daily cadence turns at 00:05 New York, so Saxo mandates cannot use daily or other non-minute cadences. Paper window defaults remain unchanged.

## What you should see

- **Pre-session**: reconciliation reads account-scoped SIM positions (`/port/v1/positions` with `ClientKey` + `AccountKey`) and accounting cash (`/port/v1/balances` → `CashBalance`); balances and account must report USD. Mismatch refuses broker startup before trading.
- **Universe check**: every fund ticker resolves via the two-call flow (instruments search → instrument details) before the first order; unresolved or untradable tickers refuse the session.
- **Orders**: session decisions place market orders (`ManualOrder: false`); fills appear in the SIM account and the ledger records **Saxo's simulated execution price** for each order (order-correlated from the transaction/execution records — not a yfinance estimate, and not the position's average acquisition cost).
- **Costs**: omitted Saxo spread and commission default to zero; explicit mandate costs remain honored. Paper costs and serialization stay unchanged.
- **Sanity check**: compare each fill price against the yfinance price at trade time — SIM fills are simulated, so expect approximate (not exact) agreement.

## Known SIM limitations (expected, not bugs)

- **No live stock prices on SIM** (only FxSpot) — the engine keeps using yfinance for market data; OpenAPI price endpoints are unused.
- **Lot precision** comes from instrument details; below-lot rebalance dust is suppressed before submission. Each submitted order still requires a complete correlated fill.
- **Market-closed orders** are rejected synchronously (`MarketClosed` expected). The unattended Saxo runner does not carry a pending bar past 16:00 ET; manual or other off-schedule order attempts may still receive this error.
- **SIM resets** are self-service; after a reset, reconciliation reports the mismatch and refuses until you decide.
- **Token rotation**: if a run crashes between refresh and write-back (should not happen — write-back precedes use), re-run the auth command.

## Validation checklist

- [ ] `poetry run pytest hedge_fund/brokers hedge_fund/secrets hedge_fund/fund -q` green (network-free; chunked runs)
- [ ] Style gate: `black --check .`, `isort --check-only .`, `flake8`
- [ ] Existing paper fund deploys and runs byte-identically (no fund.yaml diff)
- [ ] SIM smoke test: one small market order placed + filled during an open market, fill price recorded in ledger
- [ ] No secret material in logs/ledger (grep for token prefixes after a session)