import json
import logging
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hedge_fund.llm import DEFAULT_MODEL, load_api_models
from hedge_fund.llm.registry import is_supported
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import CredentialRequest, ModelRequest
from hedge_fund.web.services import DeskService, ServiceError


def test_settings_expose_presence_not_provider_values(tmp_path, monkeypatch):
    sentinel = "ANTHROPIC_KEY_SENTINEL_NEVER_RETURN"
    monkeypatch.setenv("ANTHROPIC_API_KEY", sentinel)
    service = DeskService(tmp_path)

    result = service.settings()

    anthropic = next(item for item in result["providers"] if item["provider"] == "Anthropic")
    assert anthropic == {
        "provider": "Anthropic",
        "requires_key": True,
        "configured": False,
        "version": 0,
    }
    assert sentinel not in json.dumps(result)
    service.close()


def test_service_does_not_load_root_environment_implicitly(tmp_path, monkeypatch):
    file_secret = "ROOT_ENV_SECRET_SENTINEL"
    model = next(model_id for _, model_id, _ in load_api_models() if model_id != DEFAULT_MODEL)
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={file_secret}\nHEDGE_FUND_LLM_MODEL={model}\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)

    service = DeskService(tmp_path, network_enabled=True)

    settings = service.settings()
    anthropic = next(item for item in settings["providers"] if item["provider"] == "Anthropic")
    assert anthropic["configured"] is False
    assert settings["model"] == DEFAULT_MODEL
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "HEDGE_FUND_LLM_MODEL" not in os.environ
    assert file_secret not in json.dumps(settings)
    service.close()

    shell_secret = "SHELL_ENV_SECRET_SENTINEL"
    monkeypatch.setenv("ANTHROPIC_API_KEY", shell_secret)
    second_service = DeskService(tmp_path, network_enabled=True)
    assert os.environ["ANTHROPIC_API_KEY"] == shell_secret
    assert not next(
        item
        for item in second_service.settings()["providers"]
        if item["provider"] == "Anthropic"
    )["configured"]
    second_service.close()


