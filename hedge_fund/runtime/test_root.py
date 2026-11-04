import ctypes
import os
import signal
import stat
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread

import pytest

import hedge_fund.runtime.root as root_module
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    FilesystemIdentity,
    RootConfigurationError,
    RootContext,
    RootPathError,
    UnsupportedFilesystemError,
    validate_filesystem,
)


@pytest.fixture
def root_context():
    contexts = []

    def open_context(path):
        context = RootContext.open(path)
        contexts.append(context)
        return context

    yield open_context

    for context in reversed(contexts):
        context.close()


def test_root_requires_explicit_absolute_existing_directory(tmp_path):
    root = tmp_path / "fixed-root"

    with pytest.raises(RootConfigurationError):
        RootContext.open(None)
    with pytest.raises(RootConfigurationError):
        RootContext.open("relative-root")
    with pytest.raises(RootConfigurationError):
        RootContext.open(root)

    assert not root.exists()


def test_inherited_root_close_does_not_acquire_parent_thread_lock(tmp_path, monkeypatch):
    context = RootContext.open(tmp_path)
    original_lock = context._identity_lock
    original_getpid = os.getpid

    class ForbiddenLock:
        def __enter__(self):
            pytest.fail("child attempted to acquire an inherited root lock")

        def __exit__(self, *_args):
            pass

    try:
        with monkeypatch.context() as child:
            child.setattr(root_module.os, "getpid", lambda: original_getpid() + 1)
            child.setattr(context, "_identity_lock", ForbiddenLock())
            context.close()
    finally:
        context._identity_lock = original_lock
        context.close()


