# Contract: T212 Broker Adapter

**Feature**: 003-t212-broker-adapter | **Date**: 2026-10-30

This is the contract the implementation must satisfy. It has three surfaces: the in-process Broker protocol, the outbound T212 REST surface, and the secrets interface.

## 1. In-process surface (must not change)

`T212Broker` satisfies `hedge_fund.brokers.protocol.Broker` (runtime-checkable):

```python
class T212Broker:  # structural — no inheritance required
    def positions(self) -> dict[str, Position]: ...
    def cash(self) -> float: ...
    def place_order(self, order: Order) -> Fill: ...
```

- `positions()`: keys are engine tickers (`AAPL`, not `AAPL_US_EQ`); `Position.shares` signed; a negative T212 Invest position raises (no shorts on Invest).
- `cash()`: available-to-trade cash as float; currency mismatch with the fund's expectation raises.
- `place_order()`: **fill completely and return a `Fill`, or raise.** No partial fills returned, no silent drops. `Fill.price` is the broker's actual average fill price; `Fill.quantity` is the actually-filled quantity (may differ from the order's after partial fills — the ledger records what really happened).
- Exceptions: adapter raises `T212Error` (subclass of the brokers' error type) with the HTTP status and response body verbatim in the message. Messages never contain credentials or `Authorization` headers.

## 2. Outbound REST surface (demo only)

Base URL constant: `https://demo.trading212.com/api/v0`. Auth: HTTP Basic (`api_key`, `api_secret`). All requests carry a timeout; all responses' `x-ratelimit-*` headers are honored.

| Call | Method & path | Request body | Success → mapping |
|------|---------------|--------------|-------------------|
| place market order | `POST /equity/orders/market` | `{"ticker": "AAPL_US_EQ", "quantity": 1.5, "extendedHours": false}` | 2xx + order object; poll to terminal |
| order status | `GET /equity/orders/{id}` | — | status enum; `FILLED` terminal |
| order history | `GET /equity/history/orders` | — | source of actual fill price/quantity/`filledAt` |
| positions | `GET /equity/positions` | — | `[{ticker, quantity, quantityAvailableForTrading, averagePricePaid, currentPrice}]` |
| account cash | `GET /equity/account/summary` | — | `cash.availableToTrade`, `currency` |
| instruments | `GET /equity/metadata/instruments` | — | tradable ticker set (cached ~1h) |

**Behavioral rules**:

1. Order POST is issued **at most once per logical attempt** (429-with-reset retry is the single exception). No blind retries on timeout/5xx — the beta API is non-idempotent.
2. Polling: `GET /equity/orders/{id}` no faster than 1 req/s, bounded by a 120s overall deadline, then raise with guidance to inspect pending orders.
3. Quantities: rounded to 4 decimals; sells round down (toward zero); a sell larger than `quantityAvailableForTrading` is refused locally before any HTTP call.
4. Ticker mapping: engine `AAPL` ⇄ T212 `AAPL_US_EQ`; universe validated against instruments before the first order of a session.
5. Terminal statuses: `FILLED`, `CANCELLED`, `REJECTED`, `REPLACED`. Pending: `LOCAL`, `UNCONFIRMED`, `CONFIRMED`, `NEW`, `CANCELLING`, `PARTIALLY_FILLED`.

## 3. Secrets interface

```python
hedge_fund.secrets.resolve_secret(raw: str) -> str
```

- `raw` starting with `op://` → resolved via `op read` (1Password CLI); failure raises `SecretResolutionError` with a message containing no secret material.
- Any other value → returned unchanged (plaintext passthrough).
- Credentials are read from `HEDGE_FUND_T212_API_KEY` / `HEDGE_FUND_T212_API_SECRET` at broker construction; missing/empty raises `SecretResolutionError` naming the variable.
- Invariants (tested): secrets never appear in exception messages, logs, ledger entries, events.jsonl, fund.yaml, or any persisted file; `op` is invoked only at construction, never per request.

## 4. Configuration surface

`fund.yaml` (mandate) gains one optional key:

```yaml
broker: t212        # optional, default "paper"; validated Literal["paper", "t212"]
```

- Deployed funds are immutable: the broker is fixed at deploy time.
- Serialization pops `broker` when it equals `"paper"` → existing fund.yaml files stay byte-identical.
- `redo` refuses funds with `broker != "paper"`.
- TUI fund detail and CLI status display the broker name.