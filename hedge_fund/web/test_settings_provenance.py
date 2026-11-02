"""Spec005 T145 (bounded): stored/effective/active configuration provenance."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hedge_fund.llm import DEFAULT_MODEL, load_api_models
from hedge_fund.llm.registry import is_supported
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import (
    describe_configuration,
    RuntimeSettings,
    save_settings,
)
from hedge_fund.runtime.operations import OperationStatus
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import (
    CredentialRequest,
    ModelRequest,
    RuntimeSettingsRequest,
)
from hedge_fund.web.services import DeskService, ServiceError

ENV_ORIGIN = "https://env-private-origin.invalid/tenant-path"
STORED_ORIGIN = "https://stored-origin.invalid/v1"
SECRET = "SYNTHETIC_PROVENANCE_CREDENTIAL_SENTINEL"


def _other_model() -> str:
    return next(model_id for _, model_id, provider in load_api_models() if is_supported(provider) and model_id != DEFAULT_MODEL)


def _capture(service: DeskService, credential_versions: dict[str, int] | None = None):
    return freeze_capture(
        root=service.root_context,
        subject_id="demo-alpha",
        mandate_digest="a" * 64,
        universe=("AAPL",),
        broker="paper",
        settings=service._runtime_settings,
        credential_versions=credential_versions or {},
        code_version="test-version",
    )


def _activate(service: DeskService, monkeypatch, capture, status=OperationStatus.RUNNING) -> None:
    operation = SimpleNamespace(capture_id=capture.capture_id, subject_id="demo-alpha", status=status, payload={})
    monkeypatch.setattr(service, "_active_operation_captures", lambda: [(operation, capture)])


def test_default_stored_effective_and_active_are_equal(tmp_path):
    service = DeskService(tmp_path)
    try:
        result = service.settings()
        configuration = result["configuration"]
        assert configuration["stored"] == {"available": True, "version": 0, "present": False}
        assert configuration["effective"] == {"version": 0, "startup_version": 0}
        assert configuration["overrides"] == []
        assert configuration["restart_required"] is False
        assert configuration["restart_reasons"] == []
        assert configuration["credential_captures"] == []
        assert configuration["policy"] == {
            "hot_reload": False,
            "environment_read_at": "startup",
            "process_environment_credentials_used": False,
            "restart_action": "manual",
        }
        assert all(field["source"] == "default" and field["stored_source"] == "default" and not field["diverges"] and field["override"] is None for field in configuration["fields"])
        assert configuration["stored_values"] == RuntimeSettings().to_mapping()
        assert result["endpoint_redacted"] is False
    finally:
        service.close()


def test_environment_override_divergence_is_named_but_redacted(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    writer = DeskService(tmp_path, allow_writes=True)
    try:
        writer.save_runtime_settings(
            RuntimeSettingsRequest(
                data_provider="yfinance",
                model=DEFAULT_MODEL,
                endpoint=STORED_ORIGIN,
                timeout_seconds=60,
                parameters={},
                expected_version=0,
            )
        )
    finally:
        writer.close()
    monkeypatch.setenv("HEDGE_FUND_LLM_ENDPOINT", ENV_ORIGIN)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    service = DeskService(tmp_path)
    try:
        result = service.settings()
        payload = json.dumps(result)
        assert ENV_ORIGIN not in payload
        assert "env-private-origin" not in payload
        assert result["endpoint"] is None
        assert result["endpoint_redacted"] is True
        configuration = result["configuration"]
        fields = {field["field"]: field for field in configuration["fields"]}
        assert fields["endpoint"] == {
            "field": "endpoint",
            "source": "environment",
            "override": "HEDGE_FUND_LLM_ENDPOINT",
            "stored_source": "persisted",
            "stored": "remote",
            "effective": "remote",
            "redacted": True,
            "diverges": True,
            "shadowed": True,
        }
        assert fields["data_provider"]["source"] == "environment"
        assert fields["data_provider"]["stored"] == "yfinance"
        assert fields["data_provider"]["effective"] == "fd"
        assert fields["model"]["diverges"] is False
        assert {item["variable"] for item in configuration["overrides"]} == {"HEDGE_FUND_LLM_ENDPOINT", "HEDGE_FUND_DATA_PROVIDER"}
        assert configuration["restart_reasons"] == ["override-shadows-stored"]
        assert configuration["restart_required"] is True
        assert str(tmp_path) not in payload
        public_capture = _capture(service).public_view(current_settings_version=0)
        assert public_capture["endpoint"] is None
        assert public_capture["endpoint_redacted"] is True
        assert ENV_ORIGIN not in json.dumps(public_capture)
    finally:
        service.close()


def test_version_changes_and_external_writer_require_restart_and_reject_stale_saves(tmp_path):
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        service.set_model(ModelRequest(model=_other_model(), expected_version=0))
        configuration = service.settings()["configuration"]
        assert configuration["stored"]["version"] == 1
        assert configuration["effective"] == {"version": 1, "startup_version": 0}
        assert configuration["restart_required"] is False

        save_settings(service.root_context, {"timeout_seconds": 30.0}, expected_version=1, admission=service._admission)

        result = service.settings()
        configuration = result["configuration"]
        assert result["version"] == 1
        assert result["timeout_seconds"] == 60.0
        assert configuration["stored"]["version"] == 2
        assert configuration["restart_reasons"] == ["stored-version-changed"]
        assert configuration["stored_values"] is None
        assert {field["field"]: field for field in configuration["fields"]}["timeout_seconds"]["diverges"] is True
        with pytest.raises(ServiceError) as stale:
            service.set_model(ModelRequest(model=DEFAULT_MODEL, expected_version=1))
        assert stale.value.status_code == 409
        assert stale.value.code == "stale-preview"
        assert service.settings()["version"] == 1
    finally:
        service.close()


def test_settings_update_after_snapshot_keeps_active_capture_without_server_restart(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        captured = _capture(service)
        _activate(service, monkeypatch, captured)
        assert service.settings()["configuration"]["restart_required"] is False

        service.set_model(ModelRequest(model=_other_model(), expected_version=0))

        result = service.settings()
        assert result["active_captures"][0]["restart_needed"] is True
        assert result["active_captures"][0]["model"] == DEFAULT_MODEL
        assert result["active_captures"][0]["settings_version"] == 0
        configuration = result["configuration"]
        assert configuration["active"] == {"available": True, "count": 1, "stale_count": 1}
        # The running snapshot is immutable; a server restart would not update it and
        # new work already uses the saved version, so no restart is requested.
        assert configuration["restart_reasons"] == []
        assert configuration["restart_required"] is False
        assert captured.model == DEFAULT_MODEL
    finally:
        service.close()


def test_credential_deleted_after_capture_keeps_captured_version_without_echoing_it(tmp_path, monkeypatch):
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)
    try:
        saved = service.set_credential(CredentialRequest(provider="OpenAI", value=SecretStr(SECRET), expected_version=0))
        captured = _capture(service, {"openai": saved["version"]})
        _activate(service, monkeypatch, captured)
        entry = service.settings()["configuration"]["credential_captures"][0]
        assert entry["state"] == "current"

        deleted = service.delete_credential("OpenAI", expected_version=saved["version"])

        result = service.settings()
        entry = result["configuration"]["credential_captures"][0]
        assert entry == {
            "capture_id": captured.capture_id,
            "subject_id": "demo-alpha",
            "status": "running",
            "provider": "openai",
            "captured_version": 1,
            "current_version": deleted["version"],
            "configured": False,
            "captured_version_retained": True,
            "state": "deleted-after-capture",
        }
        assert service._credential_store.read_version("openai", 1) == SECRET
        assert SECRET not in json.dumps(result)
        with pytest.raises(ServiceError) as stale:
            service.delete_credential("OpenAI", expected_version=saved["version"])
        assert stale.value.status_code == 409
    finally:
        service.close()


def test_describe_configuration_without_stored_record_is_unavailable_not_guessed():
    view = describe_configuration(stored=None, effective=RuntimeSettings(), startup_version=0)
    assert view["stored"] == {"available": False, "version": None, "present": False}
    assert all(field["stored"] is None and field["diverges"] is False for field in view["fields"])
    assert view["restart_required"] is False


def test_settings_api_exposes_provenance_only_to_loopback_same_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("HEDGE_FUND_LLM_ENDPOINT", ENV_ORIGIN)
    with TestClient(create_app(root=tmp_path), client=("127.0.0.1", 50000)) as client:
        remote = client.get("/api/settings", headers={"host": "desk.attacker.example"})
        foreign = client.get("/api/settings", headers={"host": "127.0.0.1", "origin": "https://desk.attacker.example"})
        local = client.get("/api/settings", headers={"host": "127.0.0.1", "origin": "http://127.0.0.1"})
    assert remote.status_code == 403
    assert foreign.status_code == 403
    assert local.status_code == 200
    assert ENV_ORIGIN not in local.text
    body = local.json()
    assert body["configuration"]["overrides"] == [{"field": "endpoint", "source": "environment", "variable": "HEDGE_FUND_LLM_ENDPOINT"}]
    assert body["configuration"]["stored"]["version"] == 0
