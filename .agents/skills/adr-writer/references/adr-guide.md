# ADR Reference Guide

## Why ADRs Matter

**The Problem:** Months after a decision is made, nobody remembers *why* PostgreSQL was chosen over MySQL, why the authentication flow uses OAuth rather than sessions, or why the service is written in Go instead of Python. The code shows *what*, but not *why*.

**The ADR Solution:** A short, versioned document that captures the decision at the moment it was made — including the context, the alternatives considered, and the trade-offs that drove the choice.

## Core Principle: Immutability

An Accepted ADR is **never edited**. If circumstances change and a different decision is warranted:

1. Write a **new ADR** documenting the new decision
2. Update the old ADR's Status to `Superseded by ADR-NNNN`
3. Add a link back to the new ADR
4. Keep the old ADR in place — it documents *why things were the way they were*

This preserves the historical record accurately.

## ADR Status Lifecycle

```
Proposed → Accepted → (Superseded by NNNN | Deprecated)
```

- **Proposed:** Draft, under discussion
- **Accepted:** Final, implemented
- **Superseded:** Outdated by a newer decision
- **Deprecated:** No longer relevant (rare)

## Title Conventions

Use: `XXXX-Concise-Title-That-Makes-Sense.md`

Examples:
- `0001-PostgreSQL-for-Primary-Database.md`
- `0002-OAuth2-for-Authentication.md`
- `0003-Kubernetes-for-Container-Orchestration.md`
- `0004-Event-Sourcing-for-Order-History.md`

## Decision Triggers

Common triggers for writing an ADR:

- Evaluating a new technology (library, framework, language)
- Architectural pattern choices (microservices, event-driven, CQRS)
- Data store choices (SQL vs NoSQL, specific database)
- Authentication/authorization approaches
- API design decisions (REST, GraphQL, gRPC)
- Infrastructure decisions (cloud provider, deployment approach)
- Integration patterns (sync vs async, message queues)

## Quality Checklist

Before marking an ADR as Accepted:

- [ ] Title clearly describes the decision
- [ ] Context explains *why* this decision was necessary
- [ ] All serious alternatives are listed with pros and cons
- [ ] Trade-offs are explicit, not hidden
- [ ] Consequences are realistic (positive and negative)
- [ ] A re-evaluation trigger is mentioned
- [ ] Related ADRs are linked
- [ ] Status is set to Accepted

## Tools

**adr-tools** — command-line tool for managing ADRs:
```bash
adr-tools              # github.com/npryce/adr-tools
adr new "Use PostgreSQL"
adr accept 1
adr supercede 1 "Use CockroachDB instead"
```

**ADR in Git:**
```bash
mkdir -p doc/adr
git init doc/adr
```

## Example ADR

See the SKILL.md for the full template.

## Key Sources

- Michael Nygard — coined the term "ADR" (2011)
- Martin Fowler — [martinfowler.com/articles/documenting-architecture-decisions.html](https://martinfowler.com/articles/documenting-architecture-decisions.html)
- ThoughtWorks Technology Radar — ADRs as a practice
