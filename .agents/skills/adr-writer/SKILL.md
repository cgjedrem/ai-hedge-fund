---
name: adr-writer
description: Create, review, and maintain Architecture Decision Records (ADRs) for software projects. Use when asked to write an ADR, a significant architectural decision needs documenting, reviewing why a past decision was made, updating or superseding an existing ADR, or when the user mentions ADR, architecture decision, decision record, or write up why we chose X. Triggers on phrases like write an ADR for, create an architecture decision, document this decision, why did we choose X, or log the decision to use Y. Do not use for RFCs, technical specs, API documentation, or non-decision technical writing.
---

# ADR Writer

Create and maintain Architecture Decision Records following Martin Fowler's lightweight ADR pattern.

## ADR Location
Store ADRs in the same repository as the code they describe:
```
doc/adr/
├── 0001-Short-Title-For-Decision.md
├── 0002-Another-Decision.md
└── ...
```

## When to Write an ADR

Write an ADR when:
- A significant technology choice is being made (library, framework, pattern)
- A design decision has meaningful trade-offs
- Future developers (including yourself) will need to understand *why*
- The team needs to align on a decision with competing options
- An existing ADR is being superseded by a new decision

## ADR Format

```markdown
# ADR-0001: Title of the Decision

**Status:** Accepted

**Date:** YYYY-MM-DD

## Context

[What situation forces this decision? What is the background?]

## Decision

[What was decided? Be specific.]

## Rationale

[Why was this choice made? What trade-offs were considered?]

## Forces

- [Driver 1]
- [Driver 2]
- [Driver 3]

## Alternatives Considered

### Option A: [Name]
**Pros:** ...  
**Cons:** ...  

### Option B: [Name]
**Pros:** ...  
**Cons:** ...  

## Consequences

**Positive:**
- ...

**Negative:**
- ...

**Confidence:** High / Medium / Low

**Re-evaluate when:** [What changes should trigger re-thinking?]

## Superseded By
[Link to superseding ADR if applicable]
```

## Rules

1. **One decision per ADR** — if it's complex, split it
2. **Immutability** — never edit an Accepted ADR. Create a new one to supersede it
3. **Be specific** — "use PostgreSQL" not "use a database"
4. **Capture alternatives** — list the serious options considered, not strawmen
5. **Include pros and cons** — don't just describe alternatives, evaluate them
6. **Link heavily** — don't duplicate existing docs, link to them
7. **Date every decision** — context matters for future readers

## Workflow

### Create New ADR
1. Find the highest number in `doc/adr/`
2. Create new file: `doc/adr/XXXX-New-Decision.md`
3. Fill in all sections
4. Set Status: Proposed initially, update to Accepted after team review

### Supersede Existing ADR
1. Open the old ADR
2. Update Status to "Superseded by ADR-XXXX"
3. Add link to new ADR at the bottom
4. Create new ADR with the updated decision

### Review Existing ADRs
When asked "why did we choose X":
1. Search `doc/adr/` for relevant keywords
2. Read the ADR's Context + Rationale sections
3. Check if it's been superseded (Status field)

## Reference

For full ADR format guidance and examples, see [references/adr-guide.md](references/adr-guide.md).
