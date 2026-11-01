# The AI hedge fund in a container.
#
#   mkdir -p "$PWD/.aihf-demo-data"
#   Interactive TUI: docker run -it --rm -v "$PWD/.aihf-demo-data:/data" aihf
#
# Data lives under the explicitly mounted root. Runner example uses local
# Ollama and free Yahoo data only through the Linux Compose override.

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
RUN mkdir -p /data

# Dependencies first: this layer only rebuilds when the lockfile changes.
COPY pyproject.toml poetry.lock ./
RUN pip install poetry==2.5.1 \
    && poetry install --only main --no-root

# ttyd serves the legacy TUI to a loopback browser tab.
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64', '/usr/local/bin/ttyd')" \
    && chmod +x /usr/local/bin/ttyd

COPY hedge_fund ./hedge_fund
COPY README.md ./
RUN poetry install --only main

ENTRYPOINT ["aihf", "--root", "/data"]