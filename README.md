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

(or `uv tool install aihf`, or `pip install aihf` into an environment of your choice)

Then run it from anywhere:

```bash
aihf
```

### API keys

The app asks for keys the first time it needs them and saves them to `~/.hedge-fund/.env` — nothing to configure up front. It needs:

- A [Financial Datasets](https://financialdatasets.ai) API key, for prices, fundamentals, and earnings.
- One model API key for the investor agents. Supported providers: Anthropic, OpenAI, DeepSeek, Google, xAI, Kimi, TypeSafe (Jev) — or Ollama, which runs locally and needs no key at all.

Keys exported in your shell always win over the saved file.

### Free market data (optional)

Day-to-day paper trading and iteration can run on free Yahoo Finance data
instead of spending Financial Datasets credits:

```bash
pip install aihf[yfinance]        # or: poetry install -E yfinance
export HEDGE_FUND_DATA_PROVIDER=yfinance
```

One caveat: Yahoo serves fundamentals as reported *now*, not point-in-time
— so backtests on the free provider leak the future into the past. Keep
`HEDGE_FUND_DATA_PROVIDER=fd` (the default) for final backtest validation.

## How to Run

### Interactive app

```bash
aihf
```

With no arguments, this launches the interactive terminal app. It has two modes:

- **Paper trading** — your funds, each with a ledger of real market days and fake money. Highlight a fund to see what its next run will do; press enter to review and run the next session, `y`/`n` to approve or reject a gated decision, `s` for history, and `h`/`r` for the kill switch. Build a new fund from the same list: strategies, capital, cadence, approval mode, tickers, and it is live. Every session is appended to a hash-chained ledger in `~/.hedge-fund/paper/<name>/`, so NAV is a track record, not a reset.
- **Backtesting** — replay a fund over history and watch its equity curve draw against its benchmark. Results are saved to `~/.hedge-fund/research/`. Fund definitions live in `~/.hedge-fund/mandates/` and carry no tickers; you pick the universe per backtest.

### Local React desk

The React desk is additive; the Textual TUI and its entry points remain available.
It serves a local production build through FastAPI. Views use saved records and
do not fetch live quotes.

```bash
poetry install -E web
make web
```

`make web` installs frontend build dependencies, creates the static bundle, and
starts a synthetic demo on `http://127.0.0.1:8765`. Demo files live in a temporary
directory and are removed when the server exits. Node is needed for the build,
not for Python to serve an already-built bundle.

To inspect the configured `~/.hedge-fund` root, build the bundle and start the
read-only, network-off server:

```bash
make web-build
poetry run aihf-web
```

An alternate local data root can be selected explicitly with `--root PATH`.
General writes and external network access are separate, immutable startup
capabilities. The default has neither. Backtests require both:

```bash
poetry run aihf-web --allow-writes --enable-network
```

Use those flags only when intentionally submitting local changes or historical
provider requests. The default Financial Datasets provider is paid; no view
fetches it automatically. Runner start/stop, manual runs, deletion, ledger redo,
and live quote fetching remain unavailable in the web desk. See the
[TUI parity checklist](specs/004-react-web-ui/parity-checklist.md) for all
supported and deferred workflows.

#### Docker Compose web service

The web profile builds local assets in a Node stage and runs a Python-only
image. Compose publishes the service only on host loopback:

```bash
docker compose --profile web up --build web
```

Open `http://127.0.0.1:8765`. The service reads the mounted local data root and
starts read-only with network access disabled. Do not publish this port on a
non-loopback interface. On Linux, the override keeps the same loopback port
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
aihf backtest ~/.hedge-fund/mandates/example.yaml --universe AAPL,MSFT --rebalance monthly
aihf paper create alpha --mandate ~/.hedge-fund/mandates/example.yaml --universe AAPL,MSFT --rebalance daily
```

### Per-fund approval gate

Approval is opt-in. `approval_required` defaults to `false`; without it, pending
decisions execute as they do today. Enable the gate on a new paper fund with
`approval_required: true` in its mandate, the Approval step in the TUI paper
builder, or `--approval` at CLI creation:

```bash
aihf paper create alpha --mandate ~/.hedge-fund/mandates/example.yaml --universe AAPL,MSFT --approval
aihf paper approve alpha             # queue approval for the next session
aihf paper approve alpha --now       # execute now if a session is due
aihf paper reject alpha
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

The same app in a container. All state — funds, ledgers, caches, and the `.env` key file — stays in `~/.hedge-fund`, which is mounted as a volume; nothing is baked into the image.

```bash
docker build -t aihf .

# Interactive TUI (needs a terminal):
docker run -it --rm -v ~/.hedge-fund:/root/.hedge-fund aihf

# Headless runner for one fund, surviving restarts:
docker run -d --name aihf-watchtower --restart unless-stopped \
    -v ~/.hedge-fund:/root/.hedge-fund aihf paper run watchtower
```

Or with compose (`docker-compose.yml` in this repo): `docker compose up -d runner` for the runner, `docker compose run --rm tui` for the app. One runner per fund — copy the service and change the fund name; the compose file ships a second one, `runner-weekly`, for the `watchtower-weekly` comparison fund (the same mandate as `watchtower` on a weekly cadence). After a code change, rebuild every runner you use: `docker compose up -d --build runner runner-weekly`. Do not run the same fund's runner on the host and in a container at the same time: pid files cannot see across that boundary, so both would believe they own the fund.

#### Using Ollama models in the container

Ollama models (the keyless ones, e.g. `kimi-k3:cloud`) run on the *host's* Ollama — inside a container, `localhost` is the container itself. Before starting any container:

1. **Run Ollama on the host** — install it and keep the daemon up (`ollama serve` or the desktop app; it listens on `localhost:11434`).
2. **Check the model answers on the host first**: `ollama run kimi-k3:cloud "hi"` (cloud-hosted models may ask you to sign in once).
3. **Point the container at the host** — compose sets `OLLAMA_BASE_URL=http://host.docker.internal:11434` on both services; with plain `docker run`, add `-e OLLAMA_BASE_URL=http://host.docker.internal:11434`.
4. **Sanity-check the wiring** — `curl http://localhost:11434/api/version` on the host should return JSON. If a container's LLM calls fail with "Connection refused", this env var is the first thing to check.

On a Linux host, `host.docker.internal` needs one extra flag: `--add-host=host.docker.internal:host-gateway` for `docker run`, or `extra_hosts: ["host.docker.internal:host-gateway"]` on a compose service. For a Linux home server, prefer the `docker-compose.linux.yml` override instead — see the next section.

#### Home server (Linux + Tailscale)

On a Linux host, Docker Desktop's `host.docker.internal` doesn't exist. Use the Linux override, which runs the containers on the host's own network — `localhost` inside the container *is* the host, so Ollama needs no extra wiring:

```bash
docker compose -f docker-compose.yml -f docker-compose.linux.yml up -d runner   # headless runner
docker compose -f docker-compose.yml -f docker-compose.linux.yml run --rm tui   # terminal TUI
```

Moving a fund from another machine: stop the old runner first (one runner per fund, even across machines), copy the state with `rsync -a ~/.hedge-fund/ server:~/.hedge-fund/`, then start the runner on the server. The LLM cache travels with it, so nothing is recomputed.

Remote access over Tailscale:

1. On the server: install Tailscale and run `tailscale up --ssh` (Tailscale SSH is a Linux feature — your tailnet handles auth, no keys to manage).
2. Terminal TUI from any tailnet device: `ssh <server>`, then `tmux new -s tui` (or `tmux attach -t tui`) and start the TUI with the compose command above. tmux keeps the session alive across disconnects.
3. Browser TUI: `docker compose -f docker-compose.yml -f docker-compose.linux.yml up -d tui-web` serves the full app on `127.0.0.1:7681`. Publish it to your tailnet with HTTPS: `tailscale serve --bg 7681`, then open `https://<server-name>.<tailnet>.ts.net` from any device. Only devices on your tailnet can reach it.

If Ollama runs on a different machine than the server, point `OLLAMA_BASE_URL` at that machine's tailnet IP (e.g. `http://100.x.y.z:11434`) and run Ollama there with `OLLAMA_HOST=0.0.0.0` so it accepts non-local connections.

## Development

```bash
git clone https://github.com/virattt/ai-hedge-fund.git
cd ai-hedge-fund
poetry install
poetry run aihf
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
