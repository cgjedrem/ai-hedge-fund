"""Root-private confirmation and durable operation state."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import stat
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from secrets import token_urlsafe
from types import MappingProxyType
from typing import Any, Iterator
from uuid import uuid4

from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError
from hedge_fund.runtime.capture import _root_id, FrozenCapture
from hedge_fund.runtime.root import ensure_unique_resource_name, RootContext, RootPathError

INDEX_PATH = "runtime/operations/index.json"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HEX_ID = re.compile(r"[a-f0-9]{32}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_ACTION = re.compile(r"[a-z][a-z0-9._-]{0,63}")
_MAX_INDEX_BYTES = 16 * 1024 * 1024
_MAX_PAYLOAD_BYTES = 65536
_MAX_PAYLOAD_NODES = 1024
_MAX_CAPTURE_BYTES = 1024 * 1024
_MAX_LOCK_WAIT_SECONDS = 5.0
_DENIED_FIELDS = ("apikey", "capability", "credential", "environment", "networkauthorized", "password", "pid", "process", "root", "secret", "token", "argv")
_KEY_FIELDS = {"accesskey", "clientkey", "encryptionkey", "key", "keymaterial", "keyref", "keyvalue", "privatekey", "providerkey", "secretkey", "signingkey"}


class OperationError(RuntimeError):
    """Operation input, storage or authorization failed."""


class ConfirmationExpired(OperationError):
    """Confirmation is no longer valid."""


class ConfirmationRejected(OperationError):
    """Confirmation does not match an issued preview."""


class OperationConflict(OperationError):
    """Request identity conflicts with durable state."""


class OperationStartUncertain(OperationError):
    """Worker start may have occurred; request cannot be replayed."""


class StalePreview(OperationError):
    """Reviewed head, due-set or payload changed."""


class WorkerFenced(OperationError):
    """Worker token no longer owns operation state."""


class OperationStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCEL_REQUESTED = "cancel-requested"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ConfirmationPreview:
    preview_id: str
    digest: str
    action: str
    subject_id: str
    expected_head: str | None
    due_set: tuple[str, ...]
    capture_id: str
    capture_digest: str
    operator_session_hash: str = field(repr=False)
    expires_at: datetime
    payload: Mapping[str, Any] = field(repr=False)
    confirmation_token: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.preview_id, str) or not _HEX_ID.fullmatch(self.preview_id):
            raise OperationError("preview identity is invalid")
        if not isinstance(self.digest, str) or not _SHA256.fullmatch(self.digest):
            raise OperationError("preview digest is invalid")
        if not isinstance(self.capture_id, str) or not _HEX_ID.fullmatch(self.capture_id):
            raise OperationError("capture identity is invalid")
        if not isinstance(self.capture_digest, str) or not _SHA256.fullmatch(self.capture_digest):
            raise OperationError("capture digest is invalid")
        if not isinstance(self.operator_session_hash, str) or not _SHA256.fullmatch(self.operator_session_hash):
            raise OperationError("operator session is invalid")
        if not isinstance(self.confirmation_token, str) or len(self.confirmation_token) < 32:
            raise OperationError("confirmation is invalid")
        if not isinstance(self.due_set, tuple) or len(self.due_set) > 10000 or any(not _safe_text(value, maximum=256) for value in self.due_set) or len(set(self.due_set)) != len(self.due_set):
            raise OperationError("preview due-set is invalid")
        if not isinstance(self.action, str) or not _ACTION.fullmatch(self.action):
            raise OperationError("preview action is invalid")
        if not isinstance(self.subject_id, str):
            raise OperationError("preview subject is invalid")
        try:
            subject_id = ensure_unique_resource_name(self.subject_id, [])
        except RootPathError:
            raise OperationError("preview subject is invalid") from None
        if self.expected_head is not None and not _safe_text(self.expected_head, maximum=512):
            raise OperationError("preview head is invalid")
        _validate_datetime(self.expires_at)
        payload = _normalize_payload(self.payload)
        record = _preview_digest_fields(
            action=self.action,
            subject_id=subject_id,
            expected_head=self.expected_head,
            due_set=self.due_set,
            capture_id=self.capture_id,
            capture_digest=self.capture_digest,
            operator_session_hash=self.operator_session_hash,
            expires_at=self.expires_at,
            payload=payload,
        )
        if _sha256(_canonical_json(record)) != self.digest:
            raise OperationError("preview digest does not match contents")
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "expires_at", self.expires_at.astimezone(timezone.utc))
        object.__setattr__(self, "payload", _freeze_json(payload))

    def public_view(self) -> dict[str, object]:
        return {
            "preview_id": self.preview_id,
            "preview_digest": self.digest,
            "action": self.action,
            "subject_id": self.subject_id,
            "expected_head": self.expected_head,
            "due_set": list(self.due_set),
            "capture_id": self.capture_id,
            "capture_digest": self.capture_digest,
            "expires_at": _datetime_text(self.expires_at),
            "payload": _thaw_json(self.payload),
        }


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    request_id: str
    request_digest: str
    preview_id: str
    action: str
    subject_id: str
    capture_id: str
    capture_digest: str
    status: OperationStatus
    payload: Mapping[str, Any] = field(repr=False)
    result: Mapping[str, Any] | None = field(default=None, repr=False)
    progress: int = 0
    fence_generation: int = 0

    def __post_init__(self) -> None:
        _validate_operation_id(self.operation_id)
        _validate_request_id(self.request_id)
        _validate_operation_id(self.preview_id)
        _validate_action(self.action)
        subject_id = _validate_subject(self.subject_id)
        _validate_operation_id(self.capture_id)
        if not isinstance(self.request_digest, str) or not _SHA256.fullmatch(self.request_digest):
            raise OperationError("operation request digest is invalid")
        if not isinstance(self.capture_digest, str) or not _SHA256.fullmatch(self.capture_digest):
            raise OperationError("operation capture digest is invalid")
        if not isinstance(self.status, OperationStatus):
            raise OperationError("operation status is invalid")
        if type(self.progress) is not int or not 0 <= self.progress <= 100:
            raise OperationError("operation progress is invalid")
        if (self.status is OperationStatus.COMPLETED) != (self.progress == 100):
            raise OperationError("operation progress does not match state")
        if type(self.fence_generation) is not int or self.fence_generation < 0:
            raise OperationError("operation fence generation is invalid")
        payload = _normalize_payload(self.payload)
        result = None if self.result is None else _normalize_payload(self.result)
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "payload", _freeze_json(payload))
        object.__setattr__(self, "result", None if result is None else _freeze_json(result))

    def public_view(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "request_id": self.request_id,
            "action": self.action,
            "subject_id": self.subject_id,
            "capture_id": self.capture_id,
            "capture_digest": self.capture_digest,
            "status": self.status.value,
            "payload": _thaw_json(self.payload),
            "result": None if self.result is None else _thaw_json(self.result),
            "progress": self.progress,
        }


@dataclass(frozen=True, slots=True)
class WorkerFence:
    operation_id: str
    generation: int
    nonce: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_operation_id(self.operation_id)
        if type(self.generation) is not int or self.generation < 1:
            raise OperationError("worker fence generation is invalid")
        if not isinstance(self.nonce, str) or len(self.nonce) < 32 or not _safe_text(self.nonce, maximum=512):
            raise OperationError("worker fence is invalid")


class OperationStore:
    """Persist confirmation and operation identities under one root lock."""

    def __init__(
        self,
        root: RootContext,
        *,
        admission: AdmissionCoordinator,
        private_storage_verified: bool = False,
    ) -> None:
        if not isinstance(root, RootContext) or not isinstance(admission, AdmissionCoordinator):
            raise OperationError("root and admission contexts are required")
        if admission._root is not root:
            raise OperationError("admission root does not match")
        if type(private_storage_verified) is not bool:
            raise OperationError("private storage status is invalid")
        root.revalidate()
        self._root = root
        self._admission = admission
        self._private_storage_verified = private_storage_verified

    def create_preview(
        self,
        *,
        action: str,
        subject_id: str,
        expected_head: str | None,
        due_set: tuple[str, ...],
        capture: FrozenCapture,
        operator_session: str,
        payload: Mapping[str, object],
        now: datetime,
        expires_at: datetime,
    ) -> ConfirmationPreview:
        self._require_private_storage()
        normalized_action = _validate_action(action)
        normalized_subject = _validate_subject(subject_id)
        normalized_due_set = _validate_due_set(due_set)
        _validate_datetime(now)
        _validate_datetime(expires_at)
        if expires_at <= now or (expires_at - now).total_seconds() > 3600:
            raise OperationError("preview expiry is invalid")
        if expected_head is not None and not _safe_text(expected_head, maximum=512):
            raise OperationError("preview head is invalid")
        if not isinstance(capture, FrozenCapture) or capture.root_id != _root_id(self._root) or capture.subject_id != normalized_subject:
            raise OperationError("capture identity does not match")
        operator_hash = _sha256(_validate_session(operator_session).encode("utf-8"))
        normalized_payload = _normalize_payload(payload)
        capture_payload = capture.private_bytes()
        if len(capture_payload) > _MAX_CAPTURE_BYTES:
            raise OperationError("capture sidecar exceeds its bound")
        capture_path = f"runtime/captures/{capture.capture_id}.json"

        preview_id = uuid4().hex
        token = token_urlsafe(32)
        expires_utc = expires_at.astimezone(timezone.utc)
        digest_record = _preview_digest_fields(
            action=normalized_action,
            subject_id=normalized_subject,
            expected_head=expected_head,
            due_set=normalized_due_set,
            capture_id=capture.capture_id,
            capture_digest=capture.digest,
            operator_session_hash=operator_hash,
            expires_at=expires_utc,
            payload=normalized_payload,
        )
        digest = _sha256(_canonical_json(digest_record))
        preview = ConfirmationPreview(
            preview_id=preview_id,
            digest=digest,
            action=normalized_action,
            subject_id=normalized_subject,
            expected_head=expected_head,
            due_set=normalized_due_set,
            capture_id=capture.capture_id,
            capture_digest=capture.digest,
            operator_session_hash=operator_hash,
            expires_at=expires_utc,
            payload=normalized_payload,
            confirmation_token=token,
        )
        preview_record = {
            **digest_record,
            "schema": 1,
            "preview_id": preview_id,
            "digest": digest,
            "capture_record_hash": _sha256(capture_payload),
            "payload_digest": _sha256(_canonical_json(normalized_payload)),
            "confirmation_token_hash": _sha256(token.encode("utf-8")),
            "state": "issued",
            "consumed_request_id": None,
        }
        with self._locked(normalized_subject):
            index = self._read_index()
            if preview_id in index["previews"]:
                raise OperationConflict("preview identity already exists")
            self._write_capture_if_missing(capture_path, capture_payload)
            self._write_json(f"runtime/operations/previews/{preview_id}.json", preview_record)
            index["previews"][preview_id] = preview_record
            self._write_index(index)
        return preview

    def accept_request(
        self,
        *,
        request_id: str,
        action: str,
        subject_id: str,
        preview_id: str,
        preview_digest: str,
        confirmation_token: str,
        operator_session: str,
        expected_head: str | None,
        due_set: tuple[str, ...],
        payload: Mapping[str, object],
        now: datetime,
        start_worker: Callable[[OperationRecord], object] | None = None,
    ) -> OperationRecord:
        self._require_private_storage()
        request_id = _validate_request_id(request_id)
        action = _validate_action(action)
        subject_id = _validate_subject(subject_id)
        if not isinstance(preview_id, str) or not _HEX_ID.fullmatch(preview_id):
            raise ConfirmationRejected("preview identity is invalid")
        if not isinstance(preview_digest, str) or not _SHA256.fullmatch(preview_digest):
            raise ConfirmationRejected("preview digest is invalid")
        if not isinstance(confirmation_token, str) or len(confirmation_token) < 32:
            raise ConfirmationRejected("confirmation is invalid")
        if start_worker is not None and not callable(start_worker):
            raise OperationError("worker launcher is invalid")
        due_set = _validate_due_set(due_set)
        _validate_datetime(now)
        if expected_head is not None and not _safe_text(expected_head, maximum=512):
            raise OperationError("request head is invalid")
        normalized_payload = _normalize_payload(payload)
        payload_digest = _sha256(_canonical_json(normalized_payload))
        operator_hash = _sha256(_validate_session(operator_session).encode("utf-8"))
        token_hash = _sha256(confirmation_token.encode("utf-8"))
        request_digest = _sha256(
            _canonical_json(
                {
                    "action": action,
                    "subject_id": subject_id,
                    "preview_id": preview_id,
                    "preview_digest": preview_digest,
                    "expected_head": expected_head,
                    "due_set": list(due_set),
                    "payload_digest": payload_digest,
                    "operator_session_hash": operator_hash,
                    "confirmation_token_hash": token_hash,
                }
            )
        )
        operation: OperationRecord
        created = False
        with self._locked(subject_id):
            index = self._read_index()
            existing = index["requests"].get(request_id)
            if existing is not None:
                if existing.get("request_digest") != request_digest:
                    raise OperationConflict("request identity conflicts with durable state")
                stored = self._operation_entry(index, existing.get("operation_id"))
                self._verify_operation_sidecars(stored)
                self._verify_capture_sidecar(index["previews"][stored["preview_id"]])
                operation = self._operation_from_index(index, existing.get("operation_id"))
            else:
                if request_id in index["cancel_requests"]:
                    raise OperationConflict("request identity conflicts with durable state")
                preview = index["previews"].get(preview_id)
                if not isinstance(preview, dict) or preview.get("digest") != preview_digest:
                    raise ConfirmationRejected("preview does not match")
                self._verify_preview_sidecar(preview)
                self._verify_capture_sidecar(preview)
                if preview.get("state") != "issued":
                    raise ConfirmationRejected("confirmation was consumed")
                if not hmac.compare_digest(str(preview.get("confirmation_token_hash", "")), token_hash):
                    raise ConfirmationRejected("confirmation does not match")
                if preview.get("operator_session_hash") != operator_hash:
                    raise ConfirmationRejected("operator session does not match")
                expires_at = _parse_datetime(preview.get("expires_at"))
                if now.astimezone(timezone.utc) >= expires_at:
                    raise ConfirmationExpired("confirmation expired")
                if preview.get("action") != action or preview.get("subject_id") != subject_id or preview.get("expected_head") != expected_head or preview.get("due_set") != list(due_set):
                    raise StalePreview("reviewed head or due-set changed")
                if preview.get("payload_digest") != payload_digest:
                    raise StalePreview("reviewed payload changed")

                operation_id = uuid4().hex
                timestamp = _datetime_text(now)
                operation_record = {
                    "schema": 1,
                    "operation_id": operation_id,
                    "request_id": request_id,
                    "request_digest": request_digest,
                    "preview_id": preview_id,
                    "action": action,
                    "subject_id": subject_id,
                    "capture_id": preview["capture_id"],
                    "capture_digest": preview["capture_digest"],
                    "status": OperationStatus.ACCEPTED.value,
                    "payload": normalized_payload,
                    "progress": 0,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "fence_generation": 0,
                    "worker_id_hash": None,
                    "worker_fence_hash": None,
                    "events": [{"status": OperationStatus.ACCEPTED.value, "at": timestamp}],
                    "result": None,
                }
                request_record = {
                    "operation_id": operation_id,
                    "request_digest": request_digest,
                    "preview_id": preview_id,
                    "payload_digest": payload_digest,
                }
                preview["state"] = "consumed"
                preview["consumed_request_id"] = request_id
                index["requests"][request_id] = request_record
                index["operations"][operation_id] = operation_record
                self._write_operation_sidecars(operation_record)
                self._write_json(f"runtime/operations/previews/{preview_id}.json", preview)
                self._write_index(index)
                operation = self._operation_from_index(index, operation_id)
                created = True

        if created and start_worker is not None:
            try:
                start_worker(operation)
            except Exception:
                try:
                    self._set_interrupted(operation.operation_id, now=now)
                except Exception:
                    pass
                raise OperationStartUncertain("worker start is uncertain") from None
        return operation

    def get_operation(self, operation_id: str) -> OperationRecord:
        self._require_private_storage()
        if not isinstance(operation_id, str) or not _HEX_ID.fullmatch(operation_id):
            raise OperationError("operation identity is invalid")
        index, _ = self._read_verified_operation(operation_id)
        return self._operation_from_index(index, operation_id)

    def get_by_request(self, request_id: str) -> OperationRecord | None:
        self._require_private_storage()
        request_id = _validate_request_id(request_id)
        index = self._read_index()
        record = index["requests"].get(request_id)
        if record is None:
            return None
        operation_id = record.get("operation_id")
        index, _ = self._read_verified_operation(operation_id)
        return self._operation_from_index(index, operation_id)

    def list_operations(self, *, limit: int = 100) -> tuple[OperationRecord, ...]:
        self._require_private_storage()
        if type(limit) is not int or not 1 <= limit <= 100:
            raise OperationError("operation page size is invalid")
        index = self._read_index()
        ordered_ids = [
            operation["operation_id"]
            for operation in sorted(
                index["operations"].values(),
                key=lambda operation: (operation["created_at"], operation["operation_id"]),
                reverse=True,
            )[:limit]
        ]
        result = []
        for operation_id in ordered_ids:
            snapshot, _ = self._read_verified_operation(operation_id)
            result.append(self._operation_from_index(snapshot, operation_id))
        return tuple(result)

    def _read_verified_operation(
        self,
        operation_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            with self._admission.registry_read_lock(timeout=_MAX_LOCK_WAIT_SECONDS):
                index = self._read_index()
                operation = self._operation_entry(index, operation_id)
                self._verify_operation_sidecars(operation)
                self._verify_operation_capture(index, operation)
                return index, operation
        except AdmissionError:
            raise OperationError("operation admission lock is unavailable") from None

    def claim_worker(
        self,
        operation_id: str,
        *,
        worker_id: str,
        now: datetime,
    ) -> WorkerFence:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        worker_id = _validate_worker_id(worker_id)
        _validate_datetime(now)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            if operation["status"] != OperationStatus.ACCEPTED.value or operation["worker_fence_hash"] is not None:
                raise WorkerFenced("operation cannot be claimed")
            generation = operation["fence_generation"] + 1
            nonce = token_urlsafe(32)
            operation["fence_generation"] = generation
            operation["worker_id_hash"] = _sha256(worker_id.encode("utf-8"))
            operation["worker_fence_hash"] = _sha256(nonce.encode("utf-8"))
            operation["updated_at"] = _datetime_text(now)
            self._persist_transition(index, operation)
        return WorkerFence(operation_id=operation_id, generation=generation, nonce=nonce)

    def mark_running(
        self,
        operation_id: str,
        fence: WorkerFence,
        *,
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        _validate_datetime(now)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] != OperationStatus.ACCEPTED.value:
                raise WorkerFenced("operation cannot enter running state")
            self._append_event(operation, OperationStatus.RUNNING, now)
            operation["status"] = OperationStatus.RUNNING.value
            operation["updated_at"] = _datetime_text(now)
            self._persist_transition(index, operation)
            return self._operation_from_index(index, operation_id)

    def update_progress(
        self,
        operation_id: str,
        fence: WorkerFence,
        *,
        progress: int,
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        if type(progress) is not int or not 0 <= progress <= 99:
            raise OperationError("operation progress is invalid")
        _validate_datetime(now)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] != OperationStatus.RUNNING.value:
                raise WorkerFenced("operation is not running")
            if progress < operation["progress"]:
                raise OperationError("operation progress cannot move backwards")
            operation["progress"] = progress
            operation["updated_at"] = _datetime_text(now)
            self._persist_transition(index, operation)
            return self._operation_from_index(index, operation_id)

    def cancellation_requested(
        self,
        operation_id: str,
        fence: WorkerFence,
    ) -> bool:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] == OperationStatus.CANCEL_REQUESTED.value:
                return True
            if operation["status"] == OperationStatus.RUNNING.value:
                return False
            raise WorkerFenced("operation is no longer active")

    def request_cancel(
        self,
        operation_id: str,
        *,
        request_id: str,
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        request_id = _validate_request_id(request_id)
        _validate_datetime(now)
        request_digest = _sha256(_canonical_json({"operation_id": operation_id, "request_id": request_id}))
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            existing = index["cancel_requests"].get(request_id)
            if existing is not None:
                if existing["operation_id"] != operation_id or existing["request_digest"] != request_digest:
                    raise OperationConflict("cancellation identity conflicts with durable state")
                self._verify_cancel_sidecar(request_id, existing)
                return self._operation_from_index(index, operation_id)
            if request_id in index["requests"]:
                raise OperationConflict("request identity conflicts with durable state")

            cancellation = {
                "operation_id": operation_id,
                "request_digest": request_digest,
            }
            index["cancel_requests"][request_id] = cancellation
            if operation["status"] in {
                OperationStatus.ACCEPTED.value,
                OperationStatus.RUNNING.value,
            }:
                self._append_event(operation, OperationStatus.CANCEL_REQUESTED, now)
                operation["status"] = OperationStatus.CANCEL_REQUESTED.value
                operation["updated_at"] = _datetime_text(now)
                self._write_operation_sidecars(operation)
            self._write_cancel_sidecar(request_id, cancellation)
            self._write_index(index)
            return self._operation_from_index(index, operation_id)

    def acknowledge_cancel(
        self,
        operation_id: str,
        fence: WorkerFence | None,
        *,
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        _validate_datetime(now)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            if operation["status"] != OperationStatus.CANCEL_REQUESTED.value:
                raise WorkerFenced("operation has no pending cancellation")
            if operation["worker_fence_hash"] is None:
                if fence is not None:
                    raise WorkerFenced("worker fence is stale")
            else:
                if fence is None:
                    raise WorkerFenced("worker fence is stale")
                self._require_current_fence(operation, operation_id, fence)
            operation["fence_generation"] += 1
            operation["worker_id_hash"] = None
            operation["worker_fence_hash"] = None
            operation["status"] = OperationStatus.CANCELLED.value
            operation["updated_at"] = _datetime_text(now)
            self._append_event(operation, OperationStatus.CANCELLED, now)
            self._persist_transition(index, operation)
            return self._operation_from_index(index, operation_id)

    def complete(
        self,
        operation_id: str,
        fence: WorkerFence,
        *,
        result: Mapping[str, object],
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        _validate_datetime(now)
        normalized_result = _normalize_payload(result)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] != OperationStatus.RUNNING.value:
                raise WorkerFenced("operation cannot complete")
            operation["result"] = normalized_result
            operation["progress"] = 100
            operation["fence_generation"] += 1
            operation["worker_id_hash"] = None
            operation["worker_fence_hash"] = None
            operation["status"] = OperationStatus.COMPLETED.value
            operation["updated_at"] = _datetime_text(now)
            self._append_event(operation, OperationStatus.COMPLETED, now)
            self._persist_transition(index, operation)
            return self._operation_from_index(index, operation_id)

    def fail(
        self,
        operation_id: str,
        fence: WorkerFence,
        *,
        error_code: str,
        now: datetime,
    ) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        if not isinstance(error_code, str) or not _ACTION.fullmatch(error_code):
            raise OperationError("operation error code is invalid")
        _validate_datetime(now)
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] != OperationStatus.RUNNING.value:
                raise WorkerFenced("operation cannot fail")
            operation["result"] = {"error_code": error_code}
            operation["fence_generation"] += 1
            operation["worker_id_hash"] = None
            operation["worker_fence_hash"] = None
            operation["status"] = OperationStatus.FAILED.value
            operation["updated_at"] = _datetime_text(now)
            self._append_event(operation, OperationStatus.FAILED, now)
            self._persist_transition(index, operation)
            return self._operation_from_index(index, operation_id)

    def apply_if_current(
        self,
        operation_id: str,
        fence: WorkerFence,
        effect: Callable[[], object],
    ) -> object:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        if not callable(effect):
            raise OperationError("effect callback is invalid")
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            self._require_current_fence(operation, operation_id, fence)
            if operation["status"] != OperationStatus.RUNNING.value:
                raise WorkerFenced("worker is not running")
            return effect()

    def recover_unfinished(self, *, now: datetime) -> tuple[OperationRecord, ...]:
        self._require_private_storage()
        _validate_datetime(now)
        recovered: list[OperationRecord] = []
        with self._admission.registry_lock(timeout=_MAX_LOCK_WAIT_SECONDS):
            index = self._read_index()
            for preview_id, preview in index["previews"].items():
                self._verify_capture_sidecar(preview)
                self._write_json(f"runtime/operations/previews/{preview_id}.json", preview)
            for request_id, cancellation in index["cancel_requests"].items():
                self._write_cancel_sidecar(request_id, cancellation)
            for operation_id, operation in index["operations"].items():
                if operation["status"] not in {
                    OperationStatus.ACCEPTED.value,
                    OperationStatus.RUNNING.value,
                    OperationStatus.CANCEL_REQUESTED.value,
                }:
                    self._verify_operation_sidecars(operation)
                    continue
                operation["fence_generation"] += 1
                operation["worker_id_hash"] = None
                operation["worker_fence_hash"] = None
                operation["status"] = OperationStatus.INTERRUPTED.value
                operation["updated_at"] = _datetime_text(now)
                self._append_event(operation, OperationStatus.INTERRUPTED, now)
                self._write_operation_sidecars(operation)
                recovered.append(self._operation_from_index(index, operation_id))
            if recovered:
                self._write_index(index)
        return tuple(recovered)

    def interrupt(self, operation_id: str, *, now: datetime) -> OperationRecord:
        self._require_private_storage()
        _validate_operation_id(operation_id)
        _validate_datetime(now)
        self._set_interrupted(operation_id, now=now)
        return self.get_operation(operation_id)

    def _set_interrupted(self, operation_id: str, *, now: datetime) -> None:
        with self._locked_for_operation(operation_id):
            index = self._read_index()
            operation = self._operation_entry(index, operation_id)
            self._verify_operation_sidecars(operation)
            self._verify_operation_capture(index, operation)
            if operation["status"] in {
                OperationStatus.ACCEPTED.value,
                OperationStatus.RUNNING.value,
                OperationStatus.CANCEL_REQUESTED.value,
            }:
                operation["fence_generation"] += 1
                operation["worker_id_hash"] = None
                operation["worker_fence_hash"] = None
                operation["status"] = OperationStatus.INTERRUPTED.value
                operation["updated_at"] = _datetime_text(now)
                self._append_event(operation, OperationStatus.INTERRUPTED, now)
                self._persist_transition(index, operation)

    @contextmanager
    def _locked(self, subject_id: str) -> Iterator[None]:
        with self._admission.registry_lock(timeout=_MAX_LOCK_WAIT_SECONDS):
            with self._admission.manual_session(subject_id, timeout=_MAX_LOCK_WAIT_SECONDS):
                yield

    @contextmanager
    def _locked_for_operation(self, operation_id: str) -> Iterator[None]:
        index = self._read_index()
        operation = self._operation_entry(index, operation_id)
        subject_id = operation["subject_id"]
        with self._locked(subject_id):
            current = self._operation_entry(self._read_index(), operation_id)
            if current["subject_id"] != subject_id:
                raise OperationConflict("operation subject changed")
            yield

    def _require_private_storage(self) -> None:
        if not self._private_storage_verified:
            raise OperationError("private storage protection is unverified")
        self._root.revalidate()

    def _read_index(self) -> dict[str, Any]:
        try:
            if self._root.file_info(INDEX_PATH).size > _MAX_INDEX_BYTES:
                raise OperationError("operation storage exceeds its bound")
            raw = self._root.read_bytes(INDEX_PATH)
        except FileNotFoundError:
            return {
                "schema": 1,
                "previews": {},
                "requests": {},
                "cancel_requests": {},
                "operations": {},
            }
        except OperationError:
            raise
        except Exception:
            raise OperationError("operation storage is unavailable") from None
        if len(raw) > _MAX_INDEX_BYTES:
            raise OperationError("operation storage exceeds its bound")
        try:
            index = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise OperationError("operation storage is invalid") from None
        if not isinstance(index, dict) or set(index) != {"schema", "previews", "requests", "cancel_requests", "operations"} or type(index.get("schema")) is not int or index["schema"] != 1:
            raise OperationError("operation storage is invalid")
        if any(not isinstance(index[name], dict) for name in ("previews", "requests", "cancel_requests", "operations")):
            raise OperationError("operation storage is invalid")
        if any(not isinstance(entry, dict) for name in ("previews", "requests", "cancel_requests", "operations") for entry in index[name].values()):
            raise OperationError("operation storage is invalid")
        if any(len(index[name]) > 10000 for name in ("previews", "requests", "cancel_requests", "operations")):
            raise OperationError("operation storage exceeds its bound")
        _validate_index(index)
        return index

    def _write_index(self, index: dict[str, Any]) -> None:
        _validate_index(index)
        payload = _canonical_json(index)
        if len(payload) > _MAX_INDEX_BYTES:
            raise OperationError("operation storage exceeds its bound")
        self._write_bytes(INDEX_PATH, payload)

    def _write_capture_if_missing(self, relative: str, payload: bytes) -> None:
        if len(payload) > _MAX_CAPTURE_BYTES:
            raise OperationError("capture sidecar exceeds its bound")
        try:
            if self._root.file_info(relative).size > _MAX_CAPTURE_BYTES:
                raise OperationError("capture sidecar exceeds its bound")
            existing = self._root.read_bytes(relative)
        except FileNotFoundError:
            self._write_bytes(relative, payload)
            return
        except OperationError:
            raise
        except Exception:
            raise OperationError("capture storage is unavailable") from None
        if existing != payload:
            raise OperationConflict("capture identity conflicts with stored contents")

    def _write_json(self, relative: str, value: object) -> None:
        self._write_bytes(relative, _canonical_json(value))

    def _write_bytes(self, relative: str, payload: bytes) -> None:
        if not isinstance(payload, bytes) or len(payload) > _MAX_INDEX_BYTES:
            raise OperationError("operation sidecar exceeds its bound")
        parent = relative.rsplit("/", 1)[0]
        self._root.mkdir(parent, parents=True, mode=0o700)
        try:
            self._root.write_bytes(relative, payload, mode=stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            raise OperationError("operation storage write failed") from None

    def _write_operation_sidecars(self, operation: dict[str, Any]) -> None:
        for relative, record in _operation_sidecar_records(operation):
            self._write_json(relative, record)

    def _verify_operation_sidecars(self, operation: dict[str, Any]) -> None:
        for relative, record in _operation_sidecar_records(operation):
            self._verify_sidecar(relative, _canonical_json(record))

    def _verify_preview_sidecar(self, preview: dict[str, Any]) -> None:
        relative = f"runtime/operations/previews/{preview['preview_id']}.json"
        self._verify_sidecar(relative, _canonical_json(preview))

    def _verify_capture_sidecar(self, preview: dict[str, Any]) -> None:
        relative = f"runtime/captures/{preview['capture_id']}.json"
        try:
            if self._root.file_info(relative).size > _MAX_CAPTURE_BYTES:
                raise OperationError("capture sidecar exceeds its bound")
            payload = self._root.read_bytes(relative)
        except OperationError:
            raise
        except Exception:
            raise OperationError("capture sidecar is unavailable") from None
        expected_hash = preview["capture_record_hash"]
        if not hmac.compare_digest(_sha256(payload), expected_hash):
            raise OperationError("capture sidecar does not match frozen configuration")

    def _verify_operation_capture(
        self,
        index: dict[str, Any],
        operation: dict[str, Any],
    ) -> None:
        preview = index["previews"].get(operation["preview_id"])
        if not isinstance(preview, dict):
            raise OperationError("operation capture is unavailable")
        self._verify_capture_sidecar(preview)

    def _verify_cancel_sidecar(self, request_id: str, cancellation: dict[str, Any]) -> None:
        relative = f"runtime/operations/cancellations/{_sha256(request_id.encode('utf-8'))}.json"
        expected = {"schema": 1, "request_id": request_id, **cancellation}
        self._verify_sidecar(relative, _canonical_json(expected))

    def _write_cancel_sidecar(self, request_id: str, cancellation: dict[str, Any]) -> None:
        relative = f"runtime/operations/cancellations/{_sha256(request_id.encode('utf-8'))}.json"
        self._write_json(relative, {"schema": 1, "request_id": request_id, **cancellation})

    def _verify_sidecar(self, relative: str, expected: bytes) -> None:
        try:
            if self._root.file_info(relative).size != len(expected):
                raise OperationError("operation sidecar does not match durable state")
            actual = self._root.read_bytes(relative)
        except OperationError:
            raise
        except Exception:
            raise OperationError("operation sidecar is unavailable") from None
        if not hmac.compare_digest(actual, expected):
            raise OperationError("operation sidecar does not match durable state")

    def _persist_transition(self, index: dict[str, Any], operation: dict[str, Any]) -> None:
        self._write_operation_sidecars(operation)
        self._write_index(index)

    def _operation_from_index(self, index: dict[str, Any], operation_id: object) -> OperationRecord:
        if not isinstance(operation_id, str) or not _HEX_ID.fullmatch(operation_id):
            raise OperationError("operation identity is invalid")
        entry = self._operation_entry(index, operation_id)
        try:
            result = None if entry["result"] is None else _freeze_json(_normalize_payload(entry["result"]))
            return OperationRecord(
                operation_id=entry["operation_id"],
                request_id=entry["request_id"],
                request_digest=entry["request_digest"],
                preview_id=entry["preview_id"],
                action=entry["action"],
                subject_id=entry["subject_id"],
                capture_id=entry["capture_id"],
                capture_digest=entry["capture_digest"],
                status=OperationStatus(entry["status"]),
                payload=_freeze_json(_normalize_payload(entry["payload"])),
                result=result,
                progress=entry["progress"],
                fence_generation=entry["fence_generation"],
            )
        except (KeyError, ValueError, TypeError):
            raise OperationError("operation record is invalid") from None

    def _operation_entry(self, index: dict[str, Any], operation_id: str) -> dict[str, Any]:
        entry = index["operations"].get(operation_id)
        if not isinstance(entry, dict):
            raise OperationError("operation record was not found")
        return entry

    def _require_current_fence(self, operation: dict[str, Any], operation_id: str, fence: WorkerFence) -> None:
        if not isinstance(fence, WorkerFence) or fence.operation_id != operation_id or fence.generation != operation["fence_generation"]:
            raise WorkerFenced("worker fence is stale")
        expected = operation.get("worker_fence_hash")
        actual = _sha256(fence.nonce.encode("utf-8")) if isinstance(fence.nonce, str) else ""
        if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
            raise WorkerFenced("worker fence is stale")

    def _append_event(self, operation: dict[str, Any], status: OperationStatus, now: datetime) -> None:
        if len(operation["events"]) >= 10000:
            raise OperationError("operation journal exceeds its bound")
        operation["events"].append({"status": status.value, "at": _datetime_text(now)})


def _operation_sidecar_records(operation: dict[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
    operation_id = operation["operation_id"]
    request_id = operation["request_id"]
    records = [
        (
            f"runtime/operations/requests/{_sha256(request_id.encode('utf-8'))}.json",
            {
                "schema": 1,
                "request_id": request_id,
                "operation_id": operation_id,
                "request_digest": operation["request_digest"],
                "preview_id": operation["preview_id"],
            },
        ),
        (
            f"runtime/operations/journal/{operation_id}.json",
            {"schema": 1, "operation_id": operation_id, "events": operation["events"]},
        ),
        (
            f"runtime/operations/state/{operation_id}.json",
            {
                "schema": 1,
                "operation_id": operation_id,
                "status": operation["status"],
                "progress": operation["progress"],
                "fence_generation": operation["fence_generation"],
                "updated_at": operation["updated_at"],
            },
        ),
    ]
    records.append(
        (
            f"runtime/operations/results/{operation_id}.json",
            {"schema": 1, "operation_id": operation_id, "result": operation["result"]},
        )
    )
    return tuple(records)


def _preview_digest_fields(
    *,
    action: str,
    subject_id: str,
    expected_head: str | None,
    due_set: tuple[str, ...],
    capture_id: str,
    capture_digest: str,
    operator_session_hash: str,
    expires_at: datetime,
    payload: Mapping[str, Any],
) -> dict[str, object]:
    return {
        "action": action,
        "subject_id": subject_id,
        "expected_head": expected_head,
        "due_set": list(due_set),
        "capture_id": capture_id,
        "capture_digest": capture_digest,
        "operator_session_hash": operator_session_hash,
        "expires_at": _datetime_text(expires_at),
        "payload": _thaw_json(payload),
    }


def _normalize_payload(value: object, *, depth: int = 0, count: list[int] | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or depth > 8:
        raise OperationError("operation payload is invalid")
    counter = [0] if count is None else count

    def normalize(item: object, level: int) -> Any:
        counter[0] += 1
        if counter[0] > _MAX_PAYLOAD_NODES or level > 8:
            raise OperationError("operation payload exceeds its bound")
        if item is None or isinstance(item, bool) or isinstance(item, int):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise OperationError("operation payload is invalid")
            return item
        if isinstance(item, str):
            if len(item) > 4096 or any(ord(char) < 32 and char not in "\t\n\r" for char in item):
                raise OperationError("operation payload is invalid")
            return item
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not _safe_text(key, maximum=128):
                    raise OperationError("operation payload is invalid")
                normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).casefold()
                key_parts = tuple(part for part in re.split(r"[^a-z0-9]+", normalized_key) if part)
                canonical_key = "".join(key_parts)
                if any(blocked in canonical_key for blocked in _DENIED_FIELDS) or any(part in _KEY_FIELDS for part in key_parts):
                    raise OperationError("operation payload contains a prohibited field")
                result[key] = normalize(child, level + 1)
            return result
        if isinstance(item, (list, tuple)):
            if len(item) > 256:
                raise OperationError("operation payload exceeds its bound")
            return [normalize(child, level + 1) for child in item]
        raise OperationError("operation payload is invalid")

    normalized = normalize(value, depth)
    encoded = _canonical_json(normalized)
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        raise OperationError("operation payload exceeds its bound")
    return normalized


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise OperationError("operation data is not serializable") from None


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _validate_index(index: dict[str, Any]) -> None:
    preview_fields = {
        "action",
        "subject_id",
        "expected_head",
        "due_set",
        "capture_id",
        "capture_digest",
        "capture_record_hash",
        "operator_session_hash",
        "expires_at",
        "payload",
        "schema",
        "preview_id",
        "digest",
        "payload_digest",
        "confirmation_token_hash",
        "state",
        "consumed_request_id",
    }
    operation_fields = {
        "schema",
        "operation_id",
        "request_id",
        "request_digest",
        "preview_id",
        "action",
        "subject_id",
        "capture_id",
        "capture_digest",
        "status",
        "payload",
        "progress",
        "created_at",
        "updated_at",
        "fence_generation",
        "worker_id_hash",
        "worker_fence_hash",
        "events",
        "result",
    }
    request_fields = {"operation_id", "request_digest", "preview_id", "payload_digest"}
    cancel_fields = {"operation_id", "request_digest"}
    transitions = {
        OperationStatus.ACCEPTED: {
            OperationStatus.RUNNING,
            OperationStatus.CANCEL_REQUESTED,
            OperationStatus.INTERRUPTED,
        },
        OperationStatus.RUNNING: {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCEL_REQUESTED,
            OperationStatus.INTERRUPTED,
        },
        OperationStatus.CANCEL_REQUESTED: {
            OperationStatus.CANCELLED,
            OperationStatus.INTERRUPTED,
        },
    }

    for preview_id, preview in index["previews"].items():
        if not isinstance(preview_id, str) or not _HEX_ID.fullmatch(preview_id) or set(preview) != preview_fields:
            raise OperationError("preview storage is invalid")
        if type(preview.get("schema")) is not int or preview["schema"] != 1 or preview.get("preview_id") != preview_id:
            raise OperationError("preview storage is invalid")
        if not isinstance(preview.get("due_set"), list):
            raise OperationError("preview storage is invalid")
        try:
            action = _validate_action(preview["action"])
            subject_id = _validate_subject(preview["subject_id"])
            due_set = _validate_due_set(tuple(preview["due_set"]))
            capture_id = _validate_operation_id(preview["capture_id"])
            capture_digest = preview["capture_digest"]
            operator_hash = preview["operator_session_hash"]
            expires_at = _parse_datetime(preview["expires_at"])
            payload = _normalize_payload(preview["payload"])
        except (TypeError, KeyError, ValueError):
            raise OperationError("preview storage is invalid") from None
        if action != preview["action"] or subject_id != preview["subject_id"] or list(due_set) != preview["due_set"]:
            raise OperationError("preview storage is invalid")
        if preview["expected_head"] is not None and not _safe_text(preview["expected_head"], maximum=512):
            raise OperationError("preview storage is invalid")
        if not isinstance(capture_digest, str) or not _SHA256.fullmatch(capture_digest):
            raise OperationError("preview storage is invalid")
        if not isinstance(preview.get("capture_record_hash"), str) or not _SHA256.fullmatch(preview["capture_record_hash"]):
            raise OperationError("preview storage is invalid")
        if not isinstance(operator_hash, str) or not _SHA256.fullmatch(operator_hash):
            raise OperationError("preview storage is invalid")
        if not isinstance(preview.get("digest"), str) or not _SHA256.fullmatch(preview["digest"]):
            raise OperationError("preview storage is invalid")
        if not isinstance(preview.get("payload_digest"), str) or preview["payload_digest"] != _sha256(_canonical_json(payload)):
            raise OperationError("preview storage is invalid")
        if not isinstance(preview.get("confirmation_token_hash"), str) or not _SHA256.fullmatch(preview["confirmation_token_hash"]):
            raise OperationError("preview storage is invalid")
        if preview.get("state") not in {"issued", "consumed"}:
            raise OperationError("preview storage is invalid")
        consumed_by = preview.get("consumed_request_id")
        if preview["state"] == "issued" and consumed_by is not None:
            raise OperationError("preview storage is invalid")
        if preview["state"] == "consumed":
            try:
                _validate_request_id(consumed_by)
            except OperationError:
                raise OperationError("preview storage is invalid") from None
        fields = _preview_digest_fields(
            action=action,
            subject_id=subject_id,
            expected_head=preview["expected_head"],
            due_set=due_set,
            capture_id=capture_id,
            capture_digest=capture_digest,
            operator_session_hash=operator_hash,
            expires_at=expires_at,
            payload=payload,
        )
        if _sha256(_canonical_json(fields)) != preview["digest"]:
            raise OperationError("preview digest is invalid")

    for operation_id, operation in index["operations"].items():
        if not isinstance(operation_id, str) or not _HEX_ID.fullmatch(operation_id) or set(operation) != operation_fields:
            raise OperationError("operation storage is invalid")
        if type(operation.get("schema")) is not int or operation["schema"] != 1 or operation.get("operation_id") != operation_id:
            raise OperationError("operation storage is invalid")
        try:
            request_id = _validate_request_id(operation["request_id"])
            _validate_action(operation["action"])
            subject_id = _validate_subject(operation["subject_id"])
            _validate_operation_id(operation["preview_id"])
            capture_id = _validate_operation_id(operation["capture_id"])
            status = OperationStatus(operation["status"])
            payload = _normalize_payload(operation["payload"])
            created_at = _parse_datetime(operation["created_at"])
            updated_at = _parse_datetime(operation["updated_at"])
        except (TypeError, KeyError, ValueError):
            raise OperationError("operation storage is invalid") from None
        if subject_id != operation["subject_id"] or capture_id != operation["capture_id"] or updated_at < created_at:
            raise OperationError("operation storage is invalid")
        if not isinstance(operation.get("request_digest"), str) or not _SHA256.fullmatch(operation["request_digest"]):
            raise OperationError("operation storage is invalid")
        if not isinstance(operation.get("capture_digest"), str) or not _SHA256.fullmatch(operation["capture_digest"]):
            raise OperationError("operation storage is invalid")
        if type(operation.get("fence_generation")) is not int or operation["fence_generation"] < 0:
            raise OperationError("operation storage is invalid")
        if type(operation.get("progress")) is not int or not 0 <= operation["progress"] <= 100:
            raise OperationError("operation progress is invalid")
        if (status is OperationStatus.COMPLETED) != (operation["progress"] == 100):
            raise OperationError("operation progress does not match state")
        for field_name in ("worker_id_hash", "worker_fence_hash"):
            field_value = operation.get(field_name)
            if field_value is not None and (not isinstance(field_value, str) or not _SHA256.fullmatch(field_value)):
                raise OperationError("operation storage is invalid")
        if (operation["worker_id_hash"] is None) != (operation["worker_fence_hash"] is None):
            raise OperationError("operation worker fence is invalid")
        if status is OperationStatus.RUNNING and operation["worker_fence_hash"] is None:
            raise OperationError("running operation has no worker fence")
        if status in {OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.INTERRUPTED, OperationStatus.CANCELLED} and operation["worker_fence_hash"] is not None:
            raise OperationError("terminal operation retains a worker fence")
        if not isinstance(operation.get("events"), list) or not operation["events"] or len(operation["events"]) > 10000:
            raise OperationError("operation journal is invalid")
        event_statuses: list[OperationStatus] = []
        prior_event_time: datetime | None = None
        for event in operation["events"]:
            if not isinstance(event, dict) or set(event) != {"status", "at"}:
                raise OperationError("operation journal is invalid")
            try:
                event_status = OperationStatus(event["status"])
                event_time = _parse_datetime(event["at"])
            except (TypeError, ValueError):
                raise OperationError("operation journal is invalid") from None
            if prior_event_time is not None and event_time < prior_event_time:
                raise OperationError("operation journal timestamps are invalid")
            if event_statuses and event_status not in transitions.get(event_statuses[-1], set()):
                raise OperationError("operation journal transition is invalid")
            event_statuses.append(event_status)
            prior_event_time = event_time
        if event_statuses[0] is not OperationStatus.ACCEPTED or event_statuses[-1] is not status:
            raise OperationError("operation journal does not match state")
        if operation.get("result") is not None:
            _normalize_payload(operation["result"])
        if (status is OperationStatus.COMPLETED or status is OperationStatus.FAILED) != (operation["result"] is not None):
            raise OperationError("operation result does not match state")
    for request_id, request in index["requests"].items():
        if not isinstance(request_id, str) or not _SAFE_ID.fullmatch(request_id) or set(request) != request_fields:
            raise OperationError("request storage is invalid")
        operation_id = request.get("operation_id")
        if not isinstance(operation_id, str) or not _HEX_ID.fullmatch(operation_id):
            raise OperationError("request storage is invalid")
        operation = index["operations"].get(operation_id)
        if operation is None or operation.get("request_id") != request_id or operation.get("request_digest") != request.get("request_digest") or operation.get("preview_id") != request.get("preview_id") or not isinstance(request.get("request_digest"), str) or not _SHA256.fullmatch(request["request_digest"]) or not isinstance(request.get("payload_digest"), str) or not _SHA256.fullmatch(request["payload_digest"]):
            raise OperationError("request storage is invalid")
        preview_id = request.get("preview_id")
        if not isinstance(preview_id, str) or not _HEX_ID.fullmatch(preview_id):
            raise OperationError("request storage is invalid")
        preview = index["previews"].get(preview_id)
        if preview is None or preview.get("consumed_request_id") != request_id or preview.get("state") != "consumed":
            raise OperationError("request storage is invalid")
        if request["payload_digest"] != _sha256(_canonical_json(operation["payload"])) or request["payload_digest"] != preview["payload_digest"]:
            raise OperationError("request storage is invalid")
        if operation["action"] != preview["action"] or operation["subject_id"] != preview["subject_id"] or operation["capture_id"] != preview["capture_id"] or operation["capture_digest"] != preview["capture_digest"]:
            raise OperationError("request capture linkage is invalid")

    for operation_id, operation in index["operations"].items():
        request = index["requests"].get(operation["request_id"])
        preview = index["previews"].get(operation["preview_id"])
        if request is None or request.get("operation_id") != operation_id or preview is None or preview.get("state") != "consumed" or preview.get("consumed_request_id") != operation["request_id"] or operation["events"][-1]["status"] != operation["status"]:
            raise OperationError("operation linkage is invalid")

    for request_id, cancellation in index["cancel_requests"].items():
        if not isinstance(request_id, str) or not _SAFE_ID.fullmatch(request_id) or set(cancellation) != cancel_fields:
            raise OperationError("cancellation storage is invalid")
        if request_id in index["requests"]:
            raise OperationError("request identity is duplicated")
        operation_id = cancellation.get("operation_id")
        if not isinstance(operation_id, str) or not _HEX_ID.fullmatch(operation_id):
            raise OperationError("cancellation storage is invalid")
        operation = index["operations"].get(operation_id)
        expected_digest = _sha256(_canonical_json({"operation_id": operation_id, "request_id": request_id}))
        if operation is None or not isinstance(cancellation.get("request_digest"), str) or not _SHA256.fullmatch(cancellation["request_digest"]) or cancellation["request_digest"] != expected_digest:
            raise OperationError("cancellation storage is invalid")

    for operation_id, operation in index["operations"].items():
        if operation["status"] in {OperationStatus.CANCEL_REQUESTED.value, OperationStatus.CANCELLED.value} and not any(item.get("operation_id") == operation_id for item in index["cancel_requests"].values()):
            raise OperationError("cancellation linkage is invalid")

    for preview_id, preview in index["previews"].items():
        if preview["state"] == "consumed":
            request = index["requests"].get(preview["consumed_request_id"])
            if request is None or request.get("preview_id") != preview_id:
                raise OperationError("preview linkage is invalid")


def _validate_action(value: object) -> str:
    if not isinstance(value, str) or not _ACTION.fullmatch(value):
        raise OperationError("operation action is invalid")
    return value


def _validate_subject(value: object) -> str:
    if not isinstance(value, str):
        raise OperationError("operation subject is invalid")
    try:
        return ensure_unique_resource_name(value, [])
    except RootPathError:
        raise OperationError("operation subject is invalid") from None


def _validate_due_set(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) > 10000 or any(not _safe_text(item, maximum=256) for item in value) or len(set(value)) != len(value):
        raise OperationError("operation due-set is invalid")
    return value


def _validate_request_id(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise OperationError("request identity is invalid")
    return value


def _validate_operation_id(value: object) -> str:
    if not isinstance(value, str) or not _HEX_ID.fullmatch(value):
        raise OperationError("operation identity is invalid")
    return value


def _validate_worker_id(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise OperationError("worker identity is invalid")
    return value


def _validate_session(value: object) -> str:
    if not _safe_text(value, maximum=512):
        raise OperationError("operator session is invalid")
    return value


def _validate_datetime(value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OperationError("operation time must be timezone-aware")


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise OperationError("operation timestamp is invalid")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise OperationError("operation timestamp is invalid") from None
    _validate_datetime(result)
    return result.astimezone(timezone.utc)


def _datetime_text(value: datetime) -> str:
    _validate_datetime(value)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _safe_text(value: object, *, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= maximum and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
