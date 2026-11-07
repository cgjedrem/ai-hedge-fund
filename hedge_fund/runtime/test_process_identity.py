import os

import pytest

from hedge_fund.runtime import ownership
from hedge_fund.runtime.ownership import _linux_process_identity, ProcessIdentityError


def _write_proc_fixture(tmp_path, *, start_time="987654"):
    proc_root = tmp_path / "proc"
    process = proc_root / "1"
    namespace = process / "ns" / "pid"
    namespace.parent.mkdir(parents=True)
    stat_tail = ["S", *("0" for _ in range(18)), start_time]
    (process / "stat").write_text(
        f"1 (supervisor ) with spaces) {' '.join(stat_tail)}",
        encoding="ascii",
    )
    namespace.write_text("synthetic namespace\n", encoding="ascii")
    (process / "exe").write_text("synthetic executable", encoding="ascii")
    boot_id = proc_root / "sys" / "kernel" / "random" / "boot_id"
    boot_id.parent.mkdir(parents=True)
    boot_id.write_text("synthetic-boot-id\n", encoding="ascii")
    return proc_root, process, namespace


def test_linux_process_identity_parses_pid1_stat_with_parenthesized_command(tmp_path, monkeypatch):
    proc_root, process, namespace = _write_proc_fixture(tmp_path)
    monkeypatch.setattr(
        ownership.os,
        "readlink",
        lambda path: "/usr/bin/synthetic-supervisor",
    )

    identity = _linux_process_identity(1, proc_root=proc_root)

    assert identity == {
        "pid": 1,
        "creation_time": "987654",
        "image": "/usr/bin/synthetic-supervisor",
        "host": "synthetic-boot-id",
        "namespace": str(os.stat(namespace).st_ino),
    }


@pytest.mark.parametrize(
    "start_time",
    ["0", "masked", "18446744073709551616"],
)
def test_linux_process_identity_rejects_invalid_pid1_start_time(tmp_path, start_time):
    proc_root, _process, _namespace = _write_proc_fixture(tmp_path, start_time=start_time)

    with pytest.raises(ProcessIdentityError):
        _linux_process_identity(1, proc_root=proc_root)


def test_linux_process_identity_fails_closed_when_executable_is_unreadable(tmp_path, monkeypatch):
    proc_root, _process, _namespace = _write_proc_fixture(tmp_path)

    def deny_executable_read(_path):
        raise PermissionError("synthetic procfs permission denial")

    monkeypatch.setattr(ownership.os, "readlink", deny_executable_read)

    with pytest.raises(ProcessIdentityError, match="unavailable"):
        _linux_process_identity(1, proc_root=proc_root)


def test_linux_process_identity_fails_closed_when_procfs_is_unavailable(tmp_path):
    with pytest.raises(ProcessIdentityError, match="unavailable"):
        _linux_process_identity(1, proc_root=tmp_path / "proc")
