# Acceptance Evidence — {FEATURE_NAME}

Constitution (Acceptance Evidence and Revalidation): each acceptance result must
retain the exact criterion/source, expected and observed result, revision/build
identity, timestamp, environment, scenario, and provenance. Reopen affected rows
after any behavior-affecting change (including review fixes); keep old rows as
history and append the new result.

| ID | Task | Criterion (exact quote + source) | Expected | Observed | Revision/build | Environment | Scenario | Timestamp | Provenance | Status |
|----|------|----------------------------------|----------|----------|----------------|-------------|----------|-----------|------------|--------|
| AE-1 | T___ | | | | | | | | | open |

Row status: `open` (not yet run), `pass`, `fail`, `reopened` (invalidated by a
later change — retain the row and add the new result below it). Required
blocked/inconclusive rows prevent claiming verified readiness.