@pytest.mark.parametrize("operation", ["revalidate", "prepare_private_storage", "verify_private_storage", "read_bytes", "enter"])
def test_inherited_root_use_is_rejected_before_parent_mutex(tmp_path, monkeypatch, operation):
    context = RootContext.open(tmp_path)
    original_getpid = os.getpid

    class ForbiddenLock:
        def __enter__(self):
            pytest.fail("child attempted to acquire the inherited root mutex")

        def __exit__(self, *_args):
            pass

    try:
        with monkeypatch.context() as child:
            child.setattr(root_module.os, "getpid", lambda: original_getpid() + 1)
            child.setattr(context, "_identity_lock", ForbiddenLock())
            with pytest.raises(RootPathError, match="fresh interpreter after fork"):
                if operation == "read_bytes":
                    context.read_bytes("missing")
                elif operation == "enter":
                    context.__enter__()
                else:
                    getattr(context, operation)()
    finally:
        context.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_forked_child_can_close_root_while_parent_thread_holds_lock(tmp_path):
    context = RootContext.open(tmp_path)
    held = Event()
    release = Event()

    def hold_root_lock():
        with context._identity_lock:
            held.set()
            release.wait(timeout=10)

    thread = Thread(target=hold_root_lock)
    thread.start()
    pid = None
    try:
        assert held.wait(timeout=5)
        pid = os.fork()
        if pid == 0:
            try:
                context.close()
            except BaseException:
                os._exit(2)
            os._exit(0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                pid = None
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                break
            time.sleep(0.01)
        else:
            pytest.fail("child blocked on the parent's root lock")
    finally:
        if pid:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        release.set()
        thread.join(timeout=5)
        context.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_forked_child_rejects_root_use_while_parent_thread_holds_lock(tmp_path):
    context = RootContext.open(tmp_path)
    held = Event()
    release = Event()

    def hold_root_lock():
        with context._identity_lock:
            held.set()
            release.wait(timeout=10)

    thread = Thread(target=hold_root_lock)
    thread.start()
    pid = None
    try:
        assert held.wait(timeout=5)
        pid = os.fork()
        if pid == 0:
            try:
                context.revalidate()
            except RootPathError:
                context.close()
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(1)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                pid = None
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                break
            time.sleep(0.01)
        else:
            pytest.fail("child blocked on the parent's root lock")
    finally:
        if pid:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        release.set()
        thread.join(timeout=5)
        context.close()


def test_explicit_root_ignores_home_cwd_and_environment(monkeypatch, tmp_path, root_context):
    root = tmp_path / "fixed-root"
    root.mkdir()
    decoy_home = tmp_path / "decoy-home"
    decoy_cwd = tmp_path / "decoy-cwd"
    decoy_home.mkdir()
    decoy_cwd.mkdir()
    (decoy_home / ".env").write_text("ROOT=decoy\n", encoding="utf-8")
    (decoy_cwd / ".env").write_text("ROOT=decoy\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(decoy_home))
    monkeypatch.setenv("USERPROFILE", str(decoy_home))
    monkeypatch.setenv("AIHF_ROOT", str(decoy_home))
    monkeypatch.chdir(decoy_cwd)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("implicit root discovery used")

    monkeypatch.setattr(Path, "home", forbidden)
    monkeypatch.setattr(Path, "cwd", forbidden)

    context = root_context(root)

    assert context.path == root.resolve()
    assert context.dotenv_path == root / ".env"


def test_supported_filesystems_are_local_ntfs_or_ext4():
    validate_filesystem(
        FilesystemIdentity(
            filesystem="NTFS",
            device="volume-1",
            local=True,
            cloud_synced=False,
        )
    )
    validate_filesystem(
        FilesystemIdentity(
            filesystem="ext4",
            device="device-1",
            local=True,
            cloud_synced=False,
        )
    )


@pytest.mark.parametrize(
    "identity",
    [
        FilesystemIdentity("SMB", "share-1", False, False),
        FilesystemIdentity("NFS", "mount-1", False, False),
        FilesystemIdentity("NTFS", "mapped-1", False, False),
        FilesystemIdentity("NTFS", "cloud-1", True, True),
        FilesystemIdentity("FAT32", "device-2", True, False),
        FilesystemIdentity("unknown", "", True, False),
    ],
)
def test_unsupported_filesystem_identity_fails_closed(identity):
    with pytest.raises(UnsupportedFilesystemError):
        validate_filesystem(identity)


def test_invalid_filesystem_identity_shape_fails_closed():
    with pytest.raises(UnsupportedFilesystemError):
        validate_filesystem(FilesystemIdentity(1, "", True, False))


@pytest.mark.skipif(os.name != "nt", reason="Windows cloud API")
def test_cloud_detection_fails_closed_on_unknown_windows_status(monkeypatch):
    class Query:
        argtypes = None
        restype = None

        def __init__(self, result):
            self.result = result

        def __call__(self, *_args):
            return self.result

    class CloudApi:
        def __init__(self, result):
            self.CfGetSyncRootInfoByPath = Query(result)

    monkeypatch.setattr(
        root_module.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: CloudApi(ctypes.c_long(0x80070186).value),
    )
    assert not root_module._windows_cloud_synced(Path("C:/synthetic-root"))

    monkeypatch.setattr(
        root_module.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: CloudApi(0),
    )
    assert root_module._windows_cloud_synced(Path("C:/synthetic-root"))

    unknown_api = CloudApi(ctypes.c_long(0x80070005).value)
    monkeypatch.setattr(root_module.ctypes, "WinDLL", lambda *_args, **_kwargs: unknown_api)

    with pytest.raises(UnsupportedFilesystemError, match="could not be verified"):
        root_module._windows_cloud_synced(Path("C:/synthetic-root"))


def test_handle_relative_atomic_write_replaces_and_reads_inside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        context.mkdir("cache/llm")
        context.write_bytes("record.json", b"first")
        context.write_bytes("record.json", b"second")
        context.write_bytes("cache/llm/prompt.json", b"prompt")
        assert context.read_bytes("record.json") == b"second"
        assert context.read_bytes("cache/llm/prompt.json") == b"prompt"

    assert (root / "record.json").read_bytes() == b"second"
    assert (root / "cache" / "llm" / "prompt.json").read_bytes() == b"prompt"
    assert list(root.glob(".*.tmp")) == []


def test_handle_relative_append_preserves_bytes_and_rejects_hardlinks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "paper" / "alpha").mkdir(parents=True)

    with RootContext.open(root) as context:
        context.append_bytes("paper/alpha/events.jsonl", b"first\n")
        context.append_bytes("paper/alpha/events.jsonl", b"second\n", durable=True)
        assert context.read_bytes("paper/alpha/events.jsonl") == b"first\nsecond\n"

    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"protected\n")
    os.link(outside, root / "paper" / "alpha" / "linked.jsonl")
    with RootContext.open(root) as context:
        with pytest.raises(RootPathError, match="single-link regular file"):
            context.append_bytes("paper/alpha/linked.jsonl", b"changed\n")

    assert outside.read_bytes() == b"protected\n"
    assert (root / "paper" / "alpha" / "linked.jsonl").read_bytes() == b"protected\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows ctypes ABI retention")
