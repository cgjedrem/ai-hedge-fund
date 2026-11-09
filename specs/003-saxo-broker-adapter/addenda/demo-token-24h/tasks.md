# Tasks: Saxo Demo Account Connection

**Input**: Design documents from `specs/003-saxo-broker-adapter/addenda/demo-token-24h/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/saxo-demo-connection.md`, `quickstart.md`

**Tests**: Focused fake-transport, fake-vault, synthetic-root, and regression tests are required by the specification and plan. No test makes a network request or submits an order to Saxo.

**Organization**: Tasks are grouped by user story and ordered by prerequisite.

## Phase 1: Setup

**Purpose**: Reuse the current project environment without adding dependencies or disturbing shared fund state.

- [X] T001 Confirm `pyproject.toml` already provides the required runtime/test dependencies and leave it unchanged unless a focused test proves a dependency is missing.

---

## Phase 2: Foundational

**Purpose**: Establish deterministic, side-effect-free verification helpers shared by all stories.

- [X] T002 [P] Reuse or extend fake Saxo transport and synthetic secrets-provider fixtures in `hedge_fund/brokers/test_saxo_tokens.py` without reading local credentials or contacting Saxo (FR-002, FR-003, FR-014).
- [X] T003 [P] Revalidated PR #8's existing root-admission machinery and retained its normal gates without a bypass or synthetic substitute. The independent Saxo SIM account-ownership gate remains `ownership-unknown`, so SIM mutations stay blocked (FR-009, FR-013).

**Checkpoint**: All feature tests use synthetic providers and roots; no real user state is involved.

---

## Phase 3: User Story 1 - Connect to Saxo SIM safely (Priority: P1) - MVP

**Goal**: Authenticate to Saxo SIM with the separately referenced 24-hour token and report connection status without exposing the token or changing account state.

**Independent Test**: Fake valid, missing, rejected, and expired token cases; verify that only SIM requests are constructed, visible output is redacted, and no order request is made.

### Tests for User Story 1

- [X] T004 [P] [US1] Add tests for demo-token/SIM-OAuth mode separation, rejected mixed configuration, vault resolution, token redaction, expiry/rejection without retry, and actual-transport redirect refusal in `hedge_fund/brokers/test_saxo_tokens.py` and `hedge_fund/brokers/test_saxo_client.py` (FR-001–FR-004, FR-014; SC-001).
- [X] T005 [P] [US1] Add CLI tests for successful and failed read-only connection checks and no order submission in `hedge_fund/test_run.py` (FR-004, FR-007; SC-001, SC-002).

### Implementation for User Story 1

- [X] T006 [US1] Add an explicit demo-token credential path with in-memory bearer use, no refresh/write-back, safe errors, and no token-bearing repr in `hedge_fund/brokers/saxo.py` (FR-001–FR-004, FR-014; SC-001).
- [X] T007 [US1] Select demo-token mode only from its dedicated vault-reference setting, reject ambiguous SIM-OAuth/demo settings, and preserve the existing SIM OAuth route in `hedge_fund/brokers/factory.py` (FR-001–FR-003).
- [X] T008 [US1] Add a supported read-only Saxo SIM connection-check command that avoids fund creation and order APIs in `hedge_fund/run.py` (FR-004, FR-007; SC-001, SC-002).
- [X] T009 [US1] Document local vault-reference setup, token expiry behavior, and redacted connection-check outcomes in `specs/003-saxo-broker-adapter/addenda/demo-token-24h/quickstart.md` (FR-002–FR-004, FR-014; SC-001).

**Checkpoint**: US1 is complete when the connection-check command is testable offline and does not change any broker or fund state.

---

## Phase 4: User Story 2 - Select and verify the target demo account (Priority: P1)

**Goal**: Show eligible SIM account summaries and bind only an explicitly verified account; never silently use the first match.

**Independent Test**: Fake zero, one, multiple, incomplete, unsupported-currency, and positioned-account responses; inspection makes no order mutation.

### Tests for User Story 2

- [X] T010 [P] [US2] Add tests for candidate enumeration, explicit selection, malformed responses, and zero order calls in `hedge_fund/brokers/test_saxo_client.py` (FR-005–FR-007; SC-002, SC-003).
- [X] T011 [P] [US2] Add tests for sanitized account-inspection output and ambiguous-account refusal in `hedge_fund/test_run.py` (FR-005–FR-007, FR-014; SC-002, SC-003).

