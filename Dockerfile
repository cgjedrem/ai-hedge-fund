# The AI hedge fund in a container: the same app, two ways to run it.
#
#   Interactive TUI:   docker build -t aihf . && docker run -it --rm aihf
#   Headless runner:   docker run -d --restart unless-stopped aihf paper run watchtower
#
# All state — funds, ledgers, caches, and the .env key file — lives in
# ~/.hedge-fund, which you mount as a volume; nothing is baked into the
# image. The runner's clock is New-York-aware internally, so the container's
# own timezone does not matter.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    MPLCONFIGDIR=/tmp/mpl \
    TZ=America/New_York

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first: this layer only rebuilds when the lockfile changes.
COPY pyproject.toml poetry.lock ./
RUN pip install poetry==2.5.1 \
    && poetry install -E yfinance --only main --no-root

# ttyd serves the TUI to a browser tab — used by the tui-web service in
# docker-compose.linux.yml (e.g. a home server exposing it over Tailscale).
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64', '/usr/local/bin/ttyd')" \
    && chmod +x /usr/local/bin/ttyd

COPY hedge_fund ./hedge_fund
COPY README.md ./
RUN poetry install -E yfinance --only main

# `aihf` alone starts the TUI; anything after the image name is passed to
# it, e.g. `docker run ... aihf-image paper run watchtower`.
ENTRYPOINT ["aihf"]