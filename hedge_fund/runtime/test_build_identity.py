from __future__ import annotations

import sys
from types import ModuleType

import pytest

from hedge_fund.runtime.build_identity import bake_build_identity, baked_build_identity, source_sha256


def test_source_sha256_uses_relative_paths_and_ignores_generated_files(tmp_path):
    root = tmp_path / "hedge_fund"
    (root / "runtime").mkdir(parents=True)
    source = root / "runtime" / "module.py"
    source.write_bytes(b"value = 1\r\n")
    first = source_sha256(root)

    source.touch()
    (root / "runtime" / "__pycache__").mkdir()
    (root / "runtime" / "__pycache__" / "module.pyc").write_bytes(b"generated")
    (root / "_build_identity.py").write_text("SOURCE_REVISION = 'ignored'\n")
    assert source_sha256(root) == first

    nested_identity = root / "runtime" / "_build_identity.py"
    nested_identity.write_text("nested = True\n")
    assert source_sha256(root) != first

    (root / "runtime" / "other.py").write_text("value = 1\n")
    assert source_sha256(root) != first


def test_bake_build_identity_verifies_source_before_writing(tmp_path):
    root = tmp_path / "hedge_fund"
    root.mkdir()
    (root / "module.py").write_text("value = 1\n")
    expected = source_sha256(root)
    revision = "a" * 40

    assert bake_build_identity(root, revision, expected) == (revision, expected)
    identity = root / "_build_identity.py"
    assert identity.read_text(encoding="ascii") == (f"SOURCE_REVISION = {revision!r}\nSOURCE_SHA256 = {expected!r}\n")
    assert source_sha256(root) == expected


def test_baked_build_identity_reads_validated_package_constants(monkeypatch):
    module = ModuleType("hedge_fund._build_identity")
    module.SOURCE_REVISION = "a" * 40
    module.SOURCE_SHA256 = "b" * 64
    monkeypatch.setitem(sys.modules, "hedge_fund._build_identity", module)

    assert baked_build_identity() == (module.SOURCE_REVISION, module.SOURCE_SHA256)


def test_baked_build_identity_rejects_malformed_package_constants(monkeypatch):
    module = ModuleType("hedge_fund._build_identity")
    module.SOURCE_REVISION = "short"
    module.SOURCE_SHA256 = "b" * 64
    monkeypatch.setitem(sys.modules, "hedge_fund._build_identity", module)

    with pytest.raises(RuntimeError, match="revision is invalid"):
        baked_build_identity()


@pytest.mark.parametrize(
    ("revision", "source_hash"),
    [
        ("not-a-full-revision", "b" * 64),
        ("a" * 40, "not-a-sha256"),
        ("a" * 40, "b" * 64),
    ],
)
def test_bake_build_identity_rejects_invalid_or_mismatched_identity(tmp_path, revision, source_hash):
    root = tmp_path / "hedge_fund"
    root.mkdir()
    (root / "module.py").write_text("value = 1\n")

    with pytest.raises(ValueError):
        bake_build_identity(root, revision, source_hash)
    assert not (root / "_build_identity.py").exists()


def test_source_sha256_rejects_symlinked_package_files(tmp_path):
    root = tmp_path / "hedge_fund"
    root.mkdir()
    target = tmp_path / "source.py"
    target.write_text("value = 1\n")
    linked = root / "module.py"
    try:
        linked.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    with pytest.raises(ValueError, match="symlinks"):
        source_sha256(root)
