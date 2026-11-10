import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, current_thread, Event

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.operations import (
    CAPTURE_ROOT,
    ConfirmationExpired,
    ConfirmationRejected,
    DUPLICATE_LOGICAL_OPERATION_REASON,
    DuplicateLogicalOperationRefusal,
    INDEX_PATH,
    OperationCapacityExceeded,
    OperationConflict,
    OperationError,
    OPERATIONS_ROOT,
    OperationStartUncertain,
    OperationStatus,
    OperationStore,
    StalePreview,
    WorkerFenced,
)
from hedge_fund.runtime.root import RootContext

_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def root_context(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        yield context


@pytest.fixture
def operation_store(root_context):
    owner_lease = RootOwnerLease.acquire(root_context)
    admission = AdmissionCoordinator(root_context, owner_lease=owner_lease)
    try:
        yield OperationStore(root_context, admission=admission)
    finally:
        owner_lease.close()


@pytest.fixture
def frozen_capture(root_context):
    settings = resolve_settings(root_context)
    return freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="a" * 64,
        universe=("AAA", "BBB"),
        broker="paper",
        settings=settings,
        credential_versions={},
        code_version="synthetic-code-stamp",
    )


def _preview(
    store,
    capture,
    *,
    action="paper-run",
    subject_id="alpha",
    expected_head="head-1",
    payload=None,
    due_set=("2026-10-31", "2026-11-01"),
    expires_at=None,
):
    return store.create_preview(
        action=action,
        subject_id=subject_id,
        expected_head=expected_head,
        due_set=due_set,
        capture=capture,
        operator_session="operator-1",
        payload={"mode": "manual", "limit": 1} if payload is None else payload,
        now=_NOW,
        expires_at=_NOW + timedelta(minutes=1) if expires_at is None else expires_at,
    )


def _accept(
    store,
    preview,
    *,
    request_id="request-1",
    payload=None,
    operator_session="operator-1",
    expected_head=None,
    due_set=None,
    now=_NOW,
    start_worker=None,
    current_state_resolver=None,
    capacity=None,
):
    return store.accept_request(
        request_id=request_id,
        action=preview.action,
        subject_id=preview.subject_id,
        preview_id=preview.preview_id,
        preview_digest=preview.digest,
        confirmation_token=preview.confirmation_token,
        operator_session=operator_session,
        expected_head=preview.expected_head if expected_head is None else expected_head,
        due_set=preview.due_set if due_set is None else due_set,
        payload=preview.payload if payload is None else payload,
        now=now,
        start_worker=start_worker,
        current_state_resolver=current_state_resolver,
        capacity=capacity,
    )


def test_duplicate_logical_operation_refusal_contract_fields():
    logical_key = hashlib.sha256(b"logical-operation").hexdigest()
    refusal = DuplicateLogicalOperationRefusal("a" * 32, logical_key)

    assert refusal.reason == DUPLICATE_LOGICAL_OPERATION_REASON
    assert refusal.fields == {
        "reason": "duplicate-logical-operation",
        "existing_operation_id": "a" * 32,
        "logical_key": logical_key,
    }


