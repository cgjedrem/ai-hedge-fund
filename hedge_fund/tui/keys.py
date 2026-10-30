"""Where API keys live, and how they get there.

Secrets live in ``~/.hedge-fund/.env`` (see paths.py), loaded by
``python-dotenv`` at every entry point — this module writes to that same file
rather than inventing a second store. Two rules follow from it:

1. **The environment wins.** A key exported in your shell, or injected by CI,
   is always what runs; ``load_dotenv()`` does not override an existing
   variable. ``.env`` is a fallback for people who do not want to manage
   exports, never an override.
2. **Edits are surgical.** Saving a key rewrites exactly the one line that
   defines it and leaves every other line — other keys, comments, blanks —
   byte-for-byte intact. A settings screen must never eat a file it did not
   write.

Textual-free on purpose, like shared.py — the CLI can use this too.
"""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

from hedge_fund.llm import env_var_for, PROVIDER_ENV_VARS  # noqa: F401  (re-export)
from hedge_fund.paths import ENV_PATH, write_atomic


def apply_credentials() -> None:
    """Load .env files into the environment without overriding what is already
    set. Call once at startup, before anything builds an agent. A ``.env`` in
    the current directory (a checkout) wins over the user-level file."""
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(ENV_PATH, override=False)


def save_credential(env_var: str, value: str, *, path: str | Path | None = None) -> Path:
    """Write one key into .env, replacing its line if present and appending
    otherwise, then export it for this process. Returns the file it wrote.

    Everything else in the file survives untouched — this is a line edit, not
    a regenerate.
    """
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_var):
        raise ValueError("environment variable name is invalid")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise ValueError("credential value contains control characters")
    path = Path(ENV_PATH if path is None else path)
    line = f"{env_var}={_quote(value)}"
    if path.exists():
        original = path.read_text()
        # Match an assignment at the start of a line, optionally exported and
        # optionally commented-out, so re-saving a disabled key revives it.
        pattern = re.compile(rf"^[ \t]*#?[ \t]*(?:export[ \t]+)?{re.escape(env_var)}[ \t]*=.*$", re.MULTILINE)
        updated, count = pattern.subn(lambda _: line, original, count=1)
        if count == 0:
            sep = "" if not original or original.endswith("\n") else "\n"
            updated = f"{original}{sep}{line}\n"
    else:
        updated = f"{line}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, updated)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    os.environ[env_var] = value
    return path


def missing_key(provider: str) -> str | None:
    """The env var this provider needs, if it is not set — otherwise None.
    Named as a question so it reads at the call site: `if missing_key(p):`."""
    name = env_var_for(provider)
    if name is None or os.environ.get(name):
        return None
    return name


def masked(value: str) -> str:
    """A key as it should appear on screen: enough to recognise, not enough
    to use. Short strings are hidden outright rather than half-revealed."""
    if len(value) <= 12:
        return "•" * len(value)
    return f"{value[:6]}{'•' * 8}{value[-4:]}"


def _quote(value: str) -> str:
    """Quote only when the value would not survive unquoted. Most API keys are
    bare tokens, and quoting those would look wrong next to hand-written lines.
    """
    if value and not re.search(r"[\s#'\"\\]", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
