"""Test-only second process that holds or settles durable backtest capacity.

Real-API browser acceptance cannot hold an in-process demo backtest open
deterministically, so this helper plays another process sharing the root: it
durably accepts one unfinished ``backtest`` record (never started) and later
settles it through the store's fenced interrupt. It refuses any root outside
the owned ``spec005-test-*`` harness and never enrolls or relocates a root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SUBJECT = "capacity-holder"
_MARKER = b"test-owned\n"


def _owned_root(value: str) -> Path:
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1":
        raise SystemExit("capacity holder requires the owned test harness")
    from hedge_fund.test_support.network_guard import _validate_test_root

    test_root = _validate_test_root(Path(os.environ.get("HEDGE_FUND_TEST_ROOT", "")))
    marker = test_root / ".test-owned"
    if not marker.is_file() or marker.read_bytes() != _MARKER:
        raise SystemExit("capacity holder requires a test-owned root")
    root = Path(os.path.abspath(value))
    if root.parent != test_root or root.resolve(strict=True) != root:
        raise SystemExit("capacity holder root is outside the owned harness")
    return root


def hold(root_path: Path) -> dict[str, object]:
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.capture import freeze_capture
    from hedge_fund.runtime.configuration import resolve_settings
    from hedge_fund.runtime.operations import OperationStore
    from hedge_fund.runtime.root import RootContext

    now = datetime.now(timezone.utc)
    with RootContext.open(root_path) as context, RootOwnerLease.acquire(context, timeout=5.0) as lease:
        admission = AdmissionCoordinator(context, owner_lease=lease)
        store = OperationStore(context, admission=admission)
        capture = freeze_capture(
            root=context,
            subject_id=_SUBJECT,
            mandate_digest="0" * 64,
            universe=("TEST",),
            broker="paper",
            settings=resolve_settings(context, admission=admission),
            credential_versions={},
            code_version="capacity-holder",
        )
        payload = {"fund": _SUBJECT, "universe": ["TEST"], "provider": "fixture", "model": "fixture"}
        preview = store.create_preview(
            action="backtest",
            subject_id=_SUBJECT,
            expected_head="capacity-holder-head",
            due_set=(),
            capture=capture,
            operator_session="capacity-holder-session",
            payload=payload,
            now=now,
            expires_at=now + timedelta(minutes=1),
        )
        request_id = f"capacity-holder-{preview.preview_id}"
        operation = store.accept_request(
            request_id=request_id,
            action="backtest",
            subject_id=_SUBJECT,
            preview_id=preview.preview_id,
            preview_digest=preview.digest,
            confirmation_token=preview.confirmation_token,
            operator_session="capacity-holder-session",
            expected_head="capacity-holder-head",
            due_set=(),
            payload=payload,
            now=now,
        )
        return {"operation_id": operation.operation_id, "request_id": request_id, "status": operation.status.value}


def release(root_path: Path, operation_id: str) -> dict[str, object]:
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.operations import OperationStore
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(root_path) as context, RootOwnerLease.acquire(context, timeout=5.0) as lease:
        store = OperationStore(context, admission=AdmissionCoordinator(context, owner_lease=lease))
        operation = store.get_operation(operation_id)
        if operation.subject_id != _SUBJECT or operation.action != "backtest":
            raise SystemExit("capacity holder only settles its own records")
        settled = store.interrupt(operation_id, now=datetime.now(timezone.utc))
        return {"operation_id": settled.operation_id, "status": settled.status.value}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capacity_holder")
    commands = parser.add_subparsers(dest="command", required=True)
    hold_parser = commands.add_parser("hold")
    hold_parser.add_argument("--root", required=True)
    release_parser = commands.add_parser("release")
    release_parser.add_argument("--root", required=True)
    release_parser.add_argument("--operation", required=True)
    arguments = parser.parse_args(argv)
    root = _owned_root(arguments.root)
    if arguments.command == "hold":
        result = hold(root)
    else:
        result = release(root, arguments.operation)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
