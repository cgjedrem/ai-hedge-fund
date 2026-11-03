"""Native semantics of the no-follow RootContext.unlink_file primitive (T021)."""

import os
import stat
from pathlib import Path

import pytest

from hedge_fund.runtime.root import RootContext, RootPathError


def _link_directory(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_unlink_removes_one_regular_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "file.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a" / "keep.json").write_text("{}", encoding="utf-8")
    with RootContext.open(tmp_path) as root:
        root.unlink_file("a/file.json")
    assert not (tmp_path / "a" / "file.json").exists()
    assert (tmp_path / "a" / "keep.json").exists()


def test_unlink_missing_file_raises_file_not_found(tmp_path):
    with RootContext.open(tmp_path) as root:
        with pytest.raises(FileNotFoundError):
            root.unlink_file("missing.json")


def test_unlink_refuses_directory(tmp_path):
    (tmp_path / "folder").mkdir()
    with RootContext.open(tmp_path) as root:
        with pytest.raises((OSError, RootPathError)):
            root.unlink_file("folder")
    assert (tmp_path / "folder").is_dir()


def test_unlink_refuses_traversal_and_absolute_paths(tmp_path):
    with RootContext.open(tmp_path) as root:
        for relative in ("../outside.json", str(tmp_path / "x.json"), ""):
            with pytest.raises((RootPathError, ValueError)):
                root.unlink_file(relative)


def test_unlink_never_follows_link_parent_outside_root(tmp_path):
    inside = tmp_path / "root"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (outside / "victim.json").write_text("{}", encoding="utf-8")
    _link_directory(inside / "link", outside)
    with RootContext.open(inside) as root:
        with pytest.raises(RootPathError):
            root.unlink_file("link/victim.json")
    assert (outside / "victim.json").read_text(encoding="utf-8") == "{}"


def test_unlink_never_removes_link_leaf_or_its_target(tmp_path):
    inside = tmp_path / "root"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (outside / "victim.json").write_text("{}", encoding="utf-8")
    _link_directory(inside / "leaf", outside)
    with RootContext.open(inside) as root:
        with pytest.raises((OSError, RootPathError)):
            root.unlink_file("leaf")
    assert (outside / "victim.json").exists()
    assert os.path.lexists(inside / "leaf")


def test_unlink_never_follows_file_symlink(tmp_path):
    inside = tmp_path / "root"
    inside.mkdir()
    victim = tmp_path / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    try:
        os.symlink(victim, inside / "alias.json")
    except OSError:
        pytest.skip("file symlinks are unavailable for this account")
    with RootContext.open(inside) as root:
        with pytest.raises((OSError, RootPathError)):
            root.unlink_file("alias.json")
    assert victim.exists()


@pytest.mark.skipif(os.name != "nt", reason="the read-only attribute blocks deletion only on Windows")
def test_unlink_read_only_file_fails_like_the_legacy_unlink(tmp_path):
    target = tmp_path / "locked.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)
    try:
        with RootContext.open(tmp_path) as root:
            with pytest.raises(OSError):
                root.unlink_file("locked.json")
        assert target.exists()
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="open handles block deletion only on Windows")
def test_unlink_open_file_without_delete_share_fails_and_keeps_it(tmp_path):
    target = tmp_path / "busy.json"
    target.write_text("{}", encoding="utf-8")
    with open(target, encoding="utf-8"):
        with RootContext.open(tmp_path) as root:
            with pytest.raises(OSError):
                root.unlink_file("busy.json")
    assert target.exists()