def test_logical_operation_key_normalizes_target_shape_and_payload_order():
    from hedge_fund.runtime.operations import derive_logical_operation_key

    first_payload = {"mode": "manual", "limits": {"calls": 2, "cost": "0"}}
    reordered_payload = {"limits": {"cost": "0", "calls": 2}, "mode": "manual"}

    def digest(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()

    web_shape = derive_logical_operation_key(
        subject_id="alpha",
        action="paper-run",
        target=("2026-10-31",),
        payload_digest=digest(first_payload),
    )
    cli_shape = derive_logical_operation_key(
        subject_id="alpha",
        action="paper-run",
        target="2026-10-31",
        payload_digest=digest(reordered_payload),
    )

    assert web_shape == cli_shape


def test_logical_operation_key_separates_fund_action_target_and_payload():
    from hedge_fund.runtime.operations import derive_logical_operation_key

    payload_digest = hashlib.sha256(b"reviewed-payload").hexdigest()
    base = derive_logical_operation_key(
        subject_id="alpha",
        action="paper-run",
        target=("2026-10-31",),
        payload_digest=payload_digest,
    )
    variants = {
        derive_logical_operation_key(
            subject_id="beta",
            action="paper-run",
            target=("2026-10-31",),
            payload_digest=payload_digest,
        ),
        derive_logical_operation_key(
            subject_id="alpha",
            action="paper-runner-start",
            target=("2026-10-31",),
            payload_digest=payload_digest,
        ),
        derive_logical_operation_key(
            subject_id="alpha",
            action="paper-run",
            target=("2026-11-01",),
            payload_digest=payload_digest,
        ),
        derive_logical_operation_key(
            subject_id="alpha",
            action="paper-run",
            target=("2026-10-31",),
            payload_digest=hashlib.sha256(b"different-reviewed-payload").hexdigest(),
        ),
    }

    assert len(variants) == 4
    assert base not in variants


@pytest.mark.parametrize("action", ("backtest", "lifecycle-restore"))
def test_logical_dedup_does_not_block_nonpaper_operations(operation_store, frozen_capture, action):
    first = _accept(
        operation_store,
        _preview(operation_store, frozen_capture, action=action),
        request_id="backtest-first",
    )
    second = _accept(
        operation_store,
        _preview(operation_store, frozen_capture, action=action),
        request_id="backtest-second",
    )

    assert first.operation_id != second.operation_id
    assert first.logical_key is None
    assert second.logical_key is None


def test_logical_duplicate_nonterminal_operation_refuses_and_links_existing(operation_store, frozen_capture):
    first_preview = _preview(operation_store, frozen_capture)
    starts = []
    first = _accept(operation_store, first_preview, start_worker=starts.append)
    second_preview = _preview(operation_store, frozen_capture)

    with pytest.raises(DuplicateLogicalOperationRefusal) as refused:
        _accept(
            operation_store,
            second_preview,
            request_id="request-2",
            start_worker=lambda operation: starts.append(operation.operation_id),
        )

    assert refused.value.fields == {
        "reason": "duplicate-logical-operation",
        "existing_operation_id": first.operation_id,
        "logical_key": first.logical_key,
    }
    assert operation_store.get_by_request("request-2") is None
    assert operation_store._read_index()["previews"][second_preview.preview_id]["state"] == "issued"
    assert [operation.operation_id for operation in starts] == [first.operation_id]


def test_logical_duplicate_interrupted_operation_still_blocks_retry(operation_store, frozen_capture):
    first = _accept(operation_store, _preview(operation_store, frozen_capture))
    interrupted = operation_store.interrupt(first.operation_id, now=_NOW + timedelta(seconds=1))
    assert interrupted.status is OperationStatus.INTERRUPTED

    with pytest.raises(DuplicateLogicalOperationRefusal) as refused:
        _accept(
            operation_store,
            _preview(operation_store, frozen_capture),
            request_id="request-2",
        )

    assert refused.value.fields["existing_operation_id"] == first.operation_id


def test_logical_duplicate_terminal_failure_frees_key(operation_store, frozen_capture):
    first = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(first.operation_id, worker_id="synthetic-worker", now=_NOW)
    operation_store.mark_running(first.operation_id, fence, now=_NOW)
    failed = operation_store.fail(
        first.operation_id,
        fence,
        error_code="provider-unavailable",
        now=_NOW + timedelta(seconds=1),
    )
    second = _accept(
        operation_store,
        _preview(operation_store, frozen_capture),
        request_id="request-2",
    )

    assert failed.status is OperationStatus.FAILED
    assert second.operation_id != first.operation_id
    assert second.logical_key == first.logical_key


def test_logical_duplicate_terminal_success_frees_key(operation_store, frozen_capture):
    first = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(first.operation_id, worker_id="synthetic-worker", now=_NOW)
    operation_store.mark_running(first.operation_id, fence, now=_NOW)
    completed = operation_store.complete(
        first.operation_id,
        fence,
        result={"sessions": 1},
        now=_NOW + timedelta(seconds=1),
    )
    second = _accept(
        operation_store,
        _preview(operation_store, frozen_capture),
        request_id="request-2",
    )

    assert completed.status is OperationStatus.COMPLETED
    assert second.operation_id != first.operation_id
    assert second.logical_key == first.logical_key


def test_logical_dedup_preserves_request_replay_and_changed_payload_conflict(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    starts = []
    first = _accept(operation_store, preview, start_worker=starts.append)

    replay = _accept(
        operation_store,
        preview,
        start_worker=lambda _operation: pytest.fail("same-request replay started another worker"),
    )
    with pytest.raises(OperationConflict):
        _accept(
            operation_store,
            preview,
            payload={"mode": "manual", "limit": 2},
        )

    assert replay.operation_id == first.operation_id
    assert [operation.operation_id for operation in starts] == [first.operation_id]


def test_pre_feature_logical_record_replays_unchanged_and_never_matches(
    operation_store,
    frozen_capture,
    root_context,
):
    first = _accept(operation_store, _preview(operation_store, frozen_capture))
    logical_key = first.logical_key
    with operation_store._locked("alpha"):
        index = operation_store._read_index()
        index["operations"][first.operation_id].pop("logical_key", None)
        operation_store._write_index(index)
    legacy_bytes = root_context.read_bytes(INDEX_PATH)

    replay = operation_store.get_by_request("request-1")
    assert replay.logical_key is None
    assert root_context.read_bytes(INDEX_PATH) == legacy_bytes

    second = _accept(
        operation_store,
        _preview(operation_store, frozen_capture),
        request_id="request-2",
    )

    assert second.operation_id != first.operation_id
    assert second.logical_key == logical_key


def test_logical_duplicate_survives_fresh_store_handle_restart(
    operation_store,
    frozen_capture,
    root_context,
):
    first = _accept(operation_store, _preview(operation_store, frozen_capture))
    with RootContext.open(root_context.path) as restarted_root:
        with RootOwnerLease.acquire(restarted_root) as owner:
            restarted_store = OperationStore(
                restarted_root,
                admission=AdmissionCoordinator(restarted_root, owner_lease=owner),
            )
            preview = _preview(restarted_store, frozen_capture)
            with pytest.raises(DuplicateLogicalOperationRefusal) as refused:
                _accept(
                    restarted_store,
                    preview,
                    request_id="request-after-restart",
                )

    assert refused.value.fields["existing_operation_id"] == first.operation_id


def test_preview_digest_canonicalizes_payload_and_binds_exact_due_order(operation_store, frozen_capture):
    first_payload = {"mode": "manual", "limits": {"calls": 2, "cost": "0"}}
    equivalent_payload = {"limits": {"cost": "0", "calls": 2}, "mode": "manual"}
    first = _preview(operation_store, frozen_capture, payload=first_payload)
    equivalent = _preview(operation_store, frozen_capture, payload=equivalent_payload)
    reordered_due_set = _preview(
        operation_store,
        frozen_capture,
        payload=equivalent_payload,
        due_set=("2026-11-01", "2026-10-31"),
    )

    assert first.digest == equivalent.digest
    assert first.digest != reordered_due_set.digest
    assert "confirmation_token" not in first.public_view()
    assert first.confirmation_token not in repr(first.public_view())
    assert first.confirmation_token not in repr(first)
    first_payload["limits"]["calls"] = 99
    assert first.payload["limits"]["calls"] == 2


def test_empty_due_set_is_a_valid_explicit_nothing_due_preview(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture, due_set=())
    operation = _accept(operation_store, preview)

    assert preview.due_set == ()
    assert operation.status is OperationStatus.ACCEPTED


def test_operation_observation_does_not_create_or_change_sidecars(
    operation_store,
    frozen_capture,
    root_context,
):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    runtime = root_context.path / "runtime"
    before = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file() and path.suffix != ".lock"}

    observed = operation_store.get_operation(operation.operation_id)

    after = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file() and path.suffix != ".lock"}
    assert observed.operation_id == operation.operation_id
    assert after == before


def test_operation_observation_remains_available_when_writer_owner_is_unknown(
    operation_store,
    frozen_capture,
    root_context,
):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    observer = OperationStore(
        root_context,
        admission=AdmissionCoordinator(root_context),
    )

    observed = observer.get_operation(operation.operation_id)

    assert observed.operation_id == operation.operation_id
    assert observed.status is OperationStatus.ACCEPTED


