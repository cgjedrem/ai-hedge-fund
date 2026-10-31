"""TUI adapters for credential prompts and environment loading."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from hedge_fund.llm import env_var_for, PROVIDER_ENV_VARS  # noqa: F401  (re-export)
from hedge_fund.paths import ENV_PATH
from hedge_fund.runtime.credentials import masked, missing_key, save_credential  # noqa: F401


def apply_credentials() -> None:
    """Load local dotenv files without overriding exported variables."""
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(ENV_PATH, override=False)
