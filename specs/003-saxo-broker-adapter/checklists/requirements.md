# Checklist: Saxo OpenAPI Broker Adapter — Requirements Coverage

**Feature**: 003-saxo-broker-adapter

## Requirement coverage

- [ ] FR-001 Broker protocol conformance (positions/cash/place_order, shared models) — US1/US2
- [ ] FR-002 SIM-only endpoints; live URLs absent from code/config — US1 (constants + test)
- [ ] FR-003 Fill-completely-or-raise; no partial fills, no silent drops — US2
- [ ] FR-004 Proactive token refresh; rotating single-use refresh token persisted after every refresh; re-auth error on failure — Foundational/US3
- [ ] FR-005 Broker book authoritative; reconciliation refuses on mismatch — US1
- [ ] FR-006 Universe validated against instruments search before first order — US1
- [ ] FR-007 Secrets via 1Password op:// references resolved at startup — US3
- [ ] FR-008 Order pacer ≥1/s, unique x-request-id, no automatic re-POST — US2
- [ ] FR-009 No secret material in logs/errors/ledger/events — Foundational (redaction tests)
- [ ] FR-010 Per-fund broker selection, byte-compatible serialization — US4
- [ ] FR-011 Fill detection: poll-until-gone + position/transaction read, bounded deadline — US2
- [ ] FR-012 Quantity precision (LotSize); fractional refusal over silent rounding — US2
- [ ] FR-013 yfinance remains the market-data path; no OpenAPI prices — by construction (no price calls)

## Edge cases covered

- [ ] Token expiry mid-session → proactive refresh; single refresh on 401; re-auth error
- [ ] SIM account reset → reconciliation refuses; owner decides
- [ ] Market closed → SaxoOrderError with MarketClosed code surfaced
- [ ] Instrument missing/untradable → session refuses pre-order
- [ ] Duplicate-order 409 window → inspect state, never re-POST
- [ ] Session capability collision → default OrdersOnly/Standard level only

## Success criteria mapping

- [ ] SC-1 deploy + reconcile (US1) · SC-2 orders + real simulated fills (US2) · SC-3 secret hygiene tests (US3) · SC-4 byte-identical paper funds (US4) · SC-5 suite green minus 6 baseline failures, network-free (Polish)