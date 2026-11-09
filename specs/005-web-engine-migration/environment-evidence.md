# Environment evidence — spec005

## Result

**T006 PASS — tooling and host filesystem inventory recorded.** This does not pass
native Linux/ext4 or runner acceptance. Windows is the observed host; Linux/ext4
runtime behavior remains **BLOCKED** pending an authorized ext4 runtime and tests.

## Host and tooling

| Item | Observed | Time / provenance | Scope |
|---|---|---|---|
| Windows | Windows 11 Enterprise, version `10.0.26200`, build `26200` | `2026-10-31T17:32:11.7590288+01:00` → `2026-10-31T17:32:19.1487375+01:00`; PowerShell `Get-CimInstance Win32_OperatingSystem` | Host metadata only |
| Worktree filesystem | `C:` is `NTFS` | Same PowerShell probe; `Get-Volume -DriveLetter C` | Confirms host volume type, not lock/ACL/identity primitives |
| Python / Poetry | Python `3.13.7`; Poetry `2.5.1` | Same probe; `python --version`, `python -m poetry --version` | Poetry installed in the host Python user site |
| Isolated Python | `outputs/spec005-test-py-49656-70719f85/aihf-Tbl0PwyA-py3.13/Scripts/python.exe` | Explicit interpreter used by isolated tests | Test-owned venv. `python -m poetry` from this venv reports `No module named poetry`; browser acceptance therefore passed its absolute `AIHF_E2E_PYTHON` path rather than relying on Poetry discovery. |
| Node / npm | Node `v22.13.1`; npm `10.9.2` | `2026-10-31T17:30:24.3632789+01:00`; direct version commands | Tool version only |
| Frontend packages | `@playwright/test 1.64.1`; Vite `6.4.5`; Vitest `4.1.12`; TypeScript `5.9.3` | `2026-10-31T17:39:35.9351683+01:00`; local package metadata from `frontend/node_modules` | Installed locked frontend dependencies |
| Browser | Microsoft Edge `156.0.4314.50`; Playwright used the installed `msedge` channel | `2026-10-31T17:32:11.7590288+01:00` → `2026-10-31T17:32:19.1487375+01:00`; executable version metadata | Browser/tool availability only |
| Docker | Docker client/server `29.9.2`; server metadata `linux/amd64` | `2026-10-31T17:39:36.0287862+01:00` → `2026-10-31T17:39:36.3830616+01:00`; `docker --version` and `docker version --format` | Metadata only. No container or compose service inspected, created, started, or stopped. |
| WSL | Only registered distribution reported: `docker-desktop` | Same Windows/WSL probe above; `wsl.exe --list --quiet`, exit 0 | No general Linux user distribution was available in the listing |

## Dependency preparation

- An earlier offline `npm ci` failed `ENOTCACHED` for `yallist-3.1.1.tgz`.
- The later authorized locked install `npm ci --ignore-scripts --no-audit --fund=false`
  completed **311 packages in 52 s**. Start/end timestamps were not retained.
- Locked Poetry main and dev groups installed into the isolated venv: **113 installs,
  0 updates, 0 removals, 32.51 s**. Start/end timestamps were not retained.
- Installation was limited to the approved frontend/Python dependency sets. No paid
  provider, brokerage, or LLM call was made.

## Filesystem and platform availability

- **Windows / NTFS:** available and directly identified. This does not establish the
  ownership, ACL, lock, atomic-replace, or runner lifecycle contracts; each remains
  subject to its own native tests and evidence.
- **Linux / ext4:** **BLOCKED**. Docker server metadata identifies a Linux engine, but
  no ext4 mount was inspected or tested. The only WSL distribution listed was
  `docker-desktop`. Overlay/container metadata is not ext4 evidence.
- **Container observer:** **BLOCKED / not exercised**. No container was created or
  inspected, and no existing compose service was queried or operated.
- The Linux engine and NTFS host facts are not interchangeable. Linux/ext4,
  POSIX lifecycle, observer-container, and related platform acceptance rows stay
  pending or blocked until a test-owned scenario produces actual evidence.

## Safety and provenance

- Python tests used the marked checkout-owned venv and session roots; HOME, USERPROFILE,
  TEMP/TMP and XDG paths were redirected; `PYTHON_DOTENV_DISABLED=1`; credential,
  provider, proxy and root overrides were cleared before application imports.
- Browser acceptance used `outputs/spec005-test-e2e-49624-1bb7f233`, a marked demo root,
  explicit loopback port `8876`, fixture-owned static/cache paths and the installed Edge
  channel. The root was absent after the run; server PID `49664` was absent; the exclusive
  port-bind probe exited 0.
- No real `~/.hedge-fund` root, user credential/configuration, protected runner, existing
  compose service, port `8765`, external provider or paid service was accessed.
- Evidence source: direct PowerShell, Python, Node, browser and Docker metadata output in
  this worktree. Earlier dependency-install durations are retained without timestamps;
  they are not treated as platform runtime acceptance.