def test_missing_index_reports_missing_operation_without_creating_lock_state(
    operation_store,
    root_context,
):
    with pytest.raises(OperationError, match="operation record was not found"):
        operation_store.get_operation("0" * 32)

    assert not root_context.resolve(INDEX_PATH).exists()
    assert not root_context.resolve("runtime/admission/v1/registry.lock").exists()


def test_preview_token_is_not_persisted_and_private_storage_defaults_denied(
    operation_store,
    root_context,
    frozen_capture,
):
    denied_store = OperationStore(
        root_context,
        admission=AdmissionCoordinator(root_context),
    )

    with pytest.raises(OperationError):
        _preview(denied_store, frozen_capture)
    assert not root_context.resolve(OPERATIONS_ROOT).exists()

    preview = _preview(operation_store_for(root_context, operation_store._admission), frozen_capture)
    index = root_context.read_bytes(INDEX_PATH)
    preview_record = root_context.read_bytes(f"{OPERATIONS_ROOT}/previews/{preview.preview_id}.json")

    assert preview.confirmation_token.encode("utf-8") not in index
    assert preview.confirmation_token.encode("utf-8") not in preview_record


def test_preview_is_bound_to_operator_session_and_expiry(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)

    with pytest.raises(ConfirmationRejected):
        _accept(operation_store, preview, operator_session="different-operator")
    with pytest.raises(ConfirmationExpired):
        _accept(operation_store, preview, now=preview.expires_at)

    assert operation_store.get_by_request("request-1") is None


