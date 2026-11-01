# Spec005 QA final disposition

## Status

**PARTIAL — NOT READY TO MERGE. Full migration remains BLOCKED.** This bounded closure fixes the supplied final-QA defects and adds an installed-wheel loopback smoke for code revision `5c7e2a902d85aaf5ce18963aa3e5e7de6b734514`. It does not complete Spec005, enable production writes, authorize paid/headless dispatch or retire the TUI.

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
| Wheel | **PASS — build and bounded installed-wheel runtime smoke.** Wheel SHA-256, source mapping, dependency paths and GET-only loopback evidence are in `spec005-final-evidence.md`. Not full migration acceptance. |
| Static checks | **PARTIAL — inherited Black baseline.** Isort, flake8 and diff check passed; `test_actions.py` Black failure also exists at base HEAD, with no changed-line formatter overlap. |
| Full Python suite | **INCONCLUSIVE.** Prior attempts stalled at 149 passed / 2 skipped of 1,207 collected. No full-suite rerun. |
| Linux/ext4 and actual NTFS ACL | **BLOCKED.** Not exercised on this Windows host. |

## Migration blockers

- T015/T021 remain partial. Admission and handover do not fence unaware legacy/out-of-band writers; `fund/storage.py` and `backtesting/research.py` are not fully integrated.
- T137/T138/T140/T142–T145/T147/T148 remain open. T139/T141/T146 have bounded partial evidence but stay unchecked.
- Full provider-operation authorization, durable reconciliation/runner lifecycle, complete `FundSpec` browser parity, report export/drilldown, native platform gates and full-suite completion remain open.
- React desk remains an additive subset. TUI/Textual and operator recovery paths remain intact. TUI retirement is **BLOCKED**.
- SIM denials remain in place. No resume enablement or write-surface expansion was attempted.
- The final wheel installed and served a read-only synthetic demo on loopback; no container acceptance was run.

## Installed-wheel smoke and safe preview handoff

The installed wheel smoke passed against code revision `5c7e2a902d85aaf5ce18963aa3e5e7de6b734514`. Wheel SHA-256 is `db57b12627fcb5bf86b2587c1842cf7e6a5a9be7de01768d1721f50b68cc19e0`; its three static assets match bundle hash `309b88c7a472685221fee0cb89f207d9d72e8f36d9f38a2a9a2301c82df7897a`. Install used `--no-deps --no-index` into an isolated task-owned target; package modules loaded from that target, not checkout source. Runtime GET checks returned 200 for `/`, `/api/capabilities` and both referenced static assets; capabilities reported `read_only=true`, `writes=false`, `network=false`.

No preview is running now. The detached launch attempt (shell ID `2792`) exited with code 1 before a listener was observed; no diagnostic line was captured. Attached verification ran on `127.0.0.1:8877` under PID `38972` / shell ID `2795`, then was stopped by PID; listener count was 0. `http://127.0.0.1:8877` is only a local URL when the command below is running. Recheck port availability before start.

The following foreground PowerShell command reuses the built wheel and existing project dependency environment. It installs the local wheel into a fresh isolated target, binds loopback, seeds only synthetic demo data and leaves writes/network off. It does not build, load dotenv, import checkout source or activate a provider. Stop with Ctrl+C.

```powershell
$repo = (Get-Location).Path
$testRoot = Join-Path $repo 'outputs/spec005-test-final-closure-20261101-01'
$smokeRoot = Join-Path $testRoot 'wheel-smoke-20261101-1200'
$wheelSite = Join-Path $smokeRoot 'site-preview'
$previewRoot = Join-Path $smokeRoot 'preview-root-repeat'
$wheel = Join-Path $repo 'dist/aihf-2.6.1-py3-none-any.whl'
$python = Join-Path $repo 'outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe'
$testHome = Join-Path $smokeRoot 'home-preview'
$temp = Join-Path $smokeRoot 'tmp-preview'
if (-not (Test-Path -LiteralPath (Join-Path $testRoot '.test-owned'))) { throw 'Synthetic parent marker missing.' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Project interpreter missing.' }
if (-not (Test-Path -LiteralPath $wheel)) { throw 'Final wheel missing.' }
if (Get-NetTCPConnection -LocalPort 8877 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8877 is occupied.' }
if (-not (Test-Path -LiteralPath $smokeRoot)) { New-Item -ItemType Directory -Path $smokeRoot | Out-Null }
if (Test-Path -LiteralPath $wheelSite) { throw 'Wheel target must be fresh.' }
if ((Test-Path -LiteralPath $testHome) -or (Test-Path -LiteralPath $temp)) { throw 'Isolated HOME and TEMP must be fresh.' }
if (Test-Path -LiteralPath $previewRoot) {
  if (@(Get-ChildItem -LiteralPath $previewRoot -Force).Count -ne 0) { throw 'Preview root must be fresh.' }
}

foreach ($path in @($wheelSite,$testHome,$temp,$previewRoot)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
foreach ($path in @((Join-Path $testHome 'AppData/Roaming'),(Join-Path $testHome 'AppData/Local'),(Join-Path $testHome '.cache'),(Join-Path $testHome '.config'),(Join-Path $testHome '.local/share'))) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
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
$env:PYTHONSAFEPATH = '1'
$env:PYTHONPATH = $wheelSite
$env:PIP_CONFIG_FILE = Join-Path $testRoot 'empty-pip.ini'
$env:PIP_NO_INDEX = '1'
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
  'OPENAI_API_BASE','OLLAMA_BASE_URL','NEWS_API_KEY','ALPHA_VANTAGE_API_KEY','FRED_API_KEY',
  'POLYGON_API_KEY','FINNHUB_API_KEY','TIINGO_API_KEY','MARKET_DATA_API_KEY','DATA_API_KEY',
  'GITHUB_TOKEN','GH_TOKEN','PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_TRUSTED_HOST'
)
$proxyNames = @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')
foreach ($name in ($secretNames + $proxyNames)) { Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue }
foreach ($name in @('HEDGE_FUND_TEST_MODE','HEDGE_FUND_TEST_ROOT','AIHF_WEB_STATIC_DIR','PYTHONHOME')) { Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue }
Set-Location $smokeRoot
& $python -m pip --isolated install --no-deps --no-index --no-cache-dir --target $wheelSite $wheel
$installExit = $LASTEXITCODE
if ($installExit -ne 0) { throw 'Local wheel install failed.' }
& $python -m hedge_fund.web --demo --root $previewRoot --port 8877
```

`--demo` needs no provider keys. This smoke checked HTTP GET only; it did not test browser-to-backend mutations. For any separately authorized local/free paper setup, policy accepts free `yfinance` data with a local Ollama model only; this does not establish safe existing-root deployment. Do not pass paid API keys. Headless paid-provider defaults remain open and unsupported. Do not add `--allow-writes`, `--enable-network`, `--load-dotenv` or `--build` to this preview command.

## Next stop

Keep PR #8 open and explicitly marked partial/not merge-ready. Do not merge. Before any existing-root deployment or TUI-removal proposal, complete T015/T021, remaining T137–T148, native Linux/ext4 and actual ACL acceptance, and full-suite completion. Use a new discriminating review plan if those gates remain stalled.
