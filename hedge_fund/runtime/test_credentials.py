"""Neutral credential helper tests."""

from __future__ import annotations

import os
import stat

import pytest

from hedge_fund.runtime import credentials
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def credential_store(tmp_path):
    root_path = tmp_path / "credential-root"
    root_path.mkdir()
    root = RootContext.open(root_path)
    enroll_fresh(root)
    owner = RootOwnerLease.acquire(root)
    store = credentials.CredentialStore(root, AdmissionCoordinator(root, owner_lease=owner))
    try:
        yield root, store
    finally:
        owner.close()
        root.close()


def test_save_credential_writes_private_atomic_file(tmp_path, monkeypatch):
    env_var = "COPILOT_TRIAGE_FAKE_PROVIDER_KEY"
    monkeypatch.delenv(env_var, raising=False)
    original_write_atomic = credentials.write_atomic
    requested_modes = []

    def record_mode(path, text, **kwargs):
        requested_modes.append(kwargs.get("mode"))
        return original_write_atomic(path, text, **kwargs)

    monkeypatch.setattr(credentials, "write_atomic", record_mode)
    path = credentials.save_credential(env_var, "fake-test-token", path=tmp_path / ".env")

    assert requested_modes == [stat.S_IRUSR | stat.S_IWUSR]
    assert path.read_text(encoding="utf-8") == f"{env_var}=fake-test-token\n"
    assert os.environ[env_var] == "fake-test-token"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_credential_replaces_only_matching_assignment(tmp_path, monkeypatch):
    env_var = "COPILOT_TRIAGE_FAKE_PROVIDER_KEY"
    monkeypatch.delenv(env_var, raising=False)
    path = tmp_path / ".env"
    path.write_text("# keep\nexport " + env_var + "=old\nOTHER_KEY=untouched\n", encoding="utf-8")

    credentials.save_credential(env_var, "fixture key", path=path)

    assert path.read_text(encoding="utf-8") == f'# keep\n{env_var}="fixture key"\nOTHER_KEY=untouched\n'
    assert os.environ[env_var] == "fixture key"


def test_masked_credential_does_not_return_full_value():
    value = "fixture-secret-value"
    masked = credentials.masked(value)

    assert masked.startswith(value[:6])
    assert masked.endswith(value[-4:])
    assert value not in masked


def test_missing_key_uses_allowlisted_provider_environment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert credentials.missing_key("Anthropic") == "ANTHROPIC_API_KEY"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-provider-token")
    assert credentials.missing_key("Anthropic") is None


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("bad-name", "fake-token"),
        ("COPILOT_TRIAGE_FAKE_PROVIDER_KEY", "bad\nvalue"),
        ("COPILOT_TRIAGE_FAKE_PROVIDER_KEY", None),
    ],
)
def test_save_credential_rejects_invalid_input(tmp_path, env_var, value):
    with pytest.raises(ValueError):
        credentials.save_credential(env_var, value, path=tmp_path / ".env")


def test_credentials_import_without_tui_or_textual(owned_test_process):
    process = owned_test_process("import sys; import hedge_fund.runtime.credentials; " "assert not any(name == 'hedge_fund.tui' or name.startswith('hedge_fund.tui.') " "or name == 'textual' or name.startswith('textual.') for name in sys.modules)")
    assert process.wait(timeout=10) == 0


def test_credential_store_versions_secrets_and_status_redacts(credential_store):
    root, store = credential_store

    version = store.save("OpenAI", "fixture-provider-token", expected_version=0)

    assert version == 1
    assert store.version("openai") == (1, True)
    assert store.read_version("OPENAI", version) == "fixture-provider-token"
    assert store.status()["OpenAI"] == {"version": 1, "configured": True}
    assert "fixture-provider-token" not in repr(store.status())
    index = root.read_bytes(credentials._CREDENTIAL_INDEX)
    assert b"fixture-provider-token" not in index

    deleted_version = store.delete("OpenAI", expected_version=version)

    assert deleted_version == 2
    assert store.version("OpenAI") == (2, False)
    assert store.read_version("OpenAI", version) == "fixture-provider-token"
    with pytest.raises(credentials.CredentialStoreError):
        store.read_version("OpenAI", deleted_version)


def test_credential_store_compare_and_swap_rejects_stale_version(credential_store):
    _root, store = credential_store
    store.save("OpenAI", "fixture-provider-token", expected_version=0)

    with pytest.raises(credentials.CredentialVersionConflict):
        store.save("OpenAI", "replacement-token", expected_version=0)

    assert store.version("OpenAI") == (1, True)
    assert store.read_version("OpenAI", 1) == "fixture-provider-token"


def test_credential_store_requires_root_owner_before_writing(tmp_path):
    root_path = tmp_path / "unowned-credential-root"
    root_path.mkdir()
    root = RootContext.open(root_path)
    root.prepare_private_storage()
    store = credentials.CredentialStore(root, AdmissionCoordinator(root))
    try:
        with pytest.raises(credentials.CredentialStoreError):
            store.save("OpenAI", "fixture-provider-token", expected_version=0)
        assert not root.resolve(credentials._CREDENTIAL_ROOT).exists()
    finally:
        root.close()


def test_credential_orphan_does_not_brick_next_cas_write(credential_store, monkeypatch):
    root, store = credential_store
    original_write_index = store._write_index

    def fail_index(_index):
        raise credentials.CredentialStoreError("synthetic index fault")

    monkeypatch.setattr(store, "_write_index", fail_index)
    with pytest.raises(credentials.CredentialStoreError, match="synthetic index fault"):
        store.save("OpenAI", "first-token", expected_version=0)
    monkeypatch.setattr(store, "_write_index", original_write_index)

    version = store.save("OpenAI", "second-token", expected_version=0)

    assert version == 2
    assert store.version("OpenAI") == (2, True)
    assert store.read_version("OpenAI", 1) == "first-token"
    assert store.read_version("OpenAI", 2) == "second-token"
    assert root.file_info(f"{credentials._CREDENTIAL_ROOT}/openai/1.json").size > 0


def test_headless_entrypoints_import_without_tui_or_textual(owned_test_process):
    process = owned_test_process("import sys; import check_stock; import hedge_fund.llm.test_client; " "import hedge_fund.run; import hedge_fund.web.services; " "assert not any(name == 'hedge_fund.tui' or name.startswith('hedge_fund.tui.') " "or name == 'textual' or name.startswith('textual.') for name in sys.modules)")
    assert process.wait(timeout=10) == 0
