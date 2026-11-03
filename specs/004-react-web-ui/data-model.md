# API Data Model

Persisted domain models remain unchanged. API DTOs expose presentation fields only.

- **Capabilities**: mode, read_only, writes, network, protected_names, mutation token; immutable during process lifetime.
- **Fund summary/detail**: name, validated spec, universe, errors, deployment/runner state, allowed-action reasons.
- **Paper snapshot**: last session/head hash, recorded NAV/cash/positions, pending identity, verdict/expiry, forecast, metrics, curve and verification status.
- **Live estimate**: value or unavailable reason, quote time and provenance; never included in recorded curves or scorecards.
- **Session report**: timestamp, hash, code version, executed orders/fills/costs separate from proposed targets, escaped agent text.
- **Research result**: receipt identity, configuration, session records, metrics/scorecard, stored report reference.
- **Job**: id, frozen request/provider/model, queued/running/succeeded/failed state, progress/result/error. No auto retries.
- **Credential status**: allowlisted provider, configured boolean; write request secret is never a response field.

Validation uses canonical FundSpec plus contained path/name guards. Approval transition is read displayed identity -> compare current identity -> existing mailbox verdict -> existing runner consumes or expires; web does not execute an approval.
