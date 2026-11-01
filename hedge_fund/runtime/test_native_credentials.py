"""Native credential ACL, mode, version, and capture checks."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from hedge_fund.runtime import credentials
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture, FrozenCapture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import _windows_current_user_sid, PRIVATE_ROOT, RootContext


@pytest.fixture
def native_case_dir(tmp_path):
    configured = os.environ.get("AIHF_NATIVE_TEST_ROOT_BASE")
    base = Path(configured) if configured else tmp_path
    base.mkdir(parents=True, exist_ok=True)
    case = base / f"native-credentials-{uuid.uuid4().hex}"
    case.mkdir()
    yield case
    shutil.rmtree(case)


@pytest.fixture
def native_credential_store(native_case_dir):
    root_path = native_case_dir / "credential-root"
    root_path.mkdir()
    root = RootContext.open(root_path)
    expected = "ntfs" if os.name == "nt" else "ext4"
    assert root.filesystem.filesystem.casefold() == expected
    enroll_fresh(root)
    owner = RootOwnerLease.acquire(root)
    store = credentials.CredentialStore(
        root,
        AdmissionCoordinator(root, owner_lease=owner),
    )
    try:
        yield root, store
    finally:
        owner.close()
        root.close()


def _wait_for(path: Path, process, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise AssertionError(f"owned child exited early: {process.returncode}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"owned child did not create {path.name}")
        time.sleep(0.01)


def test_native_credential_versions_are_atomic_and_capture_stays_private(
    native_credential_store,
    native_case_dir,
    owned_test_process,
):
    root, store = native_credential_store
    initial_version = store.save("OpenAI", "synthetic-token-v1", expected_version=0)
    assert initial_version == 1
    reader_ready = native_case_dir / "index-reader-ready"
    reader_stop = native_case_dir / "index-reader-stop"
    reader_result = native_case_dir / "index-reader-result"
    script = "\n".join(
        [
            "import json",
            "import time",
            "from pathlib import Path",
            "from hedge_fund.runtime.credentials import _CREDENTIAL_INDEX",
            "from hedge_fund.runtime.root import RootContext",
            f"root = RootContext.open(" f"{str(root.path)!r})",
            "index = _CREDENTIAL_INDEX",
            f"ready = Path({str(reader_ready)!r})",
            f"stop = Path({str(reader_stop)!r})",
            f"result = Path({str(reader_result)!r})",
            "ready.write_text('ready', encoding='utf-8')",
            "count = 0",
            "try:",
            "    while not stop.exists():",
            "        record = json.loads(root.read_bytes(index).decode('utf-8'))",
            "        assert record['schema'] == 1",
            "        version = record['providers']['openai']['version']",
            "        assert type(version) is int and 1 <= version <= 41",
            "        count += 1",
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
    _wait_for(reader_ready, child)
    try:
        version = initial_version
        for index in range(40):
            version = store.save(
                "OpenAI",
                f"synthetic-token-{index + 2}",
                expected_version=version,
            )
    finally:
        reader_stop.touch()
    exit_code = child.wait(timeout=10)
    assert exit_code == 0, reader_result.read_text(encoding="utf-8")
    assert int(reader_result.read_text(encoding="utf-8")) > 0
    assert version == 41
    assert store.version("OpenAI") == (41, True)

    settings = resolve_settings(root)
    capture = freeze_capture(
        root=root,
        subject_id="native-credential-case",
        mandate_digest="a" * 64,
        universe=("AAA",),
        broker="paper",
        settings=settings,
        credential_versions={"openai": version},
        code_version="native-test",
    )
    private_bytes = capture.private_bytes()
    public = capture.public_view()
    assert capture.credential_handles["openai"].version == version
    assert capture.credential_handles["openai"].root_id == capture.root_id
    assert b"synthetic-token" not in private_bytes
    assert "credential_handles" not in public
    assert "credential_versions" not in public
    captures_path = f"{PRIVATE_ROOT}/captures"
    root.mkdir(captures_path, parents=True, mode=0o700)
    capture_path = f"{captures_path}/{capture.capture_id}.json"
    root.write_bytes(capture_path, private_bytes)
    persisted_capture = root.read_bytes(capture_path)
    assert persisted_capture == private_bytes
    if sys.platform.startswith("linux"):
        capture_directory = root.path / PRIVATE_ROOT / "captures"
        capture_file = root.path / PRIVATE_ROOT / "captures" / f"{capture.capture_id}.json"
        assert capture_directory.stat().st_uid == os.geteuid()
        assert stat.S_IMODE(capture_directory.stat().st_mode) == 0o700
        assert capture_file.stat().st_uid == os.geteuid()
        assert stat.S_IMODE(capture_file.stat().st_mode) == 0o600
    assert FrozenCapture.from_private_bytes(root, persisted_capture) == capture


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux POSIX credential mode verification",
)
def test_linux_credential_modes_and_owner_are_private(native_credential_store):
    root, store = native_credential_store
    version = store.save("OpenAI", "synthetic-linux-token", expected_version=0)
    private_path = root.path / PRIVATE_ROOT
    credentials_path = private_path / "credentials"
    provider_path = credentials_path / "openai"
    secret_path = provider_path / "1.json"
    index_path = root.path.joinpath(*credentials._CREDENTIAL_INDEX.split("/"))

    assert private_path.stat().st_uid == os.geteuid()
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o700
    for directory in (credentials_path, provider_path):
        assert directory.stat().st_uid == os.geteuid()
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for file_path in (secret_path, index_path):
        info = file_path.stat()
        assert info.st_uid == os.geteuid()
        assert stat.S_IMODE(info.st_mode) == 0o600
    assert version == 1
    assert store.read_version("OpenAI", version) == "synthetic-linux-token"


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL verification")
def test_windows_credential_acl_owner_and_inheritance(native_credential_store):
    root, store = native_credential_store
    assert shutil.which("powershell.exe"), "PowerShell ACL inspection tool unavailable"
    assert shutil.which("icacls.exe"), "icacls ACL inspection tool unavailable"
    store.save("OpenAI", "synthetic-windows-token", expected_version=0)

    private_path = root.path / PRIVATE_ROOT
    credentials_path = private_path / "credentials"
    provider_path = credentials_path / "openai"
    secret_path = provider_path / "1.json"
    index_path = root.path.joinpath(*credentials._CREDENTIAL_INDEX.split("/"))
    paths = (
        private_path,
        credentials_path,
        provider_path,
        secret_path,
        index_path,
    )
    quoted_paths = ",".join("'" + str(path).replace("'", "''") + "'" for path in paths)
    command = (
        f"$paths=@({quoted_paths}); "
        "$rows=foreach($p in $paths) { "
        "$a=Get-Acl -LiteralPath $p; "
        "[pscustomobject]@{"
        "Path=$p;"
        "OwnerSid=$a.GetOwner("
        "[System.Security.Principal.SecurityIdentifier]).Value;"
        "Protected=$a.AreAccessRulesProtected;"
        "Rules=@($a.Access | ForEach-Object {"
        "[pscustomobject]@{"
        "Sid=$_.IdentityReference.Translate("
        "[System.Security.Principal.SecurityIdentifier]).Value;"
        "Inherited=$_.IsInherited;"
        "Rights=[string]$_.FileSystemRights;"
        "Type=[string]$_.AccessControlType"
        "}"
        "})"
        "}"
        "}; ConvertTo-Json -InputObject @($rows) -Depth 6 -Compress"
    )
    inspected = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    assert inspected.returncode == 0, inspected.stderr
    records = json.loads(inspected.stdout)
    assert len(records) == len(paths)
    current_sid = _windows_current_user_sid()
    system_sid = "S-1-5-18"
    admin_sid = "S-1-5-32-544"

    private_acl, *inherited_acls = records
    assert private_acl["OwnerSid"] == current_sid
    assert private_acl["Protected"] is True
    assert {rule["Sid"] for rule in private_acl["Rules"]} == {
        current_sid,
        system_sid,
        admin_sid,
    }
    assert all(rule["Type"] == "Allow" and "FullControl" in rule["Rights"] for rule in private_acl["Rules"])
    for record in inherited_acls:
        assert record["OwnerSid"] == current_sid
        assert record["Protected"] is False
        assert all(rule["Inherited"] for rule in record["Rules"])
        assert {rule["Sid"] for rule in record["Rules"]} == {
            current_sid,
            system_sid,
            admin_sid,
        }
        assert all(rule["Type"] == "Allow" and "FullControl" in rule["Rights"] for rule in record["Rules"])


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows NTFS native verification",
)
def test_reports_windows_ntfs_credential_execution(native_credential_store):
    root, _store = native_credential_store
    assert root.filesystem.filesystem.casefold() == "ntfs"


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux ext4 native verification",
)
def test_reports_linux_ext4_credential_execution(native_credential_store):
    root, _store = native_credential_store
    assert root.filesystem.filesystem.casefold() == "ext4"
