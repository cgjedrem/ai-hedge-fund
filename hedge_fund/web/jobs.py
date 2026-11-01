"""Single-worker, bounded research job registry."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from hedge_fund.runtime.operations import OperationRecord, OperationStatus, OperationStore, WorkerFenced


class JobConflict(RuntimeError):
    """A bounded research slot is already occupied."""


class JobCancelled(Exception):
    """A research job reached a cooperative cancellation boundary."""


class OperationJobRegistry:
    """Run accepted operations with durable progress and safe-boundary cancellation."""

    MAX_TRACKED = 1000

    def __init__(
        self,
        store: OperationStore,
        *,
        clock: Callable[[], datetime] | None = None,
        max_active: int = 1,
    ) -> None:
        if not isinstance(store, OperationStore):
            raise JobConflict("A durable operation store is required.")
        if type(max_active) is not int or not 1 <= max_active <= 4:
            raise JobConflict("Worker capacity is invalid.")
        if clock is not None and not callable(clock):
            raise JobConflict("Job clock is invalid.")
        self._store = store
        self._clock = clock or _now_datetime
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_active, thread_name_prefix="aihf-operation")
        self._submitted: dict[str, Future | None] = {}
        self._active: set[str] = set()
        self._max_active = max_active
        self._closed = False
        self._shutdown_requested = threading.Event()

    def submit(
        self,
        operation: OperationRecord,
        work: Callable[
            [
                Callable[[int], None],
                Callable[[], bool],
                Callable[[Callable[[], object]], object],
            ],
            Mapping[str, object],
        ],
    ) -> OperationRecord:
        if not isinstance(operation, OperationRecord) or not callable(work):
            raise JobConflict("Accepted operation and worker are required.")
        with self._lock:
            if self._closed:
                raise JobConflict("The operation worker is shutting down.")
            current = self._store.get_operation(operation.operation_id)
            if current.request_id != operation.request_id or current.request_digest != operation.request_digest:
                raise JobConflict("Operation identity changed.")
            if current.status is not OperationStatus.ACCEPTED or current.operation_id in self._submitted:
                return current
            if len(self._active) >= self._max_active:
                raise JobConflict("Operation worker capacity is full.")
            self._prune()
            if len(self._submitted) >= self.MAX_TRACKED:
                raise JobConflict("Operation history capacity is full.")
            self._submitted[current.operation_id] = None
            self._active.add(current.operation_id)
            try:
                future = self._executor.submit(self._run, current.operation_id, work)
            except Exception:
                self._active.discard(current.operation_id)
                try:
                    self._store.interrupt(current.operation_id, now=self._now())
                except Exception:
                    pass
                raise JobConflict("Operation start is uncertain.") from None
            self._submitted[current.operation_id] = future
            future.add_done_callback(
                lambda completed, operation_id=current.operation_id: self._future_done(
                    operation_id,
                    completed,
                )
            )
            return current

    def cancel(
        self,
        operation_id: str,
        *,
        request_id: str,
        now: datetime | None = None,
    ) -> OperationRecord:
        with self._lock:
            if self._closed:
                raise JobConflict("The operation worker is shutting down.")
            operation = self._store.request_cancel(
                operation_id,
                request_id=request_id,
                now=self._now() if now is None else now,
            )
            if operation.status is not OperationStatus.CANCEL_REQUESTED:
                return operation
            future = self._submitted.get(operation_id)
            if future is None:
                try:
                    return self._store.acknowledge_cancel(operation_id, None, now=self._now())
                except WorkerFenced:
                    return self._store.get_operation(operation_id)
            if future.cancel():
                return self._store.get_operation(operation_id)
            return self._store.get_operation(operation_id)

    def get(self, operation_id: str) -> OperationRecord:
        return self._store.get_operation(operation_id)

    def list(self, *, limit: int = 100) -> tuple[OperationRecord, ...]:
        return self._store.list_operations(limit=limit)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._shutdown_requested.set()
            operation_ids = tuple(self._submitted)
            futures = tuple(future for future in self._submitted.values() if future is not None)
        for operation_id in operation_ids:
            try:
                operation = self._store.get_operation(operation_id)
                if operation.status in {
                    OperationStatus.ACCEPTED,
                    OperationStatus.RUNNING,
                }:
                    self._store.request_cancel(
                        operation_id,
                        request_id=f"shutdown-{uuid.uuid4().hex}",
                        now=self._now(),
                    )
            except Exception:
                pass
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
        for operation_id in operation_ids:
            try:
                operation = self._store.get_operation(operation_id)
                if operation.status in {
                    OperationStatus.ACCEPTED,
                    OperationStatus.RUNNING,
                    OperationStatus.CANCEL_REQUESTED,
                }:
                    self._store.interrupt(operation_id, now=self._now())
            except Exception:
                pass

    def recover_unfinished(self) -> tuple[OperationRecord, ...]:
        with self._lock:
            if self._active:
                raise JobConflict("Operation recovery requires an idle worker.")
        return self._store.recover_unfinished(now=self._now())

    def _run(
        self,
        operation_id: str,
        work: Callable[
            [
                Callable[[int], None],
                Callable[[], bool],
                Callable[[Callable[[], object]], object],
            ],
            Mapping[str, object],
        ],
    ) -> None:
        fence = None
        try:
            fence = self._store.claim_worker(
                operation_id,
                worker_id=uuid.uuid4().hex,
                now=self._now(),
            )
            self._store.mark_running(operation_id, fence, now=self._now())
        except WorkerFenced:
            self._acknowledge_cancellation(operation_id, fence)
            self._finish_local(operation_id)
            return
        except Exception:
            try:
                self._store.interrupt(operation_id, now=self._now())
            except Exception:
                pass
            self._finish_local(operation_id)
            return

        def report_progress(value: int) -> None:
            if type(value) is not int:
                raise ValueError("progress is invalid")
            bounded = min(99, max(0, value))
            self._store.update_progress(
                operation_id,
                fence,
                progress=bounded,
                now=self._now(),
            )

        def cancellation_requested() -> bool:
            if self._shutdown_requested.is_set():
                return True
            try:
                return self._store.cancellation_requested(operation_id, fence)
            except WorkerFenced:
                return True

        def apply_if_current(effect: Callable[[], object]) -> object:
            return self._store.apply_if_current(operation_id, fence, effect)

        try:
            result = work(report_progress, cancellation_requested, apply_if_current)
            self._store.complete(operation_id, fence, result=result, now=self._now())
        except JobCancelled:
            self._acknowledge_cancellation(operation_id, fence)
        except WorkerFenced:
            self._acknowledge_cancellation(operation_id, fence)
        except Exception:
            try:
                self._store.fail(
                    operation_id,
                    fence,
                    error_code="worker-failed",
                    now=self._now(),
                )
            except WorkerFenced:
                pass
            except Exception:
                pass
        finally:
            self._finish_local(operation_id)

    def _acknowledge_cancellation(
        self,
        operation_id: str,
        fence,
    ) -> None:
        try:
            operation = self._store.get_operation(operation_id)
            if operation.status is OperationStatus.CANCEL_REQUESTED:
                self._store.acknowledge_cancel(operation_id, fence, now=self._now())
        except WorkerFenced:
            pass
        except Exception:
            pass

    def _finish_local(self, operation_id: str) -> None:
        with self._lock:
            self._active.discard(operation_id)

    def _future_done(self, operation_id: str, future: Future) -> None:
        try:
            if future.cancelled():
                operation = self._store.get_operation(operation_id)
                if operation.status is OperationStatus.CANCEL_REQUESTED:
                    self._store.acknowledge_cancel(
                        operation_id,
                        None,
                        now=self._now(),
                    )
        except Exception:
            pass
        finally:
            self._finish_local(operation_id)

    def _prune(self) -> None:
        for operation_id in tuple(self._submitted):
            if operation_id in self._active:
                continue
            try:
                operation = self._store.get_operation(operation_id)
            except Exception:
                continue
            if operation.status not in {
                OperationStatus.ACCEPTED,
                OperationStatus.RUNNING,
                OperationStatus.CANCEL_REQUESTED,
            }:
                self._submitted.pop(operation_id, None)
                if len(self._submitted) < self.MAX_TRACKED:
                    return

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise JobConflict("Job clock must return timezone-aware time.")
        return value


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)
