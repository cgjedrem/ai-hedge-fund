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
| `account_key` | `str` | discovered via `GET /port/v1/accounts/me` — first active account with `LegalAssetTypes` including `Stock` and `Currency=USD`; no compatible account ⇒ startup error |

Methods: `positions()`, `balances()`, `search_instrument(ticker)` (→ `Identifier`/`Uic`, `ExchangeId`), `instrument_details(uic, asset_type)` (→ `IsTradable`, `LotSize`, `SupportedOrderTypes` — a distinct second call), `place_order(payload, request_id)`, `get_open_order(order_id)`, `transactions(since)`.

### TokenManager (new, same module)

| Field | Type | Notes |
|---|---|---|
| `access_token` | `str \| None` | current bearer token |
| `access_expires_at` | `float` | monotonic/fake-clock timestamp |
| `refresh_token_ref` | `str` | 1Password `op://` reference for the rotating refresh token |
| `refresh_margin_s` | `float` | refresh when remaining < margin (default 120 s) |

State machine: `UNAUTHENTICATED → AUTHORIZED → (refresh loop) → REAUTH_REQUIRED` on refresh failure; lock contention is retryable and preserves current state. On refresh: acquire the reference-keyed atomic lock directory → re-read the latest refresh token → POST `/token` → persist rotated token → release lock → expose access token. Interactive authorization holds the same lock across code exchange and token write-back. Cleanup failure after a successful refresh is logged with recoverable owner/path context and does not invalidate the persisted token. Default temp path coordinates only same-host processes. Host/container coordination requires both environments to mount and configure the same `SAXO_REFRESH_LOCK_DIR`; atomic directory creation required. A process crash can leave a stale lock; verify owner is inactive before manual removal.

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

Methods (protocol): `positions() -> dict[str, Position]`, `cash() -> float`, `place_order(Order) -> Fill`.

- `positions()`: `GET /port/v1/positions` with `ClientKey` and `AccountKey` → group by `NetPositionId`, map ticker from instrument lookup, signed `Amount` → shared model `Position(ticker, shares)`.
- `cash()`: `GET /port/v1/balances` with `ClientKey` and `AccountKey` → **`CashBalance`**. `CashAvailableForTrading` is used only for order affordability. Account and balance currency must be USD.
- `filter_orders()`: copy orders with quantities rounded down to lot multiples; drop below-lot dust. Cycle ledger records those adjusted orders. Pipeline revalidates projected position and gross limits after filtering, before any POST. `place_order()` returns a complete correlated `Fill` or raises for every submitted order.
- Post-filter risk gate rejects a position or gross-limit breach only when filtered exposure worsens the same metric versus the current book; de-risking orders may reduce an existing breach without reaching the cap.
- `place_order(order)`: validate universe → build payload (`Uic`, `AssetType: "Stock"`, `Amount` shares, `BuySell`, `OrderType: "Market"`, `DayOrder`, `ManualOrder: false`) → pacer wait → POST with unique `x-request-id` → **inspect body**: `ErrorInfo` present ⇒ `SaxoOrderError` (message includes Saxo's ErrorCode, e.g. `MarketClosed`, `InsufficientCash`); `OrderId` present ⇒ poll open-order until gone (deadline 120 s) → **read the order-correlated executed quantity/price from the execution/transaction records tied to that OrderId** (a position's `OpenPrice`/`Amount` describe the holding, not this execution: reductions keep the old acquisition cost, full exits leave no position row) → return complete `Fill(ticker, side, quantity, price)` or raise. **Never re-POSTs**; 409 ⇒ inspect state, raise if unresolved.

### Secret references (1Password item schema, `Saxo OpenAPI SIM` item)

| Field | op:// segment | Rotates? |
|---|---|---|
| App key | `Saxo OpenAPI SIM/app-key` | no |
| App secret | `Saxo OpenAPI SIM/app-secret` | no |
| Refresh token | `Saxo OpenAPI SIM/refresh-token` | **yes — written back after every refresh** |

`provider.py` resolves `op://` references via `op read`. For token write-back, fetch the item JSON template with `op item get --format=json --reveal`, update the referenced field, then pipe JSON to `op item edit`; token never appears in argv. Redirect URI and lock directory are non-secret config.

### FundSpec / DeployedFund / factory / TUI (modified + new)

| Component | Change |
|---|---|
| `fund/spec.py` `FundSpec` | `broker: Literal["paper", "saxo"] = "paper"`; paper YAML stays byte-identical; omitted Saxo costs default to zero, explicit costs honored; Saxo requires minute cadence and 09:30–15:59 ET window (omitted window defaults to that range) |
| `paper/deployed.py` `DeployedFund` | `broker: Literal["paper", "saxo"]` kept consistent with FundSpec; **saxo deployment skips `PaperBroker.create`** (no local broker.json book — the book is external) |
| `brokers/factory.py` (NEW) | `build_broker(deployed)` routes `"paper"` → `PaperBroker`, `"saxo"` → `SaxoBroker` with secrets resolved at construction; the continuous runner reuses one Saxo broker/token manager across sessions |
| `paper/tick.py` redo path | refuses non-paper brokers (ledger replay is only defined for the internal book) |
| `tui/builder.py` fund setup | broker selector (paper \| saxo) alongside the approval gate; summary line shows the choice |
| End-to-end test | selecting Saxo in the builder deploys a saxo fund and runs a session through the external adapter (fake transport) |

## Invariants

- **INV-1**: A `Fill` is returned only when order-correlated execution records show the fill; otherwise raise. No partial fills surfaced; position state alone never establishes a fill.
- **INV-2**: Refresh and interactive authorization exchange/write-back share a secret-reference lock. The newest refresh token is persisted before access-token use. Lock acquisition has a 90-second bound and reports sanitized owner context; contention remains retryable and never sets terminal re-auth state or steals locks. Cleanup failure after successful persistence is logged and leaves the token usable. Cross-container coordination exists only when `SAXO_REFRESH_LOCK_DIR` names the same atomic shared filesystem path.
- **INV-3**: Reused broker instances revalidate the fund universe each session; cached instrument details expire after 3600 seconds.
- **INV-3**: No secret value (app secret, tokens) ever appears in logs, exceptions, events, or the ledger — redaction at the client boundary.
- **INV-4**: Order POSTs are spaced ≥1 s and carry unique `x-request-id`s; an order whose outcome is unknown is never re-sent.
- **INV-5**: Existing paper funds serialize byte-identically; `saxo` funds are immutable after deploy.
- **INV-6**: `cash()` is USD accounting cash; account currency is checked at broker startup. No FX conversion.