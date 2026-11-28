---
name: testing-strategy
description: 'Testing requirements and patterns for any software project. Defines what to test, how deep, what tools to use, and coverage expectations by layer. Use when writing tests, defining test strategy, or evaluating test coverage. Do not use for E2E test infrastructure setup, performance benchmarking, or load testing.'
---

# Testing Strategy

## Producer-to-Consumer Contracts

Before asserting an input contract, inspect the producer and its schema/fixtures.
Use deterministic synthetic fixtures that preserve valid source shapes, including
nullable fields, optional nested objects, and documented sentinel keys. Do not
reject a producer-emitted value just because it differs from an assumed ID/type.

For financial calculations, write down the metric definition and hand-calculate
expected results before implementation. Cover signed inflows/refunds, expenses,
transfers, category-role routing, missing/partial data, and complete pagination.
Keep transaction/account attribution distinct from a configured household
allocation. Compare monthly and multi-month outputs through shared accounting paths
when parity is part of the product contract; do not assume two differently defined
metrics must match. Assert cent-level totals and conservation/complement invariants
where applicable, including that rounding does not invent a settlement.

Fixtures must be synthetic and must not be copied from live financial snapshots.
When a failure depends on private data, reduce it to a minimal synthetic example
instead of retaining or printing private values.

## General Principles

- **Test behavior, not implementation.** Tests should verify what the code does, not how it does it.
- **Every test must be independent.** No test depends on another test's state or side effects.
- **Tests are mandatory, not optional.** No code ships without corresponding tests.
- **Use the project's existing test framework and patterns.** Do not introduce new testing libraries unless the project already uses them.

## Coverage Expectations

### Frontend
- Every component renders without crashing
- Every data-fetching component has loading, error, and empty state tests
- User interactions are tested (click handlers, form submissions, navigation)
- Edge cases: empty data, long strings, unusual characters, rapid clicks
- Use the project's existing test utilities (React Testing Library, etc.)

### Backend
- Every API endpoint has at least one happy path test and one error test
- Input validation is tested for each endpoint
- Authentication and authorization are tested
- Database operations are tested with proper setup/teardown
- Error response shapes match the API design specification

### Infrastructure / DevOps
- CI/CD pipeline changes are tested by running the pipeline
- Docker configurations are tested by building and running the container
- Environment variable presence is verified (values not committed)
- Rollback procedures are documented and verified

### Reviewers (Code Review Phase)
- Reviewers assess test coverage as part of every review
- Reviewers do NOT write tests — that's the implementer's job
- Missing tests are flagged as findings (severity: Important)
- Reviewers verify existing tests actually test the right thing

## Test Types by Priority

| Priority | Test Type | When Required | Who Writes |
|----------|-----------|--------------|------------|
| 1 | Happy path | Always | Implementer (frontend/backend) |
| 2 | Error path | Always | Implementer (frontend/backend) |
| 3 | Edge cases | Always | Implementer (frontend/backend) |
| 4 | Integration | When endpoints interact | Implementer (backend) |
| 5 | Authorization | When auth is involved | Implementer (backend) |
| 6 | Accessibility | Frontend user-facing components | Implementer (frontend) |
| 7 | Performance | Only when flagged in requirements | Implementer (frontend/backend) |

## Test File Conventions

- Test files live alongside the code they test (co-location)
- Test file naming: `.test.<ext>` or `.spec.<ext>`
- Follow the project's existing test file naming convention
- One test file per source file
- Test descriptions use `should <behavior> when <condition>` format

## What NOT to Test

- Implementation details (private methods, internal state)
- Third-party library behavior (test your integration, not their code)
- Trivial code (simple getters/setters with no logic)
- Configuration files (unless they contain logic)

## Coverage Assessment (Review Phase)

When reviewing test coverage, the reviewer assesses:

1. **Happy path coverage**: Are all success scenarios tested?
2. **Error path coverage**: Are failure scenarios tested?
3. **Edge case coverage**: Are boundary conditions tested?
4. **Test quality**: Do tests actually assert the right things?
5. **Test independence**: Can tests run in any order?
6. **Test clarity**: Are test descriptions meaningful?

Assessment ratings:
- **Sufficient**: Happy + error + edge cases all covered
- **Needs improvement**: Missing error paths or edge cases
- **Critical gap**: Missing happy path tests