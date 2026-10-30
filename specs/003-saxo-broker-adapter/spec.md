# Feature Specification: Trading 212 Broker Adapter

**Feature Branch**: `cgjedrem-legendary-umbrella` (app-managed worktree; branch creation skipped, numbering applied — feature 003)

**Created**: 2026-10-30

**Status**: Draft

**Input**: User description: "Spec T212 broker adapter and also usage of 1Password to get creds. I will create a demo account meanwhile."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect a fund to the T212 demo account (Priority: P1)

A fund owner with a Trading 212 demo account configures a fund to use T212 as its execution broker. On the first run, the engine reads the demo account's actual cash and holdings and presents them as the fund's book — the fund now trades against a real broker's books instead of a local simulation.

**Why this priority**: Nothing else works until the connection is verified and the book is correct. A wrong book poisons every downstream decision and fill.

**Independent Test**: Can be fully tested by selecting the T212 broker for a fund with valid credentials and running a status check — the engine displays the same cash and positions the T212 demo app shows.

**Acceptance Scenarios**:

1. **Given** valid T212 demo credentials resolvable through the user's 1Password vault, **When** the user selects the T212 broker for a fund and runs a status check, **Then** the engine displays cash and holdings identical to what the T212 demo account reports.
2. **Given** the demo account holds a position (including a fractional-share position) in a ticker the fund trades, **When** the engine reads the book, **Then** the reported share count matches T212's quantity exactly.
3. **Given** credentials are missing, malformed, or rejected, **When** the engine starts, **Then** it fails with a clear, actionable error naming the unresolved credential — and never begins trading.

---

### User Story 2 - Execute a session's orders in the demo account (Priority: P2)

When a paper session runs with the T212 broker, each order from the session's decision is placed as a real order in the T212 demo account. The engine waits for each order to reach a final state and records the actual execution price and quantity in the ledger.

**Why this priority**: This is the core value — fills come from a real venue, so returns tracking reflects real execution, not simulation.

**Independent Test**: Can be fully tested by running one session against the demo account — every order appears in T212's order history and the ledger's fills match T212's execution reports exactly.

**Acceptance Scenarios**:

1. **Given** a pending decision, **When** the session executes with the T212 broker, **Then** every order appears in the T212 demo order history with matching side and quantity.
2. **Given** an order fills at a price different from the engine's reference price, **When** the fill is recorded, **Then** the ledger carries T212's actual fill price.
3. **Given** an order that cannot complete (rejected, expired, or timed out), **When** the engine encounters it, **Then** the engine raises, halts the session safely, and the book is not updated for that order — no silent drops.
4. **Given** a fractional-share order (the engine sizes fractional), **When** it is placed, **Then** T212 accepts it and the fill quantity matches the order.

---

### User Story 3 - Credentials from 1Password, never plaintext (Priority: P2)

The fund owner stores the T212 API key and secret in their 1Password vault and places only secret references in the engine's configuration. The engine resolves the references through the 1Password command-line interface at startup. Secret material never appears in configuration files on disk, in logs, or in ledgers.

**Why this priority**: Security hygiene that must be in place before the adapter is trusted with an account; independent of the trading flow itself.

**Independent Test**: Can be fully tested by placing secret references in configuration, running the engine, and confirming it authenticates — then searching every log, config file, and ledger for the secret values and finding nothing.

**Acceptance Scenarios**:

1. **Given** a secret reference in the engine's configuration, **When** the engine resolves credentials at startup, **Then** it authenticates successfully without the plaintext secret ever being written to a project or deployment file.
2. **Given** the 1Password CLI is unavailable, locked, or unauthorized, **When** the engine tries to resolve a reference, **Then** it fails with clear guidance and does not proceed to trade.
3. **Given** any log output or persisted record from a full session, **When** inspected, **Then** no secret material is present.

---

### User Story 4 - Broker choice is fund configuration (Priority: P3)

The owner chooses the execution broker per fund in the fund's mandate — the built-in paper book or the T212 demo adapter — validated like every other mandate setting. The fund's status and detail surfaces show which broker a fund uses.

**Why this priority**: Consistency with how every other fund setting works, and required to run both kinds of funds side by side; but no single fund is blocked on it.

**Independent Test**: Can be fully tested by creating one fund on the built-in paper book and one on the T212 demo adapter and running both — each trades independently without affecting the other.

**Acceptance Scenarios**:

1. **Given** a mandate selecting the T212 broker, **When** the fund is validated, **Then** an invalid broker name or unresolvable credentials fail validation before any trading.
2. **Given** two funds with different brokers, **When** both run, **Then** each uses its own broker and its own book independently.