def test_confirmation_is_single_use_and_same_request_replay_is_idempotent(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    starts = []

    def start_worker(operation):
        stored = operation_store.get_operation(operation.operation_id)
        assert stored.status is OperationStatus.ACCEPTED
        starts.append(operation.operation_id)

    first = _accept(operation_store, preview, start_worker=start_worker)
    replay = _accept(
        operation_store,
        preview,
        start_worker=lambda _operation: pytest.fail("idempotent replay started another worker"),
    )

    assert replay.operation_id == first.operation_id
    assert starts == [first.operation_id]

    with pytest.raises(ConfirmationRejected):
        _accept(operation_store, preview, request_id="request-2")


def test_idempotent_paper_replay_does_not_wait_for_runner_lane(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    first = _accept(operation_store, preview)

    with operation_store._admission.runner_reservation("alpha", timeout=0):
        replay = _accept(
            operation_store,
            preview,
            start_worker=lambda _operation: pytest.fail("replay started another worker"),
        )

    assert replay.operation_id == first.operation_id
    assert replay.status is OperationStatus.ACCEPTED


def test_confirmation_race_admits_only_one_request(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    barrier = Barrier(2)
    starts = []

    def submit(request_id):
        barrier.wait(timeout=5)
        try:
            operation = _accept(
                operation_store,
                preview,
                request_id=request_id,
                start_worker=lambda record: starts.append(record.operation_id),
            )
            return request_id, operation
        except ConfirmationRejected:
            return request_id, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("request-a", "request-b")))

    accepted = [(request_id, operation) for request_id, operation in results if operation is not None]
    rejected = [request_id for request_id, operation in results if operation is None]
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert starts == [accepted[0][1].operation_id]
    assert operation_store.get_by_request(accepted[0][0]).operation_id == accepted[0][1].operation_id
    assert operation_store.get_by_request(rejected[0]) is None


def test_same_request_id_with_changed_payload_conflicts(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    accepted = _accept(operation_store, preview)

    with pytest.raises(OperationConflict):
        _accept(
            operation_store,
            preview,
            payload={"mode": "manual", "limit": 2},
        )

    assert operation_store.get_operation(accepted.operation_id).status is OperationStatus.ACCEPTED


def test_admission_revalidates_exact_head_and_due_set_before_worker_start(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    starts = []

    with pytest.raises(StalePreview):
        _accept(
            operation_store,
            preview,
            expected_head="head-2",
            start_worker=lambda operation: starts.append(operation.operation_id),
        )
    with pytest.raises(StalePreview):
        _accept(
            operation_store,
            preview,
            request_id="request-2",
            due_set=("2026-11-02",),
            start_worker=lambda operation: starts.append(operation.operation_id),
        )

    assert starts == []
    assert operation_store.get_by_request("request-1") is None
    assert operation_store.get_by_request("request-2") is None


@pytest.mark.parametrize("advance_worker", [False, True])
def test_accept_persists_before_worker_start_and_does_not_replay_uncertain_start(operation_store, frozen_capture, advance_worker):
    preview = _preview(operation_store, frozen_capture)
    starts = []

    def uncertain_start(operation):
        stored = operation_store.get_operation(operation.operation_id)
        assert stored.status is OperationStatus.ACCEPTED
        starts.append(operation.operation_id)
        if advance_worker:
            fence = operation_store.claim_worker(operation.operation_id, worker_id="synthetic", now=_NOW + timedelta(seconds=1))
            operation_store.mark_running(operation.operation_id, fence, now=_NOW + timedelta(seconds=2))
        raise RuntimeError("synthetic start acknowledgement lost")

    with pytest.raises(OperationStartUncertain):
        _accept(operation_store, preview, start_worker=uncertain_start)

    recovered = operation_store.get_by_request("request-1")
    assert recovered is not None
    assert recovered.status is OperationStatus.INTERRUPTED
    replay = _accept(
        operation_store,
        preview,
        start_worker=lambda _operation: pytest.fail("uncertain start was replayed"),
    )
    assert replay.status is OperationStatus.INTERRUPTED
    assert starts == [recovered.operation_id]


def test_restart_interrupts_and_fences_surviving_worker_effects(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    operation = _accept(operation_store, preview)
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)
    operation_store.recover_unfinished(now=_NOW + timedelta(seconds=1))
    effects = []

    with pytest.raises(WorkerFenced):
        operation_store.apply_if_current(
            operation.operation_id,
            fence,
            lambda: effects.append("synthetic-fill"),
        )

    assert effects == []
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.INTERRUPTED


def test_cancel_request_is_idempotent_and_acknowledged_only_at_a_safe_boundary(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    operation = _accept(operation_store, preview)
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)

    cancel_requested = operation_store.request_cancel(
        operation.operation_id,
        request_id="cancel-1",
        now=_NOW + timedelta(seconds=1),
    )
    assert cancel_requested.status is OperationStatus.CANCEL_REQUESTED
    replay = operation_store.request_cancel(
        operation.operation_id,
        request_id="cancel-1",
        now=_NOW + timedelta(seconds=2),
    )
    assert replay.status is OperationStatus.CANCEL_REQUESTED

    effects = []
    with pytest.raises(WorkerFenced):
        operation_store.apply_if_current(
            operation.operation_id,
            fence,
            lambda: effects.append("synthetic-fill"),
        )
    cancelled = operation_store.acknowledge_cancel(
        operation.operation_id,
        fence,
        now=_NOW + timedelta(seconds=3),
    )

    assert effects == []
    assert cancelled.status is OperationStatus.CANCELLED
    assert (
        operation_store.request_cancel(
            operation.operation_id,
            request_id="cancel-1",
            now=_NOW + timedelta(seconds=4),
        ).status
        is OperationStatus.CANCELLED
    )
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.CANCELLED


def test_cancel_before_worker_claim_can_finish_without_starting_a_worker(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    operation = _accept(operation_store, preview)

    operation_store.request_cancel(
        operation.operation_id,
        request_id="cancel-before-start",
        now=_NOW + timedelta(seconds=1),
    )
    cancelled = operation_store.acknowledge_cancel(
        operation.operation_id,
        None,
        now=_NOW + timedelta(seconds=2),
    )

    assert cancelled.status is OperationStatus.CANCELLED
    with pytest.raises(WorkerFenced):
        operation_store.claim_worker(
            operation.operation_id,
            worker_id="synthetic-worker",
            now=_NOW + timedelta(seconds=3),
        )


@pytest.mark.parametrize("state", ["running", "cancelled", "fenced", "state-corrupt", "capture-corrupt", "write-denied"])
def test_snapshot_workers_observe_the_operation_fence_during_paper_publication(
        root_context, operation_store, frozen_capture, monkeypatch, state
):
        from hedge_fund import paths
        from hedge_fund.data.models import PriceSnapshot
        from hedge_fund.paper.deployed import deploy
        from hedge_fund.pipeline.clock import LiveClock
        from hedge_fund.runtime import operations
        from hedge_fund.runtime.handover import paper_effect_registry
        from hedge_fund.runtime.test_inventory_cache_race import _spec

        admission = operation_store._admission
        with paths.bound_root(root_context):
            with admission.deployment_lock("alpha"):
                directory = deploy("alpha", _spec("alpha"), ["AAPL"], root=root_context.path / "paper")
            preview = _preview(operation_store, frozen_capture)
            operation = _accept(operation_store, preview)
            fence = operation_store.claim_worker(operation.operation_id, worker_id="synthetic", now=_NOW)
            operation_store.mark_running(operation.operation_id, fence, now=_NOW)
            if state == "cancelled":
                operation_store.request_cancel(operation.operation_id, request_id="cancel-1", now=_NOW)
            elif state == "fenced":
                operation_store.recover_unfinished(now=_NOW + timedelta(seconds=1))
            elif state == "state-corrupt":
                root_context.write_bytes(f"{operations.OPERATIONS_ROOT}/state/{operation.operation_id}.json", b"{}")
            elif state == "capture-corrupt":
                root_context.write_bytes(f"{operations.CAPTURE_ROOT}/{preview.capture_id}.json", b"{}")
            monkeypatch.setattr(operations, "_MAX_LOCK_WAIT_SECONDS", 0.1)
            observed = []

            class GuardedSnapshots:
                def get_snapshot(self, ticker):
                    if state == "write-denied":
                        with pytest.raises(operations.OperationBusy):
                            operation_store.request_cancel(operation.operation_id, request_id="borrower-cancel", now=_NOW)
                    try:
                        observed.append(operation_store.cancellation_requested(operation.operation_id, fence))
                    except WorkerFenced:
                        observed.append("fenced")
                    except OperationError:
                        observed.append("corrupt")
                    return PriceSnapshot(ticker=ticker, price=100, time="2024-06-04T15:00:00Z")

            clock = LiveClock(GuardedSnapshots(), 60, _spec("alpha").window)
            with admission.manual_session("alpha"):
                with paper_effect_registry(directory, "alpha"):
                    quotes = clock.observe(["AAPL"], "2024-06-04T11:00:00")

        assert "AAPL" in quotes
        assert observed == [
            {
                "running": False,
                "cancelled": True,
                "fenced": "fenced",
                "state-corrupt": "corrupt",
                "capture-corrupt": "corrupt",
                "write-denied": False,
            }[state]
        ]


@pytest.mark.parametrize("cancelled", [False, True])
def test_web_dispatch_fence_runs_in_snapshot_worker_during_publication(
        root_context, operation_store, monkeypatch, cancelled
):
        from hedge_fund import paths
        from hedge_fund.data.models import PriceSnapshot
        from hedge_fund.paper.deployed import deploy
        from hedge_fund.pipeline.clock import LiveClock
        from hedge_fund.pipeline.session import code_version, mandate_hash
        from hedge_fund.runtime import operations
        from hedge_fund.runtime.handover import paper_effect_registry
        from hedge_fund.runtime.test_inventory_cache_race import _spec
        from hedge_fund.web.jobs import JobCancelled
        from hedge_fund.web.services import DeskService

        admission = operation_store._admission
        spec = _spec("alpha")
        with paths.bound_root(root_context):
            with admission.deployment_lock("alpha"):
                directory = deploy("alpha", spec, ["AAPL"], root=root_context.path / "paper")
            service = DeskService(root_context.path, allow_writes=True, network_enabled=True, root_context=root_context)
            try:
                capture = freeze_capture(
                    root=root_context,
                    subject_id="alpha",
                    mandate_digest=mandate_hash(spec),
                    universe=("AAPL",),
                    broker="paper",
                    settings=service._runtime_settings,
                    credential_versions={},
                    code_version=code_version(),
                    mandate_snapshot=spec.model_dump(mode="json"),
                )
                preview = operation_store.create_preview(
                    action="paper-tick",
                    subject_id="alpha",
                    expected_head=None,
                    due_set=("2024-06-04",),
                    capture=capture,
                    operator_session="operator-1",
                    payload={"expected_head": None},
                    now=_NOW,
                    expires_at=_NOW + timedelta(minutes=1),
                )
                operation = _accept(operation_store, preview)
                fence = operation_store.claim_worker(operation.operation_id, worker_id="synthetic", now=_NOW)
                operation_store.mark_running(operation.operation_id, fence, now=_NOW)
                if cancelled:
                    operation_store.request_cancel(operation.operation_id, request_id="cancel-1", now=_NOW)
                monkeypatch.setattr(operations, "_MAX_LOCK_WAIT_SECONDS", 0.1)

                class GuardedSnapshots:
                    def get_snapshot(self, ticker):
                        service._check_dispatch_fence(
                            operation,
                            capture,
                            lambda: operation_store.cancellation_requested(operation.operation_id, fence),
                            paper=True,
                        )
                        return PriceSnapshot(ticker=ticker, price=100, time="2024-06-04T15:00:00Z")

                clock = LiveClock(GuardedSnapshots(), 60, spec.window)
                with admission.manual_session("alpha"):
                    with paper_effect_registry(directory, "alpha"):
                        if cancelled:
                            with pytest.raises(JobCancelled):
                                clock.observe(["AAPL"], "2024-06-04T11:00:00")
                        else:
                            assert "AAPL" in clock.observe(["AAPL"], "2024-06-04T11:00:00")
            finally:
                service.close()


def test_snapshot_worker_cannot_borrow_operation_observation_from_another_root(root_context, operation_store, tmp_path, monkeypatch):
    from hedge_fund import paths
    from hedge_fund.paper.deployed import deploy
    from hedge_fund.pipeline.clock import LiveClock
    from hedge_fund.runtime import operations
    from hedge_fund.runtime.handover import paper_effect_registry
    from hedge_fund.runtime.test_inventory_cache_race import _spec

    other_path = tmp_path / "other-root"
    other_path.mkdir()
    admission = operation_store._admission
    with RootContext.open(other_path) as other_root:
        enroll_fresh(other_root)
        with RootOwnerLease.acquire(other_root) as other_owner:
                other_admission = AdmissionCoordinator(other_root, owner_lease=other_owner)
                other_store = OperationStore(other_root, admission=other_admission)
                capture = freeze_capture(
                    root=other_root,
                    subject_id="alpha",
                    mandate_digest="a" * 64,
                    universe=("AAPL",),
                    broker="paper",
                    settings=resolve_settings(other_root),
                    credential_versions={},
                    code_version="synthetic-code-stamp",
                )
                operation = _accept(other_store, _preview(other_store, capture))
                fence = other_store.claim_worker(operation.operation_id, worker_id="synthetic", now=_NOW)
                other_store.mark_running(operation.operation_id, fence, now=_NOW)
                monkeypatch.setattr(operations, "_MAX_LOCK_WAIT_SECONDS", 0.1)

                class OtherRootSnapshot:
                    def get_snapshot(self, _ticker):
                        return other_store.cancellation_requested(operation.operation_id, fence)

                with paths.bound_root(root_context):
                    with admission.deployment_lock("alpha"):
                        directory = deploy("alpha", _spec("alpha"), ["AAPL"], root=root_context.path / "paper")
                    clock = LiveClock(OtherRootSnapshot(), 60, _spec("alpha").window)
                    with admission.manual_session("alpha"):
                        with paper_effect_registry(directory, "alpha"):
                            with other_admission.registry_lock():
                                with pytest.raises(operations.OperationBusy):
                                    clock.observe(["AAPL"], "2024-06-04T11:00:00")


def test_cancel_request_identity_cannot_alias_an_admission_or_other_operation(operation_store, frozen_capture):
    first = _accept(operation_store, _preview(operation_store, frozen_capture), request_id="request-first")
    second_preview = _preview(
        operation_store,
        frozen_capture,
        payload={"mode": "manual", "limit": 2},
    )
    second = _accept(operation_store, second_preview, request_id="request-second")

    with pytest.raises(OperationConflict):
        operation_store.request_cancel(
            first.operation_id,
            request_id="request-first",
            now=_NOW + timedelta(seconds=1),
        )
    operation_store.request_cancel(
        first.operation_id,
        request_id="cancel-shared",
        now=_NOW + timedelta(seconds=1),
    )
    with pytest.raises(OperationConflict):
        operation_store.request_cancel(
            second.operation_id,
            request_id="cancel-shared",
            now=_NOW + timedelta(seconds=1),
        )
    assert operation_store.get_operation(second.operation_id).status is OperationStatus.ACCEPTED


def test_corrupt_cancel_sidecar_fails_idempotent_replay(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    operation_store.request_cancel(
        operation.operation_id,
        request_id="cancel-1",
        now=_NOW + timedelta(seconds=1),
    )
    relative = f"{OPERATIONS_ROOT}/cancellations/{hashlib.sha256(b'cancel-1').hexdigest()}.json"
    root_context.write_bytes(relative, b"{}")

    with pytest.raises(OperationError):
        operation_store.request_cancel(
            operation.operation_id,
            request_id="cancel-1",
            now=_NOW + timedelta(seconds=2),
        )


def test_completed_result_is_durable_and_worker_effects_are_fenced(operation_store, frozen_capture, root_context):
    preview = _preview(operation_store, frozen_capture)
    operation = _accept(operation_store, preview)
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)

    completed = operation_store.complete(
        operation.operation_id,
        fence,
        result={"sessions": 1, "summary": "synthetic"},
        now=_NOW + timedelta(seconds=1),
    )

    assert completed.status is OperationStatus.COMPLETED
    assert completed.progress == 100
    assert completed.public_view()["result"] == {"sessions": 1, "summary": "synthetic"}
    assert root_context.read_bytes(f"{OPERATIONS_ROOT}/results/{operation.operation_id}.json")
    with pytest.raises(WorkerFenced):
        operation_store.apply_if_current(
            operation.operation_id,
            fence,
            lambda: pytest.fail("completed worker performed another effect"),
        )


def test_progress_is_durable_monotonic_and_bounded(operation_store, frozen_capture):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)

    progress = operation_store.update_progress(
        operation.operation_id,
        fence,
        progress=40,
        now=_NOW + timedelta(seconds=1),
    )
    assert progress.progress == 40
    with pytest.raises(OperationError):
        operation_store.update_progress(
            operation.operation_id,
            fence,
            progress=39,
            now=_NOW + timedelta(seconds=2),
        )
    with pytest.raises(OperationError):
        operation_store.update_progress(
            operation.operation_id,
            fence,
            progress=100,
            now=_NOW + timedelta(seconds=2),
        )
    assert operation_store.get_operation(operation.operation_id).progress == 40


def test_status_read_waits_for_atomic_sidecar_snapshot(operation_store, frozen_capture, monkeypatch):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)
    sidecars_written = Event()
    read_lock_attempted = Event()
    allow_index_commit = Event()
    write_index = operation_store._write_index

    def pause_before_index(index):
        if index["operations"][operation.operation_id]["progress"] == 40:
            sidecars_written.set()
            assert allow_index_commit.wait(timeout=5)
        write_index(index)

    monkeypatch.setattr(operation_store, "_write_index", pause_before_index)

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(
            operation_store.update_progress,
            operation.operation_id,
            fence,
            progress=40,
            now=_NOW + timedelta(seconds=1),
        )
        assert sidecars_written.wait(timeout=5)

        registry_lock = operation_store._admission.registry_read_lock

        def observe_read_lock(*, timeout=0.0):
            read_lock_attempted.set()
            return registry_lock(timeout=timeout)

        monkeypatch.setattr(
            operation_store._admission,
            "registry_read_lock",
            observe_read_lock,
        )
        reader = pool.submit(operation_store.get_operation, operation.operation_id)
        assert read_lock_attempted.wait(timeout=5)
        allow_index_commit.set()
        observed = reader.result(timeout=5)
        writer.result(timeout=5)

    assert observed.progress == 40


@pytest.mark.parametrize("lookup", ["get_by_request", "list_operations"])
def test_operation_indexes_wait_for_committed_snapshot(
    operation_store,
    frozen_capture,
    lookup,
    monkeypatch,
):
    preview = _preview(operation_store, frozen_capture)
    sidecars_written = Event()
    read_lock_attempted = Event()
    allow_index_commit = Event()
    write_index = operation_store._write_index
    registry_read_lock = operation_store._admission.registry_read_lock

    def pause_before_index(index):
        if index["operations"]:
            sidecars_written.set()
            assert allow_index_commit.wait(timeout=5)
        write_index(index)

    def observe_read_lock(*, timeout=0.0):
        if current_thread().name.startswith("operation-reader"):
            read_lock_attempted.set()
        return registry_read_lock(timeout=timeout)

    monkeypatch.setattr(operation_store, "_write_index", pause_before_index)
    monkeypatch.setattr(
        operation_store._admission,
        "registry_read_lock",
        observe_read_lock,
    )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="operation-reader") as pool:
        writer = pool.submit(_accept, operation_store, preview)
        assert sidecars_written.wait(timeout=5)
        if lookup == "get_by_request":
            reader = pool.submit(operation_store.get_by_request, "request-1")
        else:
            reader = pool.submit(operation_store.list_operations)
        try:
            assert read_lock_attempted.wait(timeout=5)
            assert not reader.done()
        finally:
            allow_index_commit.set()
        accepted = writer.result(timeout=5)
        observed = reader.result(timeout=5)

    if lookup == "get_by_request":
        assert observed.operation_id == accepted.operation_id
    else:
        assert [operation.operation_id for operation in observed] == [accepted.operation_id]


def test_index_entry_limit_rejects_before_writing_sidecars(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
):
    import hedge_fund.runtime.operations as operations_module

    monkeypatch.setattr(operations_module, "_MAX_INDEX_ENTRIES", 1, raising=False)
    _preview(operation_store, frozen_capture)
    runtime = root_context.path / "runtime"
    before = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file() and path.suffix != ".lock"}

    with pytest.raises(OperationError):
        _preview(operation_store, frozen_capture)

    after = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file() and path.suffix != ".lock"}
    assert after == before


