"""Native filesystem and process-incarnation checks."""

from __future__ import annotations

import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.ownership import identity_matches, process_identity
from hedge_fund.runtime.root import RootContext, RootPathError


@pytest.fixture
def native_case_dir(tmp_path):
    configured = os.environ.get("AIHF_NATIVE_TEST_ROOT_BASE")
    base = Path(configured) if configured else tmp_path
    base.mkdir(parents=True, exist_ok=True)
    case = base / f"native-primitives-{uuid.uuid4().hex}"
    case.mkdir()
    yield case
    shutil.rmtree(case)


def _assert_native_filesystem(root: RootContext) -> None:
    expected = "ntfs" if os.name == "nt" else "ext4"
    assert root.filesystem.filesystem.casefold() == expected


def _wait_for(path: Path, process, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise AssertionError(f"owned child exited early: {process.returncode}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"owned child did not create {path.name}")
        time.sleep(0.01)


def test_native_file_identity_tracks_rename_and_atomic_replace(native_case_dir):
    root_path = native_case_dir / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        _assert_native_filesystem(root)
        root.write_bytes("before.bin", b"first")
        before_path = root_path / "before.bin"
        original = before_path.stat()
        assert original.st_ino

        renamed = root.rename_file("before.bin", "renamed.bin")
        after_rename = renamed.stat()
        assert (after_rename.st_dev, after_rename.st_ino) == (
            original.st_dev,
            original.st_ino,
        )

        root.write_bytes("renamed.bin", b"replacement")
        replaced = renamed.stat()
        assert (replaced.st_dev, replaced.st_ino) != (
            original.st_dev,
            original.st_ino,
        )
        assert root.read_bytes("renamed.bin") == b"replacement"


def test_native_lock_excludes_owned_cross_process_writer(
    native_case_dir,
    owned_test_process,
):
    root_path = native_case_dir / "root"
    root_path.mkdir()
    result = native_case_dir / "lock-result"
    with RootContext.open(root_path) as root:
        _assert_native_filesystem(root)
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        script = "\n".join(
            [
                "from pathlib import Path",
                "from hedge_fund.runtime.admission import " "AdmissionCoordinator, RootOwnerLease, WriterConflict",
                "from hedge_fund.runtime.root import RootContext",
                f"root = RootContext.open({str(root_path)!r})",
                "owner = RootOwnerLease.acquire(root)",
                "admission = AdmissionCoordinator(root, owner_lease=owner)",
                "try:",
                "    try:",
                "        with admission.registry_lock(timeout=0):",
                "            outcome = 'acquired'",
                "    except WriterConflict:",
                "        outcome = 'blocked'",
                f"    Path({str(result)!r}).write_text(" "outcome, encoding='utf-8')",
                "finally:",
                "    owner.close()",
                "    root.close()",
            ]
        )
        try:
            with admission.registry_lock(timeout=0):
                child = owned_test_process(script)
                _wait_for(result, child)
                assert result.read_text(encoding="utf-8") == "blocked"
                assert child.wait(timeout=10) == 0
        finally:
            owner.close()


def test_native_atomic_replace_never_exposes_partial_reader_bytes(
    native_case_dir,
    owned_test_process,
):
    root_path = native_case_dir / "root"
    root_path.mkdir()
    target = root_path / "record.bin"
    ready = native_case_dir / "reader-ready"
    reading = native_case_dir / "reader-active"
    stop = native_case_dir / "reader-stop"
    result = native_case_dir / "reader-result"
    first = b"A" * 65536
    second = b"B" * 98304
    with RootContext.open(root_path) as root:
        _assert_native_filesystem(root)
        root.write_bytes("record.bin", first)
        script = "\n".join(
            [
                "import time",
                "from pathlib import Path",
                "from hedge_fund.runtime.root import RootContext",
                f"root = RootContext.open({str(root_path)!r})",
                "target = 'record.bin'",
                f"ready = Path({str(ready)!r})",
                f"reading = Path({str(reading)!r})",
                f"stop = Path({str(stop)!r})",
                f"result = Path({str(result)!r})",
                "allowed_lengths = {65536, 98304}",
                "ready.write_text('ready', encoding='utf-8')",
                "count = 0",
                "try:",
                "    while not stop.exists():",
                "        value = root.read_bytes(target)",
                "        if (len(value) not in allowed_lengths " "or value[:1] not in {b'A', b'B'}):",
                "            raise AssertionError(f'partial:{len(value)}')",
                "        count += 1",
                "        reading.touch(exist_ok=True)",
                "        time.sleep(0.001)",
                "except BaseException as exc:",
                "    result.write_text(" "f'error:{type(exc).__name__}:{exc}', encoding='utf-8')",
                "    raise",
                "else:",
                "    result.write_text(str(count), encoding='utf-8')",
                "finally:",
                "    root.close()",
            ]
        )
        child = owned_test_process(script)
        _wait_for(ready, child)
        _wait_for(reading, child)
        try:
            for index in range(120):
                root.write_bytes("record.bin", first if index % 2 else second)
        finally:
            stop.touch()
        exit_code = child.wait(timeout=10)
        assert exit_code == 0, result.read_text(encoding="utf-8")
        assert int(result.read_text(encoding="utf-8")) > 0
        assert target.read_bytes() in {first, second}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS reader sharing")
def test_ntfs_non_delete_sharing_reader_denies_replace_without_partial_state(
    native_case_dir,
):
    root_path = native_case_dir / "root"
    root_path.mkdir()
    target = root_path / "record.bin"
    with RootContext.open(root_path) as root:
        _assert_native_filesystem(root)
        root.write_bytes("record.bin", b"before")
        with target.open("rb") as reader:
            with pytest.raises(PermissionError):
                root.write_bytes("record.bin", b"after")
            reader.seek(0)
            assert reader.read() == b"before"
        assert root.read_bytes("record.bin") == b"before"
        assert list(root_path.glob(".*.tmp")) == []

        root.write_bytes("record.bin", b"after")
        assert root.read_bytes("record.bin") == b"after"


def test_root_handle_binds_original_directory_across_rename(native_case_dir):
    root_path = native_case_dir / "root"
    moved = native_case_dir / "moved-root"
    root_path.mkdir()
    (root_path / "record.txt").write_bytes(b"original")
    with RootContext.open(root_path) as root:
        _assert_native_filesystem(root)
        if os.name == "nt":
            with pytest.raises(OSError):
                root_path.rename(moved)
            assert root.read_bytes("record.txt") == b"original"
            assert not moved.exists()
        else:
            root_path.rename(moved)
            root_path.mkdir()
            (root_path / "record.txt").write_bytes(b"replacement")
            with pytest.raises(RootPathError, match="identity changed"):
                root.read_bytes("record.txt")
            assert (moved / "record.txt").read_bytes() == b"original"
            assert (root_path / "record.txt").read_bytes() == (b"replacement")


def test_native_process_identity_expires_with_owned_child(
    native_case_dir,
    owned_test_process,
):
    ready = native_case_dir / "identity-ready"
    release = native_case_dir / "identity-release"
    script = "\n".join(
        [
            "import os",
            "import time",
            "from pathlib import Path",
            f"ready = Path({str(ready)!r})",
            f"release = Path({str(release)!r})",
            "ready.write_text(str(os.getpid()), encoding='ascii')",
            "while not release.exists():",
            "    time.sleep(0.01)",
        ]
    )
    child = owned_test_process(script)
    _wait_for(ready, child)
    pid = int(ready.read_text(encoding="ascii"))
    identity = process_identity(pid)
    assert identity["pid"] == pid
    assert identity["creation_time"]
    assert identity["host"]
    assert identity["namespace"]
    assert identity_matches(pid, identity)
    changed_creation = dict(identity, creation_time=f"{identity['creation_time']}-changed")
    assert not identity_matches(pid, changed_creation)

    release.touch()
    assert child.wait(timeout=10) == 0
    assert not identity_matches(pid, identity)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows NTFS native verification",
)
def test_reports_windows_ntfs_execution(native_case_dir):
    root_path = native_case_dir / "windows-root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        assert root.filesystem.filesystem.casefold() == "ntfs"


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux ext4 native verification",
)
def test_reports_linux_ext4_execution(native_case_dir):
    root_path = native_case_dir / "linux-root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        assert root.filesystem.filesystem.casefold() == "ext4"
