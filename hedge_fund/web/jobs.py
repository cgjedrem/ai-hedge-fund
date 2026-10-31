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


class JobRegistry:
    MAX_JOBS = 20

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aihf-web")
        self._jobs: dict[str, dict] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._futures = {}
        self._closed = False

    def submit(
        self,
        fund: str,
        provider: str,
        model: str,
        work: Callable[[Callable[[int], None], Callable[[], bool]], dict],
    ) -> dict:
        with self._lock:
            if self._closed:
                raise JobConflict("The research worker is shutting down.")
            if any(job["status"] in {"queued", "running"} for job in self._jobs.values()):
                raise JobConflict("A research job is already running.")
            self._prune()
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "fund": fund,
                "provider": provider,
                "model": model,
                "status": "queued",
                "progress": 0,
                "submitted_at": _now(),
                "started_at": None,
                "completed_at": None,
                "report_id": None,
                "error": None,
                "cancel_requested": False,
            }
            cancel_event = threading.Event()
            self._jobs[job_id] = job
            self._cancel_events[job_id] = cancel_event
            self._futures[job_id] = self._executor.submit(self._run, job_id, work, cancel_event)
            return dict(job)

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] not in {"queued", "running"}:
                raise JobConflict("Research job is not active.")
            event = self._cancel_events[job_id]
            event.set()
            job["cancel_requested"] = True
            future = self._futures.get(job_id)
            if job["status"] == "queued" and future is not None and future.cancel():
                self._mark_cancelled(job)
            return dict(job)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(job) for job in sorted(self._jobs.values(), key=lambda item: item["submitted_at"], reverse=True)]

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for job_id, job in self._jobs.items():
                if job["status"] not in {"queued", "running"}:
                    continue
                self._cancel_events[job_id].set()
                job["cancel_requested"] = True
                future = self._futures.get(job_id)
                if job["status"] == "queued" and future is not None and future.cancel():
                    self._mark_cancelled(job)
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(
        self,
        job_id: str,
        work: Callable[[Callable[[int], None], Callable[[], bool]], dict],
        cancel_event: threading.Event,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if cancel_event.is_set():
                self._mark_cancelled(job)
                return
            job["status"] = "running"
            job["started_at"] = _now()

        def update(progress: int) -> None:
            if cancel_event.is_set():
                raise JobCancelled()
            with self._lock:
                current = self._jobs.get(job_id)
                if current is not None and current["status"] == "running":
                    current["progress"] = max(current["progress"], min(99, max(0, int(progress))))

        try:
            result = work(update, cancel_event.is_set)
        except JobCancelled:
            with self._lock:
                job = self._jobs[job_id]
                self._mark_cancelled(job)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["error"] = f"Research failed ({type(exc).__name__})."
                job["completed_at"] = _now()
        else:
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "succeeded"
                job["progress"] = 100
                job["report_id"] = result.get("report_id") if isinstance(result, dict) else None
                job["completed_at"] = _now()

    @staticmethod
    def _mark_cancelled(job: dict) -> None:
        job["status"] = "cancelled"
        job["completed_at"] = _now()

    def _prune(self) -> None:
        finished = [job for job in sorted(self._jobs.values(), key=lambda item: item["submitted_at"]) if job["status"] not in {"queued", "running"}]
        while len(self._jobs) >= self.MAX_JOBS and finished:
            job_id = finished.pop(0)["id"]
            self._jobs.pop(job_id, None)
            self._cancel_events.pop(job_id, None)
            self._futures.pop(job_id, None)


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
        self._store.recover_unfinished(now=self._now())

    def submit(
        self,
        operation: OperationRecord,
        work: Callable[[Callable[[int], None], Callable[[], bool]], Mapping[str, object]],
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
                try:
                    return self._store.acknowledge_cancel(operation_id, None, now=self._now())
                except WorkerFenced:
                    pass
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
            futures = tuple(future for future in self._submitted.values() if future is not None)
        try:
            self._store.recover_unfinished(now=self._now())
        finally:
            for future in futures:
                future.cancel()
            self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(
        self,
        operation_id: str,
        work: Callable[[Callable[[int], None], Callable[[], bool]], Mapping[str, object]],
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
            if fence is not None:
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

        try:
            result = work(report_progress, cancellation_requested)
            if cancellation_requested():
                self._acknowledge_cancellation(operation_id, fence)
            else:
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_datetime() -> datetime:
    return datetime.now(timezone.utc)
