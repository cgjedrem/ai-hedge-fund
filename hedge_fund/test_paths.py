import os
import stat
from pathlib import Path

import pytest

import hedge_fund.paths as paths
from hedge_fund.paths import write_atomic
from hedge_fund.runtime.root import RootContext, RootPathError


def test_write_atomic_survives_non_ascii(tmp_path: Path) -> None:
    # Ledger rationale must round-trip beyond platform encoding.
    path = tmp_path / "record.json"
    text = '{"rationale": "cheap \u2192 buy \u2192 \U0001f4c8"}'
    write_atomic(path, text)
    assert path.read_text(encoding="utf-8") == text
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_write_atomic_replaces_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_atomic(path, "old")
    write_atomic(path, "new")
    assert path.read_text(encoding="utf-8") == "new"


def test_write_atomic_uses_a_unique_temp_path_per_write(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    temporary_names = []
    replace = paths.os.replace

    def record_replace(source, target):
        temporary_names.append(Path(source).name)
        replace(source, target)

    monkeypatch.setattr(paths.os, "replace", record_replace)
    write_atomic(path, "first")
    write_atomic(path, "second")

    assert len(set(temporary_names)) == 2
    assert path.read_text(encoding="utf-8") == "second"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_write_atomic_applies_mode_before_write_and_replace(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "secret.env"
    path.write_text("old", encoding="utf-8")
    original_fdopen = paths.os.fdopen
    original_replace = paths.os.replace
    observed = []

    class CheckedStream:
        def __init__(self, stream, descriptor):
            self._stream = stream
            self._descriptor = descriptor

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._stream.__exit__(*exc_info)

        def write(self, text):
            observed.append(stat.S_IMODE(os.fstat(self._descriptor).st_mode))
            return self._stream.write(text)

    def check_fdopen(descriptor, *args, **kwargs):
        return CheckedStream(original_fdopen(descriptor, *args, **kwargs), descriptor)

    def check_replace(source, target):
        observed.append(stat.S_IMODE(Path(source).stat().st_mode))
        original_replace(source, target)

    monkeypatch.setattr(paths.os, "fdopen", check_fdopen)
    monkeypatch.setattr(paths.os, "replace", check_replace)

    previous_umask = os.umask(0o022)
    try:
        write_atomic(path, "new", mode=stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.umask(previous_umask)

    assert observed == [0o600, 0o600]
    assert path.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_write_atomic_removes_restricted_temp_after_interrupted_write(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "secret.env"
    path.write_text("old", encoding="utf-8")
    original_fdopen = paths.os.fdopen
    observed = []

    class InterruptedStream:
        def __init__(self, stream, descriptor):
            self._stream = stream
            self._descriptor = descriptor

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self._stream.__exit__(*exc_info)

        def write(self, _text):
            observed.append(stat.S_IMODE(os.fstat(self._descriptor).st_mode))
            self._stream.write(_text[:2])
            raise OSError("simulated interrupted write")

    def interrupt_fdopen(descriptor, *args, **kwargs):
        return InterruptedStream(original_fdopen(descriptor, *args, **kwargs), descriptor)

    monkeypatch.setattr(paths.os, "fdopen", interrupt_fdopen)

    previous_umask = os.umask(0o022)
    try:
        with pytest.raises(OSError, match="simulated interrupted write"):
            write_atomic(path, "new", mode=stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.umask(previous_umask)

    assert observed == [0o600]
    assert path.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_root_path_helpers_revalidate_identity_before_returning_child(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    moved = tmp_path / "moved-root"

    with RootContext.open(root) as context:
        if os.name == "nt":
            with pytest.raises(OSError):
                root.rename(moved)
            assert context.resolve("paper/fund/ledger") == root / "paper/fund/ledger"
        else:
            root.rename(moved)
            root.mkdir()
            with pytest.raises(RootPathError, match="identity changed"):
                context.resolve("paper/fund/ledger")
            assert not (root / "paper").exists()
            assert not (moved / "paper").exists()


def test_resolve_user_path_binds_relative_paths_to_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.yaml"

    with RootContext.open(root) as context:
        with paths.bound_root(context):
            assert paths.resolve_user_path("mandates/example.yaml") == root / "mandates" / "example.yaml"
            assert paths.resolve_user_path(root / "cache" / "entry.json") == root / "cache" / "entry.json"
            assert paths.resolve_user_path(outside) == outside
            with pytest.raises(RootPathError, match="traversal"):
                paths.resolve_user_path("../outside.yaml")
