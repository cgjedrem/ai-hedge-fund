"""Neutral credential helper tests."""

from __future__ import annotations

import os
import stat

import pytest

from hedge_fund.runtime import credentials


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


def test_headless_entrypoints_import_without_tui_or_textual(owned_test_process):
    process = owned_test_process("import sys; import check_stock; import hedge_fund.llm.test_client; " "import hedge_fund.run; import hedge_fund.web.services; " "assert not any(name == 'hedge_fund.tui' or name.startswith('hedge_fund.tui.') " "or name == 'textual' or name.startswith('textual.') for name in sys.modules)")
    assert process.wait(timeout=10) == 0
