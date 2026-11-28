---
name: design-first
description: 'Plan any work type using a design-first collaboration workflow before implementation. Use when users ask to plan engineering, documentation, operations, analysis, migrations, or cross-team delivery; break down tasks; align on architecture and interfaces; reduce rework; or create execution plans before making live changes. Trigger on requests like: "plan this first", "no code yet", "walk through design", "define scope/components/interactions/contracts", "create an implementation plan", or "break this into phases". Do not use for trivial one-step tasks, routine config changes, or tasks with a matching workflow already.'
---

# Design-First Planning

Use this workflow to make design decisions explicit before implementation.

## Core Rule

Do not produce live implementation changes until planning reaches the approved Implementation Plan stage.

Strict mode: do not write executable code, run code-generation edits, or apply implementation patches before Level 5 approval.

Exception: pseudocode may be added as comments in files if it is clearly labeled as non-executable planning guidance.

If the user asks for immediate implementation, provide a minimum viable plan first, get approval, then implement.

## Inputs To Collect

Collect only missing context:

- Desired outcome and non-goals
- Existing systems or infrastructure that must be reused
- Constraints: time, risk, compliance, performance, cost
- Environment and integration points
- Definition of done

If context is incomplete, ask a small number of high-impact questions and proceed with explicit assumptions.

## Five-Level Planning Flow

Work sequentially. At each level, present output, call out assumptions, ask clarifying questions, and request approval before continuing.

**Alignment Check (mandatory):** After presenting each level, ask the user 4-6 targeted questions that test understanding of the design decisions — not just "looks good?" but specific scenario questions that reveal misalignment. Do not proceed to the next level until the user answers and alignment is confirmed.

### Level 1: Capabilities

Define what the solution must do, without implementation details.

Produce:

- In-scope capabilities
- Out-of-scope items
- Success criteria tied to user outcomes

Checkpoint question:

- Is this the correct scope for v1?

### Level 2: Components

Define major building blocks and boundaries.

Produce:

- Components/modules/services involved
- Reuse-first choice for existing platform capabilities
- Explicit rationale for any new abstraction

Checkpoint question:

- Do these boundaries fit the current architecture?

### Level 3: Interactions

Define how components communicate and where data/control flows.

Produce:

- Request/event/data flow path
- Failure and retry behavior
- Observability touchpoints (logs/metrics/traces)

Checkpoint question:

- Are the flow and failure modes acceptable?

### Level 4: Contracts

Define interfaces and validation rules.

Produce:

- API/function/event contracts (inputs, outputs, error model)
- Data schemas and invariants
- Backward-compatibility expectations
- Testable acceptance criteria

Checkpoint question:

- Are these contracts complete enough to implement and test?

### Level 5: Implementation Plan

Convert approved design into execution steps.

Produce:

- Ordered task list with dependencies
- Risk controls and rollback strategy
- Test plan (unit/integration/e2e as applicable)
- Incremental delivery slices (small, reviewable checkpoints)

Checkpoint question:

- Approve implementation now?

## Branching Rules

- If a level is rejected: revise only that level and downstream levels.
- If user introduces new constraints: update Capabilities and propagate deltas forward.
- If a proposed component duplicates existing infrastructure: prefer existing capability unless user explicitly approves new abstraction.
- If uncertainty remains after two iterations at one level: present 2-3 options with tradeoffs and request a decision.

## Quality Gates Before Implementation

Do not proceed unless all are true:

- Scope is explicit with clear non-goals
- Architecture is compatible with existing systems
- Interaction flow includes error handling and observability
- Contracts are testable and unambiguous
- Plan includes risks, dependencies, and verification steps

## Response Pattern

Use this compact structure:

1. Current level and objective
2. Proposed output for that level
3. Assumptions and risks
4. Approval request to move forward