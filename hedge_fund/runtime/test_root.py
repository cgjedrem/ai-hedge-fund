import ctypes
import os
from pathlib import Path

import pytest

import hedge_fund.runtime.root as root_module
from hedge_fund.runtime.root import ensure_unique_resource_name, FilesystemIdentity, RootConfigurationError, RootContext, RootPathError, UnsupportedFilesystemError, validate_filesystem


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