def test_torn_terminal_transition_recovers_without_resuming_worker(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)
    write_bytes = root_context.write_bytes

    def fail_terminal_index(relative, payload, *, mode=0o600):
        if relative == INDEX_PATH:
            index = json.loads(payload.decode("utf-8"))
            if index["operations"][operation.operation_id]["status"] == "completed":
                raise OSError(5, "synthetic index replacement fault")
        return write_bytes(relative, payload, mode=mode)

    monkeypatch.setattr(root_context, "write_bytes", fail_terminal_index)
    with pytest.raises(OperationError) as error:
        operation_store.complete(
            operation.operation_id,
            fence,
            result={"sessions": 1},
            now=_NOW + timedelta(seconds=1),
        )
    assert isinstance(error.value.__cause__, OSError)

    monkeypatch.setattr(root_context, "write_bytes", write_bytes)
    recovered = operation_store.recover_unfinished(now=_NOW + timedelta(seconds=2))

    assert len(recovered) == 1
    assert recovered[0].status is OperationStatus.INTERRUPTED
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.INTERRUPTED


def test_torn_completed_sidecar_is_repaired_without_replaying_effect(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
    caplog,
):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)
    original_write = root_context.write_bytes
    failure = OSError(5, "synthetic result-sidecar fault")
    failure_used = False
    effects = []
    report_path = operation_store.apply_if_current(
        operation.operation_id,
        fence,
        lambda: effects.append("report-written") or "synthetic.json",
    )
    assert report_path == "synthetic.json"

    def fail_result_sidecar(relative, payload, *, mode=0o600):
        nonlocal failure_used
        if relative == f"{OPERATIONS_ROOT}/results/{operation.operation_id}.json":
            if not failure_used:
                failure_used = True
                raise failure
        return original_write(relative, payload, mode=mode)

    monkeypatch.setattr(root_context, "write_bytes", fail_result_sidecar)
    caplog.set_level("WARNING", logger="hedge_fund.runtime.operations")
    completed = operation_store.complete(
        operation.operation_id,
        fence,
        result={"report_id": "synthetic.json"},
        now=_NOW + timedelta(seconds=1),
    )

    assert completed.status is OperationStatus.COMPLETED
    assert "write_type=OSError errno=5 winerror=None" in caplog.text
    assert "synthetic result-sidecar fault" not in caplog.text
    assert f"{OPERATIONS_ROOT}/results/" not in caplog.text
    assert operation_store._read_index()["operations"][operation.operation_id]["status"] == "completed"
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.COMPLETED

    recovered = operation_store.recover_unfinished(now=_NOW + timedelta(seconds=2))

    assert recovered == ()
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.COMPLETED
    assert effects == ["report-written"]
    with pytest.raises(WorkerFenced):
        operation_store.apply_if_current(
            operation.operation_id,
            fence,
            lambda: effects.append("duplicate-report"),
        )
    assert effects == ["report-written"]