### Edge Cases

- What happens when T212 is unreachable mid-session (network failure, rate limiting)? The engine retries transient failures with backoff within a bounded time budget; if the budget is exhausted, the session halts safely with the failure recorded in the audit trail, and the book is never partially updated.
- What happens when the engine's book and T212's reported book disagree (e.g., a manual trade placed in the demo app)? The engine detects the mismatch before placing any order and refuses to trade until the owner explicitly reconciles — preserving ledger integrity.
- What happens when the fund trades a ticker T212 does not list? The engine validates the fund's universe against the broker's tradable instruments before the first order and refuses to run with untradable tickers.
- What happens when an order is below T212's minimum order size? The engine raises with the broker's message — no silent drops, no dust orders.
- What happens when the market is closed and T212 will not execute? The engine surfaces the broker's rejection and halts the session safely; it does not assume a fill that never happened.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The engine MUST support Trading 212 as an execution broker for paper funds, targeting T212's demo environment.
- **FR-002**: The adapter MUST NOT be able to place orders on T212's live (real-money) environment; live trading is out of scope for this feature.
- **FR-003**: The adapter MUST satisfy the existing broker contract exactly: report current positions (including fractional shares) and cash, and place orders that either fill completely and return the actual fill, or raise — never partial fills, never silent drops.
- **FR-004**: The engine MUST record fills from the external broker with the broker's actual execution price and quantity.
- **FR-005**: For funds using the external broker, the engine MUST treat the broker's reported cash and holdings as the authoritative book, MUST reconcile against it before placing any order, and MUST refuse to trade on an unexplained mismatch.
- **FR-006**: The engine MUST validate the fund's ticker universe against the broker's tradable instruments before first use and refuse to run with untradable tickers.
- **FR-007**: T212 credentials (API key and secret) MUST be resolvable from 1Password via secret references using the 1Password command-line interface; plaintext values in the existing environment file MUST also remain supported.
- **FR-008**: The engine MUST fail with an actionable error when a credential cannot be resolved (missing reference, locked or unavailable 1Password) and MUST NOT proceed to trade.
- **FR-009**: Secret material MUST NEVER be written to logs, ledgers, checkpoints, or any persisted file.
- **FR-010**: The execution broker MUST be selectable per fund in the fund mandate and validated like other mandate settings; already-deployed funds keep their broker unless redeployed, consistent with existing deployment immutability rules.
- **FR-011**: The fund status and detail surfaces MUST show which execution broker a fund uses.
- **FR-012**: Transient broker failures (network errors, rate limits) MUST be retried with backoff within a bounded budget; exhaustion MUST halt the session safely with the failure recorded in the audit trail.
- **FR-013**: The free yfinance data path MUST remain the default for analysis; the broker adapter changes execution only and MUST NOT call paid data providers.

### Key Entities *(include if feature involves data)*

- **Broker credentials**: T212 API key and secret, referenced (never stored) in engine configuration and resolved at startup through the user's 1Password vault.
- **Execution broker selection**: per-fund mandate setting naming which broker executes the fund's orders (built-in paper book or external adapter).
- **External book**: the broker-reported cash and positions that serve as the authoritative book for externally-brokered funds.
- **Reconciliation record**: an audit-trail entry capturing a book comparison performed before trading.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a T212 demo account can connect a fund to it in under 10 minutes, using only credentials stored in 1Password.
- **SC-002**: 100% of a session's orders appear in the T212 demo order history with matching side and quantity, and every ledger fill price equals T212's reported execution price.
- **SC-003**: Zero secret material is findable in logs, ledgers, or configuration files after a full session (verifiable by inspection).
- **SC-004**: Any induced book mismatch (e.g., a manual demo trade) is detected before the next order and blocks trading until explicitly reconciled.
- **SC-005**: Existing funds on the built-in paper book continue to run unchanged, and the full test suite stays green apart from the documented Windows baseline failures.

## Assumptions

- The user creates a T212 demo account and generates API credentials there (the T212 API is in beta; the demo environment is the integration target).
- The 1Password CLI is installed and authorized on the machine running the engine; unattended runs (e.g., the Docker runner) use a 1Password service account for non-interactive authorization, while interactive runs on the host may use desktop-app unlock.
- T212 demo supports fractional shares and market orders for US equities; minimum order sizes exist and are surfaced as errors.
- The engine's existing trading-costs model remains mandate-configurable; T212 demo charges no commission, and actual fill prices carry the truth.
- Live (real-money) trading is explicitly out of scope; enabling it later requires a new feature with explicit user opt-in.
- Data and analysis continue to use the free yfinance provider; financial-datasets credits remain untouched.