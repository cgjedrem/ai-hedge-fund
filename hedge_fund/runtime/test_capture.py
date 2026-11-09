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
    from hedge_fund.llm.registry import load_api_models, SUPPORTED_PROVIDERS
    from hedge_fund.runtime import configuration

    assert configuration.DEFAULT_MODEL == DEFAULT_MODEL
    assert set(configuration._PROVIDERS.values()) == SUPPORTED_PROVIDERS
    assert configuration._MODEL_PROVIDERS == {model: provider for _, model, provider in load_api_models() if provider in SUPPORTED_PROVIDERS}


def test_cloud_ollama_models_are_not_selectable_or_resolvable(root_context):
    from hedge_fund.llm.registry import load_api_models

    models = {model for _, model, _provider in load_api_models()}
    assert not any(model.endswith(":cloud") for model in models)
    with pytest.raises(ConfigurationError, match="supported catalog"):
        resolve_settings(
            root_context,
            launch={"model": "glm-5.3:cloud"},
        )


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
        replace(capture, subject_id="tampered")
    with pytest.raises(ConfigurationError):
        CredentialHandle(root_id="invalid", provider_id="openai", version=4)


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