def test_torn_preview_sidecar_is_repaired_from_committed_index(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
):
    original_write = root_context.write_bytes
    failure = OSError(5, "synthetic preview-sidecar fault")
    failure_used = False

    def fail_preview_sidecar(relative, payload, *, mode=0o600):
        nonlocal failure_used
        if relative.startswith(f"{OPERATIONS_ROOT}/previews/") and not failure_used:
            failure_used = True
            raise failure
        return original_write(relative, payload, mode=mode)

    monkeypatch.setattr(root_context, "write_bytes", fail_preview_sidecar)
    preview = _preview(operation_store, frozen_capture)

    stored = operation_store._read_index()["previews"][preview.preview_id]
    operation_store._verify_preview_sidecar(stored)
    assert stored["state"] == "issued"
    assert preview.confirmation_token


def test_torn_acceptance_sidecar_repairs_before_starting_worker(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
):
    preview = _preview(operation_store, frozen_capture)
    original_write = root_context.write_bytes
    failure = OSError(5, "synthetic acceptance-sidecar fault")
    failure_used = False
    started = []

    def fail_result_sidecar(relative, payload, *, mode=0o600):
        nonlocal failure_used
        if relative.startswith(f"{OPERATIONS_ROOT}/results/") and not failure_used:
            failure_used = True
            raise failure
        return original_write(relative, payload, mode=mode)

    monkeypatch.setattr(root_context, "write_bytes", fail_result_sidecar)
    operation = _accept(
        operation_store,
        preview,
        request_id="request-sidecar-fault",
        start_worker=lambda accepted: started.append(accepted.operation_id),
    )
    replay = _accept(
        operation_store,
        preview,
        request_id="request-sidecar-fault",
        start_worker=lambda accepted: started.append(accepted.operation_id),
    )

    assert operation.status is OperationStatus.ACCEPTED
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.ACCEPTED
    assert replay.operation_id == operation.operation_id
    assert started == [operation.operation_id]


