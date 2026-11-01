# Spec005 QA final disposition

## Status

**PARTIAL — NOT READY TO MERGE. Full migration remains BLOCKED.** This bounded closure fixes the supplied final-QA defects and records the existing convergence candidate. It does not complete Spec005, enable production writes, authorize paid/headless dispatch or retire the TUI.

## Closure result

| Area | Disposition |
|---|---|
| Mandate inventory guard | **PASS — scoped.** `_mandate_writer` verifies inventory under the admission registry lock before create/update/clone file effects. Drift denies both direct update and physical rename. |
| Dashboard research count | **PASS — scoped.** Uses uncapped `total`; >50 records and corrupt reports covered. |
| Clone/admission and classifier errors | **PASS — scoped.** Clone admission denial maps to 409; unknown local-policy classification maps to 422. |
| Backtest provider gate | **PASS — scoped.** Paid model is rejected before durable operation creation. Only local/free classification is accepted by the preview guard. |
| Rename failure recovery | **PASS — retry only.** Rename and write are separate operations. Failed write leaves old bytes at new path; retry succeeds. No transaction or crash-atomicity claim. |
| Python root/services/actions/manual-paper tests | **PASS — synthetic slice.** Combined run: 112 passed, 1 skipped. Final post-format `test_actions.py`: 28 passed. Exact runs are in `spec005-final-evidence.md`. |
| Frontend unit/type/build | **PASS.** 26 unit tests; standalone TypeScript check and Vite production build exit 0. Large-chunk warning remains. |
| Browser E2E | **PASS — demo/fake-route only.** 12 passed under owned harness. Does not prove live API mutation or backend integration. |
| Saxo token diagnostic | **PASS — fake transport/clock only.** 8 bounded tests passed. |
| Wheel | **PASS — build only.** Wheel SHA-256 and embedded static-bundle identity are in `spec005-final-evidence.md`; installation/runtime smoke not run. |
| Static checks | **PARTIAL — inherited Black baseline.** Isort, flake8 and diff check passed; `test_actions.py` Black failure also exists at base HEAD, with no changed-line formatter overlap. |
| Full Python suite | **INCONCLUSIVE.** Prior attempts stalled at 149 passed / 2 skipped of 1,207 collected. No full-suite rerun. |
| Linux/ext4 and actual NTFS ACL | **BLOCKED.** Not exercised on this Windows host. |

## Migration blockers

- T015/T021 remain partial. Admission and handover do not fence unaware legacy/out-of-band writers; `fund/storage.py` and `backtesting/research.py` are not fully integrated.
- T137/T138/T140/T142–T145/T147/T148 remain open. T139/T141/T146 have bounded partial evidence but stay unchecked.
- Full provider-operation authorization, durable reconciliation/runner lifecycle, complete `FundSpec` browser parity, report export/drilldown, native platform gates and full-suite completion remain open.
- React desk remains an additive subset. TUI/Textual and operator recovery paths remain intact. TUI retirement is **BLOCKED**.
- SIM denials remain in place. No resume enablement or write-surface expansion was attempted.
- The final wheel was built but not installed or runtime-smoked. No container acceptance was run.

## Safe preview handoff

No preview server is running. The owned E2E server on `8876` exited and the harness verified port release and test-root cleanup. At `2026-11-01T11:37:30.9982848+01:00`, loopback port `8877` bound successfully; the temporary listener closed immediately. The prepared synthetic preview root was empty, with a valid parent marker. Port availability is only a point-in-time observation; recheck before start.

From the repository root, use this foreground PowerShell command after confirming `8877` is free. It binds loopback, seeds only synthetic demo data and leaves default writes/network off. Stop with Ctrl+C.

