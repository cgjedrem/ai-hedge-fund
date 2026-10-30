# Checklist: Saxo OpenAPI Broker Adapter — Requirements Coverage

**Feature**: 003-saxo-broker-adapter

## Requirement coverage

- [ ] FR-001 Broker protocol conformance (positions/cash/place_order, shared models) — US1/US2
- [ ] FR-002 SIM-only endpoints; live URLs absent from code/config — US1 (constants + test)
- [ ] FR-003 Fill-completely-or-raise; no partial fills, no silent drops — US2
- [ ] FR-004 Proactive token refresh; rotating single-use refresh token persisted after every refresh; cross-process coordination (lock keyed by secret reference + re-read latest token before each refresh) for concurrent fund runners; re-auth error on failure — Foundational/US3
- [ ] FR-005 Broker book authoritative; `cash()` = accounting CashBalance (NAV/reconciliation), CashAvailableForTrading separate for affordability; reconciliation refuses on mismatch — US1
- [ ] FR-005a Account currency must match fund base currency at startup; no FX conversion — US1
- [ ] FR-006 Universe validated via two-call resolution (search + details) before first order — US1
- [ ] FR-007 Secrets via 1Password op:// references resolved at startup — US3
- [ ] FR-008 Order pacer ≥1/s, unique x-request-id, no automatic re-POST — US2
- [ ] FR-009 No secret material in logs/errors/ledger/events — Foundational (redaction tests)
- [ ] FR-010 Per-fund broker selection, byte-compatible serialization — US4
- [ ] FR-011 Fill detection: poll-until-gone triggers inspection; order-correlated executed quantity/price from transaction/execution records (increase/reduction/full-exit correct), bounded deadline — US2
- [ ] FR-012 Quantity precision (LotSize from details call); fractional refusal over silent rounding — US2
- [ ] FR-013 yfinance remains the market-data path; no OpenAPI prices — by construction (no price calls)
- [ ] FR-014 Saxo mandates require in-market cadence; saxo + daily (00:05 NY turn) refused at validation — US4

## Edge cases covered

- [ ] Token expiry mid-session → proactive refresh; single refresh on 401; re-auth error
- [ ] Two fund runners share the 1Password item → cross-process lock + re-read latest token; loser of rotation race succeeds
- [ ] SIM account reset → reconciliation refuses; owner decides
- [ ] Market closed → SaxoOrderError with MarketClosed code surfaced; FR-014 keeps normal cadences in-market
- [ ] Instrument missing/untradable → session refuses pre-order
- [ ] Duplicate-order 409 window → inspect state, never re-POST
- [ ] Session capability collision → default OrdersOnly/Standard level only
- [ ] Currency mismatch (EUR account / USD mandate) → deployment refused, no silent conversion

## Success criteria mapping

- [ ] SC-1 deploy + reconcile (US1) · SC-2 orders + real simulated fills (US2) · SC-3 secret hygiene tests (US3) · SC-4 byte-identical paper funds (US4) · SC-5 suite green minus 6 baseline failures, network-free (Polish)