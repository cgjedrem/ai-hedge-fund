import io
import json
import logging
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hedge_fund.llm import DEFAULT_MODEL, load_api_models
from hedge_fund.llm.registry import is_supported, ModelCatalogEntry
from hedge_fund.runtime.capture import (
    CredentialHandle,
    freeze_capture,
    root_identity_id,
)
from hedge_fund.runtime.credential_delivery import (
    CredentialDeliveryServer,
    DeliveryEnvelope,
    encode_delivery_frame,
    read_delivery_reply,
)
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    RuntimeCredentialLeaseStore,
)
from hedge_fund.runtime.operations import OperationError
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.test_support.network_guard import (
    child_test_environment,
    guarded_test_python_command,
)
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import CredentialRequest, ModelRequest
from hedge_fund.web.services import DeskService, ServiceError


def test_settings_and_catalog_expose_ollama_model_classifiers(tmp_path):
    service = DeskService(tmp_path)
    try:
        settings = service.settings()
        catalog = service.catalog()

        for response in (settings, catalog):
            ollama = next(item for item in response["models"] if item["id"] == "kimi-k3:cloud")
            ollama_pro = next(item for item in response["models"] if item["id"] == "kimi-k3.1-pro:cloud")
            assert ollama == {
                "label": "Kimi K3 Cloud",
                "id": "kimi-k3:cloud",
                "provider": "Ollama",
                "capability": "chat",
                "cost_class": "paid-cloud",
            }
            assert ollama_pro == {
                "label": "Kimi K3.1 Pro Cloud",
                "id": "kimi-k3.1-pro:cloud",
                "provider": "Ollama",
                "capability": "chat",
                "cost_class": "paid-cloud",
            }
            assert all(set(item) == {"label", "id", "provider"} for item in response["models"] if item["provider"] != "Ollama")
    finally:
        service.close()


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


def test_external_runtime_status_is_disabled_and_never_exposes_mapping(tmp_path, monkeypatch):
    reference = "op://SyntheticVault/SyntheticItem/api-key"
    monkeypatch.delenv("HEDGE_FUND_RUNTIME_ROLE", raising=False)
    service = DeskService(tmp_path)

    status = service.credential_status()["external_runtime"]

    assert status == {"state": "disabled", "providers": {}}
    assert reference not in json.dumps(status)
    assert "value" not in json.dumps(status)
    service.close()


