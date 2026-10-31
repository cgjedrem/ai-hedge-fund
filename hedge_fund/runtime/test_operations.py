import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, OwnershipState
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.operations import ConfirmationExpired, ConfirmationRejected, OperationConflict, OperationError, OperationStartUncertain, OperationStatus, OperationStore, StalePreview, WorkerFenced
from hedge_fund.runtime.root import RootContext

_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def root_context(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        yield context


@pytest.fixture
def operation_store(root_context):
    admission = AdmissionCoordinator(root_context, ownership=OwnershipState.VERIFIED)
    return OperationStore(
        root_context,
        admission=admission,
        private_storage_verified=True,
    )


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
    payload=None,
    due_set=("2026-10-31", "2026-11-01"),
    expires_at=None,
):
    return store.create_preview(
        action="paper-run",
        subject_id="alpha",
        expected_head="head-1",
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
    )


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
    before = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file()}

    observed = operation_store.get_operation(operation.operation_id)

    after = {path.relative_to(root_context.path).as_posix(): path.read_bytes() for path in runtime.rglob("*") if path.is_file()}
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
        admission=AdmissionCoordinator(root_context, ownership=OwnershipState.UNKNOWN),
        private_storage_verified=True,
    )

    observed = observer.get_operation(operation.operation_id)

    assert observed.operation_id == operation.operation_id
    assert observed.status is OperationStatus.ACCEPTED


def test_preview_token_is_not_persisted_and_private_storage_defaults_denied(root_context, frozen_capture):
    admission = AdmissionCoordinator(root_context, ownership=OwnershipState.VERIFIED)
    denied_store = OperationStore(root_context, admission=admission)

    with pytest.raises(OperationError):
        _preview(denied_store, frozen_capture)
    assert not root_context.resolve("runtime/operations").exists()

    preview = _preview(operation_store_for(root_context, admission), frozen_capture)
    index = root_context.read_bytes("runtime/operations/index.json")
    preview_record = root_context.read_bytes(f"runtime/operations/previews/{preview.preview_id}.json")

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


def test_accept_persists_before_worker_start_and_does_not_replay_uncertain_start(operation_store, frozen_capture):
    preview = _preview(operation_store, frozen_capture)
    starts = []

    def uncertain_start(operation):
        stored = operation_store.get_operation(operation.operation_id)
        assert stored.status is OperationStatus.ACCEPTED
        starts.append(operation.operation_id)
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


def test_cancel_request_identity_cannot_alias_an_admission_or_other_operation(operation_store, frozen_capture):
    first = _accept(operation_store, _preview(operation_store, frozen_capture), request_id="request-first")
    second_preview = _preview(operation_store, frozen_capture)
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
    relative = f"runtime/operations/cancellations/{hashlib.sha256(b'cancel-1').hexdigest()}.json"
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
    assert root_context.read_bytes(f"runtime/operations/results/{operation.operation_id}.json")
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

    assert not root_context.resolve("runtime/operations").exists()


def test_corrupt_operation_sidecar_fails_closed(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    state_path = f"runtime/operations/state/{operation.operation_id}.json"
    root_context.write_bytes(state_path, b'{"schema":1,"status":"completed"}')

    with pytest.raises(OperationError):
        operation_store.get_operation(operation.operation_id)


def test_corrupt_index_cross_reference_fails_closed(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    index = json.loads(root_context.read_bytes("runtime/operations/index.json"))
    index["requests"]["request-1"]["operation_id"] = "0" * 32
    root_context.write_bytes(
        "runtime/operations/index.json",
        json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )

    with pytest.raises(OperationError):
        operation_store.get_operation(operation.operation_id)


def test_restart_reconciles_torn_state_sidecar_without_resuming_worker(operation_store, frozen_capture, root_context):
    operation = _accept(operation_store, _preview(operation_store, frozen_capture))
    state_path = f"runtime/operations/state/{operation.operation_id}.json"
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
    root_context.write_bytes(f"runtime/captures/{frozen_capture.capture_id}.json", b"{}")

    with pytest.raises(OperationError):
        _accept(operation_store, preview)
    assert operation_store.get_by_request("request-1") is None


def operation_store_for(root_context, admission):
    return OperationStore(
        root_context,
        admission=admission,
        private_storage_verified=True,
    )