### Implementation for User Story 2

- [X] T012 [US2] Add candidate enumeration and require explicit account binding for demo-token mode, while preserving legacy first-eligible selection for unbound SIM OAuth mandates in `hedge_fund/brokers/saxo.py` (FR-005, FR-006; SC-003).
- [X] T013 [US2] Add a read-only account inspection action that reports sanitized identity, currency, cash, and position summaries in `hedge_fund/run.py` (FR-005–FR-007, FR-014; SC-002–SC-004).
- [X] T014 [US2] Bind a selected demo-token SIM account to the fund mandate/deployed snapshot and validate its currency and identity, without requiring the optional binding on legacy SIM OAuth mandates (FR-005, FR-006, FR-008; SC-003, SC-004).
- [X] T015 [US2] Keep CLI/TUI account-selection and status behavior consistent; preserve existing SIM OAuth deployment/run paths while blocking only the new demo-token workflow on the unsupported shared root (FR-005, FR-006, FR-014; SC-003).

**Checkpoint**: US2 is complete when an operator can verify and explicitly select an account and every ambiguous or incomplete result blocks fund preparation.

---

## Phase 5: User Story 3 - Prepare a dedicated supervised demo fund (Priority: P2)

**Goal**: Prepare and manually run a dedicated Saxo SIM fund without changing existing funds or bypassing write admission.

**Independent Test**: On synthetic roots with fake broker/data services, verify account binding, empty-book/cash reconciliation, approval and first-order gates, bounded stop, interruption handling, and unchanged existing state.

### Tests for User Story 3

- [ ] T016 [P] [US3] **BLOCKED**: although PR #8 supplies root selection and normal admission, the independent SIM account-ownership gate fails closed with `ownership-unknown`; Saxo creation/execution remain unsupported (FR-009, FR-013; SC-005).
- [ ] T017 [P] [US3] **BLOCKED**: SIM ownership is unknown, so no Saxo fund initialization is authorized; cash/position reconciliation remains unimplemented (FR-008, FR-010; SC-004).
- [ ] T018 [P] [US3] **BLOCKED**: SIM ownership is unknown and no Saxo execution path is enabled; approval, first-order authorization, bounded-run, and interruption behavior are not claimed (FR-011, FR-012; SC-005, SC-006).

### Implementation for User Story 3

- [ ] T019 [US3] **BLOCKED**: no root override or admission exception is added; passing local root admission would still not prove exclusive SIM account ownership (FR-009, FR-013; SC-005).
- [ ] T020 [US3] **BLOCKED**: no Saxo initialization path is authorized while SIM ownership is `ownership-unknown`; no cash/position reconciliation was added (FR-008, FR-010; SC-004).
- [ ] T021 [US3] **BLOCKED**: the TUI denies paper writes on enrolled roots; it does not persist or deploy a Saxo fund while root admission and SIM ownership controls do not both authorize it (FR-008, FR-011, FR-013; SC-004, SC-005).
- [ ] T022 [US3] **BLOCKED**: SIM ownership is unknown and no Saxo order path is enabled; first-order authorization and bounded execution remain unimplemented (FR-011, FR-012; SC-005, SC-006).
- [X] T023 [US3] Document the deployment/execution stop condition and prohibited workarounds in `specs/003-saxo-broker-adapter/addenda/demo-token-24h/quickstart.md` (FR-008–FR-012; SC-004–SC-006).

**Stop condition**: If either root write admission or the separate SIM ownership gate denies an operation, mark fund deployment/execution BLOCKED. Do not modify either policy, use the shared root, switch `HOME`, or use an internal deployment shortcut.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the integrated feature without credentialed or broker-mutating actions.