def test_operator_allowlist_comes_from_provider_ids_and_stays_value_free(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_ROLE", "web-operator")
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_PROVIDERS", "openai")
    monkeypatch.setattr(CredentialDeliveryServer, "start", lambda self: None)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        status = service.credential_status()["external_runtime"]
        assert status == {
            "state": "configured",
            "providers": {"openai": {"state": "requires-auth", "generation": 0}},
        }
        assert "op://" not in json.dumps(status)
        assert "secret" not in json.dumps(status).casefold()
    finally:
        service.close()


@pytest.mark.skipif(os.name != "posix", reason="Unix peer credentials required")
def test_runtime_delivery_uses_service_admission_and_real_receiver_process(tmp_path, monkeypatch):
    assert os.environ.get("HEDGE_FUND_TEST_MODE") == "1"
    enroll_synthetic_root(tmp_path)
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_ROLE", "web-operator")
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_PROVIDERS", "fd")
    service = DeskService(tmp_path, allow_writes=True)
    store = service._external_credential_store
    assert store is not None
    assert service.credential_status()["external_runtime"]["state"] == "configured"
    root_id = root_identity_id(service.root_context)
    instance_id = store._instance_id
    receiver = guarded_test_python_command(
        "-m",
        "hedge_fund.runtime.credential_delivery",
        "--receive",
    )
    repository = Path(__file__).resolve().parents[2]

    def exchange(request):
        result = subprocess.run(
            receiver,
            cwd=repository,
            input=encode_delivery_frame(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
            env=child_test_environment(),
        )
        assert result.stderr == b""
        reply = read_delivery_reply(io.BytesIO(result.stdout))
        assert result.returncode == (2 if reply.state == "denied" else 0)
        return reply

    try:
        published = exchange(
            DeliveryEnvelope(
                action="publish",
                provider_id="fd",
                destination="fd",
                root_id=root_id,
                instance_id=instance_id,
                expected_generation=0,
                delivery_id="synthetic-publish-1",
                value="synthetic-only-runtime-value",
            )
        )
        assert published.state == "available"
        assert published.generation == 1

        status = exchange(
            DeliveryEnvelope(
                action="status",
                provider_id="fd",
                destination="fd",
            )
        )
        assert status.state == "available"
        assert status.generation == 1

        assert service._owner_lease is not None
        service._owner_lease.close()
        denied = exchange(
            DeliveryEnvelope(
                action="publish",
                provider_id="fd",
                destination="fd",
                root_id=root_id,
                instance_id=instance_id,
                expected_generation=1,
                delivery_id="synthetic-publish-2",
                value="synthetic-replacement-value",
            )
        )
        assert denied.state == "denied"
        assert denied.reason_code == "delivery-denied"
        assert store.status()["fd"] == {"state": "available", "generation": 1}
    finally:
        service.close()


def test_operator_delivery_role_keeps_provider_allowlist_empty_by_default(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_ROLE", "web-operator")
    monkeypatch.delenv("HEDGE_FUND_RUNTIME_PROVIDERS", raising=False)
    monkeypatch.setattr(CredentialDeliveryServer, "start", lambda self: None)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        assert service.credential_status()["external_runtime"] == {
            "state": "unconfigured",
            "providers": {},
        }
    finally:
        service.close()


def test_runtime_revoke_maps_invalid_provider_closed_store_and_generation_cas(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_ROLE", "web-operator")
    monkeypatch.setenv("HEDGE_FUND_RUNTIME_PROVIDERS", "openai")
    monkeypatch.setattr(CredentialDeliveryServer, "start", lambda self: None)
    service = DeskService(tmp_path, allow_writes=True)
    store = service._external_credential_store
    assert store is not None
    try:
        with pytest.raises(ServiceError) as invalid:
            service.revoke_external_credential("not a provider", expected_generation=0)
        assert invalid.value.status_code == 400

        with pytest.raises(ServiceError) as unconfigured:
            service.revoke_external_credential("fd", expected_generation=0)
        assert unconfigured.value.status_code == 404

        with pytest.raises(ServiceError) as stale:
            service.revoke_external_credential("openai", expected_generation=1)
        assert stale.value.status_code == 409
        assert stale.value.code == "stale-preview"

        revoke = store.revoke

        def deny_revoke(*_args, **_kwargs):
            raise ExternalCredentialError("root identity changed")

        monkeypatch.setattr(store, "revoke", deny_revoke)
        with pytest.raises(ServiceError) as denied:
            service.revoke_external_credential("openai", expected_generation=0)
        assert denied.value.status_code == 403
        assert denied.value.code == "capability-denied"
        monkeypatch.setattr(store, "revoke", revoke)

        store.close()
        with pytest.raises(ServiceError) as closed:
            service.revoke_external_credential("openai", expected_generation=0)
        assert closed.value.status_code == 503
    finally:
        service.close()


def test_external_capture_consumes_only_its_live_process_lease(tmp_path):
    sentinel = "synthetic-runtime-only-key"
    service = DeskService(tmp_path)
    try:
        root_id = root_identity_id(service.root_context)
        store = RuntimeCredentialLeaseStore(
            root_id=root_id,
            instance_id="operator-instance",
            allowed_destinations={"openai": "openai"},
        )
        store.publish(
            "openai",
            sentinel,
            expected_generation=0,
            delivery_id="delivery-1",
            root_id=root_id,
            instance_id="operator-instance",
            destination="openai",
        )
        store.capture("openai", destination="openai")
        service._external_credential_store = store
        handle = CredentialHandle(
            root_id=root_id,
            provider_id="openai",
            version=1,
            source="external-runtime",
            instance_id="operator-instance",
            destination="openai",
        )
        capture = freeze_capture(
            root=service.root_context,
            subject_id="synthetic-fund",
            mandate_digest="a" * 64,
            universe=("AAPL",),
            broker="paper",
            settings=service._runtime_settings,
            credential_versions={"openai": 1},
            credential_handles={"openai": handle},
            code_version="test-version",
        )

        assert service._captured_provider_key(capture, "openai") == sentinel

        class DurableFallbackProbe:
            def read_version(self, *_args):
                raise AssertionError("external capture attempted durable fallback")

        service._credential_store = DurableFallbackProbe()
        store.revoke("openai")
        with pytest.raises(OperationError, match="captured runtime credential is unavailable"):
            service._captured_provider_key(capture, "openai")
    finally:
        service.close()


def test_missing_durable_capture_does_not_fall_back_to_ambient_credentials(tmp_path):
    service = DeskService(tmp_path)
    root_id = root_identity_id(service.root_context)
    handle = CredentialHandle(
        root_id=root_id,
        provider_id="openai",
        version=1,
    )
    capture = freeze_capture(
        root=service.root_context,
        subject_id="synthetic-fund",
        mandate_digest="a" * 64,
        universe=("AAPL",),
        broker="paper",
        settings=service._runtime_settings,
        credential_versions={"openai": 1},
        credential_handles={"openai": handle},
        code_version="test-version",
    )

    class MissingCredentialStore:
        def read_version(self, *_args):
            return None

    service._credential_store = MissingCredentialStore()
    try:
        with pytest.raises(OperationError, match="captured credential is unavailable"):
            service._captured_provider_key(capture, "openai")
    finally:
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
    assert not next(item for item in second_service.settings()["providers"] if item["provider"] == "Anthropic")["configured"]
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
        assert unknown.value.detail == "Model 'unregistered-model' is not in the supported provider catalog."
    finally:
        service.close()

    restarted = DeskService(tmp_path)
    try:
        assert restarted.settings()["model"] == model
        assert restarted.settings()["version"] == 1
    finally:
        restarted.close()


def test_model_write_api_uses_specific_credential_free_rejections(tmp_path, monkeypatch):
    from hedge_fund.web import services as web_services

    enroll_synthetic_root(tmp_path)
    unknown_model = "unregistered-model"
    embedding_model = "nomic-embed-text:latest"
    unsupported_provider_model = "synthetic-google-model"
    lookup = getattr(web_services, "catalog_entry_for", lambda _model_id: None)

    def catalog_entry_for(model_id):
        if model_id == embedding_model:
            return ModelCatalogEntry(
                "Nomic Embed",
                embedding_model,
                "Ollama",
                "embedding",
                "local",
            )
        if model_id == unsupported_provider_model:
            return ModelCatalogEntry(
                "Synthetic Google model",
                unsupported_provider_model,
                "Google",
                "chat",
            )
        return lookup(model_id)

    monkeypatch.setattr(web_services, "catalog_entry_for", catalog_entry_for, raising=False)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        unknown_post = client.post(
            "/api/settings/model",
            headers=headers,
            json={"model": unknown_model, "expected_version": 0},
        )
        unknown_put = client.put(
            "/api/settings",
            headers=headers,
            json={
                "data_provider": "yfinance",
                "model": unknown_model,
                "endpoint": None,
                "timeout_seconds": 60.0,
                "parameters": {},
                "expected_version": 0,
            },
        )
        embedding_post = client.post(
            "/api/settings/model",
            headers=headers,
            json={"model": embedding_model, "expected_version": 0},
        )
        unsupported_provider_post = client.post(
            "/api/settings/model",
            headers=headers,
            json={"model": unsupported_provider_model, "expected_version": 0},
        )

    assert unknown_post.status_code == unknown_put.status_code == 400
    assert unknown_post.json()["detail"] == unknown_put.json()["detail"] == f"Model '{unknown_model}' is not in the supported provider catalog."
    assert embedding_post.status_code == 400
    assert embedding_post.json()["detail"] == f"Model '{embedding_model}' is not chat-capable (embedding)."
    assert unsupported_provider_post.status_code == 400
    assert unsupported_provider_post.json()["detail"] == (f"Model '{unsupported_provider_model}' is not in the supported provider catalog.")
    assert "secret" not in json.dumps([unknown_post.json(), unknown_put.json(), embedding_post.json(), unsupported_provider_post.json()]).casefold()


def test_settings_routes_accept_and_persist_cloud_tag_across_restart(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1"},
        ).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        post = client.post(
            "/api/settings/model",
            headers=headers,
            json={"model": "kimi-k3:cloud", "expected_version": 0},
        )
        put = client.put(
            "/api/settings",
            headers=headers,
            json={
                "data_provider": "yfinance",
                "model": "kimi-k3:cloud",
                "endpoint": None,
                "timeout_seconds": 60,
                "parameters": {},
                "expected_version": 1,
            },
        )

    assert post.status_code == 200
    assert post.json() == {"model": "kimi-k3:cloud", "scope": "root", "version": 1}
    assert put.status_code == 200
    assert put.json()["model"] == "kimi-k3:cloud"
    assert put.json()["llm_provider"] == "Ollama"
    assert put.json()["version"] == 2
    persisted = tmp_path / "runtime" / "private" / "v1" / "settings.json"
    assert json.loads(persisted.read_text(encoding="utf-8"))["model"] == "kimi-k3:cloud"

    restarted = create_app(root=tmp_path)
    with TestClient(restarted, client=("127.0.0.1", 50000)) as client:
        settings = client.get("/api/settings", headers={"host": "127.0.0.1"})

    assert settings.status_code == 200
    assert settings.json()["model"] == "kimi-k3:cloud"
    assert settings.json()["version"] == 2


def test_model_switch_to_paid_cloud_ollama_removes_local_context_size(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1"},
        ).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        configured = client.put(
            "/api/settings",
            headers=headers,
            json={
                "data_provider": "yfinance",
                "model": "gemma3:4b",
                "endpoint": None,
                "timeout_seconds": 60,
                "parameters": {
                    "context_size": 8192,
                    "max_tokens": 4096,
                    "temperature": 0.4,
                    "top_p": 0.8,
                },
                "expected_version": 0,
            },
        )
        assert configured.status_code == 200
        before = client.get("/api/settings", headers={"host": "127.0.0.1"})
        selected = client.post(
            "/api/settings/model",
            headers=headers,
            json={
                "model": "kimi-k3.1-pro:cloud",
                "expected_version": configured.json()["version"],
            },
        )
        after = client.get("/api/settings", headers={"host": "127.0.0.1"})

    assert before.status_code == 200
    assert before.json()["parameters"]["context_size"] == 8192
    assert selected.status_code == 200
    assert selected.json() == {
        "model": "kimi-k3.1-pro:cloud",
        "scope": "root",
        "version": 2,
    }
    assert after.status_code == 200
    assert after.json()["model"] == "kimi-k3.1-pro:cloud"
    assert after.json()["parameters"] == {
        "max_tokens": 4096,
        "temperature": 0.4,
        "top_p": 0.8,
    }


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
    model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and is_supported(provider) and not model_id.endswith(":cloud"))
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
