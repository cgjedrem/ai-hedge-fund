import json
import logging
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hedge_fund.llm import DEFAULT_MODEL, load_api_models
from hedge_fund.llm.registry import is_supported
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import CredentialRequest, ModelRequest
from hedge_fund.web.services import DeskService, ServiceError


def test_settings_expose_presence_not_provider_values(tmp_path, monkeypatch):
    sentinel = "ANTHROPIC_KEY_SENTINEL_NEVER_RETURN"
    monkeypatch.setenv("ANTHROPIC_API_KEY", sentinel)
    service = DeskService(tmp_path)

    result = service.settings()

    anthropic = next(item for item in result["providers"] if item["provider"] == "Anthropic")
    assert anthropic == {"provider": "Anthropic", "requires_key": True, "configured": True}
    assert sentinel not in json.dumps(result)
    service.close()


def test_root_env_is_loaded_without_overriding_process_values(tmp_path, monkeypatch):
    file_secret = "ROOT_ENV_SECRET_SENTINEL"
    model = next(model_id for _, model_id, _ in load_api_models() if model_id != DEFAULT_MODEL)
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={file_secret}\nHEDGE_FUND_LLM_MODEL={model}\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)

    service = DeskService(tmp_path)

    settings = service.settings()
    anthropic = next(item for item in settings["providers"] if item["provider"] == "Anthropic")
    assert anthropic["configured"] is True
    assert settings["model"] == model
    assert os.environ["ANTHROPIC_API_KEY"] == file_secret
    assert file_secret not in json.dumps(settings)
    service.close()

    second_root = tmp_path / "second"
    second_root.mkdir()
    (second_root / ".env").write_text("ANTHROPIC_API_KEY=FILE_VALUE_MUST_NOT_OVERRIDE\n")
    shell_secret = "SHELL_ENV_SECRET_SENTINEL"
    monkeypatch.setenv("ANTHROPIC_API_KEY", shell_secret)
    second_service = DeskService(second_root)
    assert os.environ["ANTHROPIC_API_KEY"] == shell_secret
    second_service.close()


def test_credential_write_is_allowlisted_write_only_and_control_safe(tmp_path, caplog):
    sentinel = "WRITE_ONLY_CREDENTIAL_SENTINEL"
    service = DeskService(tmp_path, allow_writes=True)
    caplog.set_level(logging.DEBUG)

    result = service.set_credential(CredentialRequest(provider="Anthropic", value=SecretStr(sentinel)))

    assert result == {"provider": "Anthropic", "configured": True}
    assert sentinel not in json.dumps(result)
    assert sentinel not in caplog.text
    assert sentinel in (tmp_path / ".env").read_text(encoding="utf-8")
    with pytest.raises(ServiceError) as invalid:
        service.set_credential(CredentialRequest(provider="Ollama", value=SecretStr("key")))
    with pytest.raises(ServiceError) as control:
        service.set_credential(CredentialRequest(provider="Anthropic", value=SecretStr("line1\nline2")))
    assert invalid.value.status_code == 422
    assert control.value.status_code == 422
    assert "line1" not in control.value.detail
    service.close()


def test_model_setting_is_catalog_allowlisted_and_process_only(tmp_path, monkeypatch):
    models = [model_id for _, model_id, provider in load_api_models() if is_supported(provider)]
    if len(models) < 2:
        pytest.skip("model catalog does not expose two options")
    starting_model, model = models[:2]
    original = f"HEDGE_FUND_LLM_MODEL={starting_model}\nKEEP_THIS=unchanged\n"
    (tmp_path / ".env").write_text(original, encoding="utf-8")
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    service = DeskService(tmp_path, allow_writes=True)

    result = service.set_model(ModelRequest(model=model))

    assert result == {"model": model, "scope": "process"}
    assert service.settings()["model"] == model
    assert os.environ["HEDGE_FUND_LLM_MODEL"] == model
    assert (tmp_path / ".env").read_text(encoding="utf-8") == original
    with pytest.raises(ServiceError) as unknown:
        service.set_model(ModelRequest(model="unregistered-model"))
    assert unknown.value.status_code == 422
    assert "unregistered-model" not in unknown.value.detail
    service.close()


def test_credential_validation_errors_do_not_echo_request_values(tmp_path):
    sentinel = "SECRET_SENTINEL_MUST_NOT_ECHO"
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        control = client.post(
            "/api/settings/credentials",
            headers=headers,
            json={"provider": "Anthropic", "value": f"{sentinel}\nSECOND"},
        )
        malformed = client.post(
            "/api/settings/credentials",
            headers=headers,
            json={"provider": "Anthropic", "value": {"secret": sentinel}},
        )

    assert control.status_code == 422
    assert malformed.status_code == 422
    assert sentinel not in control.text
    assert sentinel not in malformed.text
    assert not (tmp_path / ".env").exists()
