import hashlib
import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import (
    _root_id,
    CredentialHandle,
    freeze_capture,
    FrozenCapture,
    root_identity_id,
)
from hedge_fund.runtime.configuration import (
    build_child_environment,
    child_root_arguments,
    ConfigurationError,
    environment_settings,
    load_settings,
    resolve_settings,
    save_settings,
    SettingsConflict,
)
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def root_context(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        yield context


@pytest.fixture
def root_owner(root_context):
    enroll_fresh(root_context)
    owner = RootOwnerLease.acquire(root_context)
    try:
        yield AdmissionCoordinator(root_context, owner_lease=owner)
    finally:
        owner.close()


def test_settings_precedence_uses_launch_environment_persisted_and_free_default(root_context):
    defaults = resolve_settings(root_context)
    persisted = resolve_settings(
        root_context,
        persisted={"data_provider": "fd", "model": "gpt-6-sol"},
    )
    environment = resolve_settings(
        root_context,
        environment={"data_provider": "yfinance", "model": "gemma3:4b"},
        persisted={"data_provider": "fd", "model": "gpt-6-sol"},
    )
    launch = resolve_settings(
        root_context,
        launch={"model": "jev-1.13.0"},
        environment={"data_provider": "yfinance", "model": "gemma3:4b"},
        persisted={"data_provider": "fd", "model": "gpt-6-sol"},
    )

    assert defaults.data_provider == "yfinance"
    assert persisted.data_provider == "fd"
    assert environment.model == "gemma3:4b"
    assert environment.data_provider == "yfinance"
    assert launch.model == "jev-1.13.0"
    assert launch.provenance["model"] == "launch"
    assert launch.provenance["data_provider"] == "environment"


def test_registered_model_selects_provider_without_secret_environment_access(root_context, root_owner):
    settings = resolve_settings(
        root_context,
        environment=environment_settings(
            {
                "HEDGE_FUND_LLM_MODEL": "gpt-6-sol",
                "HEDGE_FUND_LLM_TIMEOUT_SECONDS": "45",
                "OPENAI_API_KEY": "synthetic-secret-value",
                "HEDGE_FUND_ROOT": "synthetic-root",
            }
        ),
    )

    assert settings.model == "gpt-6-sol"
    assert settings.llm_provider == "OpenAI"
    assert settings.timeout_seconds == 45.0
    assert settings.provenance["llm_provider"] == "environment"
    assert "synthetic-secret-value" not in repr(settings.public_view())

    persisted = save_settings(
        root_context,
        {"model": "gpt-6-sol"},
        expected_version=0,
        admission=root_owner,
    )
    assert persisted.llm_provider == "OpenAI"

    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            launch={"model": "gpt-6-sol", "llm_provider": "Anthropic"},
        )


@pytest.mark.parametrize("context_size", [0, 255, 131073, True])
def test_local_context_size_is_bounded(context_size, root_context):
    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            launch={"parameters": {"context_size": context_size}},
        )


def test_context_size_requires_an_ollama_model(root_context):
    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            launch={
                "model": "gpt-6-sol",
                "parameters": {"context_size": 8192},
            },
        )


def test_validated_local_sampling_and_context_settings_are_captured(root_context):
    settings = resolve_settings(
        root_context,
        launch={
            "model": "gemma3:4b",
            "parameters": {
                "context_size": 16384,
                "max_tokens": 2048,
                "temperature": 0.4,
                "top_p": 0.8,
            },
        },
    )
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="a" * 64,
        universe=("AAPL",),
        broker="paper",
        settings=settings,
        credential_versions={},
        code_version="synthetic-code-stamp",
    )

    assert capture.llm_provider == "Ollama"
    assert capture.parameters == {
        "context_size": 16384,
        "max_tokens": 2048,
        "temperature": 0.4,
        "top_p": 0.8,
    }


