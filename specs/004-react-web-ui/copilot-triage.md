# Copilot Review Triage

## Review identity

- Repository: `cgjedrem/ai-hedge-fund`; PR 7; branch `cgjedrem-fictional-winner`; base `main`.
- Reviewed source: `7466ad2e979eb4be0f5c6fb4b46ca0b67104c492`.
- Copilot review `5722559422`: seven open inline findings and one “previously missed issue” embedded in the review body, submitted `2026-10-31T11:41:22Z`.
- Inline comment IDs were fetched from the explicit PR comments endpoint. The Vite finding has no separate inline-comment ID; `5722559422` is its review-summary provenance.
- Fix commit: `da78aa2cd1a282be854b5f844ce28b886d5d702a`.
- All eight findings verified and fixed. Coordinator owns QA, thread replies/resolution and push. No GitHub replies, thread resolution or push performed here.

## Decision table

| Finding | Class | Verified judgment and fix evidence | Status |
|---|---|---|---|
| `4429062053` — `hedge_fund/tui/keys.py:68` | 🔴 defect | `write_atomic(..., mode=0600)` creates and restricts the sibling temp before writing, then replaces the destination. Tests observe mode at write/replace and simulate a partial write plus cleanup in `hedge_fund/test_paths.py`; `hedge_fund/tui/test_keys.py` verifies credential save requests private mode. POSIX runtime evidence remains blocked on Windows. | accepted-fix |
| `4429062094` — `hedge_fund/web/services.py:626` | 🔴 defect | Approval, halt and resume preflight `fund.yaml`, `control.json`, `events.jsonl` and `pending-approval.json` through `_paper_control_state()` before reading or mutating. Six symlink cases cover approval/resume and assert linked targets unchanged in `hedge_fund/web/test_actions.py`. | accepted-fix |
| `4429062123` — `frontend/src/pages/backtests.tsx:54` | 🔴 defect | Backtest page restores a valid selected job from browser storage or `/api/jobs`, exposes Monitor actions, and persists selection. Unit and production-browser tests verify progress, cancellation request, navigation and reload recovery. | accepted-fix |
| `4429062152` — `hedge_fund/web/services.py:80` | 🔴 defect | Default web factory now constructs `Fund(..., blind=True)`. A real default `Fund` is tested with fake LLM construction; blind mode and `news`, `samples`, `temperature` survive. | accepted-fix |
| `4429062184` — `hedge_fund/web/services.py:419` | 🔴 defect | Default web factory injects `PromptCache` under the configured root. Regression forbids default cache construction and checks root path, blind mode and model parameters without provider calls. `research.md` already warns that cache is not offline and root isolation matters; this specific home-cache leak was not in the prior QA finding tables. | accepted-fix |
| `4429062211` — `hedge_fund/web/services.py:540` | 🔴 defect | Snapshot records and replay state now come from one `Ledger.replay(..., on_verified=...)`. Regression replaces a record after its verified read and confirms displayed NAV, cash, pending hash and history remain from that replay. | accepted-fix |
| `4431573731` — `hedge_fund/web/services.py:628` | 🔴 defect | `_paper_state`, approval and resume capture the last verified record during replay instead of calling `latest()` afterward. Regression rejects a reread; existing approval expiry/mailbox checks remain. No cross-process lock is claimed. | accepted-fix |
| Review `5722559422` body — `frontend/vite.config.ts:18`, “Proxy Vite API requests to the local adapter” | 🔴 defect | Dev server proxies `/api` to a validated loopback HTTP origin with `changeOrigin: false`. Runtime smoke: same-origin GET 200, valid-CSRF POST 200, foreign-origin GET/POST 403; invalid proxy targets reject without echoing input. Production bundle remains served by FastAPI, not the dev proxy. | accepted-fix |

## Rollup and batching

- 🔴 defect: 8 accepted-fix; 🟡 hardening: 0; 🔵 nit: 0; false positive: 0; deferred: 0.
- Source fixes are grouped in one commit on the branch reviewed by Copilot. No stack surgery was needed. Coordinator owns publication and thread follow-up.

## Convergence and remaining limits

- Prior QA `qa-review-2.md` R3 and `qa-review-3.md` F3 identified rereading a session after ledger verification. `qa-final.md` confirms the verified-record repair. Copilot findings `4429062211` and `4431573731` converge on that race class; implementation reuses the established `on_verified` hook.
- No prior QA table recorded the default web factory’s `blind=False` or home-root `PromptCache`; both Copilot findings were verified against `Fund`, CLI/TUI defaults and the actual default web factory, then covered with fakes.
- The Vite item was summary-only, not an inline thread. Its review-body claim was independently reproduced against the running dev proxy.
- Windows skipped the two POSIX-only file-mode tests. No Linux/Docker runtime permission claim is made; see `acceptance-evidence.md`.
- Copilot’s `COMMENTED` review is not approval. Coordinator-owned QA and thread follow-up remain outstanding.
