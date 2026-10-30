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
| `account_key` | `str` | discovered via `GET /port/v1/accounts/me` (first trading account) |

Methods: `positions()`, `balances()`, `search_instrument(ticker)`, `place_order(payload, request_id)`, `get_open_order(order_id)`, `transactions(since)`.

### TokenManager (new, same module)

| Field | Type | Notes |
|---|---|---|
| `access_token` | `str \| None` | current bearer token |
| `access_expires_at` | `float` | monotonic/fake-clock timestamp |
| `refresh_token_ref` | `str` | 1Password `op://` reference for the rotating refresh token |
| `refresh_margin_s` | `float` | refresh when remaining < margin (default 120 s) |

State machine: `UNAUTHENTICATED → AUTHORIZED → (refresh loop) → REAUTH_REQUIRED` (terminal until interactive re-auth). On refresh: POST `/token` (grant_type=refresh_token) → **immediately write the new refresh token back to 1Password** → swap access token. Any refresh failure → `SaxoAuthError` with re-auth guidance; never retried in a loop.

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

- `positions()`: `GET /port/v1/positions/me` → group by `NetPositionId`, map ticker from instrument lookup, `Amount` signed (long +), `OpenPrice` avg cost.
- `cash()`: `GET /port/v1/balances/me` → `CashAvailableForTrading` (buying power, not raw `CashBalance`).
- `place_order(order)`: validate universe → build payload (`Uic`, `AssetType: "Stock"`, `Amount` shares, `BuySell`, `OrderType: "Market"`, `DayOrder`, `ManualOrder: false`) → pacer wait → POST with unique `x-request-id` → **inspect body**: `ErrorInfo` present ⇒ `SaxoOrderError` (message includes Saxo's ErrorCode, e.g. `MarketClosed`, `InsufficientCash`); `OrderId` present ⇒ poll open-order until gone (deadline 120 s) → read fill from position delta / transactions → return complete `Fill` (price = Saxo's simulated fill, quantity = filled shares) or raise. **Never re-POSTs**; 409 ⇒ inspect state, raise if unresolved.

### Secret references (1Password item schema, `Saxo OpenAPI SIM` item)

| Field | op:// segment | Rotates? |
|---|---|---|
| App key | `Saxo OpenAPI SIM/app-key` | no |
| App secret | `Saxo OpenAPI SIM/app-secret` | no |
| Refresh token | `Saxo OpenAPI SIM/refresh-token` | **yes — written back after every refresh** |

Resolution via existing `secrets/provider.py` (`op read`); write-back via `op item edit` (new capability). Redirect URI for the interactive auth-code step is non-secret config (env var).

### FundSpec (modified, `hedge_fund/fund/spec.py`)

| Field | Type | Default | Serialization |
|---|---|---|---|
| `broker` | `Literal["paper", "saxo"]` | `"paper"` | popped when equal to default (same pattern as `approval_required`) — existing fund.yaml stays byte-identical |

### Factory (modified, `hedge_fund/paper/deployed.py`)

`build_broker(spec)` gains `"saxo"` → constructs `SaxoBroker(SaxoClient(...))` with secrets resolved at startup; missing/invalid secrets raise a named-variable error before any trading. `redo` restore path in `paper/tick.py` refuses non-paper brokers (ledger replay is only defined for the internal book).

## Invariants

- **INV-1**: A `Fill` is returned only when Saxo's own records show the fill; otherwise raise. No partial fills surfaced.
- **INV-2**: The newest refresh token is persisted to 1Password before any request uses the new access token.
- **INV-3**: No secret value (app secret, tokens) ever appears in logs, exceptions, events, or the ledger — redaction at the client boundary.
- **INV-4**: Order POSTs are spaced ≥1 s and carry unique `x-request-id`s; an order whose outcome is unknown is never re-sent.
- **INV-5**: Existing paper funds serialize byte-identically; `saxo` funds are immutable after deploy.