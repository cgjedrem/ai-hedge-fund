# Local HTTP Contract

Implement versioned JSON routes under `/api` (a `/v1` segment is optional if uniformly applied). Publish exact generated OpenAPI schema with runtime API.

| Route family | Reads | Explicit mutations |
|--------------|-------|--------------------|
| capabilities/catalog | mode, actions, strategies/agents | none |
| funds | mandates, validation errors, latest research | validated create/deploy; existing names refused |
| paper | deployed list/detail, sessions, report, forecast, scorecard | hash-bound verdict, halt/resume; runner/run only when safe |
| research/backtests | receipts, reports, job progress | bounded explicit backtest job |
| settings | models and key-presence only | allowlisted model/credential change |

Mutations require startup capability, acceptable Host/Origin and per-launch token. Protected-name guard precedes adapter calls. No query parameter can enable writes/network.

Errors: meaningful safe message and HTTP status; 403 denied capability/origin, 404 missing resource, 409 stale identity/conflict/ownership, 422 invalid request. Validation messages must not echo credential bodies. Never mask corrupt data as a valid empty result.

Approval body contains verdict, decision_as_of and source_record_hash; server compares both with replay and checks existing expiry. Request never contains a trusted replacement session. Read endpoints are disk-only by default and perform no initialization or market fetch.

SPA static fallback only serves built assets, not arbitrary paths; unknown API routes return API errors, not HTML.
