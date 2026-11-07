"""Every TUI test runs against a scratch home directory and without the network."""

from unittest.mock import Mock

import pytest
import requests

from hedge_fund import paths
from hedge_fund.llm import PROVIDER_ENV_VARS
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext
from hedge_fund.tui import keys


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path, monkeypatch):
    """Bind each test to its own enrolled synthetic root.

    Mandates and research live inside that root, as they do in production, so
    TUI writes meet the same registry/research admission. ``PAPER_DIR`` is a
    seed-only directory outside the root: tests build ledgers there directly,
    while the TUI itself must deny every paper write it cannot admit.
    """
    monkeypatch.chdir(tmp_path)
    saved = tmp_path / "user" / ".env"
    saved.parent.mkdir()
    root_path = tmp_path / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as context, paths.bound_root(context), monkeypatch.context() as bound:
        enroll_fresh(context)
        mandates = paths.MANDATES_DIR
        mandates.mkdir()
        paths.RESEARCH_DIR.mkdir()
        # Scoped so these are undone before bound_root restores the session root.
        bound.setattr(paths, "PAPER_DIR", tmp_path / "paper")
        bound.setattr(paths, "ENV_PATH", saved)
        bound.setattr(paths, "ensure_mandates_dir", lambda: mandates)
        monkeypatch.setattr(keys, "ENV_PATH", saved)
        for variable in (*PROVIDER_ENV_VARS.values(), "MOONSHOT_API_KEY", "FINANCIAL_DATASETS_API_KEY", "HEDGE_FUND_LLM_MODEL", "UNRELATED_KEY"):
            # Track even initially absent keys, since dotenv and the UI set them
            # directly rather than through monkeypatch.
            monkeypatch.setenv(variable, "")
            monkeypatch.delenv(variable, raising=False)
        monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("No live HTTP in TUI tests")))
        yield saved
