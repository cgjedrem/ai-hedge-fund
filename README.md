# AI Hedge Fund

This is a proof of concept for an AI-powered hedge fund. The goal of this project is to explore the use of AI to make trading decisions. This project is for **educational** purposes only and is not intended for real trading or investment.

<img width="2400" height="1460" alt="image" src="https://github.com/user-attachments/assets/e3985623-c226-4c1a-a587-e03fb4eca31e" />


Note: the system does not actually make any trades.

[![Twitter Follow](https://img.shields.io/twitter/follow/virattt?style=social)](https://twitter.com/virattt)

## Disclaimer

This project is for **educational and research purposes only**.

- Not intended for real trading or investment
- No investment advice or guarantees provided
- Creator assumes no liability for financial losses
- Consult a financial advisor for investment decisions
- Past performance does not indicate future results

By using this software, you agree to use it solely for learning purposes.

## How to Install

```bash
pipx install aihf
```

(or `uv tool install aihf`, or `pip install aihf`)

Choose an absolute data root. The CLI requires it on every launch:

```bash
export AIHF_ROOT="$HOME/.aihf-data"
mkdir -p "$AIHF_ROOT"
aihf --root "$AIHF_ROOT"
```

PowerShell:

```powershell
$env:AIHF_ROOT = Join-Path $HOME ".aihf-data"
New-Item -ItemType Directory -Force $env:AIHF_ROOT | Out-Null
aihf --root $env:AIHF_ROOT
```

### API keys

The app stores user state under the selected root. It needs:

- Market data defaults to credential-free Yahoo Finance. A [Financial Datasets](https://financialdatasets.ai) API key is needed only when explicitly selecting paid provider `fd`.
- One model API key for the selected cloud investor provider — or Ollama, which runs locally and needs no key.

Keys exported in your shell always win over the saved file.

### Market data

Credential-free Yahoo Finance is the default and part of the base dependency
set; no provider extra is required.

Financial Datasets is an explicit paid provider selected with
`HEDGE_FUND_DATA_PROVIDER=fd`. Yahoo fundamentals are reported as of now,
not point-in-time; backtests using Yahoo data can leak future information.

## How to Run

### Interactive app

```bash
aihf --root "$AIHF_ROOT"
```

With no arguments, this launches the interactive terminal app. It has two modes:

- **Paper trading** — your funds, each with a ledger of market days and paper money. Highlight a fund to review its next run; use `y`/`n` for gated decisions, `s` for history, and `h`/`r` for halt/resume. Sessions live in the selected root's `paper/<name>/`.
- **Backtesting** — replay a fund over history and compare its equity curve with a benchmark. Results live in the selected root's `research/`; mandates live in `mandates/` and carry no tickers.

### Local React desk

The React desk is additive; the Textual TUI and its entry points remain available.
It serves a local production build through FastAPI. Views use saved records and
do not fetch live quotes.

```bash
poetry install -E web
make web
```

`make web` installs frontend build dependencies, creates the static bundle, and
starts a synthetic demo on `http://127.0.0.1:8876`. Demo files live in a temporary
directory and are removed when the server exits. Node is needed for the build,
not for Python to serve an already-built bundle.

On Windows, use the native launcher instead of GNU Make:

```powershell
poetry install -E web
poetry run aihf-web --build --demo
```

`--build` runs `npm ci` from `frontend/package-lock.json`, builds the production
bundle, then starts the server. It requires Node.js and npm on `PATH`; a clean
checkout also needs package-registry access for the initial npm install. The
server does not need Node after the bundle exists. Running `aihf-web` from a
source checkout without built assets exits with build instructions. Packaged
wheels serve their included static bundle without Node. Non-demo launches
require an explicit existing `--root`; demo mode uses an isolated temporary
root.

#### Frontend development with Vite

For hot reload, start a separate synthetic API in one terminal:

```bash
poetry run aihf-web --demo --port 8766
```

In another terminal:

```bash
cd frontend
npm ci
AIHF_WEB_API_TARGET=http://127.0.0.1:8766 npm run dev
```

In PowerShell, run
`$env:AIHF_WEB_API_TARGET = "http://127.0.0.1:8766"` before `npm run dev`.
Open `http://127.0.0.1:5173`. Add `--allow-writes` to the demo server only
when testing synthetic mutations; network access stays off. Vite listens on
loopback and proxies `/api` without changing `Host` or `Origin`. The FastAPI
loopback, same-origin and CSRF checks remain active; no cross-origin exception
is added.

To inspect an existing root, build the bundle and start the read-only,
network-off server:

```bash
make web-build
poetry run aihf-web --root "$AIHF_ROOT"
```

For the same launch through Make, pass the selected root explicitly:

```bash
AIHF_ROOT="$HOME/.aihf-data" make web-local
```

General writes and external network access are separate, immutable startup
capabilities. The default has neither. Backtests require both:

```bash
poetry run aihf-web --root "$AIHF_ROOT" --allow-writes --enable-network
```

Use those flags only when intentionally submitting local changes or historical
provider requests. Reviewed web backtests permit free Yahoo data and local
Ollama only. Explicit valuation refresh also requires both capabilities and
uses free Yahoo quotes; page loads never fetch. Exchange-print freshness is
unverified. Runner start/stop, manual runs, deletion, ledger redo, and paid
market-data calls remain unavailable in the web desk. See the
[TUI parity checklist](specs/004-react-web-ui/parity-checklist.md) for all
supported and deferred workflows.

Backtests show a confirmation of the provider, model, agent count, tickers and
date range before submission. There are no automatic retries. Cancellation is
cooperative at valuation boundaries; closing the browser does not cancel a job.
Server shutdown requests cancellation and waits for active work, including any
report write already in progress.

#### Docker Compose web service

The web profile builds local assets in a Node stage and runs a Python-only
image. Compose publishes the service only on host loopback:

```bash
docker compose --profile web up --build web
```

Open `http://127.0.0.1:8876`. The service reads the mounted local data root and
starts read-only with network access disabled. Set `AIHF_DATA_ROOT` to an
existing absolute data root before running Compose; for example:

```bash
export AIHF_DATA_ROOT="$PWD/.aihf-demo-data"
mkdir -p "$AIHF_DATA_ROOT"
```

Do not publish this port on a non-loopback interface. On Linux, the override keeps the same loopback port
mapping and adds an explicit host-gateway alias for an Ollama workflow that a
user separately enables:

```bash
docker compose -f docker-compose.yml -f docker-compose.linux.yml --profile web up --build web
```

### Mandate cadence

The `rebalance` field accepts `minute`, `daily`, `weekly`, or `monthly`
(default: `weekly`). Daily, weekly, and monthly funds rebalance on the first
session of each period; minute funds rebalance every eligible bar.
`interval` and `window` apply only to minute funds.

Override cadence for a backtest or when creating a paper fund; the mandate
file stays unchanged:

```bash
aihf --root "$AIHF_ROOT" backtest "$AIHF_ROOT/mandates/example.yaml" --universe AAPL,MSFT --rebalance monthly
aihf --root "$AIHF_ROOT" paper create alpha --mandate "$AIHF_ROOT/mandates/example.yaml" --universe AAPL,MSFT --rebalance daily
```

### Per-fund approval gate

Approval is opt-in. `approval_required` defaults to `false`; without it, pending
decisions execute as they do today. Enable the gate on a new paper fund with
`approval_required: true` in its mandate, the Approval step in the TUI paper
builder, or `--approval` at CLI creation:

```bash
aihf --root "$AIHF_ROOT" paper create alpha --mandate "$AIHF_ROOT/mandates/example.yaml" --universe AAPL,MSFT --approval
aihf --root "$AIHF_ROOT" paper approve alpha             # queue approval for the next session
aihf --root "$AIHF_ROOT" paper approve alpha --now       # execute now if a session is due
aihf --root "$AIHF_ROOT" paper reject alpha
```

In the TUI fund screen, `y` approves and `n` rejects a pending decision. A
matching approval executes at the next session; `--now` executes immediately
when one is due. If no session is due, `--now` keeps the verdict and reports
that it will execute at the next close.

The verdict lives in `pending-approval.json` in the fund directory, keyed to
the decision. A rejected, missing, or stale verdict skips execution at the
next session, records an audit event, marks the book, and lets the decision
lapse. The fund keeps running; weekly/monthly funds remain mark-only until
their next decision period. The gate is separate from the kill switch:
`halt`/`resume` behavior is unchanged.

### Docker

Containers require an explicit host data root. Compose runner profiles use
local Ollama and free Yahoo data; no runner starts by default.

```bash
docker build -t aihf .
export AIHF_DATA_ROOT="$PWD/.aihf-demo-data"
mkdir -p "$AIHF_DATA_ROOT"

# Interactive TUI (needs a terminal). Image binds its root to /data:
docker run -it --rm -v "$AIHF_DATA_ROOT:/data" aihf

# One bounded local tick for an existing demo-alpha paper fund:
docker run --rm -v "$AIHF_DATA_ROOT:/data" \
    -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    -e HEDGE_FUND_LLM_MODEL=gemma3:4b \
    -e HEDGE_FUND_DATA_PROVIDER=yfinance \
    aihf --model gemma3:4b paper tick demo-alpha
```

Compose paper-tick profiles are opt-in and use generic example subjects:

```bash
docker compose --profile runner run --rm runner
docker compose run --rm tui
docker compose --profile web up --build web
```

The web profile mounts the same root read-only. Rebuild only the selected
service after code changes. Do not run one paper fund from multiple processes.

#### Using Ollama models in the container

The local `gemma3:4b` model runs on the host's Ollama — inside a container,
`localhost` is the container itself. Before starting a runner:

1. **Run Ollama on the host** — install it and keep the daemon up (`ollama serve` or the desktop app; it listens on `localhost:11434`).
2. **Check the model answers on the host first**: `ollama run gemma3:4b "hi"`.
3. **Point the container at the host** — compose sets `OLLAMA_BASE_URL=http://host.docker.internal:11434` on both services; with plain `docker run`, add `-e OLLAMA_BASE_URL=http://host.docker.internal:11434`.
4. **Sanity-check the wiring** — `curl http://localhost:11434/api/version` on the host should return JSON. If a container's LLM calls fail with "Connection refused", this env var is the first thing to check.

On a Linux host, `host.docker.internal` needs one extra flag: `--add-host=host.docker.internal:host-gateway` for `docker run`, or `extra_hosts: ["host.docker.internal:host-gateway"]` on a compose service. For a Linux home server, prefer the `docker-compose.linux.yml` override instead — see the next section.

#### Linux host networking (local-only)

On a Linux host, Docker Desktop's `host.docker.internal` doesn't exist. Use the Linux override, which runs the containers on the host's own network — `localhost` inside the container *is* the host, so Ollama needs no extra wiring:

```bash
docker compose -f docker-compose.yml -f docker-compose.linux.yml --profile runner run --rm runner   # one local tick
docker compose -f docker-compose.yml -f docker-compose.linux.yml run --rm tui   # terminal TUI
```

The web observer remains host-loopback-published. Remote access, reverse proxies,
and non-loopback publication are unsupported. The legacy browser TUI also remains
local-only.

## Development

```bash
git clone https://github.com/virattt/ai-hedge-fund.git
cd ai-hedge-fund
poetry install
export AIHF_ROOT="$HOME/.aihf-data"
mkdir -p "$AIHF_ROOT"
poetry run aihf --root "$AIHF_ROOT"
poetry run pytest hedge_fund
```

## How to Contribute

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

**Important**: Please keep your pull requests small and focused. This will make it easier to review and merge.

## Feature Requests

If you have a feature request, please open an [issue](https://github.com/virattt/ai-hedge-fund/issues) and make sure it is tagged with `enhancement`.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
