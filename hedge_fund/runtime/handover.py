"""Offline root enrollment and ledger-head fencing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    LOCK_DIRECTORY,
    OWNER_LOCK_PATH,
    PROTOCOL_VERSION,
    RootMigrationLease,
    WriterConflict,
)
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootContext,
    RootPathError,
)

HANDOVER_PATH = f"{PRIVATE_ROOT}/handover.json"
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_INVENTORY_FUNDS = 10000
_MAX_LEDGER_SESSIONS = 1000000
OPERATOR_ATTESTATION = "I confirm every legacy writer and out-of-band writer is stopped and excluded " "from this root, and this ledger-head inventory is exact."


class HandoverError(RuntimeError):
    """Enrollment, compatibility or ledger inventory failed."""


class HandoverRequired(HandoverError):
    """Root has no verified offline enrollment."""


class EnrollmentInvalid(HandoverError):
    """Enrollment record is malformed or bound to another root/build."""


class LedgerDrift(HandoverError):
    """Current ledger state differs from its enrolled head."""


def root_binding(root: RootContext) -> dict[str, Any]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    root.revalidate()
    return {
        "path": os.path.normcase(os.path.abspath(os.fspath(root.path))),
        "identity": list(root._root_identity),
        "filesystem": root.filesystem.filesystem.casefold(),
        "device": root.device_identity,
        "host": root.host_identity.casefold(),
        "namespace": root.namespace_identity,
    }


def enrollment_status(root: RootContext, *, verify_inventory: bool = False) -> dict[str, str | None]:
    """Return read-only enrollment state without creating private paths."""
    from hedge_fund.paper.ledger import LedgerError

    try:
        root.file_info(HANDOVER_PATH)
    except FileNotFoundError:
        try:
            root.file_info(OWNER_LOCK_PATH)
        except FileNotFoundError:
            try:
                root.file_info(f"{PRIVATE_ROOT}/admission")
            except FileNotFoundError:
                return {"state": "unenrolled", "reason": "handover-required"}
            except Exception:
                return {"state": "invalid", "reason": "admission-state-unavailable"}
            return {"state": "invalid", "reason": "admission-state-without-handover"}
        except Exception:
            return {"state": "invalid", "reason": "admission-state-unavailable"}
        return {"state": "invalid", "reason": "admission-state-without-handover"}
    except Exception:
        return {"state": "invalid", "reason": "handover-unavailable"}
    try:
        record = require_enrollment(root)
        if verify_inventory:
            verify_root_inventory(root, record=record)
    except LedgerDrift:
        return {"state": "drift", "reason": "ledger-drift"}
    except LedgerError:
        return {"state": "drift", "reason": "ledger-drift"}
    except HandoverRequired:
        return {"state": "unenrolled", "reason": "handover-required"}
    except Exception:
        return {"state": "invalid", "reason": "handover-unavailable"}
    return {"state": "enrolled", "reason": None}


def require_enrollment(root: RootContext) -> dict[str, Any]:
    """Validate protocol, build and launch-fixed root identity."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not root.verify_private_storage():
        raise EnrollmentInvalid("private storage is not verified")
    try:
        info = root.file_info(HANDOVER_PATH)
    except FileNotFoundError:
        raise HandoverRequired("offline handover is required") from None
    except (OSError, RootPathError) as exc:
        raise EnrollmentInvalid("handover record is unavailable") from exc
    if info.size <= 0 or info.size > _MAX_RECORD_BYTES:
        raise EnrollmentInvalid("handover record size is invalid")
    try:
        record = json.loads(root.read_bytes(HANDOVER_PATH).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, RootPathError):
        raise EnrollmentInvalid("handover record is malformed") from None
    if not isinstance(record, dict):
        raise EnrollmentInvalid("handover record is malformed")
    expected_fields = {
        "schema",
        "protocol_version",
        "build_id",
        "mode",
        "root",
        "created_at",
        "attestation",
        "heads",
        "inventory_digest",
        "record_digest",
    }
    if set(record) != expected_fields:
        raise EnrollmentInvalid("handover record fields are invalid")
    if record["schema"] != 1 or record["protocol_version"] != PROTOCOL_VERSION:
        raise EnrollmentInvalid("handover protocol is incompatible")
    if record["build_id"] != code_version():
        raise EnrollmentInvalid("handover build is incompatible")
    if record["mode"] not in {"fresh", "migrate-existing"}:
        raise EnrollmentInvalid("handover mode is invalid")
    if record["root"] != root_binding(root):
        raise EnrollmentInvalid("handover root identity does not match")
    if not _valid_timestamp(record["created_at"]):
        raise EnrollmentInvalid("handover timestamp is invalid")
    if not isinstance(record["heads"], dict) or len(record["heads"]) > _MAX_INVENTORY_FUNDS:
        raise EnrollmentInvalid("handover head inventory is invalid")
    for key, entry in record["heads"].items():
        if not isinstance(key, str) or not _valid_inventory_entry(key, entry):
            raise EnrollmentInvalid("handover head inventory is invalid")
    expected_inventory_digest = _digest(record["heads"])
    if record["inventory_digest"] != expected_inventory_digest:
        raise EnrollmentInvalid("handover head inventory digest is invalid")
    record_body = {key: value for key, value in record.items() if key != "record_digest"}
    if record["record_digest"] != _digest(record_body):
        raise EnrollmentInvalid("handover record digest is invalid")
    if record["mode"] == "fresh" and record["attestation"] is not None:
        raise EnrollmentInvalid("fresh enrollment attestation is invalid")
    if record["mode"] == "migrate-existing":
        attestation = record["attestation"]
        if not isinstance(attestation, dict) or set(attestation) != {"statement", "inventory_digest"}:
            raise EnrollmentInvalid("migration attestation is invalid")
        if attestation["statement"] != OPERATOR_ATTESTATION or not isinstance(attestation["inventory_digest"], str) or not _SHA256.fullmatch(attestation["inventory_digest"]):
            raise EnrollmentInvalid("migration attestation is invalid")
    root.revalidate()
    return record


