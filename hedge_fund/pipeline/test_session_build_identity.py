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