@pytest.mark.parametrize("operation", ["revalidate", "private-storage", "atomic-write"])
def test_windows_root_guards_do_not_retain_new_pointer_types_per_call(tmp_path, operation):
    pointer_type_cache = getattr(ctypes, "_pointer_type_cache", None)
    if not isinstance(pointer_type_cache, dict):
        pytest.skip("Windows CPython pointer-type cache is unavailable")

    class PointerCacheProbe(ctypes.Structure):
        _fields_ = [("value", ctypes.c_int)]

    cache_size = len(pointer_type_cache)
    ctypes.POINTER(PointerCacheProbe)
    if len(pointer_type_cache) == cache_size:
        pytest.skip("this CPython version does not expose pointer-type cache growth")

    root = tmp_path / "abi-root"
    root.mkdir()
    with RootContext.open(root) as context:
        context.prepare_private_storage()

        def exercise():
            if operation == "revalidate":
                context.revalidate()
            elif operation == "private-storage":
                assert context.verify_private_storage()
            else:
                context.write_bytes("record.json", b"synthetic")
                assert context.read_bytes("record.json") == b"synthetic"

        def retained_types():
            return {key for key in pointer_type_cache if getattr(key, "__module__", None) == root_module.__name__}

        exercise()
        before = retained_types()
        for _ in range(3):
            exercise()
        assert retained_types() == before


