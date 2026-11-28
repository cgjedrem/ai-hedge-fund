---
name: code-review
description: 'Structured code review process for any reviewer (human or AI). Covers readability, naming, patterns, test coverage, performance, and security review methodology. Produces review-report.md with findings organized by severity. Use when reviewing code quality, before merging changes, or when asked to audit code for issues. Do not use for PR diff comments (use caveman-review), security audits, or architectural reviews.'
---

# Code Review Protocol

## Overview

This skill defines a systematic code review process. Every review produces a `review-report.md` with findings organized by severity. The review covers readability, naming, patterns, test coverage, performance, and security.

## Review Phases

### Phase 1: High-Level Scan
- Read the change description or PR description first to understand intent
- Identify the scope of changes (which files, which modules)
- Check the stated scope against actual changes — are all changed files listed?
- Verify no out-of-scope modifications

### Phase 2: Correctness
- Does the code do what its description / commit messages say it should do?
- Are edge cases handled (null, empty, undefined, off-by-one)?
- Are error paths covered — no swallowed exceptions, no silent failures?
- Are there race conditions in async code?
- Are there resource leaks (unclosed connections, un-released locks)?

### Phase 3: Readability & Naming
- Can you understand what the code does without comments?
- Are variable and function names descriptive?
- Are function signatures clear?
- Is the code organized logically?
- Are magic numbers extracted to named constants?

### Phase 4: Patterns & Conventions
- Does the code follow existing project patterns?
- Is the coding style consistent with the rest of the codebase?
- Are the same libraries and utilities used (no reinventing the wheel)?
- Are TypeScript types used properly (no unnecessary `any`)?

### Phase 5: Test Coverage
- Are there tests for happy paths?
- Are there tests for error paths?
- Are there tests for edge cases?
- Do tests test behavior, not implementation details?
- Can tests run independently (no inter-test dependencies)?

### Phase 6: Performance
- Are there N+1 queries or unnecessary data fetching?
- Are expensive operations cached where appropriate?
- Are there unnecessary re-renders in frontend code?
- Are database queries using proper indexes (check migration files)?

### Phase 7: Security (OWASP LLM Top 10)
Apply the `llm-security-checklist` skill checklist in full. Every item must be checked and recorded in the review report.

## Severity Classifications

| Severity | Definition | Confidence Threshold |
|----------|-----------|---------------------|
| **Critical** | Security vulnerability, data loss risk, or breaking bug | >90% confidence |
| **Important** | Functional bug, missing error handling, or pattern violation | >70% confidence |
| **Minor** | Style inconsistency, minor performance concern, or missing test | >50% confidence |
| **Nitpick** | Naming preference, cosmetic formatting, or subjective style | Opinion-based, labeled as such |

## Review Report Format

```markdown
# Review Report

## Status: [pass | fail | pass-with-caveats]

## Scope
- Files reviewed: [list]
- Scope: [in-scope / out-of-scope changes noted]

## Critical
- [file:line] Description. [Confidence: X%]

## Important
- [file:line] Description. [Confidence: X%]

## Minor
- [file:line] Description. [Confidence: X%]

## Nitpick
- [file:line] Description. [Opinion]

## Security Checklist (OWASP LLM Top 10)
- [ ] LLM01: Prompt Injection
- [ ] LLM02: Insecure Output Handling
- [ ] LLM03: Training Data Poisoning
- [ ] LLM04: Model Denial of Service
- [ ] LLM05: Supply Chain Vulnerabilities
- [ ] LLM06: Sensitive Information Disclosure
- [ ] LLM07: Insecure Plugin Design
- [ ] LLM08: Excessive Agency
- [ ] LLM09: Overreliance
- [ ] LLM10: Model Theft

## General Security Checks
- [ ] Input validation at all API boundaries
- [ ] No SQL injection vectors
- [ ] No XSS vectors
- [ ] No command injection vectors
- [ ] Auth middleware applied
- [ ] Generic error messages (no internal state leaked)
- [ ] No secrets in source code

## Test Coverage Assessment
- Happy paths: [covered / not covered]
- Error paths: [covered / not covered]
- Edge cases: [covered / not covered]
- Overall: [sufficient / needs improvement / critical gap]

## Summary
- Total findings: N
- Critical: N, Important: N, Minor: N, Nitpick: N
- Recommendation: [approve | request changes | reject]
```

## Review Rules

1. **Every finding references a specific file and line.** No vague statements like "there are some issues."
2. **Confidence thresholds are mandatory.** If you're <50% confident a finding is real, it doesn't go in the report.
3. **Out-of-scope changes are flagged.** If a file was modified but not described in the change scope, that's a finding.
4. **Security findings are never downgraded.** A security issue is always at least Important, even if the exploit path is unlikely.
5. **The report status drives downstream decisions.** `fail` requires addressing findings before merge. `pass-with-caveats` flags non-blocking issues for the reviewer/maintainer to consider. `pass` allows merge.