# Data Model: Saxo OpenAPI Broker Adapter

**Feature**: 003-saxo-broker-adapter | **Date**: 2026-10-30

## Entities

### SaxoClient (new, `hedge_fund/brokers/saxo.py`)

Thin HTTP facade over the SIM OpenAPI. Owns the transport, token manager, and pacer.

| Field | Type | Notes |
|---|---|---|
| `transport` | `Transport` protocol | `request(method, url, headers, json) -> (status, body)`; real impl wraps `requests`, tests inject a fake |
| `base_url` | `str` | constant `https://gateway.saxobank.com/sim/openapi` |
| `auth_url` | `str` | constant `https://sim.logonvalidation.net` |
| `tokens` | `TokenManager` | access-token lifecycle + refresh-token rotation |
| `pacer` | `Pacer` | min-interval enforcement (orders ≥1.0 s), fake-clock friendly |
| `client_key` | `str` | discovered via `GET /port/v1/users/me` at startup |
| `account_key` | `str` | discovered via `GET /port/v1/accounts/me` — **first trading account whose `Currency` matches the fund's base currency**; no compatible account ⇒ startup error (no FX conversion in this feature) |

Methods: `positions()`, `balances()`, `search_instrument(ticker)` (→ `Identifier`/`Uic`, `ExchangeId`), `instrument_details(uic, asset_type)` (→ `IsTradable`, `LotSize`, `SupportedOrderTypes` — a distinct second call), `place_order(payload, request_id)`, `get_open_order(order_id)`, `transactions(since)`.

### TokenManager (new, same module)

| Field | Type | Notes |
|---|---|---|
| `access_token` | `str \| None` | current bearer token |
| `access_expires_at` | `float` | monotonic/fake-clock timestamp |
| `refresh_token_ref` | `str` | 1Password `op://` reference for the rotating refresh token |
| `refresh_margin_s` | `float` | refresh when remaining < margin (default 120 s) |

State machine: `UNAUTHENTICATED → AUTHORIZED → (refresh loop) → REAUTH_REQUIRED` (terminal until interactive re-auth). On refresh: **acquire the cross-process lock keyed by the secret reference → re-read the latest refresh token from 1Password → POST `/token` (grant_type=refresh_token) → immediately write the new refresh token back to 1Password → release lock → swap access token**. The re-read step means a process that lost a rotation race to another fund runner picks up the winner's token instead of presenting a spent one. Any refresh failure → `SaxoAuthError` with re-auth guidance; never retried in a loop. A test exercises two managers sharing one 1Password item.

### Pacer (new, same module)

| Field | Type | Notes |
|---|---|---|
| `min_interval_s` | `dict[str, float]` | per-endpoint-class minimum spacing (`orders`: 1.0) |
| `last_call_at` | `dict[str, float]` | fake-clock timestamps |

`wait_for(endpoint_class, now)` sleeps the remainder (no-op in tests with a fake clock).

### SaxoBroker (new, implements `Broker` protocol)

| Field | Type | Notes |
|---|---|---|
| `client` | `SaxoClient` | shared HTTP/token/pacer stack |
| `uic_cache` | `dict[str, tuple[int, str]]` | ticker → (Uic, AssetType), ~1 h TTL |
| `universe_validated` | `bool` | set after FR-006 pre-session validation |

Methods (protocol): `positions() -> dict[str, Position]`, `cash() -> float`, `place_order(Order) -> Fill`.

- `positions()`: `GET /port/v1/positions/me` → group by `NetPositionId`, map ticker from instrument lookup, `Amount` signed (long +) → shared model `Position(ticker, shares)`; `OpenPrice`/`CurrentPrice` stay internal metadata (the shared model has no cost field).
- `cash()`: `GET /port/v1/balances/me` → **`CashBalance`** (accounting cash — this is what NAV/equity and ledger reconciliation consume). `CashAvailableForTrading` (buying power) is read separately and used only for order affordability checks, never returned from `cash()`.
- `place_order(order)`: validate universe → build payload (`Uic`, `AssetType: "Stock"`, `Amount` shares, `BuySell`, `OrderType: "Market"`, `DayOrder`, `ManualOrder: false`) → pacer wait → POST with unique `x-request-id` → **inspect body**: `ErrorInfo` present ⇒ `SaxoOrderError` (message includes Saxo's ErrorCode, e.g. `MarketClosed`, `InsufficientCash`); `OrderId` present ⇒ poll open-order until gone (deadline 120 s) → **read the order-correlated executed quantity/price from the execution/transaction records tied to that OrderId** (a position's `OpenPrice`/`Amount` describe the holding, not this execution: reductions keep the old acquisition cost, full exits leave no position row) → return complete `Fill(ticker, side, quantity, price)` or raise. **Never re-POSTs**; 409 ⇒ inspect state, raise if unresolved.

### Secret references (1Password item schema, `Saxo OpenAPI SIM` item)

| Field | op:// segment | Rotates? |
|---|---|---|
| App key | `Saxo OpenAPI SIM/app-key` | no |
| App secret | `Saxo OpenAPI SIM/app-secret` | no |
| Refresh token | `Saxo OpenAPI SIM/refresh-token` | **yes — written back after every refresh** |

**The `hedge_fund/secrets/` package does not exist yet** — this feature creates it (test-first): `provider.py` resolves `op://` references via `op read` (missing reference ⇒ error naming the variable, never the value; failures sanitized) and adds write-back via `op item edit` for the rotating refresh token. Redirect URI for the interactive auth-code step is non-secret config (env var).

### FundSpec / DeployedFund / factory / TUI (modified + new)

| Component | Change |
|---|---|
| `fund/spec.py` `FundSpec` | `broker: Literal["paper", "saxo"] = "paper"`, popped when equal to default (same pattern as `approval_required`) — existing fund.yaml stays byte-identical; **saxo mandates with a daily cadence refused** (00:05 NY turn is market-closed) |
| `paper/deployed.py` `DeployedFund` | `broker: Literal["paper", "saxo"]` kept consistent with FundSpec; **saxo deployment skips `PaperBroker.create`** (no local broker.json book — the book is external) |
| `brokers/factory.py` (NEW) | `build_broker(deployed)` routes `"paper"` → `PaperBroker`, `"saxo"` → `SaxoBroker` with secrets resolved at construction; `paper/tick.py` (line ~283) and the runner construct brokers **only** through this factory |
| `paper/tick.py` redo path | refuses non-paper brokers (ledger replay is only defined for the internal book) |
| `tui/builder.py` fund setup | broker selector (paper \| saxo) alongside the approval gate; summary line shows the choice |
| End-to-end test | selecting Saxo in the builder deploys a saxo fund and runs a session through the external adapter (fake transport) |

## Invariants

- **INV-1**: A `Fill` is returned only when order-correlated execution records show the fill; otherwise raise. No partial fills surfaced; position state alone never establishes a fill.
- **INV-2**: The newest refresh token is persisted to 1Password before any request uses the new access token, under a cross-process lock keyed by the secret reference, with the latest token re-read before every refresh attempt.
- **INV-3**: No secret value (app secret, tokens) ever appears in logs, exceptions, events, or the ledger — redaction at the client boundary.
- **INV-4**: Order POSTs are spaced ≥1 s and carry unique `x-request-id`s; an order whose outcome is unknown is never re-sent.
- **INV-5**: Existing paper funds serialize byte-identically; `saxo` funds are immutable after deploy.
- **INV-6**: `cash()` is same-currency accounting cash; the account currency must match the fund's base currency or deployment is refused.