def test_handle_relative_rename_moves_regular_file_without_replacing(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        context.mkdir("mandates")
        context.write_bytes("mandates/old.yaml", b"old")
        renamed = context.rename_file("mandates/old.yaml", "mandates/new.yaml")

        assert renamed == root / "mandates" / "new.yaml"
        assert context.read_bytes("mandates/new.yaml") == b"old"
        with pytest.raises(FileNotFoundError):
            context.file_info("mandates/old.yaml")

        context.write_bytes("mandates/old.yaml", b"replacement")
        with pytest.raises(FileExistsError):
            context.rename_file("mandates/new.yaml", "mandates/old.yaml")

        assert context.read_bytes("mandates/new.yaml") == b"old"
        assert context.read_bytes("mandates/old.yaml") == b"replacement"


def test_handle_relative_rename_rejects_escape_and_non_file(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.yaml"
    root.mkdir()
    outside.write_bytes(b"outside")

    with RootContext.open(root) as context:
        context.write_bytes("record.yaml", b"inside")
        context.mkdir("subdir")
        with pytest.raises(RootPathError):
            context.rename_file("../outside.yaml", "moved.yaml")
        with pytest.raises(RootPathError):
            context.rename_file("record.yaml", "../outside.yaml")
        with pytest.raises((RootPathError, OSError)):
            context.rename_file("subdir", "moved.yaml")

    assert outside.read_bytes() == b"outside"


def test_open_reader_does_not_block_atomic_replacement(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    opened = Event()
    release = Event()

    with RootContext.open(root) as context:
        context.write_bytes("record.json", b"old")
        if os.name == "nt":
            original_read = root_module._windows_read_handle

            def paused_read(handle):
                opened.set()
                assert release.wait(timeout=5)
                return original_read(handle)

            monkeypatch.setattr(root_module, "_windows_read_handle", paused_read)
        else:
            original_open = root_module.os.open

            def paused_open(path, *args, **kwargs):
                descriptor = original_open(path, *args, **kwargs)
                if path == "record.json":
                    opened.set()
                    assert release.wait(timeout=5)
                return descriptor

            monkeypatch.setattr(root_module.os, "open", paused_open)

        with ThreadPoolExecutor(max_workers=1) as pool:
            reader = pool.submit(context.read_bytes, "record.json")
            assert opened.wait(timeout=5)
            try:
                context.write_bytes("record.json", b"new")
            finally:
                release.set()
            assert reader.result(timeout=5) == b"old"

        assert context.read_bytes("record.json") == b"new"


def test_concurrent_root_validation_and_private_storage_checks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        context.prepare_private_storage()
        context.write_bytes("record.json", b"record")

        def verify_private_storage():
            return all(context.verify_private_storage() for _ in range(8))

        def read_root_file():
            return all(context.read_bytes("record.json") == b"record" for _ in range(32))

        with ThreadPoolExecutor(max_workers=2) as pool:
            verify = pool.submit(verify_private_storage)
            read = pool.submit(read_root_file)
            assert verify.result(timeout=20)
            assert read.result(timeout=20)


def test_atomic_replace_failure_preserves_record_and_original_error(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "root"
    root.mkdir()
    failure = OSError(5, "synthetic replace failure")

    def fail_replace(*_args, **_kwargs):
        raise failure

    with RootContext.open(root) as context:
        context.write_bytes("record.json", b"before")
        if os.name == "nt":
            monkeypatch.setattr(
                root_module,
                "_windows_rename_handle",
                fail_replace,
            )
        else:
            monkeypatch.setattr(
                root_module.os,
                "replace",
                fail_replace,
            )

        with pytest.raises(OSError) as raised:
            context.write_bytes("record.json", b"after")

        assert raised.value is failure
        assert context.read_bytes("record.json") == b"before"

    assert list(root.glob(".*.tmp")) == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO is unavailable")
def test_posix_fifo_read_fails_without_blocking(tmp_path):
    from hedge_fund.test_support.network_guard import (
        child_test_environment,
        guarded_test_python_command,
    )

    root = tmp_path / "root"
    root.mkdir()
    os.mkfifo(root / "pipe")
    script = """
import sys
from hedge_fund.runtime.root import RootContext, RootPathError

try:
    with RootContext.open(sys.argv[1]) as context:
        context.read_bytes("pipe")
except RootPathError:
    raise SystemExit(0)
raise SystemExit(1)
"""

    completed = subprocess.run(
        guarded_test_python_command("-c", script, str(root)),
        env=child_test_environment(),
        capture_output=True,
        text=True,
        timeout=3,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("alias", ["WATCHT~1", "watchtower~2", "PRIVAT~1.json"])
def test_windows_short_name_aliases_are_rejected(alias):
    with pytest.raises(RootPathError, match="short-name aliases"):
        root_module._relative_parts(f"runtime/{alias}")


def test_private_storage_verifies_native_permissions(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        assert context.private_storage_verified is False
        context.prepare_private_storage()
        assert context.private_storage_verified is True
        if os.name != "nt":
            private_root = root / root_module.PRIVATE_ROOT
            assert stat.S_IMODE(private_root.stat().st_mode) == 0o700
            private_root.chmod(0o755)
            assert context.private_storage_verified is False


def test_lock_file_handle_is_root_relative_and_closed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        context.mkdir("runtime/admission/v1")
        lock_handle = context.open_lock_file("runtime/admission/v1/registry.lock")
        try:
            assert lock_handle.handle is not None if os.name == "nt" else lock_handle.fd is not None
        finally:
            lock_handle.close()

    assert (root / "runtime" / "admission" / "v1" / "registry.lock").is_file()


def test_lock_file_open_rejects_reparse_leaf(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.lock"
    root.mkdir()
    outside.write_text("synthetic", encoding="utf-8")
    link = root / "alias.lock"
    try:
        os.symlink(outside, link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"file reparse creation unavailable: {exc}")

    with RootContext.open(root) as context:
        with pytest.raises(RootPathError):
            context.open_lock_file("alias.lock")

    assert outside.read_text(encoding="utf-8") == "synthetic"


@pytest.mark.parametrize(
    "relative",
    [
        "../outside",
        r"..\outside",
        "/absolute",
        r"C:\outside",
        r"\\server\share",
        "NUL",
        "paper/COM1.txt",
        "mandates/trailing.",
        "mandates/trailing ",
    ],
)
def test_child_path_rejects_escape_and_platform_aliases(relative, tmp_path, root_context):
    context = root_context(tmp_path)

    with pytest.raises(RootPathError):
        context.resolve(relative)


@pytest.mark.parametrize("name", ["Alpha.yaml", "alpha.yml", "ALPHA.YAML"])
def test_yaml_and_case_aliases_share_one_identity(name):
    with pytest.raises(RootPathError, match="already exists"):
        ensure_unique_resource_name(name, ["alpha.yml"])


@pytest.mark.parametrize(
    "protected",
    ["watchtower", "WATCHTOWER-WEEKLY", "Umbrella"],
)
def test_protected_root_aliases_are_denied_before_path_access(protected, monkeypatch, tmp_path):
    candidate = tmp_path / protected
    original_lstat = Path.lstat

    def deny_protected_probe(path, *args, **kwargs):
        if path.name.casefold() == protected.casefold():
            raise AssertionError("protected path was probed")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", deny_protected_probe)

    with pytest.raises(RootPathError, match="protected"):
        RootContext.open(candidate)

    assert not candidate.exists()


def test_reparse_child_is_denied_before_read(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("synthetic", encoding="utf-8")
    link = root / "alias"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory reparse creation unavailable: {exc}")

    with RootContext.open(root) as context:
        with pytest.raises(RootPathError):
            context.read_bytes("alias/sentinel.txt")

    assert sentinel.read_text(encoding="utf-8") == "synthetic"


def test_handle_relative_mkdir_rejects_reparse_parent(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "alias"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory reparse creation unavailable: {exc}")

    with RootContext.open(root) as context:
        with pytest.raises(RootPathError):
            context.mkdir("alias/nested")

    assert not (outside / "nested").exists()


def test_root_replacement_is_denied_or_detected_before_child_access(tmp_path, root_context):
    root = tmp_path / "root"
    moved = tmp_path / "moved-root"
    root.mkdir()
    (root / "record.txt").write_text("original", encoding="utf-8")
    context = root_context(root)
    if os.name == "nt":
        with pytest.raises(OSError):
            root.rename(moved)
        assert context.read_bytes("record.txt") == b"original"
        assert not moved.exists()
    else:
        root.rename(moved)
        root.mkdir()
        (root / "record.txt").write_text("replacement", encoding="utf-8")
        with pytest.raises(RootPathError, match="identity changed"):
            context.read_bytes("record.txt")
        assert (root / "record.txt").read_text(encoding="utf-8") == "replacement"
        assert (moved / "record.txt").read_text(encoding="utf-8") == "original"


def test_root_atomic_write_rejects_escape_without_creating_target(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"

    with RootContext.open(root) as context:
        with pytest.raises(RootPathError):
            context.write_bytes("../outside.txt", b"no")

    assert not outside.exists()


def test_root_identity_stays_bound_to_original_directory_after_rename(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    moved = tmp_path / "moved-root"
    with RootContext.open(root) as context:
        if os.name == "nt":
            with pytest.raises(OSError):
                root.rename(moved)
            assert context.resolve("record.json") == root / "record.json"
            assert not moved.exists()
        else:
            root.rename(moved)
            root.mkdir()
            with pytest.raises(RootPathError, match="identity changed"):
                context.resolve("record.json")