```powershell
$repo = (Get-Location).Path
$testRoot = Join-Path $repo 'outputs/spec005-test-final-closure-20261101-01'
$previewRoot = Join-Path $testRoot 'preview-root'
$python = Join-Path $repo 'outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe'
$testHome = Join-Path $testRoot 'home'
$temp = Join-Path $testRoot 'tmp'
if (-not (Test-Path -LiteralPath (Join-Path $testRoot '.test-owned'))) { throw 'Synthetic parent marker missing.' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Project interpreter missing.' }
if (Test-Path -LiteralPath $previewRoot) {
  if (@(Get-ChildItem -LiteralPath $previewRoot -Force).Count -ne 0) { throw 'Preview root must be fresh.' }
} else {
  New-Item -ItemType Directory -Path $previewRoot | Out-Null
}

$env:HOME = $testHome
$env:USERPROFILE = $testHome
$env:HOMEDRIVE = $testHome.Substring(0, 2)
$env:HOMEPATH = $testHome.Substring(2)
$env:TEMP = $temp
$env:TMP = $temp
$env:APPDATA = Join-Path $testHome 'AppData/Roaming'
$env:LOCALAPPDATA = Join-Path $testHome 'AppData/Local'
$env:XDG_CACHE_HOME = Join-Path $testHome '.cache'
$env:XDG_CONFIG_HOME = Join-Path $testHome '.config'
$env:XDG_DATA_HOME = Join-Path $testHome '.local/share'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONNOUSERSITE = '1'
$env:HEDGE_FUND_TEST_MODE = '1'
$env:HEDGE_FUND_TEST_ROOT = $testRoot
$env:PYTHONPATH = (Join-Path $repo 'hedge_fund/test_support') + [System.IO.Path]::PathSeparator + $repo
$secretNames = @(
  'ANTHROPIC_API_KEY','OPENAI_API_KEY','XAI_API_KEY','DEEPSEEK_API_KEY','GOOGLE_API_KEY',
  'KIMI_API_KEY','TYPESAFE_API_KEY','MOONSHOT_API_KEY','FINANCIAL_DATASETS_API_KEY',
  'SAXO_API_KEY','SAXO_CLIENT_ID','SAXO_CLIENT_SECRET','SAXO_APP_KEY_REF',
  'SAXO_APP_SECRET_REF','SAXO_REFRESH_TOKEN_REF','SAXO_REFRESH_LOCK_DIR','OPENROUTER_API_KEY','MISTRAL_API_KEY',
  'COHERE_API_KEY','GROQ_API_KEY','HF_TOKEN','HUGGINGFACEHUB_API_TOKEN',
  'AZURE_OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN',
  'AWS_SECURITY_TOKEN','AWS_PROFILE','AWS_SHARED_CREDENTIALS_FILE','AWS_CONFIG_FILE',
  'GOOGLE_APPLICATION_CREDENTIALS','AZURE_OPENAI_AD_TOKEN','AZURE_CLIENT_SECRET',
  'AZURE_FEDERATED_TOKEN_FILE',
  'HEDGE_FUND_LLM_MODEL','HEDGE_FUND_LLM_PROVIDER','HEDGE_FUND_DATA_PROVIDER',
  'HEDGE_FUND_LLM_ENDPOINT','HEDGE_FUND_ROOT','HEDGE_FUND_HOME','AIHF_ROOT',
  'OPENAI_API_BASE','OLLAMA_BASE_URL'
)
$proxyNames = @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')
foreach ($name in ($secretNames + $proxyNames)) { Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $previewRoot -Force | Out-Null
Set-Location $repo
& $python -m hedge_fund.web --demo --root $previewRoot --port 8877
```

`--demo` needs no provider keys. For any separately authorized local/free paper setup, policy accepts free `yfinance` data with a local Ollama model only; this does not establish safe existing-root deployment. Do not pass paid API keys. Headless paid-provider defaults remain open and unsupported. Do not add `--allow-writes`, `--enable-network`, `--load-dotenv` or `--build` to this preview command.

## Next stop

Keep PR #8 open and explicitly marked partial/not merge-ready. Do not merge. Before any existing-root deployment or TUI-removal proposal, complete T015/T021, remaining T137–T148, native Linux/ext4 and actual ACL acceptance, wheel installation/runtime smoke, and full-suite completion. Use a new discriminating review plan if those gates remain stalled.
