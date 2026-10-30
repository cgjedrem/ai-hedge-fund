"""Offline-only fixtures for web adapter tests."""

import ipaddress
import socket

import pytest
from fastapi.testclient import TestClient

from hedge_fund.llm import PROVIDER_ENV_VARS
from hedge_fund.web.app import create_app
from hedge_fund.web.demo import seed_demo


@pytest.fixture(autouse=True)
def deny_network_and_clear_provider_credentials(monkeypatch):
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def loopback_only(address):
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
        except (AttributeError, ValueError):
            return False

    def connect_local_only(connection, address):
        if not loopback_only(address):
            raise AssertionError("web tests cannot connect outside loopback")
        return original_connect(connection, address)

    def create_local_only(address, *args, **kwargs):
        if not loopback_only(address):
            raise AssertionError("web tests cannot connect outside loopback")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect_local_only)
    monkeypatch.setattr(socket, "create_connection", create_local_only)
    for env_var in (*PROVIDER_ENV_VARS.values(), "FINANCIAL_DATASETS_API_KEY", "HEDGE_FUND_LLM_MODEL"):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")


@pytest.fixture
def demo_root(tmp_path):
    return seed_demo(tmp_path / "demo-root")


@pytest.fixture
def write_client(demo_root):
    with TestClient(create_app(root=demo_root, allow_writes=True, demo=True)) as client:
        capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": capabilities["mutation_token"],
        }
        yield client, headers