def test_torn_cancellation_sidecar_repairs_idempotent_replay(
    operation_store,
    frozen_capture,
    root_context,
    monkeypatch,
):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    request_id = "cancel-sidecar-fault"
    cancellation_path = f"{OPERATIONS_ROOT}/cancellations/" f"{hashlib.sha256(request_id.encode('utf-8')).hexdigest()}.json"
    original_write = root_context.write_bytes
    failure = OSError(5, "synthetic cancellation-sidecar fault")
    failure_used = False

    def fail_cancellation_sidecar(relative, payload, *, mode=0o600):
        nonlocal failure_used
        if relative == cancellation_path and not failure_used:
            failure_used = True
            raise failure
        return original_write(relative, payload, mode=mode)

    monkeypatch.setattr(root_context, "write_bytes", fail_cancellation_sidecar)
    cancelled = operation_store.request_cancel(
        operation.operation_id,
        request_id=request_id,
        now=_NOW + timedelta(seconds=1),
    )
    replay = operation_store.request_cancel(
        operation.operation_id,
        request_id=request_id,
        now=_NOW + timedelta(seconds=2),
    )

    assert cancelled.status is OperationStatus.CANCEL_REQUESTED
    assert replay.status is OperationStatus.CANCEL_REQUESTED
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.CANCEL_REQUESTED


def test_accept_revalidates_current_head_and_due_set_under_subject_lease(
    operation_store,
    frozen_capture,
):
    preview = _preview(operation_store, frozen_capture)
    resolver_calls = []

    def resolve_current_state():
        resolver_calls.append("called")
        lease_held = True
        try:
            with operation_store._admission.execution_lease("alpha", timeout=0):
                lease_held = False
        except Exception:
            pass
        assert lease_held
        return "head-2", preview.due_set

    with pytest.raises(StalePreview):
        _accept(
            operation_store,
            preview,
            current_state_resolver=resolve_current_state,
        )

    assert resolver_calls == ["called"]


def test_failure_result_contains_only_a_validated_error_code(operation_store, frozen_capture):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    fence = operation_store.claim_worker(
        operation.operation_id,
        worker_id="synthetic-worker",
        now=_NOW,
    )
    operation_store.mark_running(operation.operation_id, fence, now=_NOW)

    failed = operation_store.fail(
        operation.operation_id,
        fence,
        error_code="provider-unavailable",
        now=_NOW + timedelta(seconds=1),
    )

    assert failed.status is OperationStatus.FAILED
    assert failed.public_view()["result"] == {"error_code": "provider-unavailable"}
    with pytest.raises(OperationError):
        operation_store.fail(
            operation.operation_id,
            fence,
            error_code="synthetic error contains token",
            now=_NOW + timedelta(seconds=2),
        )


@pytest.mark.parametrize("secret_field", ["api-key", "clientKey", "provider_key", "access_token"])
def test_preview_payload_rejects_secret_field_aliases(operation_store, frozen_capture, root_context, secret_field):
    with pytest.raises(OperationError):
        _preview(
            operation_store,
            frozen_capture,
            payload={"mode": "manual", secret_field: "synthetic-not-a-secret"},
        )

    assert not root_context.resolve(OPERATIONS_ROOT).exists()


