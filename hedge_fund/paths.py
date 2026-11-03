"""Where user data lives: ~/.hedge-fund/.

Everything the user owns — mandates, paper funds and their ledgers,
backtest results, API caches, and the .env key file — lives under one home
directory, outside the package. The package directory stays read-only code,
so a pipx install behaves exactly like a checkout.

    mandates/<name>.yaml           templates: the desk, no state
    paper/<name>/                  a deployed fund: fund.yaml, ledger/, broker.json,
                                   control.json, events.jsonl
    research/<fund>-<start>-<end>-<stamp>.json   backtest results, disposable

Textual-free and import-light on purpose: every layer (CLI, TUI, caches)
anchors its paths here, and nothing here may import them back.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

USER_DIR = Path.home() / ".hedge-fund"
MANDATES_DIR = USER_DIR / "mandates"
PAPER_DIR = USER_DIR / "paper"
RESEARCH_DIR = USER_DIR / "research"
CACHE_DIR = USER_DIR / "cache"
ENV_PATH = USER_DIR / ".env"

# The example mandate ships inside the package; it is copied out (never read
# in place) so users edit their copy, not the install.
EXAMPLE_MANDATE = Path(__file__).resolve().parent / "fund" / "example.yaml"


def ensure_mandates_dir() -> Path:
    """Create the mandates dir on first use, seeded with the example."""
    if not MANDATES_DIR.exists():
        MANDATES_DIR.mkdir(parents=True)
        shutil.copy(EXAMPLE_MANDATE, MANDATES_DIR / "example.yaml")
    return MANDATES_DIR


def write_atomic(path: Path, text: str, *, mode: int | None = None) -> None:
    """Atomically replace *path*; apply optional mode before writing."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    if mode is not None and (type(mode) is not int or not 0 <= mode <= 0o777):
        raise ValueError("mode must contain permission bits")

    descriptor = None
    try:
        descriptor = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode if mode is not None else 0o666)
        if mode is not None:
            if os.name == "posix":
                os.fchmod(descriptor, mode)
            else:
                os.chmod(tmp, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        tmp.unlink(missing_ok=True)
        raise
