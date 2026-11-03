"""Synthetic-root enrollment helpers for acceptance tests."""

import os
import shutil
import uuid
from pathlib import Path

from hedge_fund.runtime.exclusion import out_of_band_exclusion_basis, SYNTHETIC_TEST_OWNED
from hedge_fund.runtime.handover import (
    enroll_fresh,
    HANDOVER_PATH,
    inspect_relocation_source,
    relocate_existing,
    RELOCATED_TOP_LEVEL,
    require_enrollment,
)
from hedge_fund.runtime.root import RootContext


def enroll_synthetic_root(path: str | Path) -> Path:
    """Give a synthetic root protocol-native write authority.

    Populated roots are relocated: their contents move to a sibling staging
    source, the relocation import copies them back through the protocol, and
    untransferred synthetic fixtures (for example a test ``.env``) are restored.
    Only use with isolated synthetic roots.
    """
    root_path = Path(path)
    with RootContext.open(root_path) as root:
        if out_of_band_exclusion_basis(root) != SYNTHETIC_TEST_OWNED:
            raise RuntimeError("synthetic enrollment requires a test-mode root inside the marked test-owned root")
        try:
            root.file_info(HANDOVER_PATH)
        except FileNotFoundError:
            if any(root.path.iterdir()):
                _relocate_in_place(root)
            else:
                enroll_fresh(root)
        else:
            require_enrollment(root)
    return root_path


def _relocate_in_place(root: RootContext) -> None:
    staging = root.path.parent / f"{root.path.name}-relocation-source-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        for entry in list(root.path.iterdir()):
            os.replace(entry, staging / entry.name)
        with RootContext.open(staging) as source:
            digest = inspect_relocation_source(source)["content_digest"]
            relocate_existing(root, source=source, expected_content_digest=digest)
    except BaseException:
        for entry in list(staging.iterdir()):
            if not (root.path / entry.name).exists():
                os.replace(entry, root.path / entry.name)
        if not any(staging.iterdir()):
            staging.rmdir()
        raise
    for entry in list(staging.iterdir()):
        if entry.name not in RELOCATED_TOP_LEVEL and entry.name != "runtime":
            os.replace(entry, root.path / entry.name)
    shutil.rmtree(staging)
