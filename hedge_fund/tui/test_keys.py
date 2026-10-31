import os
import stat

from hedge_fund.tui import keys


def test_save_credential_requests_private_atomic_file(tmp_path, monkeypatch):
    env_var = "COPILOT_TRIAGE_FAKE_PROVIDER_KEY"
    monkeypatch.delenv(env_var, raising=False)
    original_write_atomic = keys.write_atomic
    requested_modes = []

    def record_mode(path, text, **kwargs):
        requested_modes.append(kwargs.get("mode"))
        return original_write_atomic(path, text, **kwargs)

    monkeypatch.setattr(keys, "write_atomic", record_mode)
    path = keys.save_credential(env_var, "fake-test-token", path=tmp_path / ".env")

    assert requested_modes == [stat.S_IRUSR | stat.S_IWUSR]
    assert path.read_text(encoding="utf-8") == f"{env_var}=fake-test-token\n"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