def test_external_runtime_handle_is_instance_bound_in_capture_and_snapshot(root_context):
    settings = resolve_settings(
        root_context,
        launch={"model": "gpt-6-sol"},
    )
    root_id = _root_id(root_context)
    assert root_identity_id(root_context) == root_id
    handle = CredentialHandle(
        root_id,
        "openai",
        3,
        source="external-runtime",
        instance_id="backend-boot-1",
        destination="openai",
    )
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="b" * 64,
        universe=("AAPL",),
        broker="paper",
        settings=settings,
        credential_versions={"openai": 3},
        credential_handles={"openai": handle},
        code_version="synthetic-code-stamp",
    )

    snapshot = capture.private_bytes()
    restored = FrozenCapture.from_private_bytes(root_context, snapshot)

    assert restored.credential_handles["openai"].source == "external-runtime"
    assert restored.credential_handles["openai"].instance_id == "backend-boot-1"
    assert restored.credential_handles["openai"].destination == "openai"
    assert b"secret" not in snapshot.lower()


def test_external_runtime_handle_requires_instance_and_destination(root_context):
    with pytest.raises(ConfigurationError, match="credential reference is invalid"):
        CredentialHandle("a" * 64, "openai", 1, source="external-runtime")


def test_invalid_mandate_snapshot_is_rejected_before_freezing(root_context):
    with pytest.raises(ConfigurationError, match="mandate snapshot"):
        freeze_capture(
            root=root_context,
            subject_id="alpha",
            mandate_digest="a" * 64,
            universe=("AAA",),
            broker="paper",
            settings=resolve_settings(root_context),
            credential_versions={},
            code_version="synthetic-code-stamp",
            mandate_snapshot={"name": "alpha", "api_key": "synthetic-sentinel"},
        )


def test_runtime_configuration_import_does_not_load_provider_clients(owned_test_process):
    process = owned_test_process("import sys; " "import hedge_fund.runtime.configuration; " "assert 'hedge_fund.llm.client' not in sys.modules")

    assert process.wait(timeout=10) == 0


def test_runtime_provider_catalog_matches_engine_registry():
    from hedge_fund.llm.client import DEFAULT_MODEL
    from hedge_fund.llm.registry import load_api_model_entries, SUPPORTED_PROVIDERS
    from hedge_fund.runtime import configuration

    assert configuration.DEFAULT_MODEL == DEFAULT_MODEL
    assert set(configuration._PROVIDERS.values()) == SUPPORTED_PROVIDERS
    assert configuration._model_catalog() == {entry.model_name: entry for entry in load_api_model_entries()}


def test_cloud_ollama_model_is_selectable_from_all_configuration_sources(root_context):
    default = resolve_settings(root_context)
    persisted = resolve_settings(
        root_context,
        persisted={"model": "kimi-k3:cloud"},
    )
    environment = resolve_settings(
        root_context,
        environment={"model": "kimi-k3:cloud"},
    )
    launch = resolve_settings(
        root_context,
        launch={"model": "kimi-k3:cloud"},
    )

    assert default.model == "gemma3:4b"
    for settings in (persisted, environment, launch):
        assert settings.model == "kimi-k3:cloud"
        assert settings.llm_provider == "Ollama"
    assert persisted.provenance["model"] == "persisted"
    assert environment.provenance["model"] == "environment"
    assert launch.provenance["model"] == "launch"


def test_unknown_model_has_explicit_catalog_reason(root_context):
    model = "kimi-k3.1:latest"

    with pytest.raises(ConfigurationError) as caught:
        resolve_settings(
            root_context,
            launch={"model": model},
        )

    assert str(caught.value) == f"Model '{model}' is not in the supported provider catalog."


def test_unknown_model_reason_is_provider_independent(root_context):
    model = "synthetic-unknown-model"

    with pytest.raises(ConfigurationError) as caught:
        resolve_settings(
            root_context,
            environment={"llm_provider": "OpenAI"},
            launch={"model": model},
        )

    assert str(caught.value) == f"Model '{model}' is not in the supported provider catalog."


