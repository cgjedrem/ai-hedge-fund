# Research: React Trading Desk

Discovery baseline: `9f09f0d` (main); read-only code-explorer report, 2026-10-30.

| Decision | Rationale | Alternatives |
|----------|-----------|--------------|
| FastAPI adapter, React/Vite/TypeScript/Tailwind/shadcn | Matches requested React/component stack, reuses validated Python | Terminal HTML is not a React workflow; JS trading engine duplicates authority |
| Additive local UI, TUI retained | Explicit safety and retirement requirement | Replacing default CLI prematurely breaks existing users |
| Explicit root, immutable startup capabilities | Existing paths capture home at import; CLI startup also initializes state | Merely monkeypatching one constant fails child/default-argument isolation |
| Read-only real data, fake-backed demo execution | Existing default provider is paid; cache is not offline | yfinance alone still accesses external network |
| Domain DTOs and replay | Persisted hashes and fractional quantities must stay authoritative | Browser record round-tripping risks format changes |
| Defer unsafe process/destructive actions | Existing runner PID ownership is namespace/platform sensitive | Broad process controls risk unrelated runners |

## Verified Reuse Points (discovery)

- `fund/storage.py`: discover/save spec; `fund/spec.py`: FundSpec, strategies and windows.
- `paper/deployed.py`: list/load/deploy with explicit roots.
- `paper/ledger.py`: replay/records/mailbox/halt/resume; approval identity uses timestamp and source hash.
- `paper/tick.py`: following_session forecast; tick/redo are execution, never read operations.
- `backtesting/fund.py`: backtest_fund and performance_metrics; `backtesting/research.py`: receipts/save_result.
- `scorecard/__init__.py`: score; `llm/registry.py`: model/provider metadata.
- `tui/keys.py`: credential persistence patterns, not arbitrary remote environment setters.

No further research unknown blocks the bounded design. Runtime/browser/container support must be established through execution, not assumed.
