"""Synthetic-root enrollment helpers for acceptance tests."""

from pathlib import Path

from hedge_fund.runtime.handover import (
    build_head_inventory,
    enroll_fresh,
    HANDOVER_PATH,
    inventory_digest,
    migrate_existing,
    OPERATOR_ATTESTATION,
    require_enrollment,
)
from hedge_fund.runtime.root import RootContext


def enroll_synthetic_root(path: str | Path) -> Path:
    root_path = Path(path)
    with RootContext.open(root_path) as root:
        try:
            root.file_info(HANDOVER_PATH)
        except FileNotFoundError:
            if any(root.path.iterdir()):
                heads = build_head_inventory(root)
                migrate_existing(
                    root,
                    expected_inventory_digest=inventory_digest(heads),
                    operator_attestation=OPERATOR_ATTESTATION,
                )
            else:
                enroll_fresh(root)
        else:
            require_enrollment(root)
    return root_path