def enroll_fresh(root: RootContext) -> dict[str, Any]:
    """Enroll an empty root before any demo or production data is written."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    root.revalidate()
    if _record_exists(root):
        raise EnrollmentInvalid("root already has a handover record")
    if any(root.path.iterdir()):
        raise HandoverError("fresh enrollment requires an empty root")
    root.prepare_private_storage()
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            if not _fresh_bootstrap_only(root):
                raise HandoverError("root changed during fresh enrollment")
            heads = build_head_inventory(root)
            if heads:
                raise HandoverError("fresh enrollment found paper deployments")
            record = _new_record(root, mode="fresh", heads={}, attestation=None)
            _write_record(root, record)
            return require_enrollment(root)
    except WriterConflict as exc:
        raise HandoverError("another root participant is active") from exc


def migrate_existing(
    root: RootContext,
    *,
    expected_inventory_digest: str,
    operator_attestation: str,
) -> dict[str, Any]:
    """Enroll an existing root only after exact offline attestation and inventory."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not isinstance(expected_inventory_digest, str) or not _SHA256.fullmatch(expected_inventory_digest):
        raise HandoverError("head inventory digest is invalid")
    if operator_attestation != OPERATOR_ATTESTATION:
        raise HandoverError("explicit quiescent-writer attestation is required")
    root.revalidate()
    if _record_exists(root):
        raise EnrollmentInvalid("root already has a handover record")
    if not root.verify_private_storage():
        root.prepare_private_storage()
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            if _record_exists(root):
                raise EnrollmentInvalid("root already has a handover record")
            if _has_legacy_runner_pid(root.path):
                raise HandoverError("runner.pid is present; unknown owners block migration")
            heads = build_head_inventory(root)
            actual_digest = _digest(heads)
            if actual_digest != expected_inventory_digest:
                raise HandoverError("head inventory changed; inspect and retry offline")
            record = _new_record(
                root,
                mode="migrate-existing",
                heads=heads,
                attestation={
                    "statement": OPERATOR_ATTESTATION,
                    "inventory_digest": actual_digest,
                },
            )
            _write_record(root, record)
            return require_enrollment(root)
    except WriterConflict as exc:
        raise HandoverError("root participant is active; migration requires quiescence") from exc