@pytest.mark.parametrize(
    ("model", "capability"),
    [
        ("nomic-embed-text:latest", "embedding"),
        ("glm-ocr:latest", "ocr"),
    ],
)
def test_non_chat_ollama_metadata_is_rejected_with_capability_reason(
    model,
    capability,
    root_context,
    monkeypatch,
):
    from hedge_fund.llm import registry
    from hedge_fund.llm.registry import ModelCatalogEntry

    catalog = registry.load_api_model_entries()
    catalog.append(
        ModelCatalogEntry(
            display_name=model,
            model_name=model,
            provider="Ollama",
            capability=capability,
            cost_class="local",
        )
    )
    monkeypatch.setattr(
        registry,
        "load_api_model_entries",
        lambda: catalog,
    )

    with pytest.raises(ConfigurationError) as caught:
        resolve_settings(
            root_context,
            launch={"llm_provider": "Ollama", "model": model},
        )

    assert str(caught.value) == f"Model '{model}' is not chat-capable ({capability})."


def test_paid_context_size_uses_catalog_cost_class(root_context, monkeypatch):
    from hedge_fund.llm import registry
    from hedge_fund.llm.registry import ModelCatalogEntry

    catalog = registry.load_api_model_entries()
    catalog.append(
        ModelCatalogEntry(
            display_name="Synthetic paid model",
            model_name="synthetic-paid-remote",
            provider="Ollama",
            capability="chat",
            cost_class="paid-cloud",
        )
    )
    monkeypatch.setattr(
        registry,
        "load_api_model_entries",
        lambda: catalog,
    )

    with pytest.raises(ConfigurationError, match="context size is supported only by local Ollama"):
        resolve_settings(
            root_context,
            launch={
                "llm_provider": "Ollama",
                "model": "synthetic-paid-remote",
                "parameters": {"context_size": 8192},
            },
        )


def test_local_catalog_addition_updates_configuration_web_and_transport(tmp_path, root_context, monkeypatch):
    from hedge_fund.llm import registry
    from hedge_fund.runtime.endpoints import (
        validate_provider_target,
        validate_request_url,
    )
    from hedge_fund.runtime.policy import (
        approved_local_ollama_chat_models,
        classify_provider,
        ProviderClass,
        ProviderTarget,
    )
    from hedge_fund.web.services import _model_options

    model = "synthetic-local:latest"
    original = json.loads(registry.API_MODELS_PATH.read_text(encoding="utf-8"))
    catalog_path = tmp_path / "api_models.json"
    catalog_path.write_text(
        json.dumps(
            original
            + [
                {
                    "display_name": "Synthetic local model",
                    "model_name": model,
                    "provider": "Ollama",
                    "capability": "chat",
                    "cost_class": "local",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "API_MODELS_PATH", catalog_path)

    settings = resolve_settings(root_context, launch={"model": model})
    target = ProviderTarget("llm", "Ollama", model)
    validate_provider_target(target)
    assert validate_request_url(target, "http://127.0.0.1:11434/api/chat") == ("127.0.0.1", 11434, True)

    assert settings.model == model
    assert model in approved_local_ollama_chat_models()
    assert classify_provider(target, approved_local_models=approved_local_ollama_chat_models()) is ProviderClass.LOCAL
    assert model in {option["id"] for option in _model_options()}

    catalog_path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=f"Model '{model}' is not in the supported provider catalog"):
        resolve_settings(root_context, launch={"model": model})
    assert model not in approved_local_ollama_chat_models()
    assert model not in {option["id"] for option in _model_options()}


def test_environment_cannot_elevate_root_writes_network_or_paid_policy(root_context, tmp_path):
    decoy_root = tmp_path / "decoy"
    settings = resolve_settings(root_context)

    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            environment={
                "root": str(decoy_root),
                "writable": True,
                "network_enabled": True,
                "paid_authorized": True,
                "budget": 1000000,
            },
        )

    assert not hasattr(settings, "paid_authorized")
    assert not hasattr(settings, "network_enabled")
    assert not decoy_root.exists()

    with pytest.raises(ConfigurationError) as error:
        resolve_settings(
            root_context,
            launch={"api_key": "synthetic-secret-value"},
        )
    assert "synthetic-secret-value" not in str(error.value)

    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            launch={"endpoint": "https://provider.example.invalid/?key=synthetic-secret"},
        )