- [X] T024 [P] Review changed credential paths for token leakage, SIM-OAuth/demo-mode confusion, and redirects; no token value is emitted, serialized, refreshed, or sent to a non-SIM endpoint, and redirects are rejected without following them.
- [X] T025 Run focused offline broker, fund, CLI, TUI, and runner regression selections, including legacy SIM OAuth behavior; results and platform caveats are recorded in `acceptance-evidence.md`.
- [X] T026 Confirm no ledger, runner, or paper-state fixture files were changed; account-key serialization omits the optional field for existing paper funds and focused paper regressions pass.
- [X] T027 Record test revision, environment, fake-only evidence, and the admission blocker in `specs/003-saxo-broker-adapter/addenda/demo-token-24h/acceptance-evidence.md`.
- [ ] T028 **NOT RUN**: full suite intentionally deferred; it is not claimed as passing. Focused test results and observed Windows baseline failures are recorded in `specs/003-saxo-broker-adapter/addenda/demo-token-24h/acceptance-evidence.md` (FR-013; SC-005).
- [X] T029 Document the 15-second HTTP timeout, bounded fill-inspection deadline, and stop-on-rejection/interruption limits in `specs/003-saxo-broker-adapter/addenda/demo-token-24h/quickstart.md` (FR-004, FR-012; SC-005).
- [X] T030 Revalidate PR #8's fail-closed Saxo SIM ownership checks before broker secret resolution, CLI admission/ledger/provider access, and deployment mutation. Targeted fake tests confirm the `ownership-unknown` denial; this does not unblock US3 or weaken root admission (`acceptance-evidence.md`).
- [X] T031 Trace PR #8 host resolution, private delivery, application-provider allowlisting and backend lease consumption. Record its explicit Saxo exclusion and memory-only retention contract; add fake-only regressions proving Saxo delivery is denied before host effects and cannot change an application lease.
- [ ] T032 **SOURCE IMPLEMENTED; FINAL ACCEPTANCE PARTIAL/BLOCKED**: The user's explicit 2026-11-09 approval is recorded as the narrow Spec005 OP-FR-002 supersession, and the reviewed `onepassword-bridge\tasks.md` now contains the source implementation/evidence status. The separate `saxo-demo-token` -> `saxo-sim-readonly` capability, private memory-only delivery and in-app GET inspection are implemented; application provider catalogs, OP-FR-007 and ownership/admission remain unchanged. Full-suite/style verification, parent review and operator-local T026 host acceptance are not complete. File-backed delivery, generic broker/OAuth access, fund/order actions and automatic runtime/network mutation stay forbidden.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; confirm existing dependencies only.
- **Foundational (Phase 2)**: Depends on Setup; blocks user stories because test isolation is mandatory.
- **User Story 1 (Phase 3)**: Depends on Foundations; independently delivers safe connection checking.
- **User Story 2 (Phase 4)**: Depends on US1 credential handling; adds explicit account selection.
- **User Story 3 (Phase 5)**: Depends on US2 account binding and a separately verified, admission-authorized root.
- **Polish (Phase 6)**: Depends on all implementation stories attempted; if the root-admission stop condition occurs, execution-related evidence is marked BLOCKED rather than PASS.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundation; no other story dependency.
- **US2 (P1)**: Requires US1's demo-token source and read-only connection.
- **US3 (P2)**: Requires US2's explicit account binding, a root accepted by current admission, and verified exclusive SIM account ownership.

### Parallel Opportunities

- T002 and T003 can run independently in separate test files.
- T004 and T005 can be authored independently before US1 implementation, subject to shared branch sequencing.
- T010 and T011 can be authored independently before US2 implementation.
- T016, T017, and T018 can be authored independently before US3 implementation.
- Work within a user story is otherwise sequential where tasks edit the same production module.

## Parallel Example: User Story 1

```text
Task: Add fake token-mode and redaction tests in hedge_fund/brokers/test_saxo_tokens.py
Task: Add connection-check CLI tests in hedge_fund/test_run.py
```

## Implementation Strategy

### MVP First

1. Complete test-isolation setup.
2. Implement and verify US1: SIM connection check using the 24-hour vault token.
3. Implement and verify US2: explicit read-only account inspection and account binding.
4. Attempt US3 only if a dedicated root passes existing write admission; otherwise stop with a precise BLOCKED report.
5. Never claim Monday trading readiness without user-local credentialed account verification and a later separately authorized demo order.

### Incremental Delivery

Each story preserves the existing SIM-only OAuth flow and paper-fund behavior. No live-account mode is supported or implied. Unit/fake tests establish software behavior only; a user-authorized read-only Saxo SIM inspection is separate runtime evidence, and a real demo order is outside this implementation run.

## Notes

- All code tasks require co-located network-free tests.
- No local token values, auth codes, account response bodies, or `.env` values may be read into this workflow.
- Do not commit or open a PR without an explicit user request.
- A first demo order requires fresh operator confirmation after verified target-account and fund settings.