def test_read_only_offline_startup_skips_root_env_loading(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "ANTHROPIC_API_KEY=OFFLINE_ROOT_SENTINEL\nHEDGE_FUND_LLM_MODEL=offline-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    service = DeskService(tmp_path, allow_writes=False, network_enabled=False)

    assert os.environ.get("ANTHROPIC_API_KEY") is None
    assert os.environ.get("HEDGE_FUND_LLM_MODEL") is None
    assert not service.settings()["providers"][0]["configured"]
    service.close()


def test_credential_write_is_allowlisted_write_only_and_control_safe(tmp_path, caplog):
    enroll_synthetic_root(tmp_path)
    sentinel = "WRITE_ONLY_CREDENTIAL_SENTINEL"
    service = DeskService(tmp_path, allow_writes=True)
    caplog.set_level(logging.DEBUG)

    try:
        result = service.set_credential(
            CredentialRequest(
                provider="Anthropic",
                value=SecretStr(sentinel),
                expected_version=0,
            )
        )

        assert result == {"provider": "Anthropic", "configured": True, "version": 1}
        assert sentinel not in json.dumps(result)
        assert sentinel not in caplog.text
        assert not (tmp_path / ".env").exists()
        credential_file = tmp_path / "runtime" / "private" / "v1" / "credentials" / "anthropic" / "1.json"
        assert sentinel in credential_file.read_text(encoding="utf-8")
        with pytest.raises(ServiceError) as invalid:
            service.set_credential(
                CredentialRequest(
                    provider="Ollama",
                    value=SecretStr("key"),
                    expected_version=0,
                )
            )
        with pytest.raises(ServiceError) as control:
            service.set_credential(
                CredentialRequest(
                    provider="Anthropic",
                    value=SecretStr("line1\nline2"),
                    expected_version=1,
                )
            )
        assert invalid.value.status_code == 400
        assert control.value.status_code == 400
        assert "line1" not in control.value.detail
    finally:
        service.close()


def test_model_setting_is_catalog_allowlisted_and_persisted_by_root(tmp_path, monkeypatch):
    models = [model_id for _, model_id, provider in load_api_models() if is_supported(provider)]
    if len(models) < 2:
        pytest.skip("model catalog does not expose two options")
    starting_model, model = models[:2]
    original = f"HEDGE_FUND_LLM_MODEL={starting_model}\nKEEP_THIS=unchanged\n"
    (tmp_path / ".env").write_text(original, encoding="utf-8")
    enroll_synthetic_root(tmp_path)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    service = DeskService(tmp_path, allow_writes=True)

    try:
        result = service.set_model(ModelRequest(model=model, expected_version=service.settings()["version"]))

        assert result == {"model": model, "scope": "root", "version": 1}
        assert service.settings()["model"] == model
        assert "HEDGE_FUND_LLM_MODEL" not in os.environ
        assert (tmp_path / ".env").read_text(encoding="utf-8") == original
        with pytest.raises(ServiceError) as unknown:
            service.set_model(ModelRequest(model="unregistered-model", expected_version=1))
        assert unknown.value.status_code == 400
        assert "unregistered-model" not in unknown.value.detail
    finally:
        service.close()

    restarted = DeskService(tmp_path)
    try:
        assert restarted.settings()["model"] == model
        assert restarted.settings()["version"] == 1
    finally:
        restarted.close()


def test_effective_settings_resolve_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", DEFAULT_MODEL)
    service = DeskService(tmp_path)

    result = service.settings()

    assert result["data_provider"] == "fd"
    assert result["llm_provider"] == "Ollama"
    assert result["provenance"]["data_provider"] == "environment"
    assert result["provenance"]["model"] == "environment"
    assert result["data_providers"] == [
        {
            "id": "fd",
            "label": "Financial Datasets",
            "requires_key": True,
            "configured": False,
            "version": 0,
        },
        {
            "id": "yfinance",
            "label": "Yahoo Finance",
            "requires_key": False,
            "configured": True,
            "version": 0,
        },
    ]
    service.close()


def test_settings_can_change_without_mutating_existing_capture_snapshot(tmp_path):
    models = [model_id for _, model_id, provider in load_api_models() if is_supported(provider)]
    model = next(model_id for model_id in models if model_id != DEFAULT_MODEL)
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        captured = freeze_capture(
            root=service.root_context,
            subject_id="demo-alpha",
            mandate_digest="a" * 64,
            universe=("AAPL",),
            broker="paper",
            settings=service._runtime_settings,
            credential_versions={},
            code_version="test-version",
        )

        result = service.set_model(ModelRequest(model=model, expected_version=service.settings()["version"]))

        assert result["version"] == captured.settings_version + 1
        assert captured.model == DEFAULT_MODEL
        assert captured.settings_version == 0
        assert service.settings()["model"] == model
    finally:
        service.close()


def test_runtime_settings_api_persists_validated_effective_values(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    model = next(
        model_id
        for _, model_id, provider in load_api_models()
        if provider == "Ollama" and is_supported(provider) and not model_id.endswith(":cloud")
    )
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        response = client.put(
            "/api/settings",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": token,
            },
            json={
                "data_provider": "fd",
                "model": model,
                "endpoint": "http://127.0.0.1:11434",
                "timeout_seconds": 45,
                "parameters": {
                    "context_size": 16384,
                    "max_tokens": 4096,
                    "temperature": 0.4,
                    "top_p": 0.8,
                },
                "expected_version": 0,
            },
        )

    assert response.status_code == 200
    assert response.json()["scope"] == "root"
    assert response.json()["version"] == 1
    assert response.json()["data_provider"] == "fd"
    assert response.json()["endpoint"] == "http://127.0.0.1:11434"
    assert response.json()["parameters"] == {
        "context_size": 16384,
        "max_tokens": 4096,
        "temperature": 0.4,
        "top_p": 0.8,
    }
    assert (tmp_path / "runtime" / "private" / "v1" / "settings.json").is_file()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "data_provider": "yfinance",
            "model": DEFAULT_MODEL,
            "endpoint": "http://provider.example",
            "timeout_seconds": 30,
            "parameters": {},
            "expected_version": 0,
        },
        {
            "data_provider": "yfinance",
            "model": DEFAULT_MODEL,
            "endpoint": None,
            "timeout_seconds": True,
            "parameters": {},
            "expected_version": 0,
        },
        {
            "data_provider": "yfinance",
            "model": "gpt-6-sol",
            "endpoint": None,
            "timeout_seconds": 30,
            "parameters": {"context_size": 8192},
            "expected_version": 0,
        },
        {
            "data_provider": "yfinance",
            "model": DEFAULT_MODEL,
            "endpoint": None,
            "timeout_seconds": 30,
            "parameters": {"temperature": True},
            "expected_version": 0,
        },
    ],
)
def test_runtime_settings_api_rejects_invalid_values_before_persistence(tmp_path, payload):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        response = client.put(
            "/api/settings",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": token,
            },
            json=payload,
        )

    assert response.status_code == 400
    assert not (tmp_path / "runtime" / "private" / "v1" / "settings.json").exists()


def test_credential_validation_errors_do_not_echo_request_values(tmp_path):
    enroll_synthetic_root(tmp_path)
    sentinel = "SECRET_SENTINEL_MUST_NOT_ECHO"
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        control = client.post(
            "/api/settings/credentials",
            headers=headers,
            json={
                "provider": "Anthropic",
                "value": f"{sentinel}\nSECOND",
                "expected_version": 0,
            },
        )
        malformed = client.post(
            "/api/settings/credentials",
            headers=headers,
            json={
                "provider": "Anthropic",
                "value": {"secret": sentinel},
                "expected_version": 0,
            },
        )

    assert control.status_code == 400
    assert malformed.status_code == 400
    assert sentinel not in control.text
    assert sentinel not in malformed.text
    assert not (tmp_path / ".env").exists()