def test_persisted_settings_versions_are_monotonic_and_compare_and_swap(root_context, root_owner):
    initial = load_settings(root_context)
    first = save_settings(
        root_context,
        {"data_provider": "fd", "model": "gpt-6-sol"},
        expected_version=initial.version,
        admission=root_owner,
    )

    assert initial.version == 0
    assert first.version == 1
    assert load_settings(root_context, admission=root_owner) == first

    with pytest.raises(SettingsConflict):
        save_settings(
            root_context,
            {"data_provider": "yfinance"},
            expected_version=0,
            admission=root_owner,
        )

    second = save_settings(
        root_context,
        {"data_provider": "yfinance"},
        expected_version=first.version,
        admission=root_owner,
    )
    assert second.version == 2
    assert second.data_provider == "yfinance"
    assert second.model == "gpt-6-sol"


def test_frozen_capture_copies_versions_and_redacts_private_references(root_context):
    settings = resolve_settings(
        root_context,
        launch={"data_provider": "yfinance", "model": "gemma3:4b"},
    )
    versions = {"openai": 4}
    universe = ["AAA", "BBB"]
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="a" * 64,
        universe=universe,
        broker="paper",
        settings=settings,
        credential_versions=versions,
        code_version="synthetic-code-stamp",
    )
    versions["openai"] = 5
    universe[0] = "CCC"

    assert capture.credential_versions["openai"] == 4
    assert capture.universe == ("AAA", "BBB")
    with pytest.raises(FrozenInstanceError):
        capture.model = "changed-model"
    with pytest.raises(TypeError):
        capture.credential_versions["openai"] = 6

    public = capture.public_view()
    assert public["model"] == "gemma3:4b"
    assert "credential_versions" not in public
    assert "credential_material" not in public
    assert "mandate_digest" not in public
    assert "a" * 64 not in repr(public)
    assert str(root_context.path).encode("utf-8") not in capture.private_bytes()
    assert public["provenance"]["model"] == "launch"
    assert public["restart_needed"] is None
    assert not hasattr(capture, "credential_material")
    assert capture.credential_handles["openai"].version == 4
    assert capture.credential_handles["openai"].root_id == capture.root_id

    with pytest.raises(ConfigurationError):
        replace(capture, root=root_context, subject_id="tampered")
    with pytest.raises(ConfigurationError):
        CredentialHandle(root_id="invalid", provider_id="openai", version=4)


def test_unattested_protected_subject_is_rejected_when_freezing(root_context):
    with pytest.raises(ConfigurationError, match="capture subject is invalid"):
        freeze_capture(
            root=root_context,
            subject_id="umbrella",
            mandate_digest="a" * 64,
            universe=("AAA",),
            broker="paper",
            settings=resolve_settings(root_context),
            credential_versions={},
            code_version="synthetic-code-stamp",
        )


def test_unattested_protected_subject_is_rejected_when_restoring(root_context):
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="a" * 64,
        universe=("AAA",),
        broker="paper",
        settings=resolve_settings(root_context),
        credential_versions={},
        code_version="synthetic-code-stamp",
    )
    record = json.loads(capture.private_bytes())
    record["subject_id"] = "umbrella"
    payload = {
        "schema": record["schema"],
        "root_id": record["root_id"],
        "subject_id": record["subject_id"],
        "mandate_digest": record["mandate_digest"],
        "universe": record["universe"],
        "broker": record["broker"],
        "settings_version": record["settings_version"],
        "settings": record["settings"],
        "provenance": record["settings"]["provenance"],
        "credential_versions": {},
        "code_version": record["code_version"],
    }
    record["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    with pytest.raises(ConfigurationError, match="capture is invalid"):
        FrozenCapture.from_private_bytes(
            root_context,
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        )


def test_frozen_capture_restores_only_verified_root_private_bytes(root_context, tmp_path):
    settings = resolve_settings(
        root_context,
        launch={"data_provider": "yfinance", "model": "gemma3:4b"},
    )
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="b" * 64,
        universe=("AAA",),
        broker="paper",
        settings=settings,
        credential_versions={},
        code_version="synthetic-code-stamp",
    )

    restored = FrozenCapture.from_private_bytes(root_context, capture.private_bytes())
    assert restored == capture

    with pytest.raises(ConfigurationError):
        other = tmp_path / "other"
        other.mkdir()
        with RootContext.open(other) as other_root:
            FrozenCapture.from_private_bytes(other_root, capture.private_bytes())
    with pytest.raises(ConfigurationError):
        FrozenCapture.from_private_bytes(
            root_context,
            capture.private_bytes().replace(b"gemma3:4b", b"tampered-model"),
        )


