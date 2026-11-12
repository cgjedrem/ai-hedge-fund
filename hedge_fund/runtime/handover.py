"""Offline root enrollment and ledger-head fencing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import threading
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, TypedDict, TypeVar

from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError, LOCK_DIRECTORY, MAX_LOCK_WAIT_SECONDS, OWNER_LOCK_PATH, PROTOCOL_VERSION, require_paper_write_lanes, RootMigrationLease, RootOwnerLease, WriterConflict
from hedge_fund.runtime.exclusion import out_of_band_exclusion_basis
from hedge_fund.runtime.exclusion import UNPROVEN_REASON as EXCLUSION_UNPROVEN_REASON
from hedge_fund.runtime.ownership import process_identity, process_is_running, ProcessIdentityError
from hedge_fund.runtime.root import _handover_resource_access, _relative_parts, _windows_current_user_sid, ensure_unique_resource_name, PRIVATE_ROOT, RootContext, RootPathError

HANDOVER_PATH = f"{PRIVATE_ROOT}/handover.json"
RECOVERY_ROOT = f"{PRIVATE_ROOT}/recoveries"
SINGLE_WRITER_STATE_PATH = f"{PRIVATE_ROOT}/single-writer.json"
SINGLE_WRITER_CHALLENGE_PATH = f"{PRIVATE_ROOT}/single-writer-review.json"
SOURCE_EVIDENCE_PATH = f"{PRIVATE_ROOT}/source-evidence.json"
RELOCATION_STATE_PATH = f"{PRIVATE_ROOT}/relocation-copy.json"
ATTESTATION_ROOT = f"{PRIVATE_ROOT}/attestations"
RETIRED_MARKER_ROOT = f"{ATTESTATION_ROOT}/retired-markers"
_SHA256 = re.compile(r"[a-f0-9]{64}")
_WINDOWS_SID = re.compile(r"S-\d(?:-\d+){1,15}", re.IGNORECASE | re.ASCII)
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_TRUST_RECORD_BYTES = 64 * 1024
_MAX_TRUST_REVIEW_AGE = timedelta(minutes=15)
_MAX_INVENTORY_FUNDS = 10000
_MAX_LEDGER_SESSIONS = 1000000
OPERATOR_ATTESTATION = "I confirm known participants are quiescent during this exact root inventory; migration remains read-only."
STALE_RECOVERY_ATTESTATION = "I confirm the runner owner is quiescent in this root namespace and I accept responsibility " "for excluding other programs while recording this recovery."
TRUSTED_SINGLE_WRITER_AUTHORITY = "operator-trusted-single-writer"
SINGLE_WRITER_RESPONSIBILITY_WARNING = "Operator responsibility: stop and exclude every other program that can reach this root. " "Cooperative locks do not fence unaware or malicious same-account writers."
_WRITABLE_AUTHORITIES = frozenset({"protocol-native", TRUSTED_SINGLE_WRITER_AUTHORITY})
_TRUST_REQUIRED_REASON = "operator-single-writer-acknowledgement-required"
_TRUST_INVALID_REASON = "operator-single-writer-acknowledgement-invalid"
_TRUST_REVOKED_REASON = "operator-single-writer-acknowledgement-revoked"
_TRUST_RUNTIME_SCOPE_CHANGED_REASON = "operator-single-writer-runtime-scope-changed"
_TRUST_RUNTIME_SCOPE_UNAVAILABLE_REASON = "operator-single-writer-runtime-scope-unavailable"
_MAX_RUNTIME_IDENTITY_COUNTER = 2**64 - 1


class HandoverError(RuntimeError):
    """Enrollment, compatibility or ledger inventory failed."""


class HandoverRequired(HandoverError):
    """Root has no verified offline enrollment."""


class EnrollmentInvalid(HandoverError):
    """Enrollment record is malformed or bound to another root/build."""


class LedgerDrift(HandoverError):
    """Current ledger state differs from its enrolled head."""


class LedgerInventoryCorrupt(LedgerDrift):
    """Paper replay cannot establish the ledger inventory."""


class LedgerHeadPublicationError(HandoverError):
    """A committed paper mutation could not publish its enrolled head."""


class InventoryObservationUnavailable(HandoverError):
    """A coordinated inventory observation could not obtain admission."""


class WriteAuthorityDenied(HandoverError):
    """Raised when a root cannot hold production write authority."""


PROTOCOL_NATIVE_MODES = frozenset({"fresh", "relocated"})
LEGACY_HOME_NAME = ".hedge-fund"
RELOCATED_TOP_LEVEL = ("mandates", "paper", "research")
RELOCATED_SETTINGS_PATH = f"{PRIVATE_ROOT}/settings.json"
_MAX_RELOCATION_FILES = 50000
_MAX_RELOCATION_FILE_BYTES = 256 * 1024 * 1024
_MAX_RELOCATION_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_PROTECTED_RESOURCE_NAMES = frozenset({"umbrella", "watchtower", "watchtower-weekly"})
_ATTESTATION_KINDS = frozenset({"stale-marker-retirement", "protected-fund-inclusion"})


_OBSERVATION_CONTEXT = threading.local()
_T = TypeVar("_T")


class _PaperObservationWindow:
    def __init__(self, root: RootContext) -> None:
        self._root_identity = root._root_identity
        self._owner_thread = threading.get_ident()
        self._condition = threading.Condition()
        self._accepting = True
        self._active = True
        self._borrowers: dict[int, int] = {}

    @contextmanager
    def borrow(self) -> Iterator[None]:
        thread = threading.get_ident()
        with self._condition:
            if not self._active or not self._accepting:
                raise InventoryObservationUnavailable("paper inventory observation window has closed")
            self._borrowers[thread] = self._borrowers.get(thread, 0) + 1
        try:
            yield
        finally:
            with self._condition:
                remaining = self._borrowers[thread] - 1
                if remaining:
                    self._borrowers[thread] = remaining
                else:
                    del self._borrowers[thread]
                self._condition.notify_all()

    def permits(self, root: RootContext) -> bool:
        with self._condition:
            return self._active and root._root_identity == self._root_identity and threading.get_ident() in self._borrowers

    def close_observations(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise InventoryObservationUnavailable("paper inventory observation owner changed")
        with self._condition:
            self._accepting = False
            while self._borrowers:
                self._condition.wait()
            self._active = False


def _current_paper_observation() -> _PaperObservationWindow | None:
    return getattr(_OBSERVATION_CONTEXT, "window", None)


def _paper_observation_authorized(root: RootContext) -> bool:
    window = _current_paper_observation()
    return window is not None and window.permits(root)


def _run_with_paper_observation(
    window: _PaperObservationWindow | None,
    callback: Callable[..., _T],
    *args: Any,
) -> _T:
    if window is None:
        return callback(*args)
    with window.borrow():
        previous = _current_paper_observation()
        _OBSERVATION_CONTEXT.window = window
        try:
            return callback(*args)
        finally:
            _OBSERVATION_CONTEXT.window = previous


class StaleReservationRecoveryRecord(TypedDict):
    schema: int
    protocol_version: int
    build_id: str
    root: dict[str, Any]
    fund: str
    inventory_digest: str
    prior_owner_identity: dict[str, Any]
    evidence: dict[str, str]
    operator_attestation: str
    recovered_at: str
    record_digest: str


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


def _runtime_scope_identity(root: RootContext) -> dict[str, Any]:
    """Return stable runtime scope for participating processes."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if sys.platform.startswith("linux"):
        try:
            pid1 = process_identity(1)
        except (OSError, ProcessIdentityError, ValueError) as exc:
            raise HandoverError("Linux PID 1 runtime identity is unavailable") from exc
        try:
            namespace = f"pid:{os.readlink('/proc/self/ns/pid')};mnt:{os.readlink('/proc/self/ns/mnt')}"
            pid_namespace = str(os.stat("/proc/self/ns/pid").st_ino)
        except OSError as exc:
            raise HandoverError("Linux runtime namespace identity is unavailable") from exc
        if not isinstance(pid1, dict):
            raise HandoverError("Linux runtime scope identity is incomplete")
        if type(pid1.get("pid")) is not int or pid1["pid"] != 1:
            raise HandoverError("Linux runtime scope identity is incomplete")
        required_fields = ("creation_time", "image", "host", "namespace")
        if any(not isinstance(pid1.get(key), str) or not pid1[key] for key in required_fields):
            raise HandoverError("Linux runtime scope identity is incomplete")
        if not _valid_runtime_identity_counter(pid1["creation_time"]):
            raise HandoverError("Linux runtime scope identity is incomplete")
        if not _valid_runtime_identity_counter(pid1["namespace"]):
            raise HandoverError("Linux runtime scope identity is incomplete")
        if pid1["namespace"] != pid_namespace or pid1["host"] != root.boot_identity or namespace != root.namespace_identity:
            raise HandoverError("Linux runtime scope identity is incomplete")
        return {
            "kind": "linux-pid1",
            "pid1": pid1,
            "namespace": namespace,
        }
    if os.name == "nt" or sys.platform.startswith("win"):
        try:
            machine = root.host_identity.strip()
            volume = root.device_identity.strip()
            operator_sid = _windows_current_user_sid()
        except (OSError, ValueError, AttributeError) as exc:
            raise HandoverError("Windows runtime scope identity is unavailable") from exc
        if not machine or machine.casefold() == "unknown" or not volume or not isinstance(operator_sid, str) or not _WINDOWS_SID.fullmatch(operator_sid):
            raise HandoverError("Windows runtime scope identity is incomplete")
        return {
            "kind": "windows-user-volume",
            "machine": machine.casefold(),
            "operator_sid": operator_sid.upper(),
            "volume": volume.casefold(),
        }
    raise HandoverError("runtime scope identity is unsupported")


def _valid_runtime_identity_counter(value: object) -> bool:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        return False
    if not 1 <= len(value) <= 20 or value[0] == "0":
        return False
    return int(value) <= _MAX_RUNTIME_IDENTITY_COUNTER


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
        require_enrollment(root)
        if verify_inventory:
            verify_root_inventory(root)
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
    if record["mode"] not in {"fresh", "migrate-existing", "relocated"}:
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
    if record["mode"] == "relocated":
        provenance = record["attestation"]
        if not isinstance(provenance, dict) or set(provenance) != {"source_inventory_digest", "source_content_digest"}:
            raise EnrollmentInvalid("relocation provenance is invalid")
        if any(not isinstance(provenance[key], str) or not _SHA256.fullmatch(provenance[key]) for key in provenance):
            raise EnrollmentInvalid("relocation provenance is invalid")
    try:
        _validate_enrollment_attestation_refs(root, record["heads"])
    except EnrollmentInvalid:
        raise
    except (HandoverError, OSError, RootPathError) as exc:
        raise EnrollmentInvalid("handover attestation inventory is invalid") from exc
    root.revalidate()
    return record


def write_authority(root: RootContext) -> dict[str, str | None]:
    """Classify production write authority; enrollment alone stays read-only."""
    try:
        record = require_enrollment(root)
    except HandoverRequired:
        return {"authority": "unavailable", "reason": "handover-required"}
    except Exception:
        return {"authority": "unavailable", "reason": "handover-unavailable"}
    return _classify_write_authority(root, record)


def has_write_authority(authority: object) -> bool:
    """Return whether a classified authority permits protocol writes."""
    return isinstance(authority, dict) and authority.get("authority") in _WRITABLE_AUTHORITIES


def require_write_authority(root: RootContext) -> dict[str, Any]:
    """Return the enrollment record only when current authority permits writes."""
    record = require_enrollment(root)
    authority = _classify_write_authority(root, record)
    if has_write_authority(authority):
        return record
    reason = authority["reason"] or "handover-unavailable"
    if reason == "attested-migration-read-only":
        message = "attested migration is read-only until trusted-single-writer acknowledgement"
    elif reason == _TRUST_REQUIRED_REASON:
        message = "explicit root-specific offline trusted-single-writer acknowledgement is required"
    elif reason == _TRUST_REVOKED_REASON:
        message = "trusted-single-writer acknowledgement was revoked"
    elif reason == _TRUST_INVALID_REASON:
        message = "trusted-single-writer acknowledgement is invalid"
    elif reason == _TRUST_RUNTIME_SCOPE_CHANGED_REASON:
        message = "trusted-single-writer authority belongs to another runtime; review and trust this runtime explicitly"
    elif reason == _TRUST_RUNTIME_SCOPE_UNAVAILABLE_REASON:
        message = "trusted-single-writer runtime identity is unavailable"
    elif reason == EXCLUSION_UNPROVEN_REASON:
        message = "synthetic test-owner basis is unavailable"
    else:
        message = f"root write authority is ownership-unknown ({reason})"
    raise WriteAuthorityDenied(message)


def _classify_write_authority(root: RootContext, enrollment: dict[str, Any]) -> dict[str, str | None]:
    reason = None
    try:
        reason = legacy_reachability_reason(root)
    except Exception:
        reason = "legacy-reachability-unverified"
    if reason is not None:
        return {"authority": "ownership-unknown", "reason": reason}
    if enrollment["mode"] in PROTOCOL_NATIVE_MODES and out_of_band_exclusion_basis(root) is not None:
        return {"authority": "protocol-native", "reason": None}
    try:
        state = _read_single_writer_state(root, enrollment)
    except FileNotFoundError:
        reason = "attested-migration-read-only" if enrollment["mode"] == "migrate-existing" else _TRUST_REQUIRED_REASON
        try:
            _runtime_scope_identity(root)
        except HandoverError:
            return {"authority": "ownership-unknown", "reason": _TRUST_RUNTIME_SCOPE_UNAVAILABLE_REASON}
        return {"authority": "ownership-unknown", "reason": reason}
    except Exception:
        return {"authority": "ownership-unknown", "reason": _TRUST_INVALID_REASON}
    if state["state"] == "revoked":
        return {"authority": "ownership-unknown", "reason": _TRUST_REVOKED_REASON}
    try:
        runtime_scope = _runtime_scope_identity(root)
    except HandoverError:
        return {"authority": "ownership-unknown", "reason": _TRUST_RUNTIME_SCOPE_UNAVAILABLE_REASON}
    if state["runtime_scope"] != runtime_scope:
        return {"authority": "ownership-unknown", "reason": _TRUST_RUNTIME_SCOPE_CHANGED_REASON}
    return {"authority": TRUSTED_SINGLE_WRITER_AUTHORITY, "reason": None}


