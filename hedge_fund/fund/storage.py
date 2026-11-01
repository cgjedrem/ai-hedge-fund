"""Saved fund configurations on disk: find them, and write a new one."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from hedge_fund import paths
from hedge_fund.fund.spec import FundSpec, load_spec
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    root_registry_writer,
)
from hedge_fund.runtime.root import RootContext, RootPathError


@dataclass(frozen=True)
class SavedFund:
    """A saved mandate, or its loading error when unavailable."""

    path: Path
    spec: FundSpec | None = None
    error: str | None = None


class StorageAdmissionError(RuntimeError):
    """Mandate storage lacks root-bound writer admission."""


def discover_funds(directory: str | Path) -> list[SavedFund]:
    """List YAML mandates in filename order, retaining invalid files as errors.

    Files are read independently and never modified. A missing directory
    returns an empty list.
    """
    entries: list[SavedFund] = []
    for path in sorted(Path(directory).glob("*.yaml")):
        try:
            entries.append(SavedFund(path, spec=load_spec(path)))
        except ValueError as exc:
            entries.append(SavedFund(path, error=str(exc)))
    return entries


def save_spec(
    spec: FundSpec,
    directory: str | Path,
    *,
    admission: AdmissionCoordinator | None = None,
) -> Path:
    """Write *spec* as <directory>/<name>.yaml and return the path.

    Never overwrites: raises FileExistsError when a mandate already holds the
    name. Root writes require registry admission.
    """
    if not isinstance(spec, FundSpec):
        raise TypeError("a validated FundSpec is required")
    from hedge_fund.paper.deployed import validate_fund_name

    try:
        validate_fund_name(spec.name)
    except ValueError:
        raise ValueError("mandate name is invalid") from None
    if not isinstance(directory, (str, os.PathLike)):
        raise TypeError("mandate directory must be path-like")
    if admission is not None and not isinstance(admission, AdmissionCoordinator):
        raise TypeError("admission must be an AdmissionCoordinator")
    directory = Path(directory)
    configured = paths.root_context(required=False)
    root = admission.root if admission is not None else configured
    if root is None:
        raise StorageAdmissionError("mandate writes require an explicit root context")
    if configured is not None and admission is None:
        _require_root_child(configured, directory)
    relative_directory = _relative_root_path(root, directory)
    relative_file = "/".join(part for part in (relative_directory, f"{spec.name}.yaml") if part)
    payload = yaml.safe_dump(spec.model_dump(), sort_keys=False).encode("utf-8")
    try:
        with root_registry_writer(root, admission):
            if relative_directory:
                root.mkdir(relative_directory, parents=True)
            try:
                root.file_info(relative_file)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError(f"{root.path / Path(relative_file)}: mandate already exists")
            root.write_bytes(relative_file, payload)
    except (AdmissionError, RootPathError, OSError, RuntimeError) as exc:
        if isinstance(exc, FileExistsError):
            raise
        raise StorageAdmissionError("mandate writer admission is unavailable") from exc
    return root.path / Path(relative_file)


def _relative_root_path(root: RootContext, path: Path) -> str:
    root_path = os.path.normcase(os.path.abspath(os.fspath(root.path)))
    target_path = os.path.normcase(os.path.abspath(os.fspath(path)))
    try:
        common = os.path.commonpath((root_path, target_path))
    except ValueError:
        raise StorageAdmissionError("mandate directory is outside the configured root") from None
    if os.path.normcase(common) != root_path:
        raise StorageAdmissionError("mandate directory is outside the configured root")
    relative = os.path.relpath(target_path, root_path)
    return "" if relative == "." else Path(relative).as_posix()


def _require_root_child(root: RootContext, path: Path) -> None:
    _relative_root_path(root, path)
