"""Build-time source identity for packaged Docker artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import re
from pathlib import Path
from typing import Sequence

_BUILD_IDENTITY_MODULE = "_build_identity.py"
_REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def source_sha256(package_root: str | Path) -> str:
    """Hash package-relative source paths and bytes."""
    root = Path(package_root)
    if root.is_symlink():
        raise ValueError("package root must not be a symlink")
    if not root.is_absolute():
        root = root.resolve()
    if not root.is_dir():
        raise ValueError("package root must be an existing directory")

    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError("package source must not contain symlinks")
        if not path.is_file():
            continue
        if relative == Path(_BUILD_IDENTITY_MODULE) or path.name == ".env" or "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"} or relative.parts[:2] == ("web", "static"):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        count += 1
    if count == 0:
        raise ValueError("package source is empty")
    return digest.hexdigest()


def bake_build_identity(
    package_root: str | Path,
    revision: str,
    expected_source_sha256: str,
) -> tuple[str, str]:
    """Verify source identity, then write package-local immutable constants."""
    if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("source revision must be a full lowercase Git object ID")
    if not isinstance(expected_source_sha256, str) or _SHA256_PATTERN.fullmatch(expected_source_sha256) is None:
        raise ValueError("source SHA-256 must be 64 lowercase hexadecimal characters")

    root = Path(package_root)
    if root.is_symlink():
        raise ValueError("package root must not be a symlink")
    if not root.is_absolute():
        root = root.resolve()
    digest = source_sha256(root)
    if digest != expected_source_sha256:
        raise ValueError("package source SHA-256 does not match the build argument")

    identity_path = root / _BUILD_IDENTITY_MODULE
    if identity_path.is_symlink():
        raise ValueError("build identity target must not be a symlink")
    identity_path.write_text(
        f"SOURCE_REVISION = {revision!r}\nSOURCE_SHA256 = {digest!r}\n",
        encoding="ascii",
    )
    return revision, digest


def baked_build_identity() -> tuple[str, str] | None:
    """Return validated baked identity; absent module means non-image source."""
    try:
        module = importlib.import_module("hedge_fund._build_identity")
    except ModuleNotFoundError as exc:
        if exc.name == "hedge_fund._build_identity":
            return None
        raise

    revision = getattr(module, "SOURCE_REVISION", None)
    source_hash = getattr(module, "SOURCE_SHA256", None)
    if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
        raise RuntimeError("baked source revision is invalid")
    if not isinstance(source_hash, str) or _SHA256_PATTERN.fullmatch(source_hash) is None:
        raise RuntimeError("baked source SHA-256 is invalid")
    return revision, source_hash


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bake verified package source identity.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        bake_build_identity(args.root, args.revision, args.expected_source_sha256)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