def test_corrupt_operation_sidecar_fails_closed(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    state_path = f"{OPERATIONS_ROOT}/state/{operation.operation_id}.json"
    root_context.write_bytes(state_path, b'{"schema":1,"status":"completed"}')

    with pytest.raises(OperationError):
        operation_store.get_operation(operation.operation_id)


def test_corrupt_index_cross_reference_fails_closed(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    index = json.loads(root_context.read_bytes(INDEX_PATH))
    index["requests"]["request-1"]["operation_id"] = "0" * 32
    root_context.write_bytes(
        INDEX_PATH,
        json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )

    with pytest.raises(OperationError):
        operation_store.get_operation(operation.operation_id)


def test_restart_reconciles_torn_state_sidecar_without_resuming_worker(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    state_path = f"{OPERATIONS_ROOT}/state/{operation.operation_id}.json"
    root_context.write_bytes(state_path, b'{"schema":1,"status":"running"}')

    with pytest.raises(OperationError):
        operation_store.get_operation(operation.operation_id)
    recovered = operation_store.recover_unfinished(now=_NOW + timedelta(seconds=1))

    assert len(recovered) == 1
    assert recovered[0].operation_id == operation.operation_id
    assert recovered[0].status is OperationStatus.INTERRUPTED
    assert operation_store.get_operation(operation.operation_id).status is OperationStatus.INTERRUPTED


def test_corrupt_capture_sidecar_denies_confirmation(operation_store, frozen_capture, root_context):
    preview = _preview(operation_store, frozen_capture)
    root_context.write_bytes(f"{CAPTURE_ROOT}/{frozen_capture.capture_id}.json", b"{}")

    with pytest.raises(OperationError):
        _accept(operation_store, preview)
    assert operation_store.get_by_request("request-1") is None


def operation_store_for(root_context, admission):
    return OperationStore(root_context, admission=admission)


_CAPACITY = (frozenset({"paper-run"}), 1)


def _runtime_bytes(root_context):
    runtime = root_context.path / "runtime"
    return {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file() and path.suffix != ".lock"}


def test_full_capacity_denies_before_any_durable_change_and_keeps_preview_issued(operation_store, frozen_capture, root_context):
    first = _accept(operation_store, _preview(operation_store, frozen_capture), capacity=_CAPACITY)
    waiting = _preview(
        operation_store,
        frozen_capture,
        payload={"mode": "manual", "limit": 2},
    )
    before = _runtime_bytes(root_context)
    started = []

    with pytest.raises(OperationCapacityExceeded):
        _accept(operation_store, waiting, request_id="request-2", capacity=_CAPACITY, start_worker=started.append)

    assert started == []
    assert _runtime_bytes(root_context) == before
    assert operation_store.get_by_request("request-2") is None
    assert operation_store._read_index()["previews"][waiting.preview_id]["state"] == "issued"

    fence = operation_store.claim_worker(first.operation_id, worker_id="synthetic", now=_NOW)
    operation_store.mark_running(first.operation_id, fence, now=_NOW)
    operation_store.complete(first.operation_id, fence, result={"sessions": 1}, now=_NOW + timedelta(seconds=1))

    second = _accept(operation_store, waiting, request_id="request-2", capacity=_CAPACITY, start_worker=started.append)

    assert second.status is OperationStatus.ACCEPTED
    assert [item.operation_id for item in started] == [second.operation_id]


def test_capacity_counts_only_unfinished_operations_of_the_bounded_actions(operation_store, frozen_capture):
    _accept(operation_store, _preview(operation_store, frozen_capture), capacity=_CAPACITY)

    other_pool = _accept(
        operation_store,
        _preview(operation_store, frozen_capture, action="backtest"),
        request_id="request-2",
        capacity=(frozenset({"backtest"}), 1),
    )

    assert other_pool.status is OperationStatus.ACCEPTED


def test_replay_of_admitted_request_is_answered_even_when_no_capacity_is_offered(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    first = _accept(operation_store, preview, capacity=_CAPACITY)

    replay = _accept(operation_store, preview, capacity=(_CAPACITY[0], 0))

    assert replay.operation_id == first.operation_id
    with pytest.raises(OperationCapacityExceeded):
        _accept(
            operation_store,
            _preview(
                operation_store,
                frozen_capture,
                payload={"mode": "manual", "limit": 2},
            ),
            request_id="request-2",
            capacity=(_CAPACITY[0], 0),
        )


@pytest.mark.parametrize(
    "capacity",
    [(frozenset(), 1), (frozenset({"paper-run"}), -1), (frozenset({"paper-run"}), 17), ({"paper-run"}, 1), (frozenset({"paper-run"}), True), (frozenset({"paper-run"}),)],
)
def test_invalid_capacity_is_rejected_before_storage(operation_store, frozen_capture, root_context, capacity):
    preview = _preview(operation_store, frozen_capture)
    before = _runtime_bytes(root_context)

    with pytest.raises(OperationError, match="capacity is invalid"):
        _accept(operation_store, preview, capacity=capacity)

    assert _runtime_bytes(root_context) == before


_CHILD_ACCEPT = """
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.operations import OperationCapacityExceeded, OperationStore
from hedge_fund.runtime.root import RootContext

now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
with RootContext.open(Path(sys.argv[1])) as context, RootOwnerLease.acquire(context) as lease:
    store = OperationStore(context, admission=AdmissionCoordinator(context, owner_lease=lease))
    capture = freeze_capture(root=context, subject_id="alpha", mandate_digest="a" * 64, universe=("AAA",), broker="paper", settings=resolve_settings(context), credential_versions={}, code_version="synthetic-code-stamp")
    preview = store.create_preview(action="paper-run", subject_id="alpha", expected_head="head-1", due_set=(), capture=capture, operator_session="operator-2", payload={"mode": "manual"}, now=now, expires_at=now + timedelta(minutes=1))
    try:
        store.accept_request(request_id="child-request", action="paper-run", subject_id="alpha", preview_id=preview.preview_id, preview_digest=preview.digest, confirmation_token=preview.confirmation_token, operator_session="operator-2", expected_head="head-1", due_set=(), payload={"mode": "manual"}, now=now, capacity=(frozenset({"paper-run"}), 1))
    except OperationCapacityExceeded:
        print(json.dumps({"outcome": "capacity-denied", "preview_state": store._read_index()["previews"][preview.preview_id]["state"]}))
    else:
        print(json.dumps({"outcome": "accepted"}))
"""


def test_durable_capacity_bounds_a_second_process_sharing_the_root(operation_store, frozen_capture, root_context, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    _accept(operation_store, _preview(operation_store, frozen_capture), capacity=_CAPACITY)
    env = {key: value for key, value in os.environ.items() if not any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY", "AIHF_"))}
    env.update({"PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[2])})

    child = subprocess.run(
        [sys.executable, "-c", _CHILD_ACCEPT, str(root_context.path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=tmp_path,
        check=False,
    )

    assert child.returncode == 0, child.stderr[-2000:]
    assert json.loads(child.stdout.strip().splitlines()[-1]) == {"outcome": "capacity-denied", "preview_state": "issued"}
    assert operation_store.get_by_request("child-request") is None