def build_head_inventory(root: RootContext) -> dict[str, dict[str, Any]]:
    """Replay every deployed paper ledger and return canonical head identities."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    root.revalidate()
    paper = root.path / "paper"
    if _is_reparse_point(paper):
        raise HandoverError("paper inventory contains a reparse point")
    if not paper.exists():
        root.revalidate()
        return {}
    if not paper.is_dir():
        raise HandoverError("paper inventory is not a directory")
    from hedge_fund.paper.deployed import DeployedFund, FUND_FILE, load_deployed
    from hedge_fund.paper.ledger import Ledger

    inventory: dict[str, dict[str, Any]] = {}
    for directory in sorted(paper.iterdir(), key=lambda item: item.name.casefold()):
        if _is_reparse_point(directory):
            raise HandoverError("paper inventory contains a reparse point")
        if not directory.is_dir():
            raise HandoverError("paper inventory contains an unknown entry")
        if _has_legacy_runner_pid(directory):
            raise HandoverError("runner.pid is present; unknown owners block handover")
        fund_file = directory / FUND_FILE
        if not fund_file.is_file():
            if any(directory.iterdir()):
                raise HandoverError("paper inventory contains an incomplete deployment")
            continue
        try:
            deployed: DeployedFund = load_deployed(directory)
            key = ensure_unique_resource_name(deployed.name, [])
            if key != ensure_unique_resource_name(directory.name, []):
                raise HandoverError("paper deployment identity does not match its directory")
            ledger = Ledger(directory)
            sessions = ledger.sessions()
            if len(sessions) > _MAX_LEDGER_SESSIONS:
                raise HandoverError("paper ledger exceeds its inventory bound")
            state = ledger.replay(deployed.spec.capital, full=True)
            latest = ledger.latest()
            if state.last_session != (latest.session if latest is not None else None):
                raise HandoverError("paper ledger head is inconsistent")
            entry = {
                "name": deployed.name,
                "deployment_digest": hashlib.sha256(fund_file.read_bytes()).hexdigest(),
                "last_session": latest.session if latest is not None else None,
                "head_hash": latest.hash if latest is not None else None,
                "session_count": len(sessions),
            }
        except HandoverError:
            raise
        except (OSError, ValueError, RootPathError) as exc:
            raise HandoverError(f"paper inventory is invalid ({type(exc).__name__})") from None
        if key in inventory:
            raise HandoverError("paper inventory contains duplicate identities")
        inventory[key] = entry
    root.revalidate()
    return dict(sorted(inventory.items()))


def verify_root_inventory(
    root: RootContext,
    *,
    record: dict[str, Any] | None = None,
) -> None:
    expected = (record or require_enrollment(root))["heads"]
    actual = build_head_inventory(root)
    if actual != expected:
        raise LedgerDrift("paper ledger inventory differs from offline handover")


def verify_ledger_head(root: RootContext, name: str) -> dict[str, Any] | None:
    record = require_enrollment(root)
    key = _resource_key(name)
    expected = record["heads"].get(key)
    try:
        actual = build_head_inventory(root).get(key)
    except HandoverError as exc:
        raise LedgerDrift("paper ledger inventory cannot be verified") from exc
    if actual != expected:
        raise LedgerDrift("paper ledger head differs from offline handover")
    return actual


def record_ledger_head(
    root: RootContext,
    name: str,
    *,
    admission: AdmissionCoordinator,
) -> None:
    if not isinstance(admission, AdmissionCoordinator) or admission.root is not root:
        raise HandoverError("root admission is required")
    key = _resource_key(name)
    try:
        with admission.registry_lock(timeout=5.0):
            record = require_enrollment(root)
            heads = dict(record["heads"])
            actual = build_head_inventory(root).get(key)
            if actual is None:
                heads.pop(key, None)
            else:
                heads[key] = actual
            updated = _new_record(
                root,
                mode=record["mode"],
                heads=dict(sorted(heads.items())),
                attestation=record["attestation"],
                created_at=record["created_at"],
            )
            _write_record(root, updated)
    except AdmissionError as exc:
        raise HandoverError("ledger head inventory update is unavailable") from exc


def root_is_enrolled(root: RootContext) -> bool:
    try:
        root.file_info(HANDOVER_PATH)
    except FileNotFoundError:
        return False
    except (OSError, RootPathError):
        return True
    return True


def inventory_digest(heads: dict[str, dict[str, Any]]) -> str:
    if not isinstance(heads, dict):
        raise TypeError("head inventory must be a mapping")
    return _digest(heads)


def _new_record(
    root: RootContext,
    *,
    mode: str,
    heads: dict[str, dict[str, Any]],
    attestation: dict[str, str] | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    body = {
        "schema": 1,
        "protocol_version": PROTOCOL_VERSION,
        "build_id": code_version(),
        "mode": mode,
        "root": root_binding(root),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attestation": attestation,
        "heads": heads,
        "inventory_digest": _digest(heads),
    }
    return {**body, "record_digest": _digest(body)}


def _write_record(root: RootContext, record: dict[str, Any]) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > _MAX_RECORD_BYTES:
        raise HandoverError("handover record exceeds its storage bound")
    root.write_bytes(HANDOVER_PATH, payload, mode=stat.S_IRUSR | stat.S_IWUSR)


def _record_exists(root: RootContext) -> bool:
    try:
        root.file_info(HANDOVER_PATH)
    except FileNotFoundError:
        return False
    except (OSError, RootPathError) as exc:
        raise EnrollmentInvalid("handover path is unavailable") from exc
    return True


def _fresh_bootstrap_only(root: RootContext) -> bool:
    expected_dirs = {
        Path("runtime"),
        Path("runtime/private"),
        Path("runtime/private/v1"),
        Path("runtime/private/v1/admission"),
        Path("runtime/private/v1/admission/v1"),
    }
    expected_files = {
        Path(f"{LOCK_DIRECTORY}/owner.lock"),
    }
    observed_dirs: set[Path] = set()
    observed_files: set[Path] = set()
    for directory, subdirs, files in os.walk(root.path, followlinks=False):
        current = Path(directory)
        for name in list(subdirs):
            child = current / name
            if _is_reparse_point(child):
                return False
            observed_dirs.add(child.relative_to(root.path))
        for name in files:
            child = current / name
            if _is_reparse_point(child):
                return False
            observed_files.add(child.relative_to(root.path))
    return observed_dirs == expected_dirs and observed_files == expected_files


def _has_legacy_runner_pid(root: Path) -> bool:
    for directory, subdirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in list(subdirs):
            if _is_reparse_point(current / name):
                raise HandoverError("root inventory contains a reparse point")
        if "runner.pid" in files:
            return True
    return False


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _valid_inventory_entry(key: str, entry: object) -> bool:
    if not isinstance(entry, dict) or set(entry) != {
        "name",
        "deployment_digest",
        "last_session",
        "head_hash",
        "session_count",
    }:
        return False
    try:
        if ensure_unique_resource_name(entry["name"], []) != key:
            return False
    except (TypeError, RootPathError):
        return False
    if not isinstance(entry["deployment_digest"], str) or not _SHA256.fullmatch(entry["deployment_digest"]):
        return False
    if type(entry["session_count"]) is not int or not 0 <= entry["session_count"] <= _MAX_LEDGER_SESSIONS:
        return False
    session = entry["last_session"]
    head_hash = entry["head_hash"]
    if session is None:
        return head_hash is None and entry["session_count"] == 0
    return isinstance(session, str) and len(session) <= 32 and isinstance(head_hash, str) and _SHA256.fullmatch(head_hash) is not None and entry["session_count"] > 0


def _resource_key(name: str) -> str:
    try:
        return ensure_unique_resource_name(name, [])
    except (TypeError, RootPathError):
        raise HandoverError("paper deployment identity is invalid") from None


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
