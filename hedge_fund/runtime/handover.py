"""Offline root enrollment and ledger-head fencing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, TypedDict, TypeVar

from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    LOCK_DIRECTORY,
    MAX_LOCK_WAIT_SECONDS,
    OWNER_LOCK_PATH,
    PROTOCOL_VERSION,
    require_paper_write_lanes,
    RootMigrationLease,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootContext,
    RootPathError,
)

HANDOVER_PATH = f"{PRIVATE_ROOT}/handover.json"
RECOVERY_ROOT = f"{PRIVATE_ROOT}/recoveries"
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_INVENTORY_FUNDS = 10000
_MAX_LEDGER_SESSIONS = 1000000
OPERATOR_ATTESTATION = "I confirm every legacy writer and out-of-band writer is stopped and excluded " "from this root, and this ledger-head inventory is exact."
STALE_RECOVERY_ATTESTATION = "I confirm the runner owner is quiescent in this root namespace, legacy and out-of-band " "writers are excluded, and the recorded evidence is exact."


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
    """Raised when a root cannot hold protocol-native production write authority."""


PROTOCOL_NATIVE_MODES = frozenset({"fresh", "relocated"})
LEGACY_HOME_NAME = ".hedge-fund"
RELOCATED_TOP_LEVEL = ("mandates", "paper", "research")
_MAX_RELOCATION_FILES = 50000
_MAX_RELOCATION_FILE_BYTES = 256 * 1024 * 1024
_MAX_RELOCATION_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


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
            return (
                self._active
                and root._root_identity == self._root_identity
                and threading.get_ident() in self._borrowers
            )

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
    root.revalidate()
    return record


def write_authority(root: RootContext) -> dict[str, str | None]:
    """Classify whether this process may claim production write authority.

    Only protocol-native roots qualify: roots enrolled empty by this protocol or
    populated exclusively by a verified relocation import. An operator
    attestation is recorded evidence, not exclusion, so attested migrations are
    ``ownership-unknown`` and read-only. A protocol-native root that a shipped
    legacy writer could address (``<HOME>/.hedge-fund`` layout or alias) or that
    carries a legacy runner marker is also ``ownership-unknown``.
    """
    try:
        record = require_enrollment(root)
    except HandoverRequired:
        return {"authority": "unavailable", "reason": "handover-required"}
    except Exception:
        return {"authority": "unavailable", "reason": "handover-unavailable"}
    if record["mode"] not in PROTOCOL_NATIVE_MODES:
        return {"authority": "ownership-unknown", "reason": "attested-migration-read-only"}
    reason = None
    try:
        reason = legacy_reachability_reason(root)
    except Exception:
        reason = "legacy-reachability-unverified"
    if reason is not None:
        return {"authority": "ownership-unknown", "reason": reason}
    return {"authority": "protocol-native", "reason": None}


def require_write_authority(root: RootContext) -> dict[str, Any]:
    """Return the enrollment record only when write authority is protocol-native."""
    record = require_enrollment(root)
    if record["mode"] not in PROTOCOL_NATIVE_MODES:
        raise WriteAuthorityDenied("attested migration is read-only; relocate into a protocol-native root")
    try:
        reason = legacy_reachability_reason(root)
    except Exception as exc:
        raise WriteAuthorityDenied(f"root write authority is unverified ({type(exc).__name__})") from None
    if reason is not None:
        raise WriteAuthorityDenied(f"root write authority is ownership-unknown ({reason})")
    return record


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
    """Enroll an empty root before any demo or production data is written."""
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


def inspect_relocation_source(source: RootContext) -> dict[str, Any]:
    """Describe a source root for relocation without writing anything to it."""
    snapshot = _relocation_source_snapshot(source)
    return {
        "inventory_digest": snapshot["inventory_digest"],
        "content_digest": snapshot["content_digest"],
        "funds": len(snapshot["heads"]),
        "files": sum(1 for entry in snapshot["entries"].values() if entry["type"] == "file"),
        "bytes": sum(entry["size"] for entry in snapshot["entries"].values() if entry["type"] == "file"),
    }


def relocate_existing(
    target: RootContext,
    *,
    source: RootContext,
    expected_content_digest: str,
) -> dict[str, Any]:
    """Import a quiescent legacy root into an empty protocol-native target.

    The source is only read. Mandates, deployed paper funds and research are
    copied after a reviewed content digest matches, and the source must be
    byte-identical before and after the copy. Credentials, caches and runtime
    state never transfer. The target is the only root that gains write
    authority; the source remains whatever it was and is never enrolled.
    """
    if not isinstance(target, RootContext) or not isinstance(source, RootContext):
        raise TypeError("explicit RootContexts are required")
    if not isinstance(expected_content_digest, str) or not _SHA256.fullmatch(expected_content_digest):
        raise HandoverError("source content digest is invalid")
    target.revalidate()
    source.revalidate()
    _require_disjoint_roots(source, target)
    if _record_exists(target):
        raise EnrollmentInvalid("root already has a handover record")
    if any(target.path.iterdir()):
        raise HandoverError("relocation requires an empty target root")
    reason = legacy_reachability_reason(target)
    if reason is not None:
        raise WriteAuthorityDenied(f"relocation target must be unreachable by legacy writers ({reason})")
    before = _relocation_source_snapshot(source)
    if before["content_digest"] != expected_content_digest:
        raise HandoverError("source content changed; inspect the source and retry")
    target.prepare_private_storage()
    try:
        with RootMigrationLease.acquire(target, timeout=0):
            if not _fresh_bootstrap_only(target):
                raise HandoverError("target changed during relocation")
            for relative, entry in before["entries"].items():
                if entry["type"] == "dir":
                    target.mkdir(relative, parents=True)
                    continue
                data = source.read_bytes(relative)
                if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise HandoverError("source content changed during relocation")
                target.write_bytes(relative, data, mode=stat.S_IRUSR | stat.S_IWUSR)
            after = _relocation_source_snapshot(source)
            if after["content_digest"] != before["content_digest"] or after["heads"] != before["heads"]:
                raise HandoverError("source content changed during relocation")
            copied = _relocation_entries(target)
            if _digest(copied) != before["content_digest"]:
                raise HandoverError("relocated content does not match the source")
            heads = build_head_inventory(target)
            if heads != before["heads"]:
                raise HandoverError("relocated ledger heads do not match the source")
            record = _new_record(
                target,
                mode="relocated",
                heads=heads,
                attestation={
                    "source_inventory_digest": before["inventory_digest"],
                    "source_content_digest": before["content_digest"],
                },
            )
            _write_record(target, record)
            return require_enrollment(target)
    except WriterConflict as exc:
        raise HandoverError("another target participant is active") from exc


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
    if any(relative.rsplit("/", 1)[-1] == "runner.pid" for relative in entries):
        raise HandoverError("runner.pid is present; unknown owners block relocation")
    heads = build_head_inventory(source)
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
    return {
        "heads": heads,
        "inventory_digest": _digest(heads),
        "entries": entries,
        "content_digest": _digest(entries),
    }


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
                    data = root.read_bytes(relative)
                    entries[relative] = {"type": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                if len(entries) > _MAX_RELOCATION_FILES:
                    raise HandoverError("relocation source exceeds its bound")
    except HandoverError:
        raise
    except (OSError, RootPathError) as exc:
        raise HandoverError(f"relocation source is unreadable ({type(exc).__name__})") from None
    root.revalidate()
    return dict(sorted(entries.items()))


def build_head_inventory(root: RootContext) -> dict[str, dict[str, Any]]:
    """Replay every deployed paper ledger and return canonical head identities."""
    try:
        return _build_head_inventory(root)
    except OSError as exc:
        raise HandoverError(f"paper inventory is unavailable ({type(exc).__name__})") from None


def _build_head_inventory(root: RootContext) -> dict[str, dict[str, Any]]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    root.revalidate()
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
        if _has_legacy_runner_pid(directory):
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
        except LedgerError:
            raise LedgerInventoryCorrupt("paper ledger inventory is invalid") from None
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
                    raise LedgerHeadPublicationError(
                        "paper head publication failed; offline reconciliation is required"
                    ) from exc


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

    from hedge_fund.runtime.owned_runner import (
        OwnedRunnerError,
        read_runner_record,
        runner_key,
        validate_runner_state,
        write_runner_record,
    )

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
