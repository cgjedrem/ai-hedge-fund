"""Offline-only fixtures for web adapter tests."""

import pytest
from fastapi.testclient import TestClient

from hedge_fund.llm import PROVIDER_ENV_VARS
from hedge_fund.web.app import create_app
from hedge_fund.web.demo import seed_demo


@pytest.fixture(autouse=True)
def deny_network_and_clear_provider_credentials(monkeypatch):
    for env_var in (
        *PROVIDER_ENV_VARS.values(),
        "FINANCIAL_DATASETS_API_KEY",
        "HEDGE_FUND_LLM_MODEL",
    ):
        monkeypatch.delenv(env_var, raising=False)


@pytest.fixture
def demo_root(tmp_path):
    return seed_demo(tmp_path / "demo-root")


@pytest.fixture
def write_client(demo_root):
    app = create_app(
        root=demo_root,
        allow_writes=True,
        demo=True,
    )
    with TestClient(app) as client:
        capabilities = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1"},
        ).json()
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": capabilities["mutation_token"],
        }
        yield client, headers
