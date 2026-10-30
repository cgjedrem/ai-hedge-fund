# Data Model: Trading 212 Broker Adapter

**Feature**: 003-t212-broker-adapter | **Date**: 2026-10-30

## Entities

### 1. `T212Broker` (new, `hedge_fund/brokers/t212.py`)

Satisfies the existing `Broker` protocol structurally (no inheritance from SimBroker — it is not a simulation).

| Field | Type | Notes |
|-------|------|-------|
| `_client` | `T212Client` | HTTP layer (requests.Session + auth + pacer) |
| `_universe` | `frozenset[str]` | engine tickers this fund may trade; validated against instruments before first order |

**Protocol methods** (contract identical to `protocol.py`):

- `positions() -> dict[str, Position]` — from `GET /equity/positions`; ticker unmapped (`AAPL_US_EQ` → `AAPL`); shares signed (T212 Invest has no shorts; negative would indicate data corruption and raises).
- `cash() -> float` — `GET /equity/account/summary` → `cash.availableToTrade` (converted to engine float; currency asserted to match the fund's expected currency).
- `place_order(order: Order) -> Fill` — market order; polls to terminal state; returns a complete `Fill` with the broker's actual price/quantity or raises. Never returns a partial fill.

**State machine per order**:

```text
place_order
  ├─ validate universe + round quantity (4dp; sells round down)
  ├─ POST /equity/orders/market  (once — never blind-retried)
  │    ├─ 2xx → order id; status in {LOCAL, UNCONFIRMED, CONFIRMED, NEW, CANCELLING, PARTIALLY_FILLED}
  │    │    └─ poll GET /equity/orders/{id} (>=1s apart, bounded 120s)
  │    │         ├─ FILLED            → fetch fill from history → return Fill(actual price, actual qty)
  │    │         ├─ REJECTED/CANCELLED→ raise BrokerError(body verbatim)
  │    │         └─ timeout           → raise BrokerError("order still pending; inspect before retrying")
  │    ├─ 429 → sleep until x-ratelimit-reset, retry POST once (still a single logical attempt)
  │    └─ other 4xx/5xx → raise BrokerError(status + body verbatim)
```

### 2. `T212Client` (new, same module)

Thin `requests`-based client. Owns: Basic auth, base URL constant (`https://demo.trading212.com/api/v0`), per-endpoint pacing, 429 handling, JSON decoding, and error normalization (branch on HTTP status; bodies vary — RFC7807 / `{code, clarification}` / `{code, message}`).

| Endpoint | Used for | Pacing (min interval) |
|----------|----------|----------------------|
| `POST /equity/orders/market` | place_order | 1.2s (limit 50/min) |
| `GET /equity/orders/{id}` | fill polling | 1.05s (limit 1/s) |
| `GET /equity/positions` | positions() | 1.05s (limit 1/s) |
| `GET /equity/account/summary` | cash() | 5.05s (limit 1/5s) |
| `GET /equity/metadata/instruments` | universe validation | 50s + ~1h in-memory cache |

### 3. Secret resolution (new, `hedge_fund/secrets/__init__.py`)

```text
resolve_secret(raw: str) -> str
  ├─ raw startswith "op://" → subprocess `op read <raw>` (stdout captured; stderr suppressed)
  │    ├─ exit 0 → stripped stdout
  │    └─ else   → SecretResolutionError (message contains NO secret material)
  └─ otherwise → raw unchanged (plaintext passthrough)
```

Env vars: `HEDGE_FUND_T212_API_KEY`, `HEDGE_FUND_T212_API_SECRET`. Missing/empty → `SecretResolutionError` naming the variable (never the value). Secrets are held only in memory; never logged, never written to ledger/events/fund.yaml/broker files.

### 4. `FundSpec` change (`hedge_fund/fund/spec.py`)

| Field | Type | Default | Serialization |
|-------|------|---------|---------------|
| `broker` | `Literal["paper", "t212"]` | `"paper"` | **popped when equal to default** (byte-compat with existing deployed fund.yaml, same pattern as `approval_required`) |

### 5. Broker factory (changed, `hedge_fund/paper/deployed.py`)

```text
build_broker(deployed) -> Broker
  ├─ spec.broker == "paper" → PaperBroker(directory/BROKER_FILE, spec.costs)   (unchanged behavior)
  └─ spec.broker == "t212"  → T212Broker(resolve creds, universe=spec.universe, costs=spec.costs)
```

`tick.py` uses the factory for the session path. The **redo path refuses** any broker other than `paper` (R9): a redo cannot restore a book that lives at an external broker.

## Relationships

- `FundSpec.broker` → selects the broker implementation at tick time; deployed funds are immutable, so a fund's broker never changes after deploy (deploy a new fund to switch).
- `T212Broker` → consumes `Order`/returns `Fill`/reports `Position` — the exact models in `brokers/models.py`, unchanged.
- Ledger → records T212 `Fill`s exactly like SimBroker fills (hash-chained, replayable); the only difference is the fill price is the broker's actual price.
- `broker.json` → **not created** for t212 funds; the external book replaces it.

## Validation rules (from spec FRs)

- FR-002: live URL unreachable — enforced by constant, plus a test asserting the client's base URL is the demo host.
- FR-003: T212Broker passes a structural `isinstance(x, Broker)` check (runtime_checkable protocol).
- FR-005: pre-session reconciliation unchanged; mismatch → refuse session (existing behavior, now sourced from the API).
- FR-006: untradable/missing ticker in universe → refuse before first order.
- FR-007/FR-009: `op://` resolution; secrets never in logs/files (tests assert error messages and log output contain no secret material).
- FR-010: `broker` validated by pydantic Literal; unknown value → FundSpec validation error at load.
- Quantity: >4dp input → rounded (4dp); sell rounding is downward; zero/negative effective quantity after rounding → refuse the order.