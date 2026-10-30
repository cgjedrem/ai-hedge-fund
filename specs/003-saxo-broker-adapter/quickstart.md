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
$env:SAXO_REDIRECT_URI     = "http://localhost:port"   # registered redirect (no explicit port in URI per Saxo rules)
```

## First authentication (interactive, ~1 min)

```powershell
poetry run python -m hedge_fund.brokers.saxo_auth
# → opens sim.logonvalidation.net/authorize (auth-code + PKCE) in your browser
# → logs in with SIM credentials, approves the app
# → exchanges the code, stores the refresh token into the 1Password item
```

From here the adapter self-refreshes (~every 15 min) and rotates the refresh token in 1Password. Expect an interactive re-auth roughly weekly (Saxo has no unattended retail login; CBA is institutional-only).

## Deploy a Saxo fund

```powershell
poetry run aihf
# fund setup → broker: saxo
# (mandate yaml: broker: saxo)
```

**Cadence matters**: Saxo orders only fill while the market is open, but the daily cadence's turn is 00:05 New York (when daily funds look for yesterday's close) — the market is closed then. Saxo mandates therefore require an **in-market intraday cadence** (e.g. hourly during regular trading hours); deploy validation refuses `saxo` + daily with guidance.

## What you should see

- **Pre-session**: reconciliation reads SIM positions (`/port/v1/positions/me`) and the accounting cash balance (`/port/v1/balances/me` → `CashBalance`); a fresh SIM account shows empty positions and the simulated cash. The account's currency must match the fund's base currency — deployment is refused otherwise (no FX conversion).
- **Universe check**: every fund ticker resolves via the two-call flow (instruments search → instrument details) before the first order; unresolved or untradable tickers refuse the session.
- **Orders**: session decisions place market orders (`ManualOrder: false`); fills appear in the SIM account and the ledger records **Saxo's simulated execution price** for each order (order-correlated from the transaction/execution records — not a yfinance estimate, and not the position's average acquisition cost).
- **Sanity check**: compare each fill price against the yfinance price at trade time — SIM fills are simulated, so expect approximate (not exact) agreement.

## Known SIM limitations (expected, not bugs)

- **No live stock prices on SIM** (only FxSpot) — the engine keeps using yfinance for market data; OpenAPI price endpoints are unused.
- **Fractional shares unverified** for US stocks on SIM — if a fractional order is rejected, the adapter refuses rather than rounding exposure (FR-012).
- **Market-closed orders** are rejected synchronously (`MarketClosed` expected) — sessions run at/after close will see this.
- **SIM resets** are self-service; after a reset, reconciliation reports the mismatch and refuses until you decide.
- **Token rotation**: if a run crashes between refresh and write-back (should not happen — write-back precedes use), re-run the auth command.

## Validation checklist

- [ ] `poetry run pytest hedge_fund/brokers hedge_fund/secrets hedge_fund/fund -q` green (network-free; chunked runs)
- [ ] Style gate: `black --check .`, `isort --check-only .`, `flake8`
- [ ] Existing paper fund deploys and runs byte-identically (no fund.yaml diff)
- [ ] SIM smoke test: one small market order placed + filled during an open market, fill price recorded in ledger
- [ ] No secret material in logs/ledger (grep for token prefixes after a session)