def test_capture_rejects_casefolded_duplicate_credential_providers(root_context):
    settings = resolve_settings(root_context)

    with pytest.raises(ConfigurationError):
        freeze_capture(
            root=root_context,
            subject_id="alpha",
            mandate_digest="a" * 64,
            universe=("AAA",),
            broker="paper",
            settings=settings,
            credential_versions={"OpenAI": 4, "openai": 5},
            code_version="synthetic-code-stamp",
        )


def test_child_environment_isolated_and_root_bound(root_context, tmp_path):
    settings = resolve_settings(
        root_context,
        launch={"data_provider": "yfinance", "model": "gemma3:4b"},
    )
    decoy_root = tmp_path / "decoy-root"
    inherited = {
        "PATH": "synthetic-path",
        "SystemRoot": "synthetic-system-root",
        "COMPUTERNAME": "synthetic-host",
        "OPENAI_API_KEY": "synthetic-secret-value",
        "HEDGE_FUND_ROOT": str(decoy_root),
        "AIHF_ROOT": str(decoy_root),
        "HEDGE_FUND_ALLOW_NETWORK": "1",
        "HEDGE_FUND_DATA_PROVIDER": "fd",
        "PYTHONPATH": "synthetic-import-path",
    }

    child = build_child_environment(
        root_context,
        child_id="worker-1",
        settings=settings,
        inherited_environment=inherited,
    )

    home = str(root_context.resolve("runtime/children/worker-1/home"))
    assert child["HOME"] == home
    assert child["USERPROFILE"] == home
    assert child["TEMP"] == child["TMP"]
    assert child["PYTHON_DOTENV_DISABLED"] == "1"
    assert child["HEDGE_FUND_DATA_PROVIDER"] == "yfinance"
    assert child["HEDGE_FUND_LLM_MODEL"] == "gemma3:4b"
    assert child["PATH"] == "synthetic-path"
    assert child["SystemRoot"] == "synthetic-system-root"
    if os.name == "nt":
        assert child["COMPUTERNAME"] == "synthetic-host"
    else:
        assert "COMPUTERNAME" not in child
    assert "--root" in child_root_arguments(root_context)
    assert str(root_context.path) in child_root_arguments(root_context)
    assert "OPENAI_API_KEY" not in child
    assert "HEDGE_FUND_ROOT" not in child
    assert "AIHF_ROOT" not in child
    assert "HEDGE_FUND_ALLOW_NETWORK" not in child
    assert "PYTHONPATH" not in child
    assert "synthetic-secret-value" not in child.values()
    assert not decoy_root.exists()

    with pytest.raises(ConfigurationError):
        build_child_environment(
            root_context,
            child_id="../outside",
            settings=settings,
            inherited_environment=inherited,
        )


def test_owned_child_environment_carries_network_guard_without_secrets(root_context):
    settings = resolve_settings(
        root_context,
        launch={
            "data_provider": "yfinance",
            "llm_provider": "Ollama",
            "model": "gemma3:4b",
            "endpoint": "http://127.0.0.1:11434",
        },
    )
    inherited = os.environ.copy()
    inherited["OPENAI_API_KEY"] = "synthetic-secret"
    child = build_child_environment(
        root_context,
        child_id="guard-probe",
        settings=settings,
        inherited_environment=inherited,
    )

    test_root = Path(inherited["HEDGE_FUND_TEST_ROOT"])
    assert "OPENAI_API_KEY" not in child
    assert "synthetic-secret" not in child.values()
    assert child["HEDGE_FUND_TEST_MODE"] == "1"
    assert child["HEDGE_FUND_TEST_BLOCK_LOOPBACK"] == "1"
    assert Path(child["HOME"]).is_relative_to(test_root)
    assert child["HEDGE_FUND_TEST_CHILD_HOME"] == child["HOME"]
    assert "test_support" in child["PYTHONPATH"]
