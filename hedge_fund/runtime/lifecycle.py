"""Reversible root-scoped archive transitions."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hedge_fund.runtime.admission import AdmissionCoordinator
from hedge_fund.runtime.handover import (
    require_enrollment,
    transition_ledger_inventory,
    verify_root_inventory,
)
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootContext,
    RootPathError,
)

ARCHIVE_ROOT = f"{PRIVATE_ROOT}/archives/v1"
ARCHIVE_INDEX = f"{ARCHIVE_ROOT}/index.json"
_REPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.json$")
_SAFE_ID = re.compile(r"[a-f0-9]{32}")
_MAX_INDEX_BYTES = 16 * 1024 * 1024
_MAX_ENTRIES = 10000
_MAX_BYTES = 512 * 1024 * 1024


class ArchiveError(RuntimeError):
    """Archive state or identity is invalid."""


class ArchiveConflict(ArchiveError):
    """Archive identity changed or destination collides."""


class ArchiveNotFound(ArchiveError):
    """Archive identity does not exist."""


class LifecycleArchiveStore:
    """Move one exact object under shared root and object admission."""

    def __init__(self, root: RootContext, admission: AdmissionCoordinator) -> None:
        if not isinstance(root, RootContext) or not isinstance(admission, AdmissionCoordinator):
            raise TypeError("root and admission contexts are required")
        if admission.root is not root or not root.verify_private_storage():
            raise ArchiveError("verified matching root admission is required")
        require_enrollment(root)
        self._root = root
        self._admission = admission

    def preview(self, kind: str, identity: str) -> dict[str, str]:
        kind, identity = _validate_identity(kind, identity)
        verify_root_inventory(self._root)
        source, lane_identity = self._source(kind, identity)
        return {
            "kind": kind,
            "identity": identity,
            "source_path": source,
            "lane_identity": lane_identity,
            "digest": self._tree_digest(source),
        }

    def archive(
        self,
        kind: str,
        identity: str,
        *,
        expected_digest: str,
        archive_id: str,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        kind, identity = _validate_identity(kind, identity)
        archive_id = _validate_id(archive_id)
        if operation_id is not None:
            _validate_id(operation_id)
        if not _is_sha256(expected_digest):
            raise ArchiveError("archive digest is invalid")
        with self._admission.registry_lock(timeout=0):
            self._admission.require_root_owner()
            verify_root_inventory(self._root)
            index = self._read_index()
            existing = index["items"].get(archive_id)
            if existing is not None:
                if existing["digest"] != expected_digest or existing["kind"] != kind or existing["identity"] != identity:
                    raise ArchiveConflict("archive operation identity conflicts")
                if existing["state"] != "archived":
                    raise ArchiveConflict("archive requires explicit journal recovery")
                if self._tree_digest(existing["archive_path"]) != expected_digest:
                    raise ArchiveConflict("archived object changed after review")
                return dict(existing)
            source, lane_identity = self._source(kind, identity)
            with self._object_lane(kind, lane_identity):
                current = self._tree_digest(source)
                if current != expected_digest:
                    raise ArchiveConflict("object changed after review")
                index = self._read_index()
                existing = index["items"].get(archive_id)
                if existing is not None:
                    if existing["digest"] != expected_digest or existing["source_path"] != source:
                        raise ArchiveConflict("archive operation identity conflicts")
                    return self._finalize_archive(index, existing)
                target = f"{ARCHIVE_ROOT}/objects/{archive_id}"
                self._require_absent(target)
                self._root.mkdir(f"{ARCHIVE_ROOT}/objects", parents=True, mode=0o700)
                inventory_before, ledger_entry = self._inventory_snapshot(kind, identity)
                record = {
                    "schema": 1,
                    "archive_id": archive_id,
                    "kind": kind,
                    "identity": identity,
                    "lane_identity": lane_identity,
                    "source_path": source,
                    "archive_path": target,
                    "digest": expected_digest,
                    "state": "archive-prepared",
                    "updated_at": _now(),
                    "restore_operation_id": None,
                    "inventory_before": inventory_before,
                    "ledger_entry": ledger_entry,
                    "reconciled_operations": [],
                    "archive_operation_id": operation_id,
                }
                index["items"][archive_id] = record
                self._write_index(index)
                self._move(kind, source, target)
                index = self._read_index()
                record = index["items"].get(archive_id)
                if not isinstance(record, dict):
                    raise ArchiveError("archive journal disappeared")
                return self._finalize_archive(index, record)

    def restore(
        self,
        archive_id: str,
        *,
        expected_digest: str,
        operation_id: str,
    ) -> dict[str, Any]:
        archive_id = _validate_id(archive_id)
        operation_id = _validate_id(operation_id)
        if not _is_sha256(expected_digest):
            raise ArchiveError("restore digest is invalid")
        with self._admission.registry_lock(timeout=0):
            self._admission.require_root_owner()
            verify_root_inventory(self._root)
            index = self._read_index()
            record = index["items"].get(archive_id)
            if not isinstance(record, dict):
                raise ArchiveNotFound("archive does not exist")
            kind = record["kind"]
            identity = record["identity"]
            lane_identity = record["lane_identity"]
            with self._object_lane(kind, lane_identity):
                index = self._read_index()
                record = index["items"].get(archive_id)
                if not isinstance(record, dict) or record.get("digest") != expected_digest:
                    raise ArchiveConflict("archive changed after review")
                if record.get("state") == "restored":
                    if record.get("restore_operation_id") == operation_id:
                        return dict(record)
                    raise ArchiveConflict("archive was already restored")
                if record.get("state") != "archived":
                    raise ArchiveConflict("archive requires explicit journal recovery")
                if self._tree_digest(record["archive_path"]) != expected_digest:
                    raise ArchiveConflict("archived object changed after review")
                self._require_absent(record["source_path"])
                self._require_identity_absent(kind, identity)
                inventory_before, _ = self._inventory_snapshot(kind, identity, restoring=True)
                record["inventory_before"] = inventory_before
                record["state"] = "restore-prepared"
                record["restore_operation_id"] = operation_id
                record["updated_at"] = _now()
                self._write_index(index)
                self._move(kind, record["archive_path"], record["source_path"])
                index = self._read_index()
                record = index["items"].get(archive_id)
                if not isinstance(record, dict):
                    raise ArchiveError("archive journal disappeared")
                return self._finalize_restore(index, record)

    def inspect(self, archive_id: str) -> dict[str, Any]:
        archive_id = _validate_id(archive_id)
        record = self._read_index()["items"].get(archive_id)
        if not isinstance(record, dict):
            raise ArchiveNotFound("archive does not exist")
        view = dict(record)
        source_exists = self._exists(record["source_path"])
        archive_exists = self._exists(record["archive_path"])
        source_matches = source_exists and self._tree_digest(record["source_path"]) == record["digest"]
        archive_matches = archive_exists and self._tree_digest(record["archive_path"]) == record["digest"]
        view["recovery_required"] = record["state"] in {"archive-prepared", "restore-prepared"}
        if record["state"] == "archive-prepared":
            view["recovery_action"] = "finalize-archive" if archive_matches and not source_exists else "abandon-archive" if source_matches and not archive_exists else "manual-review"
        elif record["state"] == "restore-prepared":
            view["recovery_action"] = "finalize-restore" if source_matches and not archive_exists else "retry-restore" if archive_matches and not source_exists else "manual-review"
        return view

    def review_archive(self, archive_id: str, *, action: str) -> dict[str, Any]:
        archive_id = _validate_id(archive_id)
        if action not in {"restore", "recover"}:
            raise ArchiveError("archive review action is invalid")
        record = self.inspect(archive_id)
        if action == "restore":
            if record["state"] != "archived":
                raise ArchiveConflict("only a completed archive can be restored")
            self._require_absent(record["source_path"])
            self._require_identity_absent(record["kind"], record["identity"])
            path = record["archive_path"]
        else:
            if not record["recovery_required"] or record["recovery_action"] == "manual-review":
                raise ArchiveConflict("archive journal has no safe recovery")
            path = record["archive_path"] if record["recovery_action"] in {"finalize-archive", "retry-restore"} else record["source_path"]
        if self._tree_digest(path) != record["digest"]:
            raise ArchiveConflict("archive contents changed after review")
        record["review_path"] = path
        return record

    def review_unprepared(self, kind: str, identity: str, *, archive_id: str, expected_digest: str, deployment_before: dict[str, Any] | None = None) -> dict[str, Any]:
        """Prove an admitted, no-provider archive left the exact original object intact."""
        archive_id = _validate_id(archive_id)
        if archive_id in self._read_index()["items"]:
            raise ArchiveConflict("archive journal already exists")
        target = f"{ARCHIVE_ROOT}/objects/{archive_id}"
        self._require_absent(target)
        current = self.preview(kind, identity)
        if current["digest"] != expected_digest:
            if kind != "deployment" or not isinstance(deployment_before, dict):
                raise ArchiveConflict("unjournaled archive source changed; manual review required")
            _, entry = self._inventory_snapshot(kind, identity)
            if entry["deployment_digest"] != deployment_before.get("deployment_digest") or entry["session_count"] < deployment_before.get("session_count", _MAX_ENTRIES + 1):
                raise ArchiveConflict("unjournaled deployment identity changed")
            if deployment_before.get("last_session") is not None:
                from hedge_fund.paper.ledger import Ledger, LedgerError

                try:
                    prior = Ledger(self._root.resolve(current["source_path"])).read(deployment_before["last_session"])
                except LedgerError as exc:
                    raise ArchiveConflict("unjournaled deployment prior history is unavailable") from exc
                if prior.hash != deployment_before.get("head_hash"):
                    raise ArchiveConflict("unjournaled deployment history changed")
        return {
            "schema": 1,
            "archive_id": archive_id,
            "kind": current["kind"],
            "identity": current["identity"],
            "lane_identity": current["lane_identity"],
            "source_path": current["source_path"],
            "archive_path": target,
            "digest": expected_digest,
            "review_digest": current["digest"],
            "deployment_before": deployment_before,
            "state": "archive-unprepared",
            "updated_at": _now(),
            "restore_operation_id": None,
            "inventory_before": None,
            "ledger_entry": None,
            "reconciled_operations": [],
            "recovery_required": True,
            "recovery_action": "abandon-unprepared",
            "review_path": current["source_path"],
        }

    def abandon_unprepared(self, kind: str, identity: str, *, archive_id: str, expected_digest: str, reconciled_operations: tuple[str, ...], review_digest: str, deployment_before: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._admission.registry_lock(timeout=0):
            current = self.review_unprepared(kind, identity, archive_id=archive_id, expected_digest=expected_digest, deployment_before=deployment_before)
            with self._object_lane(kind, current["lane_identity"]):
                current = self.review_unprepared(kind, identity, archive_id=archive_id, expected_digest=expected_digest, deployment_before=deployment_before)
                if current["review_digest"] != review_digest:
                    raise ArchiveConflict("recovery source changed after review")
                if not reconciled_operations or len(reconciled_operations) > _MAX_ENTRIES or any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in reconciled_operations):
                    raise ArchiveError("recovery operation identities are invalid")
                for field in ("recovery_required", "recovery_action", "review_path"):
                    current.pop(field)
                current["state"] = "abandoned"
                current["reconciled_operations"] = sorted(set(reconciled_operations))
                index = self._read_index()
                index["items"][archive_id] = current
                self._write_index(index)
                return dict(current)

    def reconcile_unprepared_restore(self, archive_id: str, *, expected_digest: str, reconciled_operations: tuple[str, ...]) -> dict[str, Any]:
        """Explicitly close a restore that never prepared its write-ahead move."""
        with self._admission.registry_lock(timeout=0):
            reviewed = self.review_unprepared_restore(archive_id)
            with self._object_lane(reviewed["kind"], reviewed["lane_identity"]):
                reviewed = self.review_unprepared_restore(archive_id)
                if reviewed["digest"] != expected_digest:
                    raise ArchiveConflict("restore recovery changed after review")
                if not reconciled_operations or len(reconciled_operations) > _MAX_ENTRIES or any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in reconciled_operations):
                    raise ArchiveError("recovery operation identities are invalid")
                index = self._read_index()
                record = index["items"][archive_id]
                record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | set(reconciled_operations))
                record["updated_at"] = _now()
                self._write_index(index)
                return dict(record)

    def review_unprepared_restore(self, archive_id: str) -> dict[str, Any]:
        record = self.inspect(archive_id)
        if record["state"] != "archived" or self._tree_digest(record["archive_path"]) != record["digest"]:
            raise ArchiveConflict("restore no-effect evidence is unavailable")
        record["review_path"] = record["archive_path"]
        record["recovery_required"] = True
        record["recovery_action"] = "abandon-unprepared-restore"
        return record

    def recover(self, archive_id: str, *, expected_digest: str, reconciled_operations: tuple[str, ...] = ()) -> dict[str, Any]:
        """Reconcile journal only after explicit identity-bound review."""
        archive_id = _validate_id(archive_id)
        if not _is_sha256(expected_digest):
            raise ArchiveError("recovery digest is invalid")
        if not isinstance(reconciled_operations, tuple) or len(reconciled_operations) > _MAX_ENTRIES or any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in reconciled_operations):
            raise ArchiveError("recovery operation identities are invalid")
        with self._admission.registry_lock(timeout=0):
            self._admission.require_root_owner()
            index = self._read_index()
            record = index["items"].get(archive_id)
            if not isinstance(record, dict):
                raise ArchiveNotFound("archive does not exist")
            if record.get("digest") != expected_digest:
                raise ArchiveConflict("archive changed after review")
            with self._object_lane(record["kind"], record["lane_identity"]):
                action = self.inspect(archive_id).get("recovery_action")
                if action not in {"finalize-archive", "finalize-restore", "abandon-archive", "retry-restore"}:
                    raise ArchiveConflict("archive has no pending recovery")
                record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | set(reconciled_operations))
                if action == "finalize-archive":
                    self._transition_deployment_head(record, restore=False)
                    operation_id = record.get("archive_operation_id")
                    if operation_id is not None:
                        record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | {operation_id})
                    record["state"] = "archived"
                    record["updated_at"] = _now()
                    self._write_index(index)
                elif action == "finalize-restore":
                    self._transition_deployment_head(record, restore=True)
                    record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | {record["restore_operation_id"]})
                    record["state"] = "restored"
                    record["updated_at"] = _now()
                    self._write_index(index)
                elif action == "abandon-archive":
                    record["state"] = "abandoned"
                    record["updated_at"] = _now()
                    self._write_index(index)
                elif action == "retry-restore":
                    record["state"] = "archived"
                    record["restore_operation_id"] = None
                    record["updated_at"] = _now()
                    self._write_index(index)
                else:
                    raise ArchiveConflict("archive requires manual review")
                return dict(record)

    def list_archives(self) -> list[dict[str, Any]]:
        index = self._read_index()
        return [
            dict(item)
            for item in sorted(
                index["items"].values(),
                key=lambda value: (value.get("updated_at", ""), value.get("archive_id", "")),
                reverse=True,
            )
        ]

    @contextmanager
    def _object_lane(self, kind: str, identity: str):
        lanes = ("deployment", "runner", "execution", "control")
        if kind == "deployment":
            lanes += ("halt",)
        lanes += ("research",)
        with ExitStack() as stack:
            for lane in lanes:
                if not self._admission.lane_is_held(lane, identity):
                    acquire = {
                        "deployment": self._admission.deployment_lock,
                        "runner": self._admission.runner_reservation,
                        "execution": self._admission.execution_lease,
                        "control": self._admission.control_lane,
                        "halt": self._admission.halt_lane,
                        "research": self._admission.research_lane,
                    }[lane]
                    stack.enter_context(acquire(identity, timeout=0))
            self._require_runner_stopped(identity)
            yield

    def _require_runner_stopped(self, identity: str) -> None:
        from hedge_fund.runtime.owned_runner import (
            OwnedRunnerError,
            read_runner_record,
            validate_runner_state,
        )

        try:
            state = read_runner_record(self._root, identity, "state")
            if state is None:
                if read_runner_record(self._root, identity, "launch") is not None:
                    raise ArchiveConflict("runner launch ownership is unknown")
            elif not validate_runner_state(self._root, identity, state) or state["status"] not in {"stopped", "completed"}:
                raise ArchiveConflict("runner is active or its ownership is unknown")
        except OwnedRunnerError as exc:
            raise ArchiveConflict("runner ownership cannot be verified") from exc

    def _inventory_snapshot(
        self,
        kind: str,
        identity: str,
        *,
        restoring: bool = False,
    ) -> tuple[dict[str, dict[str, Any]] | None, dict[str, Any] | None]:
        if kind != "deployment":
            return None, None
        verify_root_inventory(self._root)
        heads = dict(require_enrollment(self._root)["heads"])
        entry = heads.get(_resource_key(identity))
        if restoring and entry is not None:
            raise ArchiveConflict("deployment inventory collision")
        if not restoring and not isinstance(entry, dict):
            raise ArchiveConflict("deployment ledger head is not enrolled")
        return heads, dict(entry) if entry is not None else None

    def _source(self, kind: str, identity: str) -> tuple[str, str]:
        if kind == "deployment":
            relative = f"paper/{identity}"
            return self._require_tree(relative, directory=True), identity
        if kind == "research":
            relative = f"research/{identity}"
            path = self._require_tree(relative, directory=False)
            try:
                report = json.loads(self._root.read_bytes(path).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ArchiveConflict("research report is unreadable") from None
            fund = report.get("fund") if isinstance(report, dict) else None
            if not isinstance(fund, str):
                raise ArchiveConflict("research report identity is invalid")
            fund = _validate_lane_identity(fund)
            if not identity.startswith(f"{fund}-"):
                raise ArchiveConflict("research report identity does not match its fund")
            return path, fund
        directory = self._root.resolve("mandates")
        if not directory.is_dir():
            raise ArchiveNotFound("mandate does not exist")
        candidates = [entry.name for entry in directory.iterdir() if entry.suffix.casefold() in {".yaml", ".yml"} and _resource_key(entry.stem) == _resource_key(identity)]
        if len(candidates) != 1:
            raise ArchiveNotFound("mandate identity is missing or ambiguous")
        relative = f"mandates/{candidates[0]}"
        return self._require_tree(relative, directory=False), identity

    def _require_tree(self, relative: str, *, directory: bool) -> str:
        path = self._root.resolve(relative)
        try:
            mode = path.lstat().st_mode
        except OSError:
            raise ArchiveNotFound("archive target does not exist") from None
        if stat.S_ISLNK(mode) or (directory and not stat.S_ISDIR(mode)) or (not directory and not stat.S_ISREG(mode)):
            raise ArchiveConflict("archive target has an unsupported filesystem type")
        self._tree_digest(relative)
        return relative

    def _tree_digest(self, relative: str) -> str:
        path = self._root.resolve(relative)
        digest = hashlib.sha256()
        entries = 0
        total_bytes = 0

        def visit(candidate: Path, rel: str, depth: int) -> None:
            nonlocal entries, total_bytes
            if depth > 32:
                raise ArchiveConflict("archive tree exceeds its depth bound")
            try:
                info = candidate.lstat()
            except OSError:
                raise ArchiveConflict("archive tree changed during inspection") from None
            reparse = getattr(info, "st_file_attributes", 0) & getattr(
                stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            )
            if stat.S_ISLNK(info.st_mode) or reparse:
                raise ArchiveConflict("archive tree contains a symbolic link")
            entries += 1
            if entries > _MAX_ENTRIES:
                raise ArchiveConflict("archive tree exceeds its entry bound")
            if stat.S_ISDIR(info.st_mode):
                digest.update(b"D\0" + rel.encode("utf-8") + b"\0")
                try:
                    children = sorted(candidate.iterdir(), key=lambda item: item.name.casefold())
                except OSError:
                    raise ArchiveConflict("archive tree is unreadable") from None
                for child in children:
                    child_relative = f"{rel}/{child.name}" if rel else child.name
                    visit(child, child_relative, depth + 1)
                return
            if not stat.S_ISREG(info.st_mode):
                raise ArchiveConflict("archive tree contains an unsupported file")
            root_relative = f"{relative}/{rel}" if rel else relative
            try:
                content = self._root.read_bytes(root_relative)
            except (OSError, RootPathError):
                raise ArchiveConflict("archive tree changed during inspection") from None
            total_bytes += len(content)
            if total_bytes > _MAX_BYTES:
                raise ArchiveConflict("archive tree exceeds its byte bound")
            digest.update(b"F\0" + rel.encode("utf-8") + b"\0")
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(hashlib.sha256(content).digest())

        visit(path, "", 0)
        self._root.revalidate()
        return digest.hexdigest()

    def _move(self, kind: str, source: str, destination: str) -> None:
        self._admission.require_root_owner()
        if kind == "deployment":
            self._root.rename_directory(source, destination)
        else:
            self._root.rename_file(source, destination)

    def _finalize_archive(self, index: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        if self._tree_digest(record["archive_path"]) != record["digest"]:
            raise ArchiveConflict("archive contents do not match the reviewed identity")
        self._transition_deployment_head(record, restore=False)
        operation_id = record.get("archive_operation_id")
        if operation_id is not None:
            record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | {operation_id})
        record["state"] = "archived"
        record["updated_at"] = _now()
        self._write_index(index)
        return dict(record)

    def _finalize_restore(self, index: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        if self._tree_digest(record["source_path"]) != record["digest"]:
            raise ArchiveConflict("restored contents do not match the reviewed identity")
        self._transition_deployment_head(record, restore=True)
        record["reconciled_operations"] = sorted(set(record.get("reconciled_operations", [])) | {record["restore_operation_id"]})
        record["state"] = "restored"
        record["updated_at"] = _now()
        self._write_index(index)
        return dict(record)

    def _transition_deployment_head(self, record: dict[str, Any], *, restore: bool) -> None:
        if record["kind"] != "deployment":
            return
        expected_heads = record.get("inventory_before")
        entry = record.get("ledger_entry")
        if not isinstance(expected_heads, dict) or not isinstance(entry, dict):
            raise ArchiveError("deployment inventory journal is unavailable")
        transition_ledger_inventory(
            self._root,
            record["identity"],
            expected_heads=expected_heads,
            expected_entry=None if restore else entry,
            new_entry=entry if restore else None,
            admission=self._admission,
        )

    def _read_index(self) -> dict[str, Any]:
        try:
            raw = self._root.read_bytes(ARCHIVE_INDEX)
        except FileNotFoundError:
            return {"schema": 1, "items": {}}
        if len(raw) > _MAX_INDEX_BYTES:
            raise ArchiveError("archive index exceeds its bound")
        try:
            index = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ArchiveError("archive index is malformed") from None
        if not isinstance(index, dict) or set(index) != {"schema", "items"} or index["schema"] != 1 or not isinstance(index["items"], dict) or len(index["items"]) > _MAX_ENTRIES:
            raise ArchiveError("archive index is malformed")
        for key, item in index["items"].items():
            if not _SAFE_ID.fullmatch(key) or not _valid_record(item, key):
                raise ArchiveError("archive index entry is malformed")
        return index

    def _write_index(self, index: dict[str, Any]) -> None:
        self._admission.require_root_owner()
        self._root.mkdir(ARCHIVE_ROOT, parents=True, mode=0o700)
        raw = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > _MAX_INDEX_BYTES:
            raise ArchiveError("archive index exceeds its bound")
        self._root.write_bytes(ARCHIVE_INDEX, raw, mode=0o600)

    def _exists(self, relative: str) -> bool:
        try:
            self._root.resolve(relative).lstat()
        except FileNotFoundError:
            return False
        return True

    def _require_absent(self, relative: str) -> None:
        if self._exists(relative):
            raise ArchiveConflict("archive destination collision")

    def _require_identity_absent(self, kind: str, identity: str) -> None:
        directory = {"template": "mandates", "deployment": "paper", "research": "research"}[kind]
        path = self._root.resolve(directory)
        if path.is_dir():
            for entry in path.iterdir():
                candidate = entry.stem if kind == "template" else entry.name
                if _resource_key(candidate) == _resource_key(identity):
                    raise ArchiveConflict("archive destination identity collision")


def _validate_identity(kind: object, identity: object) -> tuple[str, str]:
    if not isinstance(kind, str) or kind not in {"template", "deployment", "research"}:
        raise ArchiveError("archive scope is invalid")
    if not isinstance(identity, str) or not identity or len(identity) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in identity):
        raise ArchiveError("archive identity is invalid")
    if kind == "research":
        if not _REPORT_ID.fullmatch(identity):
            raise ArchiveError("research report identity is invalid")
        return str(kind), identity
    identity = _validate_lane_identity(identity)
    if identity[-1:] in {".", " "}:
        raise ArchiveError("fund identity is invalid")
    return str(kind), identity


def _validate_lane_identity(identity: object) -> str:
    if not isinstance(identity, str) or not identity or len(identity) > 64 or identity[-1:] in {".", " "}:
        raise ArchiveError("fund identity is invalid")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}", identity):
        raise ArchiveError("fund identity is invalid")
    try:
        ensure_unique_resource_name(identity, [])
    except RootPathError:
        raise ArchiveError("fund identity is invalid or protected") from None
    return identity


def _resource_key(value: str) -> str:
    return ensure_unique_resource_name(value, [])


def _validate_id(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ArchiveError("archive operation identity is invalid")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _valid_record(record: object, key: str) -> bool:
    basic = (
        isinstance(record, dict)
        and record.get("schema") == 1
        and record.get("archive_id") == key
        and record.get("kind") in {"template", "deployment", "research"}
        and record.get("state") in {"archive-prepared", "archived", "restore-prepared", "restored", "abandoned"}
        and isinstance(record.get("identity"), str)
        and isinstance(record.get("lane_identity"), str)
        and isinstance(record.get("source_path"), str)
        and isinstance(record.get("archive_path"), str)
        and _is_sha256(record.get("digest"))
        and isinstance(record.get("updated_at"), str)
        and (record.get("inventory_before") is None or isinstance(record.get("inventory_before"), dict))
        and (record.get("ledger_entry") is None or isinstance(record.get("ledger_entry"), dict))
        and (record.get("archive_operation_id") is None or isinstance(record["archive_operation_id"], str) and _SAFE_ID.fullmatch(record["archive_operation_id"]))
        and isinstance(record.get("reconciled_operations", []), list)
        and len(record.get("reconciled_operations", [])) <= _MAX_ENTRIES
        and all(isinstance(value, str) and _SAFE_ID.fullmatch(value) for value in record.get("reconciled_operations", []))
    )
    if not basic:
        return False
    try:
        kind, identity = _validate_identity(record["kind"], record["identity"])
        lane = _validate_lane_identity(record["lane_identity"])
        source = record["source_path"]
        if record["archive_path"] != f"{ARCHIVE_ROOT}/objects/{key}":
            return False
        if kind == "deployment":
            return source == f"paper/{identity}" and lane == identity
        if kind == "research":
            return source == f"research/{identity}" and identity.startswith(f"{lane}-")
        parts = source.split("/")
        return len(parts) == 2 and parts[0] == "mandates" and Path(parts[1]).suffix.casefold() in {".yaml", ".yml"} and _resource_key(Path(parts[1]).stem) == _resource_key(identity) and lane == identity
    except (ArchiveError, RootPathError, ValueError):
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
