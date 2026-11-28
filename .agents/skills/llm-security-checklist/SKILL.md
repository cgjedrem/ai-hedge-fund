---
name: llm-security-checklist
description: OWASP LLM Top 10 security checklist for code-generating agents. Applied by QA during review and referenced by all write agents during implementation. Use when reviewing code for security, writing code that handles user input/auth/data/external communication. Do not use for general code quality, performance review, or non-security concerns.
---

# LLM Security Checklist (OWASP LLM Top 10)

This checklist is applied during QA review and referenced by all write agents during implementation. Every item must be checked during Phase 4 (Review).

## LLM01: Prompt Injection
- [ ] No LLM-generated code evaluates untrusted input as instructions
- [ ] System prompts and user data are separated in any AI-integrated features
- [ ] No `eval()`, `exec()`, or dynamic code execution on untrusted input
- [ ] Input sanitization is applied before any AI/LLM processing

## LLM02: Insecure Output Handling
- [ ] LLM-generated content is treated as untrusted before rendering
- [ ] No LLM output is rendered as raw HTML without sanitization
- [ ] No LLM output is used in SQL queries without parameterization
- [ ] No LLM output is passed to shell commands without escaping

## LLM03: Training Data Poisoning
- [ ] No hardcoded data from unverified sources in the codebase
- [ ] Data sources are verified and documented
- [ ] Training/inference data pipelines have integrity checks

## LLM04: Model Denial of Service
- [ ] Input size limits are enforced on all endpoints
- [ ] Rate limiting is applied to resource-intensive operations
- [ ] No unbounded recursive operations on user-controlled depth

## LLM05: Supply Chain Vulnerabilities
- [ ] Dependencies are pinned to specific versions in lockfiles
- [ ] No unnecessary dependencies introduced
- [ ] Dependencies come from verified registries only
- [ ] No `latest` tags in production Docker images

## LLM06: Sensitive Information Disclosure
- [ ] No secrets, API keys, or tokens in source code
- [ ] Environment variables are documented but values are never committed
- [ ] Error messages do not leak internal state, stack traces, or configuration
- [ ] Logging does not capture sensitive user data (PII, credentials, tokens)
- [ ] API responses do not expose internal IDs, emails, or system details beyond what's required

## LLM07: Insecure Plugin Design
- [ ] Plugin/tool integrations validate input before processing
- [ ] Plugin permissions follow least-privilege principle
- [ ] No plugin can execute arbitrary system commands
- [ ] Plugin data flows are auditable

## LLM08: Excessive Agency
- [ ] Agent actions are scoped to minimum necessary permissions
- [ ] No agent can modify files outside its defined scope
- [ ] Destructive actions require explicit human approval
- [ ] Agent output is validated before execution

## LLM09: Overreliance
- [ ] Generated code is reviewed by QA before merging
- [ ] No generated code runs in production without review
- [ ] Test coverage is verified for all generated code
- [ ] Critical paths have manual verification steps

## LLM10: Model Theft
- [ ] No model weights or proprietary data exposed in the codebase
- [ ] API keys for AI services are not committed to version control
- [ ] Model endpoints are not publicly accessible without auth

---

## General Security Checks (Non-LLM)

### Input Validation
- [ ] All user input is validated at API boundaries
- [ ] Input type, length, and format are enforced
- [ ] No SQL injection vectors (parameterized queries used everywhere)
- [ ] No XSS vectors (output encoding applied)
- [ ] No command injection vectors (no shell=True, no string concatenation in commands)

### Authentication & Authorization
- [ ] Auth middleware applied at router level
- [ ] Every endpoint checks authorization
- [ ] Principle of least privilege applied
- [ ] No IDOR (Insecure Direct Object Reference) vulnerabilities

### Error Handling
- [ ] Generic error messages returned to clients
- [ ] Detailed errors logged server-side only
- [ ] No stack traces or internal state in error responses
- [ ] All edge cases handled explicitly

### Data Protection
- [ ] Passwords hashed with bcrypt/Argon2/scrypt
- [ ] Sensitive data encrypted at rest
- [ ] TLS used for all network communication
- [ ] No sensitive data in URLs or query parameters