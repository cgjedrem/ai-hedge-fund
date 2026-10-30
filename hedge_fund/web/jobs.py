"""Single-worker, bounded research job registry."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable


class JobConflict(RuntimeError):
    """A bounded research slot is already occupied."""


class JobRegistry:
    MAX_JOBS = 20

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aihf-web")
        self._jobs: dict[str, dict] = {}

    def submit(self, fund: str, provider: str, model: str, work: Callable[[Callable[[int], None]], dict]) -> dict:
        with self._lock:
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
            }
            self._jobs[job_id] = job
            self._executor.submit(self._run, job_id, work)
            return dict(job)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(job) for job in sorted(self._jobs.values(), key=lambda item: item["submitted_at"], reverse=True)]

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str, work: Callable[[Callable[[int], None]], dict]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "running"
            job["started_at"] = _now()

        def update(progress: int) -> None:
            with self._lock:
                current = self._jobs.get(job_id)
                if current is not None and current["status"] == "running":
                    current["progress"] = max(current["progress"], min(99, max(0, int(progress))))

        try:
            result = work(update)
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

    def _prune(self) -> None:
        finished = [job for job in sorted(self._jobs.values(), key=lambda item: item["submitted_at"]) if job["status"] not in {"queued", "running"}]
        while len(self._jobs) >= self.MAX_JOBS and finished:
            self._jobs.pop(finished.pop(0)["id"], None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
