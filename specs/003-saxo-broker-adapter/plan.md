# Plan: Saxo OpenAPI Broker Adapter (SIM)

**Feature**: 003-saxo-broker-adapter | **Branch**: `003-saxo-broker-adapter` | **Date**: 2026-10-30

## Summary

Add a second broker backend for deployed paper funds: Saxo Bank OpenAPI against the **SIM** environment. The adapter implements the existing `Broker` protocol (`positions()`, `cash()`, `place_order()`), authenticates via OAuth2 with 1Password-stored rotating refresh tokens, places market orders with real SIM fills, and keeps the external broker's book authoritative for reconciliation. Broker selection is a per-fund mandate field, byte-compatible with existing funds.

## Technical Context

**Language/Version**: Python 3.12 (Poetry-managed)
**Primary Dependencies**: `requests ^2.32.0` (already present — no new packages), `pydantic` (models), `rich`/`textual` (TUI display only)
**Storage**: existing ledger + broker book files unchanged; OAuth token state lives in 1Password (rotating refresh token), never on disk
**Testing**: pytest, network-free (fake transport + fake clock); 6 documented Windows baseline failures elsewhere are unrelated
**Target Platform**: Windows host + Docker (watchtower); Python only
**Project Type**: single package (`hedge_fund`), library + TUI

## Constitution Check

- **I. Ledger integrity**: fills are recorded only after Saxo confirms them (order leaves open orders + position/transaction read); reconciliation keeps the broker book authoritative; never-overshoot-cash enforced against `CashAvailableForTrading`. PASS.
- **II. Paper only**: SIM endpoints hardcoded; live gateway/auth URLs never appear in code or config; all tests network-free. PASS.
- **III. Test-First**: every task lists its test first; co-located tests. PASS.
- **IV. Determinism**: fake clock for pacer/token refresher; fixture-driven fake transport; no wall-clock or network in tests. PASS.
- **V. Mandate/CLI/TUI consistency**: `broker` field appears in mandate validation, deploy CLI, and TUI status. PASS.
- **VI. Style**: black (line-length 420), isort (black profile), flake8; files written UTF-8 **without BOM**. PASS.

## Project Structure

```text
hedge_fund/
  brokers/
    protocol.py          # existing Broker protocol (unchanged)
    models.py            # existing Order/Fill/Position (unchanged: Position(ticker, shares), Fill(ticker, side, quantity, price))
    paper.py             # existing PaperBroker (unchanged)
    saxo.py              # NEW: SaxoBroker (protocol impl) + SaxoClient (HTTP) + token manager + pacer
    saxo_auth.py         # NEW: interactive auth-code+PKCE helper for first login
    factory.py           # NEW: build_broker(spec) routing paper|saxo (tick/runner construct via this)
  secrets/
    __init__.py          # NEW: package does not exist yet — created by this feature
    provider.py          # NEW: 1Password op:// resolution (op read) + write-back (op item edit) for rotating tokens
  paper/
    deployed.py          # MODIFIED: DeployedFund.broker Literal["paper","saxo"]; saxo deployment skips local paper book
    tick.py              # MODIFIED: broker construction routed through factory; redo refuses non-paper brokers
  fund/
    spec.py              # MODIFIED: FundSpec.broker Literal["paper","saxo"]="paper", popped-on-default; cadence validation for saxo
  tui/
    builder.py           # MODIFIED: fund-setup broker selector (paper|saxo) alongside approval gate
specs/003-saxo-broker-adapter/
  tests/ (co-located under hedge_fund/brokers/test_saxo*.py, hedge_fund/secrets/test_*.py etc.)
```

**Key decisions** (from research.md):
- R1 `requests`-only thin client; no SDK.
- R2 SIM-only endpoints; live URLs absent by construction.
- R3 OAuth2 auth-code + PKCE; proactive ~15 min refresh; single-use rotating refresh token persisted to 1Password after every refresh; **cross-process refresh coordination** (lock keyed by secret reference + re-read latest token before each refresh) because fund runners are separate processes; refresh failure → clear re-auth error, no retry loop.
- R5 Market orders, `ManualOrder: false`, unique `x-request-id`; HTTP 200 with `ErrorInfo` = failure.
- R6 Fill detection: poll open-order until gone → **order-correlated executed quantity/price** from execution/transaction records (correct for increases, reductions, full exits); bounded deadline.
- R7 Pacer ≥1 order/s; 409 on duplicate window → inspect state, never re-POST.
- R8 Universe validation via **two calls** (instruments search → details) before first order.
- R9 `cash()` = accounting `CashBalance` (NAV/reconciliation); `CashAvailableForTrading` separate for affordability; account currency must match fund base currency.
- R11 No OpenAPI prices; yfinance stays the data path.
- R12 Default session capabilities (`OrdersOnly`/`Standard`) — never demote the user's own SaxoTraderGO session.
- R14 `broker` mandate field with popped-on-default serialization; **saxo mandates require an in-market cadence** (daily 00:05 NY turn is refused).

## Implementation Phases

1. **Foundational**: secrets package creation (test-first `op read` resolution + sanitized failures + `op item edit` write-back), `SaxoClient` transport abstraction (fake-able), token manager (refresh + rotation write-back + cross-process coordination), pacer, error taxonomy (`SaxoAuthError`, `SaxoOrderError`, `SaxoReconcileError`).
2. **US1 book reads**: positions/cash/account discovery with currency validation, UIC resolution (search + details) + universe validation, reconciliation integration.
3. **US2 order execution**: place market order, 200-with-ErrorInfo handling, order-correlated fill detection loop, `Fill` construction, pacer + `x-request-id`, no-re-POST rule.
4. **US3 secrets**: 1Password item schema (Saxo app credentials + refresh token field), write-back, redaction guarantees (logs/errors/ledger).
5. **US4 mandate config + routing**: `FundSpec.broker` + cadence validation, `DeployedFund.broker` consistency, saxo deployment (no local paper book), `brokers/factory.py` + tick/runner routing, TUI fund-setup broker selector, end-to-end test (select Saxo → deploy → run session through the external adapter).
6. **Polish**: quickstart smoke test doc, style gate, full chunked pytest.

## Risks & Mitigations

- **SIM quirks** (instrument-specific lot size, market-closed behavior, transaction feed latency): fixture-driven handling uses details `LotSize`, rounds order quantities down, and refuses untradable instruments (FR-012, FR-011 deadline).
- **Token rotation loss** (crash between refresh and write-back): write-back happens immediately after refresh, before the token is used; worst case the user re-authenticates interactively.
- **Byte-compat regression**: popped-on-default serialization + golden-file test for existing fund.yaml.

## Validation

- `poetry run pytest hedge_fund/brokers hedge_fund/secrets hedge_fund/fund -q` (chunked; network-free)
- Style gate: `black --check`, `isort --check-only`, `flake8`
- Manual SIM smoke test per quickstart.md (user-driven, not CI)