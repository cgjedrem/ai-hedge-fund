from types import SimpleNamespace

from hedge_fund.pipeline import session


def test_code_version_uses_baked_source_identity_not_runtime_environment(monkeypatch):
    revision = "a" * 40
    source_sha256 = "b" * 64
    monkeypatch.setattr(session, "baked_build_identity", lambda: (revision, source_sha256))
    monkeypatch.setattr(session, "_version", lambda _distribution: "2.6.1")
    monkeypatch.setenv("AIHF_SOURCE_REVISION", "f" * 40)
    monkeypatch.setenv("AIHF_SOURCE_SHA256", "c" * 64)
    session.code_version.cache_clear()
    try:
        assert session.code_version() == f"2.6.1+g{revision}.sha256.{source_sha256}"
    finally:
        session.code_version.cache_clear()


def test_code_version_uses_short_git_head_without_baked_identity(monkeypatch):
    def git_output(command, **_kwargs):
        if command[-3:] == ["rev-parse", "--short", "HEAD"]:
            return SimpleNamespace(stdout="abc1234\n")
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="")
        raise AssertionError(f"unexpected Git command: {command}")

    monkeypatch.setattr(session, "baked_build_identity", lambda: None)
    monkeypatch.setattr(session, "_version", lambda _distribution: "2.6.1")
    monkeypatch.setattr(session.subprocess, "run", git_output)
    session.code_version.cache_clear()
    try:
        assert session.code_version() == "2.6.1+abc1234"
    finally:
        session.code_version.cache_clear()


def test_code_version_marks_dirty_git_checkout(monkeypatch):
    def git_output(command, **_kwargs):
        if command[-3:] == ["rev-parse", "--short", "HEAD"]:
            return SimpleNamespace(stdout="abc1234\n")
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M hedge_fund/pipeline/session.py\n")
        raise AssertionError(f"unexpected Git command: {command}")

    monkeypatch.setattr(session, "baked_build_identity", lambda: None)
    monkeypatch.setattr(session, "_version", lambda _distribution: "2.6.1")
    monkeypatch.setattr(session.subprocess, "run", git_output)
    session.code_version.cache_clear()
    try:
        assert session.code_version() == "2.6.1+abc1234.dirty"
    finally:
        session.code_version.cache_clear()


def test_code_version_uses_package_version_when_git_is_unavailable(monkeypatch):
    def missing_git(*_args, **_kwargs):
        raise FileNotFoundError("git is unavailable")

    monkeypatch.setattr(session, "baked_build_identity", lambda: None)
    monkeypatch.setattr(session, "_version", lambda _distribution: "2.6.1")
    monkeypatch.setattr(session.subprocess, "run", missing_git)
    session.code_version.cache_clear()
    try:
        assert session.code_version() == "2.6.1"
    finally:
        session.code_version.cache_clear()
