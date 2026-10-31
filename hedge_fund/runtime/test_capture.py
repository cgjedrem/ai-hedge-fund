from dataclasses import FrozenInstanceError, replace

import pytest

from hedge_fund.runtime.capture import CredentialHandle, freeze_capture
from hedge_fund.runtime.configuration import build_child_environment, child_root_arguments, ConfigurationError, environment_settings, load_settings, resolve_settings, save_settings, SettingsConflict
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def root_context(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        yield context


def test_settings_precedence_uses_launch_environment_persisted_and_free_default(root_context):
    defaults = resolve_settings(root_context)
    persisted = resolve_settings(
        root_context,
        persisted={"data_provider": "fd", "model": "persisted-model"},
    )
    environment = resolve_settings(
        root_context,
        environment={"data_provider": "yfinance", "model": "environment-model"},
        persisted={"data_provider": "fd", "model": "persisted-model"},
    )
    launch = resolve_settings(
        root_context,
        launch={"model": "launch-model"},
        environment={"data_provider": "yfinance", "model": "environment-model"},
        persisted={"data_provider": "fd", "model": "persisted-model"},
    )

    assert defaults.data_provider == "yfinance"
    assert persisted.data_provider == "fd"
    assert environment.model == "environment-model"
    assert environment.data_provider == "yfinance"
    assert launch.model == "launch-model"
    assert launch.provenance["model"] == "launch"
    assert launch.provenance["data_provider"] == "environment"


def test_registered_model_selects_provider_without_secret_environment_access(root_context):
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
    )
    assert persisted.llm_provider == "OpenAI"

    with pytest.raises(ConfigurationError):
        resolve_settings(
            root_context,
            launch={"model": "gpt-6-sol", "llm_provider": "Anthropic"},
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
    assert configuration._MODEL_PROVIDERS == {model: provider for _, model, provider in load_api_models()}


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


def test_persisted_settings_versions_are_monotonic_and_compare_and_swap(root_context):
    initial = load_settings(root_context)
    first = save_settings(
        root_context,
        {"data_provider": "fd", "model": "persisted-model"},
        expected_version=initial.version,
    )

    assert initial.version == 0
    assert first.version == 1
    assert load_settings(root_context) == first

    with pytest.raises(SettingsConflict):
        save_settings(
            root_context,
            {"data_provider": "yfinance"},
            expected_version=0,
        )

    second = save_settings(
        root_context,
        {"data_provider": "yfinance"},
        expected_version=first.version,
    )
    assert second.version == 2
    assert second.data_provider == "yfinance"
    assert second.model == "persisted-model"


def test_frozen_capture_copies_versions_and_redacts_private_references(root_context):
    settings = resolve_settings(
        root_context,
        launch={"data_provider": "yfinance", "model": "local-model"},
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
    assert public["model"] == "local-model"
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
        launch={"data_provider": "yfinance", "model": "local-model"},
    )
    decoy_root = tmp_path / "decoy-root"
    inherited = {
        "PATH": "synthetic-path",
        "SystemRoot": "synthetic-system-root",
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
    assert child["HEDGE_FUND_LLM_MODEL"] == "local-model"
    assert child["PATH"] == "synthetic-path"
    assert child["SystemRoot"] == "synthetic-system-root"
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