def prepare_single_writer_acknowledgement(root: RootContext) -> dict[str, Any]:
    """Review current root state and issue one non-authorizing challenge."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            enrollment = require_enrollment(root)
            verify_root_inventory(root, record=enrollment)
            heads = build_head_inventory(root)
            digest = _digest(heads)
            authority = _classify_write_authority(root, enrollment)
            legacy_reason = legacy_reachability_reason(root)
            if has_write_authority(authority) or legacy_reason is not None:
                _remove_single_writer_challenge(root)
                return {
                    "heads": heads,
                    "inventory_digest": digest,
                    "write_authority": authority["authority"],
                    "reason": authority["reason"] or legacy_reason,
                    "operator_acknowledgement": None,
                    "review_expires_at": None,
                    "runtime_scope": None,
                }

            try:
                runtime_scope = _runtime_scope_identity(root)
            except HandoverError:
                return {
                    "heads": heads,
                    "inventory_digest": digest,
                    "write_authority": "ownership-unknown",
                    "reason": _TRUST_RUNTIME_SCOPE_UNAVAILABLE_REASON,
                    "operator_acknowledgement": None,
                    "review_expires_at": None,
                    "runtime_scope": None,
                }
            challenge_id = secrets.token_hex(16)
            reviewed_at = datetime.now(timezone.utc)
            body = {
                "schema": 2,
                "protocol_version": PROTOCOL_VERSION,
                "build_id": code_version(),
                "root": root_binding(root),
                "enrollment_identity": _enrollment_identity(enrollment),
                "runtime_scope": runtime_scope,
                "inventory_digest": digest,
                "challenge_id": challenge_id,
                "prior_authority_digest": _single_writer_state_digest(root),
                "reviewed_at": reviewed_at.isoformat(),
            }
            _write_single_writer_challenge(root, body)
            return {
                "heads": heads,
                "inventory_digest": digest,
                "write_authority": authority["authority"],
                "reason": authority["reason"],
                "operator_acknowledgement": _single_writer_acknowledgement(
                    root,
                    enrollment,
                    digest,
                    challenge_id,
                    runtime_scope,
                ),
                "review_expires_at": (reviewed_at + _MAX_TRUST_REVIEW_AGE).isoformat(),
                "runtime_scope": runtime_scope,
            }
    except WriterConflict as exc:
        raise HandoverError("another root participant is active; offline trust review requires quiescence") from exc


def trust_single_writer(
    root: RootContext,
    *,
    expected_inventory_digest: str,
    operator_acknowledgement: str,
) -> dict[str, str | None]:
    """Record exact root-specific operator trust after a fresh offline review."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not isinstance(expected_inventory_digest, str) or not _SHA256.fullmatch(expected_inventory_digest):
        raise HandoverError("reviewed inventory digest is invalid")
    if not isinstance(operator_acknowledgement, str) or not 1 <= len(operator_acknowledgement) <= 1024:
        raise HandoverError("explicit root-specific operator acknowledgement is required")
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            enrollment = require_enrollment(root)
            legacy_reason = legacy_reachability_reason(root)
            if legacy_reason is not None:
                _remove_single_writer_challenge(root)
                raise WriteAuthorityDenied(f"known or unverified legacy participant blocks trust ({legacy_reason})")
            runtime_scope = _runtime_scope_identity(root)
            verify_root_inventory(root, record=enrollment)
            heads = build_head_inventory(root)
            actual_digest = _digest(heads)
            if actual_digest != expected_inventory_digest:
                _remove_single_writer_challenge(root)
                raise LedgerDrift("reviewed inventory changed; inspect the root again")
            challenge = _read_single_writer_challenge(root, enrollment, runtime_scope)
            if challenge["inventory_digest"] != actual_digest:
                _remove_single_writer_challenge(root)
                raise LedgerDrift("reviewed inventory changed; inspect the root again")
            if challenge["prior_authority_digest"] != _single_writer_state_digest(root):
                _remove_single_writer_challenge(root)
                raise HandoverError("trust review is stale; inspect the root again")
            expected_acknowledgement = _single_writer_acknowledgement(
                root,
                enrollment,
                actual_digest,
                challenge["challenge_id"],
                runtime_scope,
            )
            if operator_acknowledgement != expected_acknowledgement:
                raise HandoverError("exact root-specific operator acknowledgement is required")

            _remove_single_writer_challenge(root)
            body = {
                "schema": 2,
                "state": "trusted",
                "protocol_version": PROTOCOL_VERSION,
                "build_id": code_version(),
                "root": root_binding(root),
                "enrollment_identity": _enrollment_identity(enrollment),
                "runtime_scope": runtime_scope,
                "reviewed_inventory_digest": actual_digest,
                "challenge_id": challenge["challenge_id"],
                "operator_acknowledgement": operator_acknowledgement,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_single_writer_state(root, body)
            authority = _classify_write_authority(root, enrollment)
            if authority["authority"] != TRUSTED_SINGLE_WRITER_AUTHORITY:
                raise WriteAuthorityDenied("trusted-single-writer authority could not be verified")
            return authority
    except WriterConflict as exc:
        raise HandoverError("another root participant is active; trust requires quiescence") from exc


def revoke_single_writer(root: RootContext) -> dict[str, str | None]:
    """Persist revocation before removing any pending trust review."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            enrollment = require_enrollment(root)
            body = {
                "schema": 1,
                "state": "revoked",
                "protocol_version": PROTOCOL_VERSION,
                "build_id": code_version(),
                "root": root_binding(root),
                "enrollment_identity": _enrollment_identity(enrollment),
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_single_writer_state(root, body)
            _remove_single_writer_challenge(root)
            return _classify_write_authority(root, enrollment)
    except WriterConflict as exc:
        raise HandoverError("another root participant is active; revocation requires quiescence") from exc


def _read_single_writer_state(root: RootContext, enrollment: dict[str, Any]) -> dict[str, Any]:
    record = _read_private_json(root, SINGLE_WRITER_STATE_PATH)
    state = record.get("state")
    if state == "trusted":
        schema = 2
        expected_fields = {
            "schema",
            "state",
            "protocol_version",
            "build_id",
            "root",
            "enrollment_identity",
            "runtime_scope",
            "reviewed_inventory_digest",
            "challenge_id",
            "operator_acknowledgement",
            "acknowledged_at",
            "record_digest",
        }
        timestamp = record.get("acknowledged_at")
    elif state == "revoked":
        schema = 1
        expected_fields = {
            "schema",
            "state",
            "protocol_version",
            "build_id",
            "root",
            "enrollment_identity",
            "revoked_at",
            "record_digest",
        }
        timestamp = record.get("revoked_at")
    else:
        raise HandoverError("single-writer state is invalid")
    if set(record) != expected_fields:
        raise HandoverError("single-writer state fields are invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    if type(record["schema"]) is not int or record["schema"] != schema or record["protocol_version"] != PROTOCOL_VERSION or record["build_id"] != code_version() or record["root"] != root_binding(root) or record["enrollment_identity"] != _enrollment_identity(enrollment) or not _valid_timestamp(timestamp) or record["record_digest"] != _digest(body):
        raise HandoverError("single-writer state identity is invalid")
    if state == "trusted":
        reviewed_digest = record["reviewed_inventory_digest"]
        challenge_id = record["challenge_id"]
        acknowledgement = record["operator_acknowledgement"]
        runtime_scope = record["runtime_scope"]
        if not isinstance(runtime_scope, dict) or not isinstance(reviewed_digest, str) or not _SHA256.fullmatch(reviewed_digest) or not _valid_challenge_id(challenge_id) or not isinstance(acknowledgement, str) or not 1 <= len(acknowledgement) <= 1024 or acknowledgement != _single_writer_acknowledgement(root, enrollment, reviewed_digest, challenge_id, runtime_scope):
            raise HandoverError("single-writer acknowledgement is invalid")
    return record


def _read_single_writer_challenge(
    root: RootContext,
    enrollment: dict[str, Any],
    runtime_scope: dict[str, Any],
) -> dict[str, Any]:
    try:
        record = _read_private_json(root, SINGLE_WRITER_CHALLENGE_PATH)
    except FileNotFoundError:
        raise HandoverError("trust review challenge is missing; inspect the root again") from None
    expected_fields = {
        "schema",
        "protocol_version",
        "build_id",
        "root",
        "enrollment_identity",
        "runtime_scope",
        "inventory_digest",
        "challenge_id",
        "prior_authority_digest",
        "reviewed_at",
        "challenge_digest",
    }
    body = {key: value for key, value in record.items() if key != "challenge_digest"}
    if (
        set(record) != expected_fields
        or type(record["schema"]) is not int
        or record["schema"] != 2
        or record["protocol_version"] != PROTOCOL_VERSION
        or record["build_id"] != code_version()
        or record["root"] != root_binding(root)
        or record["enrollment_identity"] != _enrollment_identity(enrollment)
        or not isinstance(record["runtime_scope"], dict)
        or not isinstance(record["inventory_digest"], str)
        or not _SHA256.fullmatch(record["inventory_digest"])
        or not _valid_challenge_id(record["challenge_id"])
        or not isinstance(record["prior_authority_digest"], str)
        or not _SHA256.fullmatch(record["prior_authority_digest"])
        or not _valid_timestamp(record["reviewed_at"])
        or record["challenge_digest"] != _digest(body)
    ):
        raise HandoverError("single-writer review challenge is invalid")
    if record["runtime_scope"] != runtime_scope:
        raise HandoverError("trust review challenge belongs to another runtime; inspect the root again")
    reviewed_at = datetime.fromisoformat(record["reviewed_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
    review_age = (datetime.now(timezone.utc) - reviewed_at).total_seconds()
    if not 0 <= review_age <= _MAX_TRUST_REVIEW_AGE.total_seconds():
        raise HandoverError("trust review expired or is stale; inspect the root again")
    return record


def _read_private_json(root: RootContext, relative: str) -> dict[str, Any]:
    info = root.file_info(relative)
    if info.size <= 0 or info.size > _MAX_TRUST_RECORD_BYTES:
        raise HandoverError("single-writer record size is invalid")
    try:
        record = json.loads(root.read_bytes(relative).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, RootPathError):
        raise HandoverError("single-writer record is malformed") from None
    if not isinstance(record, dict):
        raise HandoverError("single-writer record is malformed")
    return record


def _write_single_writer_state(root: RootContext, record: dict[str, Any]) -> None:
    body = dict(record)
    body["record_digest"] = _digest(record)
    _write_private_json(root, SINGLE_WRITER_STATE_PATH, body)


def _write_single_writer_challenge(root: RootContext, record: dict[str, Any]) -> None:
    body = dict(record)
    body["challenge_digest"] = _digest(record)
    _write_private_json(root, SINGLE_WRITER_CHALLENGE_PATH, body)


def _write_private_json(root: RootContext, relative: str, record: dict[str, Any]) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > _MAX_TRUST_RECORD_BYTES:
        raise HandoverError("single-writer record exceeds its storage bound")
    root.write_bytes(relative, payload, mode=stat.S_IRUSR | stat.S_IWUSR)


def _attestation_path(kind: str, subject: str) -> str:
    if not isinstance(kind, str) or kind not in _ATTESTATION_KINDS or not isinstance(subject, str) or not subject:
        raise HandoverError("attestation identity is invalid")
    key = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return f"{ATTESTATION_ROOT}/{kind}/{key}.json"


def _new_attestation_artifact(
    root: RootContext,
    *,
    kind: str,
    subject: str,
    evidence: dict[str, Any],
    source_evidence_digest: str,
    operator_statement: str,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not isinstance(kind, str) or kind not in _ATTESTATION_KINDS:
        raise HandoverError("attestation kind is invalid")
    if not isinstance(subject, str) or not subject or not isinstance(evidence, dict):
        raise HandoverError("attestation subject or evidence is invalid")
    if not isinstance(source_evidence_digest, str) or not _SHA256.fullmatch(source_evidence_digest):
        raise HandoverError("attestation source evidence digest is invalid")
    if not isinstance(operator_statement, str) or not operator_statement.strip() or len(operator_statement) > 1024:
        raise HandoverError("attestation operator statement is invalid")
    body = {
        "schema": 1,
        "kind": kind,
        "subject": subject,
        "evidence": evidence,
        "source_evidence_digest": source_evidence_digest,
        "operator_statement": operator_statement,
        "recorded_at": recorded_at if recorded_at is not None else datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "root_binding": root_binding(root),
    }
    try:
        record = {**body, "record_digest": _digest(body)}
    except (TypeError, ValueError, OverflowError):
        raise HandoverError("attestation artifact is not serializable") from None
    _validate_attestation_artifact(root, record)
    return record


def _validate_attestation_artifact(
    root: RootContext,
    record: object,
    *,
    kind: str | None = None,
    subject: str | None = None,
    source_evidence_digest: str | None = None,
) -> dict[str, Any]:
    expected_fields = {
        "schema",
        "kind",
        "subject",
        "evidence",
        "source_evidence_digest",
        "operator_statement",
        "recorded_at",
        "root_binding",
        "record_digest",
    }
    if not isinstance(root, RootContext) or not isinstance(record, dict) or set(record) != expected_fields:
        raise HandoverError("attestation artifact fields are invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    statement = record["operator_statement"]
    try:
        expected_digest = _digest(body)
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise HandoverError("attestation artifact is not serializable") from None
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or not isinstance(record["kind"], str)
        or record["kind"] not in _ATTESTATION_KINDS
        or (kind is not None and record["kind"] != kind)
        or not isinstance(record["subject"], str)
        or not record["subject"]
        or len(record["subject"]) > 4096
        or not isinstance(record["evidence"], dict)
        or not isinstance(record["source_evidence_digest"], str)
        or not _SHA256.fullmatch(record["source_evidence_digest"])
        or (source_evidence_digest is not None and record["source_evidence_digest"] != source_evidence_digest)
        or not isinstance(statement, str)
        or not statement.strip()
        or len(statement) > 1024
        or any(ord(char) < 32 and char not in "\t\n\r" for char in statement)
        or not _valid_timestamp(record["recorded_at"])
        or record["root_binding"] != root_binding(root)
        or (subject is not None and record["subject"] != subject)
        or record["record_digest"] != expected_digest
    ):
        raise HandoverError("attestation artifact identity is invalid")
    if len(payload) > _MAX_TRUST_RECORD_BYTES:
        raise HandoverError("attestation artifact exceeds its storage bound")
    return record


def _read_attestation_artifact(
    root: RootContext,
    *,
    kind: str,
    subject: str,
) -> dict[str, Any] | None:
    path = _attestation_path(kind, subject)
    try:
        record = _read_private_json(root, path)
    except FileNotFoundError:
        return None
    return _validate_attestation_artifact(root, record, kind=kind, subject=subject)


def inspect_attestation_state(root: RootContext) -> dict[str, Any]:
    """Return verified destination attestations and unresolved source blockers."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    artifacts = _list_attestation_artifacts(root)
    relocation_state = _read_relocation_state(root)
    source_binding = relocation_state["source_root_binding"] if relocation_state is not None else None
    source_evidence = _read_source_evidence_bundle(root, source_binding=source_binding)
    source_digest = source_evidence["record_digest"] if source_evidence is not None else None
    if source_evidence is not None:
        blockers = source_evidence["blockers"]
    else:
        entries = _relocation_entries(root)
        blockers = _source_evidence_blockers(root, entries)

    remaining = []
    for blocker in blockers:
        matching = [artifact for artifact in artifacts if artifact["kind"] == blocker["kind"] and artifact["subject"] == blocker["subject"] and artifact["source_evidence_digest"] == source_digest]
        if source_digest is not None and len(matching) == 1 and _attestation_resolves_blocker(root, matching[0], blocker, source_evidence):
            continue
        if source_digest is None:
            command = "handover inspect-source"
            arguments = ["--evidence-out", f"<destination>/{SOURCE_EVIDENCE_PATH}"]
            state = "source-evidence-required"
        elif blocker["kind"] == "stale-marker-retirement":
            command = "handover attest-stale-marker"
            arguments = [
                "--marker",
                blocker["subject"],
                "--source-evidence",
                source_digest,
                "--operator-statement",
                "<operator statement>",
            ]
            state = "attestation-required"
        else:
            command = "handover attest-protected-fund"
            arguments = [
                "--fund",
                blocker["subject"],
                "--source-evidence",
                source_digest,
                "--operator-statement",
                "<operator statement>",
            ]
            state = "attestation-required"
        remaining.append(
            {
                **blocker,
                "source_evidence_digest": source_digest,
                "state": state,
                "resolving_subcommand": command,
                "resolving_arguments": arguments,
            }
        )
    remaining.sort(key=lambda item: (item["kind"], item["subject"].casefold()))
    return {
        "source_evidence_digest": source_digest,
        "attestation_artifacts": artifacts,
        "remaining_blockers": remaining,
    }


def _attestation_resolves_blocker(
    root: RootContext,
    artifact: dict[str, Any],
    blocker: dict[str, Any],
    source_evidence: dict[str, Any],
) -> bool:
    if artifact["source_evidence_digest"] != source_evidence["record_digest"] or artifact["kind"] != blocker["kind"] or artifact["subject"] != blocker["subject"]:
        return False
    try:
        if artifact["kind"] == "protected-fund-inclusion":
            if artifact["evidence"] != blocker["evidence"]:
                return False
            _validate_protected_fund_artifact(root, artifact, source_evidence=source_evidence)
        else:
            _validate_marker_retirement_artifact(root, artifact, source_evidence=source_evidence)
    except HandoverError:
        return False
    return True


def _list_attestation_artifacts(root: RootContext) -> list[dict[str, Any]]:
    if not root.verify_private_storage():
        return []
    base = root.path.joinpath(*Path(ATTESTATION_ROOT).parts)
    try:
        if _is_reparse_point(base) or not stat.S_ISDIR(base.lstat().st_mode):
            raise HandoverError("attestation storage is not a regular directory")
    except FileNotFoundError:
        return []
    artifacts = []
    allowed_root_entries = _ATTESTATION_KINDS | {"retired-markers"}
    try:
        with os.scandir(base) as entries:
            kind_dirs = []
            for entry in entries:
                if entry.name not in allowed_root_entries or not entry.is_dir(follow_symlinks=False):
                    raise HandoverError("attestation storage contains an unknown entry")
                if entry.name in _ATTESTATION_KINDS:
                    kind_dirs.append(entry.name)
    except OSError as exc:
        raise HandoverError(f"attestation storage is unavailable ({type(exc).__name__})") from None
    for kind in sorted(kind_dirs):
        directory = base / kind
        if _is_reparse_point(directory):
            raise HandoverError("attestation storage contains a reparse point")
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
                        raise HandoverError("attestation storage contains an invalid artifact entry")
                    relative = f"{ATTESTATION_ROOT}/{kind}/{entry.name}"
                    try:
                        info = root.file_info(relative)
                        if info.size <= 0 or info.size > _MAX_TRUST_RECORD_BYTES:
                            raise HandoverError("attestation artifact size is invalid")
                        data = root.read_bytes(relative)
                        if len(data) != info.size:
                            raise HandoverError("attestation artifact changed during inspection")
                        record = json.loads(data.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise HandoverError("attestation artifact is malformed") from None
                    artifact = _validate_attestation_artifact(root, record, kind=kind)
                    if _attestation_path(kind, artifact["subject"]) != relative:
                        raise HandoverError("attestation artifact path does not match its identity")
                    artifacts.append(artifact)
                    if len(artifacts) > _MAX_INVENTORY_FUNDS * 2:
                        raise HandoverError("attestation inventory exceeds its bound")
        except OSError as exc:
            raise HandoverError(f"attestation storage is unavailable ({type(exc).__name__})") from None
    _validate_retired_marker_storage(root, artifacts)
    root.revalidate()
    return sorted(artifacts, key=lambda item: (item["kind"], item["subject"].casefold()))


def _write_attestation_artifact(root: RootContext, record: dict[str, Any]) -> str:
    validated = _validate_attestation_artifact(root, record)
    if not root.verify_private_storage():
        raise HandoverError("destination private storage is not verified")
    relative = _attestation_path(validated["kind"], validated["subject"])
    try:
        root.file_info(relative)
    except FileNotFoundError:
        pass
    else:
        raise HandoverError("attestation already exists; inspect the destination root")
    directory = relative.rsplit("/", 1)[0]
    root.mkdir(directory, parents=True, mode=0o700)
    _write_private_json(root, relative, validated)
    return relative


def attest_stale_marker(
    root: RootContext,
    *,
    marker: str,
    source_evidence_digest: str,
    operator_statement: str,
) -> dict[str, Any]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not isinstance(marker, str):
        raise HandoverError("marker path is invalid")
    try:
        parts = _relative_parts(marker, allow_protected=True)
    except RootPathError as exc:
        raise HandoverError("marker path is invalid") from exc
    if "/".join(parts) != marker or parts[0] not in RELOCATED_TOP_LEVEL or parts[-1] != "runner.pid":
        raise HandoverError("marker path must name a copied runner.pid file")
    if not isinstance(source_evidence_digest, str) or not _SHA256.fullmatch(source_evidence_digest):
        raise HandoverError("source evidence digest is invalid")
    if not isinstance(operator_statement, str) or not operator_statement.strip() or len(operator_statement) > 1024:
        raise HandoverError("attestation operator statement is invalid")
    root.revalidate()
    if not root.verify_private_storage():
        raise HandoverError("destination private storage is not verified")

    try:
        with RootMigrationLease.acquire(root, timeout=0):
            state, source_evidence = _require_attestation_destination(root, source_evidence_digest)
            blocker = _source_evidence_blocker(source_evidence, "stale-marker-retirement", marker)
            existing = _read_attestation_artifact(root, kind="stale-marker-retirement", subject=marker)
            if existing is not None:
                _validate_marker_retirement_artifact(root, existing, source_evidence=source_evidence)
                raise HandoverError(f"marker attestation already exists at {_attestation_path('stale-marker-retirement', marker)}")

            try:
                retired_info = root.file_info(_retired_marker_path(marker))
            except FileNotFoundError:
                retired_info = None
            if retired_info is not None:
                raise HandoverError("retired marker exists without a valid attestation artifact; destination needs offline recovery")

            entries = _relocation_entries(root)
            if marker not in entries:
                raise HandoverError("destination marker is missing; inspect the copied root before retrying")
            _validate_marker_source_evidence(blocker)
            marker_bytes = _read_destination_marker(root, marker, blocker["evidence"])
            liveness = _require_marker_process_stopped(blocker["evidence"]["pid"])
            _validate_relocation_entries_with_retired_markers(root, state, source_evidence, entries=entries)

            retired_path = _retired_marker_path(marker)
            evidence = {
                **blocker["evidence"],
                "liveness": liveness,
                "retired_marker_path": retired_path,
            }
            record = _new_attestation_artifact(
                root,
                kind="stale-marker-retirement",
                subject=marker,
                evidence=evidence,
                source_evidence_digest=source_evidence["record_digest"],
                operator_statement=operator_statement,
            )
            _require_marker_process_stopped(blocker["evidence"]["pid"])
            try:
                root.file_info(retired_path)
            except FileNotFoundError:
                pass
            else:
                raise HandoverError("retired marker path already exists; destination needs offline recovery")

            root.mkdir(RETIRED_MARKER_ROOT, parents=True, mode=0o700)
            marker_moved = False
            try:
                with _handover_resource_access(root, allow_writes=True, allow_unattested_protected_writes=True):
                    root.rename_file(marker, retired_path)
                marker_moved = True
                retired_bytes = root.read_bytes(retired_path)
                if retired_bytes != marker_bytes or hashlib.sha256(retired_bytes).hexdigest() != blocker["evidence"]["sha256"]:
                    raise HandoverError("retired marker bytes differ from reviewed source evidence")
                artifact_path = _write_attestation_artifact(root, record)
                _validate_marker_retirement_artifact(root, record, source_evidence=source_evidence)
            except BaseException as exc:
                artifact_path = _attestation_path("stale-marker-retirement", marker)
                rollback_errors = []
                try:
                    root.file_info(artifact_path)
                except FileNotFoundError:
                    pass
                else:
                    try:
                        root.unlink_file(artifact_path)
                    except BaseException as rollback_error:
                        rollback_errors.append(rollback_error)
                if marker_moved:
                    try:
                        with _handover_resource_access(root, allow_writes=True, allow_unattested_protected_writes=True):
                            root.rename_file(retired_path, marker)
                    except BaseException as rollback_error:
                        rollback_errors.append(rollback_error)
                if rollback_errors:
                    raise HandoverError("marker attestation failed and destination rollback is incomplete") from exc
                raise
            return {
                "state": "attested",
                "kind": record["kind"],
                "subject": marker,
                "source_evidence_digest": record["source_evidence_digest"],
                "artifact_path": artifact_path,
            }
    except WriterConflict as exc:
        raise HandoverError("another destination participant is active") from exc


def attest_protected_fund(
    root: RootContext,
    *,
    fund: str,
    source_evidence_digest: str,
    operator_statement: str,
) -> dict[str, Any]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if not isinstance(fund, str) or fund not in _PROTECTED_RESOURCE_NAMES:
        raise HandoverError("fund name must match a protected original identity")
    if not isinstance(source_evidence_digest, str) or not _SHA256.fullmatch(source_evidence_digest):
        raise HandoverError("source evidence digest is invalid")
    if not isinstance(operator_statement, str) or not operator_statement.strip() or len(operator_statement) > 1024:
        raise HandoverError("attestation operator statement is invalid")
    root.revalidate()
    if not root.verify_private_storage():
        raise HandoverError("destination private storage is not verified")

    try:
        with RootMigrationLease.acquire(root, timeout=0):
            state, source_evidence = _require_attestation_destination(root, source_evidence_digest)
            blocker = _source_evidence_blocker(source_evidence, "protected-fund-inclusion", fund)
            _validate_protected_fund_source_evidence(fund, blocker)
            existing = _read_attestation_artifact(root, kind="protected-fund-inclusion", subject=fund)
            if existing is not None:
                _validate_protected_fund_artifact(root, existing, source_evidence=source_evidence)
                raise HandoverError(f"protected-fund attestation already exists at {_attestation_path('protected-fund-inclusion', fund)}")

            evidence = blocker["evidence"]
            _validate_destination_protected_fund(root, fund, evidence)
            _validate_relocation_entries_with_retired_markers(root, state, source_evidence)
            record = _new_attestation_artifact(
                root,
                kind="protected-fund-inclusion",
                subject=fund,
                evidence=evidence,
                source_evidence_digest=source_evidence["record_digest"],
                operator_statement=operator_statement,
            )
            artifact_path = _write_attestation_artifact(root, record)
            _validate_protected_fund_artifact(root, record, source_evidence=source_evidence)
            return {
                "state": "attested",
                "kind": record["kind"],
                "subject": fund,
                "source_evidence_digest": record["source_evidence_digest"],
                "artifact_path": artifact_path,
            }
    except WriterConflict as exc:
        raise HandoverError("another destination participant is active") from exc


def _validate_protected_fund_source_evidence(fund: str, blocker: dict[str, Any]) -> None:
    evidence = blocker["evidence"]
    if set(evidence) != {"directory", "fund_file_sha256", "fund_file_size"} or evidence["directory"] != f"paper/{fund}" or not isinstance(evidence["fund_file_sha256"], str) or not _SHA256.fullmatch(evidence["fund_file_sha256"]) or type(evidence["fund_file_size"]) is not int or evidence["fund_file_size"] < 0:
        raise HandoverError("protected-fund source evidence is invalid")


def _validate_destination_protected_fund(root: RootContext, fund: str, evidence: dict[str, Any]) -> None:
    from hedge_fund.paper.deployed import FUND_FILE, load_deployed

    relative = f"paper/{fund}/{FUND_FILE}"
    try:
        with _handover_resource_access(root):
            info = root.file_info(relative)
            data = root.read_bytes(relative)
        deployed = load_deployed(root.path / "paper" / fund)
    except FileNotFoundError:
        raise HandoverError("protected fund original name is missing from the destination copy") from None
    except (OSError, ValueError, RootPathError) as exc:
        raise HandoverError(f"protected fund destination is unreadable ({type(exc).__name__})") from None
    if deployed.name != fund or info.size != evidence["fund_file_size"] or len(data) != info.size or hashlib.sha256(data).hexdigest() != evidence["fund_file_sha256"]:
        raise HandoverError("protected fund identity or file differs from source evidence")


def _validate_protected_fund_artifact(
    root: RootContext,
    record: dict[str, Any],
    *,
    source_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = _validate_attestation_artifact(root, record, kind="protected-fund-inclusion")
    if artifact["subject"] not in _PROTECTED_RESOURCE_NAMES:
        raise HandoverError("protected-fund attestation subject is invalid")
    evidence = artifact["evidence"]
    if set(evidence) != {"directory", "fund_file_sha256", "fund_file_size"} or evidence.get("directory") != f"paper/{artifact['subject']}" or not isinstance(evidence.get("fund_file_sha256"), str) or not _SHA256.fullmatch(evidence["fund_file_sha256"]) or type(evidence.get("fund_file_size")) is not int or evidence["fund_file_size"] < 0:
        raise HandoverError("protected-fund attestation evidence is invalid")
    if source_evidence is not None:
        blocker = _source_evidence_blocker(source_evidence, "protected-fund-inclusion", artifact["subject"])
        _validate_protected_fund_source_evidence(artifact["subject"], blocker)
        if artifact["source_evidence_digest"] != source_evidence["record_digest"] or evidence != blocker["evidence"]:
            raise HandoverError("protected-fund attestation does not match source evidence")
    _validate_destination_protected_fund(root, artifact["subject"], evidence)
    return artifact


def protected_fund_is_authorized(root: RootContext, fund: str) -> bool:
    if not isinstance(root, RootContext) or not isinstance(fund, str) or fund not in _PROTECTED_RESOURCE_NAMES:
        return False
    try:
        state = _read_relocation_state(root)
        if state is None or state["state"] != "copied" or not root.verify_private_storage():
            return False
        source_evidence = _read_source_evidence_bundle(root, source_binding=state["source_root_binding"])
        if not _source_evidence_matches_relocation_state(source_evidence, state):
            return False
        artifact = _read_attestation_artifact(root, kind="protected-fund-inclusion", subject=fund)
        if artifact is None:
            return False
        _validate_protected_fund_artifact(root, artifact, source_evidence=source_evidence)
        return True
    except Exception:
        return False


def _require_attestation_destination(root: RootContext, source_evidence_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if _record_exists(root):
        raise HandoverError("attestations require an unenrolled copied destination")
    state = _read_relocation_state(root)
    if state is None or state["state"] != "copied":
        raise HandoverError("attestations require a completed relocate-copy")
    source_evidence = _read_source_evidence_bundle(root, source_binding=state["source_root_binding"])
    if not _source_evidence_matches_relocation_state(source_evidence, state):
        raise HandoverError("source evidence is missing or differs from the copied destination")
    if source_evidence_digest != source_evidence["record_digest"]:
        raise HandoverError("source evidence digest mismatch; inspect-source and retry with the destination bundle digest")
    return state, source_evidence


def _source_evidence_blocker(source_evidence: dict[str, Any], kind: str, subject: str) -> dict[str, Any]:
    matches = [item for item in source_evidence["blockers"] if item["kind"] == kind and item["subject"] == subject]
    if len(matches) != 1:
        raise HandoverError("source evidence does not contain one matching attestation blocker")
    return matches[0]


def _validate_marker_source_evidence(blocker: dict[str, Any]) -> None:
    evidence = blocker["evidence"]
    if set(evidence) != {"content_class", "pid", "sha256", "size"} or evidence["content_class"] != "pid" or type(evidence["pid"]) is not int or evidence["pid"] <= 0 or not isinstance(evidence["sha256"], str) or not _SHA256.fullmatch(evidence["sha256"]) or type(evidence["size"]) is not int or evidence["size"] < 0:
        raise HandoverError("source marker evidence has no verifiable process identity")


def _read_destination_marker(root: RootContext, marker: str, evidence: dict[str, Any]) -> bytes:
    try:
        with _handover_resource_access(root):
            info = root.file_info(marker)
            data = root.read_bytes(marker)
    except FileNotFoundError:
        raise HandoverError("destination marker is missing; no attestation was recorded") from None
    except (OSError, RootPathError) as exc:
        raise HandoverError(f"destination marker is unreadable ({type(exc).__name__})") from None
    if info.size != evidence["size"] or len(data) != info.size or hashlib.sha256(data).hexdigest() != evidence["sha256"]:
        raise HandoverError("destination marker differs from source evidence; inspect-source and relocate-copy again")
    return data


def _require_marker_process_stopped(pid: int) -> dict[str, Any]:
    try:
        running = process_is_running(pid)
    except (OSError, ProcessIdentityError, ValueError):
        raise HandoverError("marker process liveness cannot be verified; marker remains unchanged") from None
    if type(running) is not bool:
        raise HandoverError("marker process liveness cannot be verified; marker remains unchanged")
    if running:
        raise HandoverError("marker identifies a live process; destination marker remains unchanged")
    return {
        "status": "not-running",
        "method": "native-process-identity",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }


def _retired_marker_path(subject: str) -> str:
    return f"{RETIRED_MARKER_ROOT}/{hashlib.sha256(subject.encode('utf-8')).hexdigest()}.marker"


def _validate_marker_retirement_artifact(
    root: RootContext,
    record: dict[str, Any],
    *,
    source_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = _validate_attestation_artifact(root, record, kind="stale-marker-retirement")
    evidence = artifact["evidence"]
    liveness = evidence.get("liveness") if isinstance(evidence, dict) else None
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"content_class", "pid", "sha256", "size", "liveness", "retired_marker_path"}
        or evidence.get("content_class") != "pid"
        or type(evidence.get("pid")) is not int
        or evidence["pid"] <= 0
        or not isinstance(evidence.get("sha256"), str)
        or not _SHA256.fullmatch(evidence["sha256"])
        or type(evidence.get("size")) is not int
        or evidence["size"] < 0
        or not isinstance(liveness, dict)
        or set(liveness) != {"status", "method", "checked_at"}
        or liveness.get("status") != "not-running"
        or liveness.get("method") != "native-process-identity"
        or not _valid_timestamp(liveness.get("checked_at"))
        or evidence.get("retired_marker_path") != _retired_marker_path(artifact["subject"])
    ):
        raise HandoverError("stale-marker attestation evidence is invalid")
    if source_evidence is not None:
        blocker = _source_evidence_blocker(source_evidence, "stale-marker-retirement", artifact["subject"])
        _validate_marker_source_evidence(blocker)
        if artifact["source_evidence_digest"] != source_evidence["record_digest"] or any(evidence[key] != value for key, value in blocker["evidence"].items()):
            raise HandoverError("stale-marker attestation does not match source evidence")

    retired_path = evidence["retired_marker_path"]
    try:
        info = root.file_info(retired_path)
        retired_bytes = root.read_bytes(retired_path)
    except (OSError, RootPathError) as exc:
        raise HandoverError(f"retired marker is unavailable ({type(exc).__name__})") from None
    if info.size != evidence["size"] or len(retired_bytes) != info.size or hashlib.sha256(retired_bytes).hexdigest() != evidence["sha256"]:
        raise HandoverError("retired marker bytes do not match attestation evidence")
    try:
        with _handover_resource_access(root):
            root.file_info(artifact["subject"])
    except FileNotFoundError:
        pass
    else:
        raise HandoverError("attested marker remains active in the destination copy")
    return artifact


def _validate_retired_marker_storage(root: RootContext, artifacts: list[dict[str, Any]]) -> None:
    marker_artifacts = [artifact for artifact in artifacts if artifact["kind"] == "stale-marker-retirement"]
    expected_names = {Path(_retired_marker_path(artifact["subject"])).name for artifact in marker_artifacts}
    directory = root.path.joinpath(*Path(RETIRED_MARKER_ROOT).parts)
    try:
        info = directory.lstat()
    except FileNotFoundError:
        if expected_names:
            raise HandoverError("retired marker storage is missing")
        return
    if _is_reparse_point(directory) or not stat.S_ISDIR(info.st_mode):
        raise HandoverError("retired marker storage is not a regular directory")
    try:
        with os.scandir(directory) as entries:
            observed = set()
            for entry in entries:
                if entry.name not in expected_names or not entry.is_file(follow_symlinks=False):
                    raise HandoverError("retired marker storage contains an unreferenced entry")
                observed.add(entry.name)
    except OSError as exc:
        raise HandoverError(f"retired marker storage is unavailable ({type(exc).__name__})") from None
    if observed != expected_names:
        raise HandoverError("retired marker storage does not match its attestation artifacts")
    for artifact in marker_artifacts:
        _validate_marker_retirement_artifact(root, artifact)


def _validated_destination_attestations(root: RootContext) -> tuple[dict[str, Any] | None, dict[tuple[str, str], dict[str, Any]]]:
    state = _read_relocation_state(root)
    source_binding = state["source_root_binding"] if state is not None else None
    source_evidence = _read_source_evidence_bundle(root, source_binding=source_binding)
    if state is None:
        if source_evidence is not None:
            raise HandoverError("source evidence is not bound to a completed relocation copy")
    elif state["source_evidence_digest"] is None:
        if source_evidence is not None:
            raise HandoverError("source evidence differs from relocation state")
    elif not _source_evidence_matches_relocation_state(source_evidence, state):
        raise HandoverError("source evidence is missing or differs from relocation state")

    artifacts = _list_attestation_artifacts(root)
    if artifacts and source_evidence is None:
        raise HandoverError("attestation artifacts require destination-bound source evidence")
    indexed = {}
    for artifact in artifacts:
        if source_evidence is None:
            raise HandoverError("attestation artifacts require destination-bound source evidence")
        blocker = _source_evidence_blocker(source_evidence, artifact["kind"], artifact["subject"])
        if not _attestation_resolves_blocker(root, artifact, blocker, source_evidence):
            raise HandoverError("attestation artifact does not resolve its source-evidence blocker")
        indexed[(artifact["kind"], artifact["subject"])] = artifact
    if source_evidence is not None:
        for blocker in source_evidence["blockers"]:
            artifact = indexed.get((blocker["kind"], blocker["subject"]))
            if artifact is None or not _attestation_resolves_blocker(root, artifact, blocker, source_evidence):
                raise HandoverError(f"source blocker remains unresolved: {blocker['subject']}")
    return source_evidence, indexed


def _attestation_reference(artifact: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": artifact["kind"],
        "subject": artifact["subject"],
        "record_digest": artifact["record_digest"],
    }


def _attestation_inventory_key(kind: str, subject: str) -> str:
    if kind != "stale-marker-retirement" or not isinstance(subject, str) or not subject:
        raise HandoverError("attestation inventory identity is invalid")
    return f"@attestation/{kind}/{hashlib.sha256(subject.encode('utf-8')).hexdigest()}"


def _head_inventory_projection(heads: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    projection = {}
    for key, entry in heads.items():
        if key.startswith("@attestation/"):
            continue
        projection[key] = {field: value for field, value in entry.items() if field != "attestation_refs"}
    return projection


def _validate_enrollment_attestation_refs(root: RootContext, heads: dict[str, dict[str, Any]]) -> None:
    _, attestations = _validated_destination_attestations(root)
    expected = {}
    for (kind, subject), artifact in attestations.items():
        if kind == "protected-fund-inclusion":
            expected[subject] = _attestation_reference(artifact)
        else:
            key = _attestation_inventory_key(kind, subject)
            expected[key] = {
                "kind": kind,
                "subject": subject,
                "attestation_digest": artifact["record_digest"],
            }

    observed = {}
    for key, entry in heads.items():
        if key.startswith("@attestation/"):
            observed[key] = entry
        elif "attestation_refs" in entry:
            observed[key] = entry["attestation_refs"][0]
    if observed != expected:
        raise EnrollmentInvalid("handover attestation references do not match destination artifacts")


def _validate_relocation_entries_with_retired_markers(
    root: RootContext,
    state: dict[str, Any],
    source_evidence: dict[str, Any],
    *,
    entries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    reconstructed = dict(entries if entries is not None else _relocation_entries(root))
    for blocker in source_evidence["blockers"]:
        if blocker["kind"] != "stale-marker-retirement" or blocker["subject"] in reconstructed:
            continue
        artifact = _read_attestation_artifact(root, kind="stale-marker-retirement", subject=blocker["subject"])
        if artifact is None:
            continue
        artifact = _validate_marker_retirement_artifact(root, artifact, source_evidence=source_evidence)
        marker_evidence = artifact["evidence"]
        reconstructed[blocker["subject"]] = {
            "type": "file",
            "size": marker_evidence["size"],
            "sha256": marker_evidence["sha256"],
        }
    reconstructed = dict(sorted(reconstructed.items()))
    if _digest(reconstructed) != state["source_content_digest"]:
        raise HandoverError("destination copy content changed; inspect-source and relocate-copy again")
    return reconstructed


def _remove_single_writer_challenge(root: RootContext) -> None:
    try:
        root.unlink_file(SINGLE_WRITER_CHALLENGE_PATH)
    except FileNotFoundError:
        pass


def _single_writer_state_digest(root: RootContext) -> str:
    try:
        data = root.read_bytes(SINGLE_WRITER_STATE_PATH)
    except FileNotFoundError:
        return _digest({"state": "absent"})
    if len(data) > _MAX_TRUST_RECORD_BYTES:
        raise HandoverError("single-writer state size is invalid")
    return hashlib.sha256(data).hexdigest()


def _enrollment_identity(enrollment: dict[str, Any]) -> str:
    stable_fields = ("schema", "protocol_version", "build_id", "mode", "root", "created_at", "attestation")
    return _digest({key: enrollment[key] for key in stable_fields})


def _single_writer_acknowledgement(
    root: RootContext,
    enrollment: dict[str, Any],
    inventory_digest_value: str,
    challenge_id: str,
    runtime_scope: dict[str, Any],
) -> str:
    root_digest = _digest(
        {
            "root": root_binding(root),
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "enrollment_identity": _enrollment_identity(enrollment),
            "runtime_scope": runtime_scope,
        }
    )
    return f"I ACCEPT TRUSTED SINGLE-WRITER MODE ROOT={root_digest} " f"INVENTORY={inventory_digest_value} CHALLENGE={challenge_id}; " "I ACCEPT RESPONSIBILITY FOR STOPPING AND EXCLUDING ALL OTHER PROGRAMS " "THAT CAN REACH THIS ROOT."


def _valid_challenge_id(value: object) -> bool:
    return isinstance(value, str) and len(value) == 32 and all(character in "0123456789abcdef" for character in value)


def legacy_reachability_reason(root: RootContext) -> str | None:
    """Return why a shipped legacy writer could address this root, if it can.

    Legacy CLI/TUI/cron/compose writers only address ``Path.home()/.hedge-fund``.
    This check denies roots that are, contain, sit inside, or resolve to such a
    directory for the current account, plus roots with a legacy ``runner.pid``.
    It is not a claim that arbitrary third-party processes are fenced.
    """
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if any(part.casefold() == LEGACY_HOME_NAME for part in root.path.parts):
        return "legacy-layout-path"
    try:
        os.lstat(root.path / LEGACY_HOME_NAME)
    except FileNotFoundError:
        pass
    except OSError:
        return "legacy-reachability-unverified"
    else:
        return "legacy-layout-nested"
    try:
        root_info = os.stat(root.path)
        root_real = os.path.normcase(os.path.realpath(root.path))
    except OSError:
        return "legacy-reachability-unverified"
    for home in _legacy_home_candidates():
        candidate = home / LEGACY_HOME_NAME
        try:
            info = os.stat(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            return "legacy-reachability-unverified"
        if (info.st_dev, info.st_ino) == (root_info.st_dev, root_info.st_ino):
            return "legacy-home-alias"
        try:
            if _legacy_tree_reaches(candidate, root_real):
                return "legacy-home-alias"
        except (OSError, HandoverError):
            return "legacy-reachability-unverified"
    try:
        if _paper_runner_pid_present(root):
            return "legacy-runner-present"
    except Exception:
        return "legacy-reachability-unverified"
    root.revalidate()
    return None


_MAX_LEGACY_ALIAS_ENTRIES = 65_536


def _overlaps(first: str, second: str) -> bool:
    try:
        return os.path.commonpath([first, second]) in {first, second}
    except ValueError:
        return False


def _legacy_tree_reaches(candidate: Path, root_real: str) -> bool:
    """True when ``candidate`` or an entry a legacy writer opens beneath it resolves into the root.

    Legacy writers open ``<legacy>/<top>`` and ``<legacy>/<top>/<item>`` (for example
    ``paper/<fund>``), so aliases at those two levels are resolved. Plain entries
    cannot reach the root unless ``candidate`` itself already overlaps it.
    """
    if _overlaps(os.path.normcase(os.path.realpath(candidate)), root_real):
        return True
    seen = 0
    pending = [(candidate, 0)]
    while pending:
        directory, depth = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                seen += 1
                if seen > _MAX_LEGACY_ALIAS_ENTRIES:
                    raise HandoverError("legacy home inventory exceeds its bound")
                info = entry.stat(follow_symlinks=False)
                aliased = stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)
                if aliased and _overlaps(os.path.normcase(os.path.realpath(entry.path)), root_real):
                    return True
                if depth == 0 and entry.is_dir(follow_symlinks=True):
                    pending.append((Path(entry.path), 1))
    return False


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _legacy_home_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        candidates.append(Path.home())
    except (KeyError, RuntimeError, OSError):
        pass
    for variable in ("HOME", "USERPROFILE"):
        value = os.environ.get(variable)
        if value:
            candidates.append(Path(value))
    drive, home_path = os.environ.get("HOMEDRIVE"), os.environ.get("HOMEPATH")
    if drive and home_path:
        candidates.append(Path(drive + home_path))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_absolute():
            continue
        key = os.path.normcase(os.path.normpath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _paper_runner_pid_present(root: RootContext) -> bool:
    paper = root.path / "paper"
    try:
        entries = list(os.scandir(paper))
    except FileNotFoundError:
        return False
    if len(entries) > _MAX_INVENTORY_FUNDS:
        raise HandoverError("paper inventory exceeds its bound")
    for entry in entries:
        if entry.is_dir(follow_symlinks=False) and os.path.lexists(os.path.join(entry.path, "runner.pid")):
            return True
    return False


def enroll_fresh(root: RootContext) -> dict[str, Any]:
    """Enroll an empty root; production writes still require deliberate trust."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    root.revalidate()
    if _record_exists(root):
        raise EnrollmentInvalid("root already has a handover record")
    if any(root.path.iterdir()):
        raise HandoverError("fresh enrollment requires an empty root")
    reason = legacy_reachability_reason(root)
    if reason is not None:
        raise WriteAuthorityDenied(f"fresh enrollment requires a root no legacy writer can address ({reason})")
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


_INTERRUPTED_ARTIFACT = re.compile(r"^\..+\.\d+\.[0-9a-f]{32}\.tmp$")
_PAPER_LANE_LOCK = re.compile(r"^\.paper-[a-z]+\.lock$")
_SECRET_DOTENV = re.compile(r"^\.env(\..*)?$", re.IGNORECASE)


def inspect_relocation_source(
    source: RootContext,
    *,
    evidence_out: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Inspect source read-only; optionally stage evidence at a disjoint destination."""
    snapshot = _relocation_source_snapshot(source)
    result = {
        "inventory_digest": snapshot["inventory_digest"],
        "content_digest": snapshot["content_digest"],
        "funds": len(snapshot["heads"]),
        "files": sum(1 for entry in snapshot["entries"].values() if entry["type"] == "file"),
        "bytes": sum(entry["size"] for entry in snapshot["entries"].values() if entry["type"] == "file"),
        "observed_inventory_digest": snapshot["observed_inventory_digest"],
        "blockers": snapshot["blockers"],
    }
    if evidence_out is not None:
        result["source_evidence_digest"] = _write_source_evidence_bundle(source, snapshot, evidence_out)
    return result


def _new_source_evidence_bundle(source: RootContext, snapshot: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema": 1,
        "source_root_binding": root_binding(source),
        "observed_inventory_digest": snapshot["observed_inventory_digest"],
        "content_digest": snapshot["content_digest"],
        "inventory_digest": snapshot["inventory_digest"],
        "blockers": snapshot["blockers"],
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }
    try:
        record = {**body, "record_digest": _digest(body)}
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise HandoverError("source evidence bundle is not serializable") from None
    if len(payload) > _MAX_TRUST_RECORD_BYTES:
        raise HandoverError("source evidence bundle exceeds its storage bound")
    return record


def _validate_source_evidence_bundle(record: object, *, source_binding: dict[str, Any] | None = None) -> dict[str, Any]:
    fields = {
        "schema",
        "source_root_binding",
        "observed_inventory_digest",
        "content_digest",
        "inventory_digest",
        "blockers",
        "recorded_at",
        "record_digest",
    }
    if not isinstance(record, dict) or set(record) != fields:
        raise HandoverError("source evidence bundle fields are invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    try:
        digest = _digest(body)
        observed_inventory_digest = _digest(
            {
                "source_root_binding": record["source_root_binding"],
                "inventory_digest": record["inventory_digest"],
                "content_digest": record["content_digest"],
                "blockers": record["blockers"],
            }
        )
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise HandoverError("source evidence bundle is not serializable") from None
    blockers = record["blockers"]
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or not isinstance(record["source_root_binding"], dict)
        or (source_binding is not None and record["source_root_binding"] != source_binding)
        or any(not isinstance(record[key], str) or not _SHA256.fullmatch(record[key]) for key in ("observed_inventory_digest", "content_digest", "inventory_digest"))
        or not isinstance(blockers, list)
        or len(blockers) > _MAX_INVENTORY_FUNDS * 2
        or record["observed_inventory_digest"] != observed_inventory_digest
        or any(not isinstance(item, dict) or set(item) != {"kind", "subject", "evidence"} or not isinstance(item["kind"], str) or item["kind"] not in _ATTESTATION_KINDS or not isinstance(item["subject"], str) or not item["subject"] or not isinstance(item["evidence"], dict) for item in blockers)
        or not _valid_timestamp(record["recorded_at"])
        or not isinstance(record["record_digest"], str)
        or record["record_digest"] != digest
        or len(payload) > _MAX_TRUST_RECORD_BYTES
    ):
        raise HandoverError("source evidence bundle identity is invalid")
    return record


def _write_source_evidence_bundle(
    source: RootContext,
    snapshot: dict[str, Any],
    evidence_out: str | os.PathLike[str],
) -> str:
    if not isinstance(source, RootContext):
        raise TypeError("an explicit RootContext is required")
    try:
        raw_path = os.fspath(evidence_out)
    except TypeError:
        raise HandoverError("source evidence output path is invalid") from None
    if not isinstance(raw_path, str) or not raw_path:
        raise HandoverError("source evidence output path is invalid")
    output = Path(raw_path)
    suffix = Path(SOURCE_EVIDENCE_PATH).parts
    if not output.is_absolute() or ".." in output.parts or len(output.parts) <= len(suffix):
        raise HandoverError("source evidence output must be an absolute destination-private path")
    if tuple(part.casefold() for part in output.parts[-len(suffix) :]) != tuple(part.casefold() for part in suffix):
        raise HandoverError(f"source evidence output must be the destination's {SOURCE_EVIDENCE_PATH}")
    destination_path = output.parents[len(suffix) - 1]
    expected_output = destination_path / SOURCE_EVIDENCE_PATH
    if os.path.normcase(os.path.abspath(os.fspath(output))) != os.path.normcase(os.path.abspath(os.fspath(expected_output))):
        raise HandoverError("source evidence output path is not canonical")

    record = _new_source_evidence_bundle(source, snapshot)
    try:
        destination = RootContext.open(destination_path)
    except (OSError, RootPathError) as exc:
        raise HandoverError(f"source evidence destination is unavailable ({type(exc).__name__})") from None
    try:
        _require_disjoint_roots(source, destination)
        if not destination.verify_private_storage():
            if any(destination.path.iterdir()):
                raise HandoverError("source evidence destination must be empty or have verified private storage")
            destination.prepare_private_storage()
        elif not _private_stage_layout_matches(destination, allowed_files=(SOURCE_EVIDENCE_PATH,)):
            raise HandoverError("source evidence destination contains unrelated data")
        try:
            with RootMigrationLease.acquire(destination, timeout=0):
                current = _relocation_source_snapshot(source)
                if current["observed_inventory_digest"] != snapshot["observed_inventory_digest"]:
                    raise HandoverError("source changed during inspection; inspect again")
                try:
                    existing = _read_private_json(destination, SOURCE_EVIDENCE_PATH)
                except FileNotFoundError:
                    if not _fresh_bootstrap_only(destination):
                        raise HandoverError("source evidence destination contains unrelated data")
                    _write_private_json(destination, SOURCE_EVIDENCE_PATH, record)
                    return record["record_digest"]
                existing = _validate_source_evidence_bundle(existing, source_binding=root_binding(source))
                if existing["observed_inventory_digest"] != record["observed_inventory_digest"] or existing["content_digest"] != record["content_digest"] or existing["blockers"] != record["blockers"]:
                    raise HandoverError("different source evidence already exists at the destination")
                if not _fresh_bootstrap_only(destination, allowed_files=(SOURCE_EVIDENCE_PATH,)):
                    raise HandoverError("source evidence destination contains unrelated data")
                return existing["record_digest"]
        except WriterConflict as exc:
            raise HandoverError("source evidence destination is active") from exc
    finally:
        destination.close()


def _read_source_evidence_bundle(
    root: RootContext,
    *,
    source_binding: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        record = _read_private_json(root, SOURCE_EVIDENCE_PATH)
    except FileNotFoundError:
        return None
    return _validate_source_evidence_bundle(record, source_binding=source_binding)


def _new_relocation_state(
    target: RootContext,
    source: RootContext,
    snapshot: dict[str, Any],
    *,
    state: str,
    source_evidence_digest: str | None,
) -> dict[str, Any]:
    body = {
        "schema": 1,
        "state": state,
        "source_root_binding": root_binding(source),
        "target_root_binding": root_binding(target),
        "source_content_digest": snapshot["content_digest"],
        "source_inventory_digest": snapshot["inventory_digest"],
        "source_observed_inventory_digest": snapshot["observed_inventory_digest"],
        "source_evidence_digest": source_evidence_digest,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }
    return {**body, "record_digest": _digest(body)}


def _validate_relocation_state(
    target: RootContext,
    record: object,
    *,
    source_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields = {
        "schema",
        "state",
        "source_root_binding",
        "target_root_binding",
        "source_content_digest",
        "source_inventory_digest",
        "source_observed_inventory_digest",
        "source_evidence_digest",
        "recorded_at",
        "record_digest",
    }
    if not isinstance(target, RootContext) or not isinstance(record, dict) or set(record) != fields:
        raise HandoverError("relocation state fields are invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    try:
        digest = _digest(body)
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise HandoverError("relocation state is not serializable") from None
    evidence_digest = record["source_evidence_digest"]
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or not isinstance(record["state"], str)
        or record["state"] not in {"incomplete", "copied"}
        or not isinstance(record["source_root_binding"], dict)
        or (source_binding is not None and record["source_root_binding"] != source_binding)
        or record["target_root_binding"] != root_binding(target)
        or any(not isinstance(record[key], str) or not _SHA256.fullmatch(record[key]) for key in ("source_content_digest", "source_inventory_digest", "source_observed_inventory_digest"))
        or (evidence_digest is not None and (not isinstance(evidence_digest, str) or not _SHA256.fullmatch(evidence_digest)))
        or not _valid_timestamp(record["recorded_at"])
        or not isinstance(record["record_digest"], str)
        or record["record_digest"] != digest
        or len(payload) > _MAX_TRUST_RECORD_BYTES
    ):
        raise HandoverError("relocation state identity is invalid")
    return record


def _read_relocation_state(target: RootContext, *, source_binding: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        record = _read_private_json(target, RELOCATION_STATE_PATH)
    except FileNotFoundError:
        return None
    return _validate_relocation_state(target, record, source_binding=source_binding)


def _source_evidence_matches_relocation_state(evidence: dict[str, Any] | None, state: dict[str, Any]) -> bool:
    return evidence is not None and evidence["record_digest"] == state["source_evidence_digest"] and evidence["content_digest"] == state["source_content_digest"] and evidence["inventory_digest"] == state["source_inventory_digest"] and evidence["observed_inventory_digest"] == state["source_observed_inventory_digest"]


def _write_relocation_state(target: RootContext, record: dict[str, Any]) -> None:
    _validate_relocation_state(target, record)
    _write_private_json(target, RELOCATION_STATE_PATH, record)


def _relocation_target_layout_matches(
    target: RootContext,
    entries: dict[str, dict[str, Any]],
    *,
    has_source_evidence: bool,
    allow_partial: bool,
) -> bool:
    bootstrap_dirs = {
        Path("runtime"),
        Path("runtime/private"),
        Path(PRIVATE_ROOT),
        Path(f"{PRIVATE_ROOT}/admission"),
        Path(f"{PRIVATE_ROOT}/admission/v1"),
    }
    expected_dirs = set(bootstrap_dirs)
    expected_files = {
        Path(OWNER_LOCK_PATH),
        Path(RELOCATION_STATE_PATH),
    }
    if has_source_evidence:
        expected_files.add(Path(SOURCE_EVIDENCE_PATH))
    for relative, entry in entries.items():
        path = Path(relative)
        if entry["type"] == "dir":
            expected_dirs.add(path)
        else:
            expected_files.add(path)
            expected_dirs.update(parent for parent in path.parents if parent != Path("."))

    observed_dirs: set[Path] = set()
    observed_files: set[Path] = set()

    def fail_walk(_exc: OSError) -> None:
        raise HandoverError("relocation target cannot be inspected")

    try:
        target.revalidate()
        for directory, subdirs, files in os.walk(target.path, followlinks=False, onerror=fail_walk):
            current = Path(directory)
            for name in list(subdirs):
                child = current / name
                if _is_reparse_point(child):
                    return False
                observed_dirs.add(child.relative_to(target.path))
            for name in files:
                child = current / name
                if _is_reparse_point(child):
                    return False
                observed_files.add(child.relative_to(target.path))
        target.revalidate()
    except (OSError, RootPathError, HandoverError):
        return False
    if not bootstrap_dirs.issubset(observed_dirs) or not {Path(OWNER_LOCK_PATH), Path(RELOCATION_STATE_PATH)}.issubset(observed_files):
        return False
    if has_source_evidence and Path(SOURCE_EVIDENCE_PATH) not in observed_files:
        return False
    if allow_partial:
        return observed_dirs.issubset(expected_dirs) and observed_files.issubset(expected_files)
    return observed_dirs == expected_dirs and observed_files == expected_files


def _validate_relocation_target_entries(
    target: RootContext,
    expected: dict[str, dict[str, Any]],
    *,
    allow_partial: bool,
) -> None:
    with _handover_resource_access(target):
        actual = _relocation_entries(target)
    if any(relative not in expected or expected[relative]["type"] != entry["type"] for relative, entry in actual.items()):
        raise HandoverError("relocation target contains unrelated data")
    if not allow_partial and actual != expected:
        raise HandoverError("relocation target content does not match the source")


def relocate_copy(
    target: RootContext,
    *,
    source: RootContext,
    expected_content_digest: str,
) -> dict[str, Any]:
    """Copy reviewed source data; leave target unenrolled until finalize."""
    if not isinstance(target, RootContext) or not isinstance(source, RootContext):
        raise TypeError("explicit RootContexts are required")
    if not isinstance(expected_content_digest, str) or not _SHA256.fullmatch(expected_content_digest):
        raise HandoverError("source content digest is invalid")
    target.revalidate()
    source.revalidate()
    _require_disjoint_roots(source, target)
    if _record_exists(target):
        raise EnrollmentInvalid("root already has a handover record")
    reason = legacy_reachability_reason(target)
    if reason is not None:
        raise WriteAuthorityDenied(f"relocation target must be unreachable by legacy writers ({reason})")
    before = _relocation_source_snapshot(source)
    if before["content_digest"] != expected_content_digest:
        raise HandoverError("source content changed; inspect the source and retry")
    private_storage_verified = target.verify_private_storage()
    if before["blockers"] and not private_storage_verified:
        raise HandoverError("source blockers require inspect-source --evidence-out before relocation-copy")
    staged_evidence = _read_source_evidence_bundle(target, source_binding=root_binding(source)) if private_storage_verified else None
    if before["blockers"] and staged_evidence is None:
        raise HandoverError("source blockers require inspect-source --evidence-out before relocation-copy")
    if staged_evidence is not None and (staged_evidence["content_digest"] != before["content_digest"] or staged_evidence["inventory_digest"] != before["inventory_digest"] or staged_evidence["observed_inventory_digest"] != before["observed_inventory_digest"]):
        raise HandoverError("source evidence does not match the reviewed source; inspect again")
    if not private_storage_verified:
        if any(target.path.iterdir()):
            raise HandoverError("relocation requires an empty target or a verified evidence stage")
        target.prepare_private_storage()
    state_before_lock = _read_relocation_state(target, source_binding=root_binding(source))
    if state_before_lock is None:
        if not _private_stage_layout_matches(target, allowed_files=(SOURCE_EVIDENCE_PATH,) if staged_evidence else ()):
            raise HandoverError("relocation target contains unrelated data")
    else:
        if state_before_lock["source_content_digest"] != before["content_digest"] or state_before_lock["source_inventory_digest"] != before["inventory_digest"] or state_before_lock["source_observed_inventory_digest"] != before["observed_inventory_digest"] or state_before_lock["source_evidence_digest"] != (staged_evidence["record_digest"] if staged_evidence else None):
            raise HandoverError("relocation state does not match the reviewed source")
        if not _relocation_target_layout_matches(target, before["entries"], has_source_evidence=staged_evidence is not None, allow_partial=state_before_lock["state"] == "incomplete"):
            raise HandoverError("relocation target contains unrelated data")
        _validate_relocation_target_entries(target, before["entries"], allow_partial=state_before_lock["state"] == "incomplete")

    try:
        with RootMigrationLease.acquire(target, timeout=0):
            if _record_exists(target):
                raise EnrollmentInvalid("root already has a handover record")
            source_evidence = _read_source_evidence_bundle(target, source_binding=root_binding(source))
            if before["blockers"] and source_evidence is None:
                raise HandoverError("source blockers require inspect-source --evidence-out before relocation-copy")
            if source_evidence is not None and (source_evidence["content_digest"] != before["content_digest"] or source_evidence["inventory_digest"] != before["inventory_digest"] or source_evidence["observed_inventory_digest"] != before["observed_inventory_digest"]):
                raise HandoverError("source evidence does not match the reviewed source; inspect again")

            state = _read_relocation_state(target, source_binding=root_binding(source))
            has_evidence = source_evidence is not None
            if state is None:
                if not _fresh_bootstrap_only(target, allowed_files=(SOURCE_EVIDENCE_PATH,) if has_evidence else ()):
                    raise HandoverError("relocation target contains unrelated data")
                state = _new_relocation_state(
                    target,
                    source,
                    before,
                    state="incomplete",
                    source_evidence_digest=source_evidence["record_digest"] if source_evidence else None,
                )
                _write_relocation_state(target, state)
            else:
                if state["source_content_digest"] != before["content_digest"] or state["source_inventory_digest"] != before["inventory_digest"] or state["source_observed_inventory_digest"] != before["observed_inventory_digest"] or state["source_evidence_digest"] != (source_evidence["record_digest"] if source_evidence else None):
                    raise HandoverError("relocation state does not match the reviewed source")
                if state["state"] == "copied":
                    if not _relocation_target_layout_matches(target, before["entries"], has_source_evidence=has_evidence, allow_partial=False):
                        raise HandoverError("copied relocation target contains unrelated data")
                    _validate_relocation_target_entries(target, before["entries"], allow_partial=False)
                    return {
                        "state": "copied",
                        "content_digest": state["source_content_digest"],
                        "inventory_digest": state["source_inventory_digest"],
                    }
                if state["state"] != "incomplete":
                    raise HandoverError("relocation target state is invalid")
                if not _relocation_target_layout_matches(target, before["entries"], has_source_evidence=has_evidence, allow_partial=True):
                    raise HandoverError("incomplete relocation target contains unrelated data")
                _validate_relocation_target_entries(target, before["entries"], allow_partial=True)

            with _handover_resource_access(source), _handover_resource_access(target, allow_writes=True, allow_unattested_protected_writes=True):
                for relative, entry in before["entries"].items():
                    if entry["type"] == "dir":
                        target.mkdir(relative, parents=True)
                        continue
                    data = source.read_bytes(relative)
                    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                        raise HandoverError("source content changed during relocation")
                    target.write_bytes(relative, data, mode=stat.S_IRUSR | stat.S_IWUSR)
            after = _relocation_source_snapshot(source)
            if after["observed_inventory_digest"] != before["observed_inventory_digest"] or after["heads"] != before["heads"]:
                raise HandoverError("source content changed during relocation")
            _validate_relocation_target_entries(target, before["entries"], allow_partial=False)
            if not _relocation_target_layout_matches(target, before["entries"], has_source_evidence=has_evidence, allow_partial=False):
                raise HandoverError("relocation target contains unrelated data")
            copied_state = _new_relocation_state(
                target,
                source,
                before,
                state="copied",
                source_evidence_digest=source_evidence["record_digest"] if source_evidence else None,
            )
            _write_relocation_state(target, copied_state)
            return {
                "state": "copied",
                "content_digest": copied_state["source_content_digest"],
                "inventory_digest": copied_state["source_inventory_digest"],
            }
    except WriterConflict as exc:
        raise HandoverError("another target participant is active") from exc


def relocate_finalize(target: RootContext) -> dict[str, Any]:
    """Validate a completed copy and enroll destination read-only."""
    if not isinstance(target, RootContext):
        raise TypeError("an explicit RootContext is required")
    target.revalidate()
    if _record_exists(target):
        raise EnrollmentInvalid("root already has a handover record")
    if not target.verify_private_storage():
        raise HandoverError("relocation-copy must complete before relocate-finalize")
    reason = legacy_reachability_reason(target)
    if reason is not None:
        raise WriteAuthorityDenied(f"relocation target must be unreachable by legacy writers ({reason})")
    staged_state = _read_relocation_state(target)
    if staged_state is None or staged_state["state"] != "copied":
        raise HandoverError("relocation-copy is incomplete; rerun relocate-copy before finalize")
    if staged_state["source_evidence_digest"] is not None:
        staged_evidence = _read_source_evidence_bundle(target, source_binding=staged_state["source_root_binding"])
        if not _source_evidence_matches_relocation_state(staged_evidence, staged_state):
            raise HandoverError("source evidence is missing or changed; inspect-source and relocate-copy again")
    try:
        with RootMigrationLease.acquire(target, timeout=0):
            state = _read_relocation_state(target)
            if state is None or state["state"] != "copied":
                raise HandoverError("relocation-copy is incomplete; rerun relocate-copy before finalize")
            if state["source_evidence_digest"] is not None:
                evidence = _read_source_evidence_bundle(target, source_binding=state["source_root_binding"])
                if not _source_evidence_matches_relocation_state(evidence, state):
                    raise HandoverError("source evidence is missing or changed; inspect-source and relocate-copy again")
                _validate_relocation_entries_with_retired_markers(target, state, evidence)
            elif _digest(_relocation_entries(target)) != state["source_content_digest"]:
                raise HandoverError("copied relocation content changed; inspect and relocate again")
            heads = build_head_inventory(target)
            if _digest(_head_inventory_projection(heads)) != state["source_inventory_digest"]:
                raise HandoverError("relocated ledger heads do not match the source")
            record = _new_record(
                target,
                mode="relocated",
                heads=heads,
                attestation={
                    "source_inventory_digest": state["source_inventory_digest"],
                    "source_content_digest": state["source_content_digest"],
                },
            )
            _write_record(target, record)
            return require_enrollment(target)
    except WriterConflict as exc:
        raise HandoverError("another target participant is active") from exc


def relocate_existing(
    target: RootContext,
    *,
    source: RootContext,
    expected_content_digest: str,
) -> dict[str, Any]:
    """Run the legacy one-command relocation ceremony."""
    if not isinstance(target, RootContext) or not isinstance(source, RootContext):
        raise TypeError("explicit RootContexts are required")
    if not isinstance(expected_content_digest, str) or not _SHA256.fullmatch(expected_content_digest):
        raise HandoverError("source content digest is invalid")
    before = _relocation_source_snapshot(source)
    if before["blockers"]:
        raise HandoverError("source blockers require relocate-copy, destination attestations, and relocate-finalize")
    copied = relocate_copy(target, source=source, expected_content_digest=expected_content_digest)
    if copied["state"] != "copied":
        raise HandoverError("relocation-copy is incomplete")
    return relocate_finalize(target)


def _require_disjoint_roots(source: RootContext, target: RootContext) -> None:
    try:
        source_info = os.stat(source.path)
        target_info = os.stat(target.path)
        source_real = os.path.normcase(os.path.realpath(source.path))
        target_real = os.path.normcase(os.path.realpath(target.path))
    except OSError as exc:
        raise HandoverError("relocation roots cannot be compared") from exc
    if (source_info.st_dev, source_info.st_ino) == (target_info.st_dev, target_info.st_ino):
        raise HandoverError("relocation source and target must differ")
    try:
        common = os.path.commonpath([source_real, target_real])
    except ValueError:
        return
    if common in {source_real, target_real}:
        raise HandoverError("relocation source and target must not overlap")


def _relocation_source_snapshot(source: RootContext) -> dict[str, Any]:
    if not isinstance(source, RootContext):
        raise TypeError("an explicit RootContext is required")
    source.revalidate()
    entries = _relocation_entries(source)
    blockers = _source_evidence_blockers(source, entries)
    heads = _build_head_inventory(source, allow_relocation_blockers=True)
    from hedge_fund.paper.deployed import load_deployed

    for relative in entries:
        parts = relative.split("/")
        if len(parts) == 3 and parts[0] == "paper" and parts[2] == "fund.yaml":
            try:
                broker = load_deployed(source.path / "paper" / parts[1]).spec.broker
            except (OSError, ValueError, RootPathError) as exc:
                raise HandoverError(f"paper deployment is unreadable ({type(exc).__name__})") from None
            if broker != "paper":
                raise HandoverError("broker-backed deployments cannot be relocated")
    source.revalidate()
    content_digest = _digest(entries)
    inventory_digest_value = _digest(heads)
    return {
        "heads": heads,
        "inventory_digest": inventory_digest_value,
        "entries": entries,
        "content_digest": content_digest,
        "blockers": blockers,
        "observed_inventory_digest": _digest(
            {
                "source_root_binding": root_binding(source),
                "inventory_digest": inventory_digest_value,
                "content_digest": content_digest,
                "blockers": blockers,
            }
        ),
    }


def _source_evidence_blockers(source: RootContext, entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from hedge_fund.paper.deployed import FUND_FILE, load_deployed

    blockers = []
    with _handover_resource_access(source):
        for relative, entry in entries.items():
            parts = relative.split("/")
            if len(parts) == 2 and parts[0] == "paper" and entry["type"] == "dir" and parts[1] in _PROTECTED_RESOURCE_NAMES:
                fund_file = entries.get(f"{relative}/{FUND_FILE}")
                if fund_file is None or fund_file["type"] != "file":
                    continue
                try:
                    fund_data = source.read_bytes(f"{relative}/{FUND_FILE}")
                except (OSError, RootPathError) as exc:
                    raise HandoverError(f"protected fund evidence is unreadable ({type(exc).__name__})") from None
                if len(fund_data) != fund_file["size"] or hashlib.sha256(fund_data).hexdigest() != fund_file["sha256"]:
                    raise HandoverError("source content changed during inspection")
                try:
                    deployed = load_deployed(source.path / relative)
                except (OSError, ValueError, RootPathError) as exc:
                    raise HandoverError(f"protected fund evidence is unreadable ({type(exc).__name__})") from None
                if deployed.name != parts[1]:
                    raise HandoverError("protected fund identity must keep its original name")
                blockers.append(
                    {
                        "kind": "protected-fund-inclusion",
                        "subject": deployed.name,
                        "evidence": {
                            "directory": relative,
                            "fund_file_sha256": fund_file["sha256"],
                            "fund_file_size": fund_file["size"],
                        },
                    }
                )
            if parts[-1] != "runner.pid" or entry["type"] != "file":
                continue
            try:
                data = source.read_bytes(relative)
            except (OSError, RootPathError) as exc:
                raise HandoverError(f"source marker is unreadable ({type(exc).__name__})") from None
            if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise HandoverError("source content changed during inspection")
            try:
                text = data.decode("ascii").strip()
            except UnicodeDecodeError:
                text = ""
            marker_pid = int(text) if text.isdecimal() and len(text) <= 10 else None
            content_class = "empty" if not text else "pid" if marker_pid is not None and marker_pid > 0 else "opaque"
            blockers.append(
                {
                    "kind": "stale-marker-retirement",
                    "subject": relative,
                    "evidence": {
                        "content_class": content_class,
                        "pid": marker_pid,
                        "sha256": entry["sha256"],
                        "size": entry["size"],
                    },
                }
            )
    return sorted(blockers, key=lambda item: (item["kind"], item["subject"].casefold()))


def _relocation_entries(root: RootContext) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    total = 0

    def fail_walk(exc: OSError) -> None:
        raise exc

    try:
        for top in RELOCATED_TOP_LEVEL:
            base = root.path / top
            try:
                info = base.lstat()
            except FileNotFoundError:
                continue
            if _is_reparse_point(base) or not stat.S_ISDIR(info.st_mode):
                raise HandoverError(f"{top} is not a plain directory")
            entries[top] = {"type": "dir"}
            for directory, subdirs, files in os.walk(base, followlinks=False, onerror=fail_walk):
                current = Path(directory)
                subdirs.sort()
                for name in subdirs:
                    child = current / name
                    if _is_reparse_point(child):
                        raise HandoverError("relocation source contains a reparse point")
                    entries[child.relative_to(root.path).as_posix()] = {"type": "dir"}
                for name in sorted(files):
                    child = current / name
                    relative = child.relative_to(root.path).as_posix()
                    if _INTERRUPTED_ARTIFACT.fullmatch(name):
                        raise HandoverError("relocation source contains an interrupted write")
                    if _SECRET_DOTENV.fullmatch(name):
                        raise HandoverError("relocation source contains a .env file under engine data; remove it first")
                    if top == "paper" and _PAPER_LANE_LOCK.fullmatch(name):
                        continue
                    child_info = child.lstat()
                    if _is_reparse_point(child) or not stat.S_ISREG(child_info.st_mode):
                        raise HandoverError("relocation source contains a non-regular file")
                    if child_info.st_size > _MAX_RELOCATION_FILE_BYTES:
                        raise HandoverError("relocation source file exceeds its bound")
                    total += child_info.st_size
                    if total > _MAX_RELOCATION_TOTAL_BYTES or len(entries) >= _MAX_RELOCATION_FILES:
                        raise HandoverError("relocation source exceeds its bound")
                    with _handover_resource_access(root):
                        data = root.read_bytes(relative)
                    entries[relative] = {"type": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                if len(entries) > _MAX_RELOCATION_FILES:
                    raise HandoverError("relocation source exceeds its bound")
        settings_path = root.path / RELOCATED_SETTINGS_PATH
        try:
            settings_info = settings_path.lstat()
        except FileNotFoundError:
            pass
        else:
            if _is_reparse_point(settings_path) or not stat.S_ISREG(settings_info.st_mode):
                raise HandoverError("relocation settings file is not a regular file")
            if settings_info.st_size > _MAX_RELOCATION_FILE_BYTES:
                raise HandoverError("relocation source file exceeds its bound")
            data = root.read_bytes(RELOCATED_SETTINGS_PATH)
            total += len(data)
            if total > _MAX_RELOCATION_TOTAL_BYTES or len(entries) >= _MAX_RELOCATION_FILES:
                raise HandoverError("relocation source exceeds its bound")
            entries[RELOCATED_SETTINGS_PATH] = {
                "type": "file",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    except HandoverError:
        raise
    except (OSError, RootPathError) as exc:
        raise HandoverError(f"relocation source is unreadable ({type(exc).__name__})") from None
    root.revalidate()
    return dict(sorted(entries.items()))


def build_head_inventory(
    root: RootContext,
    *,
    allow_relocation_blockers: bool = False,
) -> dict[str, dict[str, Any]]:
    """Replay deployed ledgers; inspection may retain relocation blockers."""
    try:
        return _build_head_inventory(root, allow_relocation_blockers=allow_relocation_blockers)
    except OSError as exc:
        raise HandoverError(f"paper inventory is unavailable ({type(exc).__name__})") from None


def _build_head_inventory(root: RootContext, *, allow_relocation_blockers: bool = False) -> dict[str, dict[str, Any]]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if type(allow_relocation_blockers) is not bool:
        raise TypeError("allow_relocation_blockers must be a bool")
    root.revalidate()
    if not allow_relocation_blockers and _has_legacy_runner_pid(root.path):
        raise HandoverError("runner.pid is present; unknown owners block handover")
    if allow_relocation_blockers:
        source_evidence = None
        attestations = {}
    else:
        source_evidence, attestations = _validated_destination_attestations(root)
        if source_evidence is None:
            blockers = _source_evidence_blockers(root, _relocation_entries(root))
            if any(blocker["kind"] == "stale-marker-retirement" for blocker in blockers):
                raise HandoverError("runner.pid is present; unknown owners block handover")
    paper = root.path / "paper"
    try:
        paper_info = paper.lstat()
    except FileNotFoundError:
        root.revalidate()
        return {}
    if _is_reparse_point(paper):
        raise HandoverError("paper inventory contains a reparse point")
    if not stat.S_ISDIR(paper_info.st_mode):
        raise HandoverError("paper inventory is not a directory")
    from hedge_fund.paper.deployed import DeployedFund, FUND_FILE, load_deployed
    from hedge_fund.paper.ledger import Ledger, LedgerError

    inventory: dict[str, dict[str, Any]] = {}
    for directory in sorted(paper.iterdir(), key=lambda item: item.name.casefold()):
        directory_info = directory.lstat()
        if _is_reparse_point(directory):
            raise HandoverError("paper inventory contains a reparse point")
        if not stat.S_ISDIR(directory_info.st_mode):
            raise HandoverError("paper inventory contains an unknown entry")
        if not allow_relocation_blockers and _has_legacy_runner_pid(directory):
            raise HandoverError("runner.pid is present; unknown owners block handover")
        fund_file = directory / FUND_FILE
        try:
            fund_info = fund_file.stat()
        except FileNotFoundError:
            if any(directory.iterdir()):
                raise HandoverError("paper inventory contains an incomplete deployment")
            continue
        if not stat.S_ISREG(fund_info.st_mode):
            raise HandoverError("paper inventory contains an incomplete deployment")
        try:
            deployed: DeployedFund = load_deployed(directory)
            if allow_relocation_blockers:
                key = _relocation_resource_key(deployed.name)
                directory_key = _relocation_resource_key(directory.name)
            elif deployed.name in _PROTECTED_RESOURCE_NAMES and directory.name == deployed.name:
                artifact = attestations.get(("protected-fund-inclusion", deployed.name))
                if artifact is None:
                    raise HandoverError("protected fund requires a destination-bound inclusion attestation")
                key = deployed.name
                directory_key = deployed.name
            else:
                key = ensure_unique_resource_name(deployed.name, [])
                directory_key = ensure_unique_resource_name(directory.name, [])
            if key != directory_key:
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
            if not allow_relocation_blockers and deployed.name in _PROTECTED_RESOURCE_NAMES:
                entry["attestation_refs"] = [_attestation_reference(attestations[("protected-fund-inclusion", deployed.name)])]
        except HandoverError:
            raise
        except LedgerError:
            raise LedgerInventoryCorrupt("paper ledger inventory is invalid") from None
        except (OSError, ValueError, RootPathError) as exc:
            raise HandoverError(f"paper inventory is invalid ({type(exc).__name__})") from None
        if key in inventory:
            raise HandoverError("paper inventory contains duplicate identities")
        inventory[key] = entry
    for (kind, subject), artifact in attestations.items():
        if kind == "stale-marker-retirement":
            key = _attestation_inventory_key(kind, subject)
            if key in inventory:
                raise HandoverError("attestation inventory identity is duplicated")
            inventory[key] = {
                "kind": kind,
                "subject": subject,
                "attestation_digest": artifact["record_digest"],
            }
    root.revalidate()
    return dict(sorted(inventory.items()))


def _relocation_resource_key(name: str) -> str:
    if name in _PROTECTED_RESOURCE_NAMES:
        return name
    return ensure_unique_resource_name(name, [])


def verify_root_inventory(
    root: RootContext,
    *,
    record: dict[str, Any] | None = None,
) -> None:
    current, actual = _inventory_snapshot(root, record=record)
    expected = current["heads"]
    if actual != expected:
        raise LedgerDrift("paper ledger inventory differs from offline handover")


def verify_ledger_head(root: RootContext, name: str) -> dict[str, Any] | None:
    key = _resource_key(name)
    try:
        record, inventory = _inventory_snapshot(root)
    except InventoryObservationUnavailable:
        raise
    except HandoverError as exc:
        raise LedgerDrift("paper ledger inventory cannot be verified") from exc
    expected = record["heads"].get(key)
    actual = inventory.get(key)
    if actual != expected:
        raise LedgerDrift("paper ledger head differs from offline handover")
    return actual


def _inventory_snapshot(
    root: RootContext,
    *,
    record: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    from hedge_fund.paper.ledger import LedgerError

    coordinator = AdmissionCoordinator(root)

    def read() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        return (record or require_enrollment(root)), build_head_inventory(root)

    def registry_exists() -> bool:
        try:
            root.file_info(f"{LOCK_DIRECTORY}/registry.lock")
        except FileNotFoundError:
            return False
        return True

    if coordinator.lane_is_held("registry"):
        return read()
    if _paper_observation_authorized(root):
        return read()
    if not registry_exists():
        try:
            snapshot = read()
        except (HandoverError, LedgerError, OSError, RootPathError, ValueError):
            if not registry_exists():
                raise
        else:
            if not registry_exists():
                return snapshot
    with ExitStack() as stack:
        try:
            stack.enter_context(coordinator.registry_read_lock(timeout=MAX_LOCK_WAIT_SECONDS))
        except WriterConflict as exc:
            raise InventoryObservationUnavailable("paper inventory observation is unavailable") from exc
        except AdmissionError as exc:
            raise HandoverError("paper inventory admission failed") from exc
        return read()


def _verify_paper_transition_inventory(
    root: RootContext,
    admission: AdmissionCoordinator,
    name: str | None,
    *,
    transition: PaperInventoryTransition | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    record, actual = _inventory_snapshot(root)
    expected = record["heads"]
    mismatches = {key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)}
    if transition is not None:
        if name is None:
            raise HandoverError("paper transition identity is required")
        key = _resource_key(name)
        if expected.get(key) != transition.previous_entry or actual.get(key) != transition.expected_entry:
            raise LedgerDrift("paper mutation differs from its expected head")
        mismatches.discard(key)
    if not mismatches:
        return record, actual
    if name is not None and _resource_key(name) in mismatches:
        raise LedgerDrift("paper ledger inventory differs from offline handover")

    from hedge_fund.runtime.lifecycle import ArchiveError, LifecycleArchiveStore

    verified: set[str] = set()
    try:
        store = LifecycleArchiveStore(root, admission)
        for item in store.list_archives():
            if item["kind"] != "deployment" or item["state"] not in {"archive-prepared", "restore-prepared"}:
                continue
            key = _resource_key(item["identity"])
            if key not in mismatches:
                continue
            if key in verified:
                raise LedgerDrift("multiple lifecycle journals claim one ledger head")
            entry = item["ledger_entry"]
            before = item["inventory_before"]
            if not isinstance(entry, dict) or not isinstance(before, dict) or not _valid_inventory_entry(key, entry):
                raise LedgerDrift("prepared lifecycle inventory is invalid")
            reviewed = store.inspect(item["archive_id"])
            if item["state"] == "archive-prepared":
                valid = reviewed["recovery_action"] == "finalize-archive" and before.get(key) == entry and expected.get(key) == entry and actual.get(key) is None
            else:
                valid = reviewed["recovery_action"] == "finalize-restore" and before.get(key) is None and expected.get(key) is None and actual.get(key) == entry
            if not valid:
                raise LedgerDrift("prepared lifecycle inventory does not match its journal")
            verified.add(key)
    except (ArchiveError, OSError, RootPathError, ValueError) as exc:
        raise LedgerDrift("prepared lifecycle inventory cannot be verified") from exc
    if verified != mismatches:
        raise LedgerDrift("paper ledger inventory differs from offline handover")
    return record, actual


def verify_cache_write_inventory(root: RootContext, admission: AdmissionCoordinator) -> None:
    """Allow cache writes only across exactly inspected lifecycle transitions."""
    if admission.root is not root or not admission.lane_is_held("registry"):
        raise HandoverError("root registry admission is required")
    _verify_paper_transition_inventory(root, admission, None)


class PaperInventoryTransition:
    """Exact enrolled head before and after one admitted paper mutation."""

    def __init__(
        self,
        key: str,
        previous_entry: dict[str, Any] | None,
        *,
        root: RootContext | None = None,
        base: tuple[str, ...] = (),
    ) -> None:
        self._key = key
        self._previous_entry = dict(previous_entry) if previous_entry is not None else None
        self._expected_entry: dict[str, Any] | None = None
        self._root = root
        self._base = tuple(base)

    def _effect_root(self, relative: str | os.PathLike[str]) -> tuple[RootContext, str]:
        """Recheck authority immediately before one no-follow root effect."""
        if self._root is None:
            raise HandoverError("paper transition has no admitted root")
        require_write_authority(self._root)
        parts = Path(os.fspath(relative)).parts
        if not parts or any(part in {"", ".", ".."} for part in parts) or Path(os.fspath(relative)).is_absolute():
            raise RootPathError("paper transition effect must be fund-relative")
        return self._root, "/".join(self._base + parts)

    def mkdir(self, relative: str | os.PathLike[str], *, parents: bool = True, ensure_base: bool = False) -> None:
        root, target = self._effect_root(relative)
        if ensure_base and self._base:
            root.mkdir("/".join(self._base), parents=True)
        root.mkdir(target, parents=parents)

    def write_text(self, relative: str | os.PathLike[str], text: str) -> None:
        # Preserve the native newline bytes of the legacy text writer.
        root, target = self._effect_root(relative)
        root.write_bytes(target, text.replace("\n", os.linesep).encode("utf-8"))

    def write_bytes(self, relative: str | os.PathLike[str], data: bytes) -> None:
        root, target = self._effect_root(relative)
        root.write_bytes(target, data)

    def rename_file(self, source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        root, target = self._effect_root(destination)
        _, origin = self._effect_root(source)
        root.rename_file(origin, target)

    def unlink_file(self, relative: str | os.PathLike[str], *, missing_ok: bool = False) -> bool:
        root, target = self._effect_root(relative)
        try:
            root.unlink_file(target)
        except FileNotFoundError:
            if missing_ok:
                return False
            raise
        return True

    @property
    def previous_entry(self) -> dict[str, Any] | None:
        return dict(self._previous_entry) if self._previous_entry is not None else None

    def expect_entry(self, entry: dict[str, Any]) -> None:
        if self._expected_entry is not None or not _valid_inventory_entry(self._key, entry):
            raise HandoverError("expected paper inventory transition is invalid")
        self._expected_entry = dict(entry)

    @property
    def expected_entry(self) -> dict[str, Any]:
        if self._expected_entry is None:
            raise HandoverError("expected paper inventory transition is missing")
        return dict(self._expected_entry)


@contextmanager
def paper_effect_registry(
    path: str | os.PathLike[str],
    name: str,
) -> Iterator[_PaperObservationWindow | None]:
    """Reserve publication before a local paper order changes its book."""
    admitted = require_paper_write_lanes(
        path,
        name,
        lane_sets=(("runner", "execution"),),
    )
    if not admitted:
        yield None
        return
    directory = Path(os.path.abspath(os.fspath(path)))
    with RootContext.open(directory.parent.parent) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.registry_lock(timeout=MAX_LOCK_WAIT_SECONDS):
                _verify_paper_transition_inventory(root, admission, name)
                window = _PaperObservationWindow(root)
                previous = _current_paper_observation()
                _OBSERVATION_CONTEXT.window = window
                try:
                    yield window
                finally:
                    window.close_observations()
                    _OBSERVATION_CONTEXT.window = previous


@contextmanager
def paper_inventory_transition(
    path: str | os.PathLike[str],
    name: str,
    *,
    lane_sets: tuple[tuple[str, ...], ...],
    paper_root: bool = False,
) -> Iterator[PaperInventoryTransition | None]:
    from hedge_fund.paper.ledger import LedgerError

    admitted = require_paper_write_lanes(
        path,
        name,
        lane_sets=lane_sets,
        paper_root=paper_root,
    )
    if not admitted:
        yield None
        return
    candidate = Path(os.path.abspath(os.fspath(path)))
    root_path = candidate.parent if paper_root else candidate.parent.parent
    with RootContext.open(root_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.registry_lock(timeout=MAX_LOCK_WAIT_SECONDS):
                record, actual_before = _verify_paper_transition_inventory(root, admission, name)
                key = _resource_key(name)
                transition = PaperInventoryTransition(
                    key,
                    record["heads"].get(key),
                    root=root,
                    base=(candidate.name,) if paper_root else (candidate.parent.name, candidate.name),
                )
                yield transition
                try:
                    _publish_expected_ledger_head(
                        root,
                        name,
                        transition=transition,
                        actual_before=actual_before,
                        admission=admission,
                    )
                    _verify_paper_transition_inventory(root, admission, name)
                except (HandoverError, LedgerError, OSError, RootPathError, ValueError) as exc:
                    raise LedgerHeadPublicationError("paper head publication failed; offline reconciliation is required") from exc


def _publish_expected_ledger_head(
    root: RootContext,
    name: str,
    *,
    transition: PaperInventoryTransition,
    actual_before: dict[str, dict[str, Any]],
    admission: AdmissionCoordinator,
) -> None:
    if admission.root is not root or not admission.lane_is_held("registry"):
        raise HandoverError("root registry admission is required")
    key = _resource_key(name)
    record, actual = _verify_paper_transition_inventory(root, admission, name, transition=transition)
    if record["heads"].get(key) != transition.previous_entry:
        raise LedgerDrift("paper ledger head changed before publication")
    expected = transition.expected_entry
    if actual.get(key) != expected:
        raise LedgerDrift("paper mutation differs from its expected head")
    other_keys = (actual_before.keys() | actual.keys()) - {key}
    if any(actual_before.get(other) != actual.get(other) for other in other_keys):
        raise LedgerDrift("another paper ledger changed during publication")
    heads = dict(record["heads"])
    heads[key] = expected
    updated = _new_record(
        root,
        mode=record["mode"],
        heads=dict(sorted(heads.items())),
        attestation=record["attestation"],
        created_at=record["created_at"],
    )
    require_write_authority(root)
    _write_record(root, updated)


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
            require_write_authority(root)
            _write_record(root, updated)
    except AdmissionError as exc:
        raise HandoverError("ledger head inventory update is unavailable") from exc


def transition_ledger_inventory(
    root: RootContext,
    name: str,
    *,
    expected_heads: dict[str, dict[str, Any]],
    expected_entry: dict[str, Any] | None,
    new_entry: dict[str, Any] | None,
    admission: AdmissionCoordinator,
) -> None:
    """Commit one journaled lifecycle head transition under registry CAS."""
    if not isinstance(admission, AdmissionCoordinator) or admission.root is not root:
        raise HandoverError("root admission is required")
    if not admission.lane_is_held("registry"):
        raise HandoverError("root registry admission is required")
    key = _resource_key(name)
    if not isinstance(expected_heads, dict) or any(not isinstance(head_key, str) or not _valid_inventory_entry(head_key, entry) for head_key, entry in expected_heads.items()):
        raise HandoverError("expected ledger inventory is invalid")
    try:
        record = require_enrollment(root)
        current_heads = record["heads"]
        current_entry = current_heads.get(key)
        if expected_heads.get(key) != expected_entry:
            raise LedgerDrift("reviewed lifecycle entry does not match its journal")
        # Other enrolled funds may legitimately advance while this object is interrupted.
        updated_heads = dict(current_heads)
        if new_entry is None:
            updated_heads.pop(key, None)
        else:
            if not _valid_inventory_entry(key, new_entry):
                raise HandoverError("new ledger head is invalid")
            updated_heads[key] = new_entry
        actual_heads = build_head_inventory(root)
        if actual_heads != updated_heads:
            raise LedgerDrift("paper ledger inventory differs from the reviewed lifecycle transition")
        if current_heads == updated_heads and current_entry == new_entry:
            return
        if current_entry != expected_entry:
            raise LedgerDrift("paper ledger inventory changed before lifecycle transition")
        updated = _new_record(
            root,
            mode=record["mode"],
            heads=dict(sorted(updated_heads.items())),
            attestation=record["attestation"],
            created_at=record["created_at"],
        )
        require_write_authority(root)
        _write_record(root, updated)
    except (AdmissionError, OSError, RootPathError) as exc:
        raise HandoverError("ledger lifecycle transition is unavailable") from exc


def recover_stale_reservation(
    root: RootContext,
    fund: str,
    *,
    evidence: dict[str, str],
    operator_attestation: str,
) -> dict[str, Any]:
    """Record operator recovery after root-wide participant quiescence."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    _resource_key(fund)
    evidence = _validated_recovery_evidence(evidence)
    if operator_attestation != STALE_RECOVERY_ATTESTATION:
        raise HandoverError("explicit stale-reservation recovery attestation is required")

    from hedge_fund.runtime.owned_runner import OwnedRunnerError, read_runner_record, runner_key, validate_runner_state, write_runner_record

    runner_identity = runner_key(fund)
    try:
        migration = RootMigrationLease.acquire(root, timeout=0)
    except WriterConflict as exc:
        raise HandoverError("root participant is active; stale recovery requires quiescence") from exc
    try:
        enrollment = require_write_authority(root)
        verify_root_inventory(root, record=enrollment)
        if _has_legacy_runner_pid(root.path):
            raise HandoverError("legacy runner marker blocks stale recovery")
        state = read_runner_record(root, fund, "state")
        if not validate_runner_state(root, fund, state):
            raise HandoverError("runner owner identity is unavailable for recovery")
        if state is None:
            raise HandoverError("runner reservation is not present")

        prior_owner = _prior_owner_identity(state)
        recovery_path = f"{RECOVERY_ROOT}/{runner_identity}/{state['nonce_hash']}.json"
        try:
            existing = read_stale_recovery(root, fund)
        except HandoverError:
            raise
        if state["status"] not in {"starting", "running", "stopping"}:
            if state["status"] == "failed" and state["reason"] == "operator-stale-recovery" and existing is not None and existing["evidence"] == evidence and existing["operator_attestation"] == operator_attestation:
                return existing
            raise HandoverError("runner reservation is not stale and active")

        if existing is None:
            heads = build_head_inventory(root)
            if heads != enrollment["heads"]:
                raise LedgerDrift("ledger head changed; stale recovery is blocked")
            body = {
                "schema": 1,
                "protocol_version": PROTOCOL_VERSION,
                "build_id": code_version(),
                "root": root_binding(root),
                "fund": state["fund"],
                "inventory_digest": _digest(heads),
                "prior_owner_identity": prior_owner,
                "evidence": evidence,
                "operator_attestation": operator_attestation,
                "recovered_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            }
            record = {**body, "record_digest": _digest(body)}
            _validate_stale_recovery_record(root, fund, record, require_local_scope=True)
            root.mkdir(f"{RECOVERY_ROOT}/{runner_identity}", parents=True, mode=0o700)
            try:
                root.file_info(recovery_path)
            except FileNotFoundError:
                _write_stale_recovery_record(root, recovery_path, record)
            else:
                raise HandoverError("recovery record already exists but is unreadable")
        else:
            if existing["prior_owner_identity"] != prior_owner or existing["evidence"] != evidence or existing["operator_attestation"] != operator_attestation:
                raise HandoverError("existing recovery record does not match this owner and attestation")
            record = existing

        state["status"] = "failed"
        state["reason"] = "operator-stale-recovery"
        state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        write_runner_record(root, fund, "state", state)
        return record
    except HandoverError:
        raise
    except (AdmissionError, OwnedRunnerError, OSError, RootPathError, ValueError) as exc:
        raise HandoverError("stale-reservation recovery failed closed") from exc
    finally:
        migration.close()


def read_stale_recovery(root: RootContext, fund: str) -> dict[str, Any] | None:
    """Read one validated recovery record by fund identity."""
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    from hedge_fund.runtime.owned_runner import read_runner_record, runner_key

    name = _resource_key(fund)
    key = runner_key(fund)
    try:
        state_record = read_runner_record(root, fund, "state")
    except (OSError, RootPathError, ValueError):
        raise HandoverError("runner state is unavailable for recovery lookup") from None
    if state_record is None:
        return None
    nonce_hash = state_record.get("nonce_hash") if isinstance(state_record, dict) else None
    if not isinstance(nonce_hash, str) or not _SHA256.fullmatch(nonce_hash):
        raise HandoverError("runner state identity is invalid for recovery lookup")
    relative = f"{RECOVERY_ROOT}/{key}/{nonce_hash}.json"
    try:
        info = root.file_info(relative)
    except FileNotFoundError:
        return None
    except (OSError, RootPathError) as exc:
        raise HandoverError("stale recovery record is unavailable") from exc
    if info.size <= 0 or info.size > 64 * 1024:
        raise HandoverError("stale recovery record size is invalid")
    try:
        record = json.loads(root.read_bytes(relative).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RootPathError):
        raise HandoverError("stale recovery record is malformed") from None
    _validate_stale_recovery_record(root, name, record)
    return record


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


def _validated_recovery_evidence(value: object) -> dict[str, str]:
    fields = {"owner_quiescence", "legacy_exclusion"}
    if not isinstance(value, dict) or set(value) != fields:
        raise HandoverError("stale recovery evidence is incomplete")
    evidence: dict[str, str] = {}
    for field in sorted(fields):
        text = value[field]
        if not isinstance(text, str) or not text.strip() or len(text) > 2048 or any(ord(char) < 32 and char not in "\t\n\r" for char in text):
            raise HandoverError("stale recovery evidence is invalid")
        evidence[field] = text.strip()
    return evidence


def _prior_owner_identity(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": state["status"],
        "nonce_hash": state["nonce_hash"],
        "created_at": state["created_at"],
        "pid": state["pid"],
        "process_identity": state["process_identity"],
    }


def _same_process_scope(identity: dict[str, Any]) -> bool:
    """Bind a recorded owner to this host boot and process namespace, using the native identity scheme."""
    from hedge_fund.runtime.ownership import process_identity, ProcessIdentityError

    try:
        current = process_identity(os.getpid())
    except (OSError, ProcessIdentityError):
        return False
    return identity["host"].casefold() == current["host"].casefold() and identity["namespace"] == current["namespace"]


def _validate_stale_recovery_record(
    root: RootContext,
    fund: str,
    record: object,
    *,
    require_local_scope: bool = False,
) -> None:
    fields = {
        "schema",
        "protocol_version",
        "build_id",
        "root",
        "fund",
        "inventory_digest",
        "prior_owner_identity",
        "evidence",
        "operator_attestation",
        "recovered_at",
        "record_digest",
    }
    if not isinstance(record, dict) or set(record) != fields:
        raise HandoverError("stale recovery record fields are invalid")
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or type(record["protocol_version"]) is not int
        or record["protocol_version"] != PROTOCOL_VERSION
        or record["build_id"] != code_version()
        or record["root"] != root_binding(root)
        or not isinstance(record["fund"], str)
        or _resource_key(record["fund"]) != _resource_key(fund)
        or not isinstance(record["inventory_digest"], str)
        or not _SHA256.fullmatch(record["inventory_digest"])
        or record["operator_attestation"] != STALE_RECOVERY_ATTESTATION
        or not _valid_timestamp(record["recovered_at"])
    ):
        raise HandoverError("stale recovery record identity is invalid")
    evidence = _validated_recovery_evidence(record["evidence"])
    if evidence != record["evidence"]:
        raise HandoverError("stale recovery evidence is not canonical")
    prior = record["prior_owner_identity"]
    if not isinstance(prior, dict) or set(prior) != {"status", "nonce_hash", "created_at", "pid", "process_identity"}:
        raise HandoverError("stale recovery owner identity is invalid")
    if prior["status"] not in {"starting", "running", "stopping"} or not isinstance(prior["nonce_hash"], str) or not _SHA256.fullmatch(prior["nonce_hash"]) or not _valid_timestamp(prior["created_at"]):
        raise HandoverError("stale recovery owner identity is invalid")
    process_identity = prior["process_identity"]
    if prior["pid"] is None:
        if prior["status"] != "starting" or process_identity is not None:
            raise HandoverError("stale recovery process identity is invalid")
    elif (
        type(prior["pid"]) is not int
        or prior["pid"] <= 0
        or not isinstance(process_identity, dict)
        or set(process_identity) != {"pid", "creation_time", "image", "host", "namespace"}
        or type(process_identity.get("pid")) is not int
        or process_identity["pid"] != prior["pid"]
        or any(not isinstance(process_identity.get(key), str) or not process_identity[key] for key in ("creation_time", "image", "host", "namespace"))
        or (require_local_scope and not _same_process_scope(process_identity))
    ):
        raise HandoverError("stale recovery process identity is invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    if not isinstance(record["record_digest"], str) or record["record_digest"] != _digest(body):
        raise HandoverError("stale recovery record digest is invalid")
    root.revalidate()


def _write_stale_recovery_record(
    root: RootContext,
    relative: str,
    record: StaleReservationRecoveryRecord,
) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > 64 * 1024:
        raise HandoverError("stale recovery record exceeds its storage bound")
    root.write_bytes(relative, payload, mode=stat.S_IRUSR | stat.S_IWUSR)


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


def _fresh_bootstrap_only(root: RootContext, *, allowed_files: tuple[str, ...] = ()) -> bool:
    expected_dirs = {
        Path("runtime"),
        Path("runtime/private"),
        Path("runtime/private/v1"),
        Path("runtime/private/v1/admission"),
        Path("runtime/private/v1/admission/v1"),
    }
    expected_files = {
        Path(f"{LOCK_DIRECTORY}/owner.lock"),
        *(Path(relative) for relative in allowed_files),
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


def _private_stage_layout_matches(root: RootContext, *, allowed_files: tuple[str, ...] = ()) -> bool:
    expected_dirs = {
        Path("runtime"),
        Path("runtime/private"),
        Path(PRIVATE_ROOT),
        Path(f"{PRIVATE_ROOT}/admission"),
        Path(f"{PRIVATE_ROOT}/admission/v1"),
    }
    expected_files = {
        Path(OWNER_LOCK_PATH),
        *(Path(relative) for relative in allowed_files),
    }
    observed_dirs: set[Path] = set()
    observed_files: set[Path] = set()

    def fail_walk(_exc: OSError) -> None:
        raise HandoverError("private staging area cannot be inspected")

    try:
        root.revalidate()
        for directory, subdirs, files in os.walk(root.path, followlinks=False, onerror=fail_walk):
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
        root.revalidate()
    except (OSError, RootPathError, HandoverError):
        return False
    return observed_dirs.issubset(expected_dirs) and observed_files.issubset(expected_files)


def _has_legacy_runner_pid(root: Path) -> bool:
    def fail_walk(exc: OSError) -> None:
        raise exc

    for directory, subdirs, files in os.walk(root, followlinks=False, onerror=fail_walk):
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
    if not isinstance(key, str) or not isinstance(entry, dict):
        return False
    attestation_fields = {"kind", "subject", "attestation_digest"}
    if set(entry) == attestation_fields:
        try:
            subject = entry["subject"]
            parts = _relative_parts(subject, allow_protected=True) if isinstance(subject, str) else ()
            return entry["kind"] == "stale-marker-retirement" and bool(parts) and "/".join(parts) == subject and parts[0] in RELOCATED_TOP_LEVEL and parts[-1] == "runner.pid" and isinstance(entry["attestation_digest"], str) and _SHA256.fullmatch(entry["attestation_digest"]) is not None and key == _attestation_inventory_key(entry["kind"], subject)
        except (HandoverError, RootPathError, TypeError, ValueError):
            return False
    base_fields = {"name", "deployment_digest", "last_session", "head_hash", "session_count"}
    if frozenset(entry) not in {frozenset(base_fields), frozenset(base_fields | {"attestation_refs"})}:
        return False
    name = entry["name"]
    if not isinstance(name, str):
        return False
    try:
        if _relocation_resource_key(name) != key:
            return False
    except (TypeError, RootPathError):
        return False
    if name in _PROTECTED_RESOURCE_NAMES:
        refs = entry.get("attestation_refs")
        if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict) or set(refs[0]) != {"kind", "subject", "record_digest"} or refs[0]["kind"] != "protected-fund-inclusion" or refs[0]["subject"] != name or not isinstance(refs[0]["record_digest"], str) or _SHA256.fullmatch(refs[0]["record_digest"]) is None:
            return False
    elif "attestation_refs" in entry:
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
        return _relocation_resource_key(name)
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
