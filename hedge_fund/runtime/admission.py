"""Root-scoped cross-process writer admission."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import math
import os
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager, ExitStack
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootConfigurationError,
    RootContext,
    RootPathError,
    UnsupportedFilesystemError,
)

PROTOCOL_VERSION = 1
LOCK_DIRECTORY = f"{PRIVATE_ROOT}/admission/v{PROTOCOL_VERSION}"
OWNER_LOCK_PATH = f"{LOCK_DIRECTORY}/owner.lock"
OPERATION_SERVICE_LANE = "service:operations"
MAX_LOCK_WAIT_SECONDS = 5.0
MAX_CONTROL_WAIT_SECONDS = 0.5
_LOCK_POLL_SECONDS = 0.01
_LOCK_STATE = threading.local()
_LOCAL_LANES_GUARD = threading.Lock()
_LOCAL_LANES: dict[tuple[tuple[int, ...], str], deque[threading.Event]] = {}
_APPROVAL_SEAL = object()
_ADMISSION_PROCESS_ID = os.getpid()
_T = TypeVar("_T")


class AdmissionError(RuntimeError):
    """Admission input or OS primitive failed."""


class OwnershipUnknown(AdmissionError):
    """Root writer ownership is not verified."""


class WriterConflict(AdmissionError):
    """Another writer owns the requested lane."""


class PaperControlBusy(WriterConflict):
    """The paper control lane was occupied before admission."""


class PaperPreflightBusy(PaperControlBusy):
    """Paper work was not started because control admission was occupied."""


class PaperAuditObservationBusy(WriterConflict):
    """A stable audit observation could not acquire its lane."""


def _require_current_process() -> None:
    if os.getpid() != _ADMISSION_PROCESS_ID:
        raise OwnershipUnknown("Admission requires a fresh interpreter after fork.")


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("internal", ctypes.c_size_t),
        ("internal_high", ctypes.c_size_t),
        ("offset", ctypes.c_ulong),
        ("offset_high", ctypes.c_ulong),
        ("event", ctypes.c_void_p),
    ]


class RootOwnerLease:
    """Hold shared root participation for one process lifetime."""

    def __init__(
        self,
        root: RootContext,
        handle,
        token,
        *,
        exclusive: bool = False,
    ) -> None:
        self._root = root
        self._root_identity = root._root_identity
        self._handle = handle
        self._token = token
        self._exclusive = exclusive
        self._closed = False
        self._guard = threading.Lock()

    @classmethod
    def acquire(
        cls,
        root: RootContext,
        *,
        timeout: float = 0.0,
    ) -> RootOwnerLease:
        _require_current_process()
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        if not root.verify_private_storage():
            raise OwnershipUnknown("Private root storage is not verified.")
        _require_protocol_native_authority(root)
        root.mkdir(LOCK_DIRECTORY, parents=True, mode=0o700)
        handle = root.open_lock_file(OWNER_LOCK_PATH, mode=0o600)
        token = None
        try:
            token = _acquire_os_lock(handle, wait, exclusive=False)
            root.revalidate()
            _require_protocol_native_authority(root)
            return cls(root, handle, token)
        except BaseException:
            try:
                if token is not None:
                    _release_os_lock(handle, token)
            except Exception:
                pass
            finally:
                handle.close()
            raise

    def is_open_for(self, root: RootContext) -> bool:
        _require_current_process()
        with self._guard:
            return not (self._closed or self._exclusive or self._root is not root or root._root_identity != self._root_identity)

    def matches(self, root: RootContext) -> bool:
        if not self.is_open_for(root):
            return False
        if not root.verify_private_storage():
            return False
        try:
            _require_protocol_native_authority(root)
        except Exception:
            return False
        return True

    def close(self) -> None:
        if os.getpid() != _ADMISSION_PROCESS_ID:
            handle = self._handle
            self._handle = None
            self._token = None
            self._closed = True
            if handle is not None:
                handle.close()
            return
        with self._guard:
            if self._closed:
                return
            self._closed = True
            handle = self._handle
            token = self._token
            self._handle = None
            self._token = None
        try:
            _release_os_lock(handle, token)
        finally:
            handle.close()

    def __enter__(self) -> RootOwnerLease:
        _require_current_process()
        with self._guard:
            if self._closed:
                raise OwnershipUnknown("Root owner lease is closed.")
        if not self._root.verify_private_storage():
            raise OwnershipUnknown("Private root storage is not verified.")
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


class RootMigrationLease(RootOwnerLease):
    """Hold exclusive root ownership during offline enrollment."""

    @classmethod
    def acquire(
        cls,
        root: RootContext,
        *,
        timeout: float = 0.0,
    ) -> RootMigrationLease:
        _require_current_process()
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        if not root.verify_private_storage():
            raise OwnershipUnknown("Private root storage is not verified.")
        root.mkdir(LOCK_DIRECTORY, parents=True, mode=0o700)
        handle = root.open_lock_file(OWNER_LOCK_PATH, mode=0o600)
        token = None
        try:
            token = _acquire_os_lock(handle, wait, exclusive=True)
            root.revalidate()
            return cls(root, handle, token, exclusive=True)
        except BaseException:
            try:
                if token is not None:
                    _release_os_lock(handle, token)
            except Exception:
                pass
            finally:
                handle.close()
            raise


RootParticipantLease = RootOwnerLease


def _require_protocol_native_authority(root: RootContext) -> None:
    """Enrollment alone is not write authority."""
    from hedge_fund.runtime.handover import (
        HandoverError,
        require_write_authority,
        WriteAuthorityDenied,
    )

    try:
        require_write_authority(root)
    except WriteAuthorityDenied as exc:
        raise OwnershipUnknown(str(exc)) from None
    except HandoverError:
        raise
    except Exception as exc:
        raise OwnershipUnknown(f"root write authority is unavailable ({type(exc).__name__})") from None


class AdmissionCoordinator:
    """Acquire versioned root and deployment writer lanes."""

    def __init__(
        self,
        root: RootContext,
        *,
        owner_lease: RootOwnerLease | None = None,
    ) -> None:
        _require_current_process()
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")
        if owner_lease is not None and not isinstance(owner_lease, RootOwnerLease):
            raise TypeError("a root owner lease is required")
        root.revalidate()
        self._root = root
        self._owner_lease = owner_lease

    @property
    def root(self) -> RootContext:
        return self._root

    @contextmanager
    def registry_lock(self, *, timeout: float = 0.0) -> Iterator[None]:
        self._require_verified_owner()
        _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        if self.lane_is_held("registry"):
            yield
            return
        with self._lock("registry", timeout=timeout):
            yield

    @contextmanager
    def operation_recovery_lease(self, *, timeout: float = 0.0) -> Iterator[None]:
        """Exclude live participating services while unfinished operations are fenced."""
        with self._lock(OPERATION_SERVICE_LANE, timeout=timeout):
            yield

    @contextmanager
    def operation_service_lease(self, *, timeout: float = 0.0) -> Iterator[None]:
        """Hold shared root admission for a writable operation service lifetime."""
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        relative = f"{LOCK_DIRECTORY}/{_lock_filename(OPERATION_SERVICE_LANE)}"
        self._require_open_owner_lease()
        self._root.mkdir(LOCK_DIRECTORY, parents=True, mode=0o700)
        handle = self._root.open_lock_file(relative, mode=0o600)
        acquired = False
        token = None
        try:
            self._root.revalidate()
            token = _acquire_os_lock(handle, wait, exclusive=False)
            acquired = True
            self._require_verified_owner()
            yield
        finally:
            try:
                if acquired and os.getpid() == _ADMISSION_PROCESS_ID:
                    _release_os_lock(handle, token)
            finally:
                handle.close()

    def require_root_owner(self) -> None:
        self._require_verified_owner()

    def lane_is_held(self, lane: str, identity: str | None = None) -> bool:
        if lane == "registry":
            key = "registry"
        elif lane in {"deployment", "runner", "execution", "control", "halt", "audit", "research", "service"} and identity is not None:
            key = f"{lane}:{_resource_identity(identity)}"
        else:
            raise AdmissionError("admission lane is invalid")
        filename = f"{LOCK_DIRECTORY}/{_lock_filename(key)}"
        return _thread_lock_key(self._root, filename) in _held_locks()

    @contextmanager
    def registry_read_lock(self, *, timeout: float = 0.0) -> Iterator[None]:
        """Serialize snapshots without writer-ownership authority."""
        relative = f"{LOCK_DIRECTORY}/{_lock_filename('registry')}"
        with _existing_read_lock(self._root, relative, "registry", timeout=timeout):
            yield

    @contextmanager
    def deployment_lock(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        with self._lock(f"deployment:{resource}", timeout=timeout):
            yield

    @contextmanager
    def runner_reservation(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        with self._lock(f"runner:{resource}", timeout=timeout):
            yield

    @contextmanager
    def execution_lease(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        with self._lock(f"execution:{resource}", timeout=timeout):
            yield

    @contextmanager
    def control_lane(
        self,
        identity: str,
        *,
        timeout: float = 0.1,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        wait = _validate_timeout(timeout, MAX_CONTROL_WAIT_SECONDS)
        with self._lock(f"control:{resource}", timeout=wait):
            yield

    @contextmanager
    def halt_lane(
        self,
        identity: str,
        *,
        timeout: float = 0.1,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        wait = _validate_timeout(timeout, MAX_CONTROL_WAIT_SECONDS)
        with self._lock(f"halt:{resource}", timeout=wait):
            yield

    @contextmanager
    def audit_lane(
        self,
        identity: str,
        *,
        timeout: float = MAX_CONTROL_WAIT_SECONDS,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        wait = _validate_timeout(timeout, MAX_CONTROL_WAIT_SECONDS)
        with self._lock(f"audit:{resource}", timeout=wait):
            yield

    @contextmanager
    def research_lane(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        with self._lock(f"research:{resource}", timeout=timeout):
            yield

    @contextmanager
    def manual_session(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        deadline = time.monotonic() + wait
        with ExitStack() as stack:
            stack.enter_context(
                self._lock(
                    f"deployment:{resource}",
                    timeout=_remaining(deadline),
                )
            )
            stack.enter_context(self._lock(f"runner:{resource}", timeout=0.0))
            stack.enter_context(
                self._lock(
                    f"execution:{resource}",
                    timeout=_remaining(deadline),
                )
            )
            yield

    @contextmanager
    def multi_deployment(
        self,
        identities: list[str] | tuple[str, ...],
        *,
        timeout: float = 0.0,
    ) -> Iterator[tuple[str, ...]]:
        if not isinstance(identities, (list, tuple)) or not identities:
            raise TypeError("deployment identities must be a non-empty text list")
        ordered = tuple(_resource_identity(identity) for identity in identities)
        if len(set(ordered)) != len(ordered):
            raise AdmissionError("deployment identities must be unique")
        ordered = tuple(sorted(ordered))
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        deadline = time.monotonic() + wait
        with ExitStack() as stack:
            stack.enter_context(self._lock("registry", timeout=_remaining(deadline)))
            for identity in ordered:
                stack.enter_context(
                    self._lock(
                        f"deployment:{identity}",
                        timeout=_remaining(deadline),
                    )
                )
            yield ordered

    @contextmanager
    def _lock(self, key: str, *, timeout: float) -> Iterator[None]:
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        filename = _lock_filename(key)
        relative = f"{LOCK_DIRECTORY}/{filename}"
        lock_key = _thread_lock_key(self._root, relative)
        held = _held_locks()
        with _local_lane(lock_key, wait) as deadline:
            # Cheap pre-check; full authority is verified once the OS lock is held.
            self._require_open_owner_lease()
            self._root.mkdir(LOCK_DIRECTORY, parents=True, mode=0o700)
            handle = self._root.open_lock_file(
                relative,
                mode=0o600,
            )
            acquired = False
            token = None
            try:
                self._root.revalidate()
                token = _acquire_os_lock(handle, _remaining(deadline))
                acquired = True
                self._require_verified_owner()
                held[lock_key] = 1
                yield
            finally:
                held.pop(lock_key, None)
                try:
                    if acquired and os.getpid() == _ADMISSION_PROCESS_ID:
                        _release_os_lock(handle, token)
                finally:
                    handle.close()

    def _require_open_owner_lease(self) -> None:
        lease = self._owner_lease
        if lease is None or not lease.is_open_for(self._root):
            raise OwnershipUnknown("Writer ownership is unknown.")

    def _require_verified_owner(self) -> None:
        if self._owner_lease is None or not self._owner_lease.matches(self._root):
            raise OwnershipUnknown("Writer ownership is unknown.")
        self._root.revalidate()


@contextmanager
def _existing_read_lock(
    root: RootContext,
    relative: str,
    label: str,
    *,
    timeout: float,
) -> Iterator[None]:
    _require_current_process()
    wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
    root.revalidate()
    lock_key = _thread_lock_key(root, relative)
    held = _held_locks()
    if lock_key in held:
        held[lock_key] += 1
        try:
            yield
        finally:
            held[lock_key] -= 1
        return
    with _local_lane(lock_key, wait) as deadline:
        try:
            root.file_info(relative)
            handle = root.open_lock_file(relative, mode=0o600)
        except (OSError, RootPathError) as exc:
            raise AdmissionError(f"existing {label} lock is unavailable") from exc
        acquired = False
        token = None
        try:
            root.revalidate()
            token = _acquire_os_lock(handle, _remaining(deadline))
            acquired = True
            root.revalidate()
            held[lock_key] = 1
            yield
        finally:
            held.pop(lock_key, None)
            try:
                if acquired and os.getpid() == _ADMISSION_PROCESS_ID:
                    _release_os_lock(handle, token)
            finally:
                handle.close()


def paper_audit_snapshot(
    path: str | os.PathLike[str],
    identity: str,
    read: Callable[[], _T],
) -> _T:
    directory = Path(os.path.abspath(os.fspath(path)))
    if not directory.is_dir():
        try:
            result = read()
        except (OSError, UnicodeError, ValueError):
            if not directory.is_dir():
                raise
        else:
            if not directory.is_dir():
                return result

    def snapshot(root: RootContext, relative: str) -> _T:
        def lock_exists() -> bool:
            try:
                root.file_info(relative)
            except FileNotFoundError:
                return False
            return True

        if _thread_lock_key(root, relative) in _held_locks():
            return read()
        if not lock_exists():
            try:
                result = read()
            except (OSError, UnicodeError, ValueError):
                if not lock_exists():
                    raise
            else:
                if not lock_exists():
                    return result
        with ExitStack() as stack:
            try:
                stack.enter_context(_existing_read_lock(root, relative, "paper audit", timeout=MAX_CONTROL_WAIT_SECONDS))
            except WriterConflict as exc:
                raise PaperAuditObservationBusy("Paper audit observation is occupied.") from exc
            return read()

    if _is_paper_component(directory.parent.name):
        from hedge_fund.runtime.handover import root_is_enrolled

        resource = _resource_identity(identity)
        if _resource_identity(directory.name) != resource:
            raise AdmissionError("paper path identity does not match the fund")
        with RootContext.open(directory.parent.parent) as root:
            if root_is_enrolled(root):
                relative = f"{LOCK_DIRECTORY}/{_lock_filename(f'audit:{resource}')}"
                return snapshot(root, relative)
    with RootContext.open(directory) as root:
        return snapshot(root, ".paper-audit.lock")


@contextmanager
def root_registry_writer(
    root: RootContext,
    admission: AdmissionCoordinator | None = None,
    *,
    timeout: float = 0.0,
    allow_prepared_lifecycle: bool = False,
) -> Iterator[AdmissionCoordinator]:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if admission is not None and (not isinstance(admission, AdmissionCoordinator) or admission.root is not root):
        raise TypeError("admission must match the RootContext")
    if type(allow_prepared_lifecycle) is not bool:
        raise TypeError("lifecycle inventory option must be a boolean")
    owner = None
    coordinator = admission
    if coordinator is None:
        owner = RootOwnerLease.acquire(root, timeout=0)
        coordinator = AdmissionCoordinator(root, owner_lease=owner)

    def verify_inventory() -> None:
        if allow_prepared_lifecycle:
            from hedge_fund.runtime.handover import verify_cache_write_inventory

            verify_cache_write_inventory(root, coordinator)
        else:
            from hedge_fund.runtime.handover import verify_root_inventory

            verify_root_inventory(root)

    try:
        _require_protocol_native_authority(root)
        if coordinator.lane_is_held("registry"):
            verify_inventory()
            yield coordinator
        else:
            with coordinator.registry_lock(timeout=timeout):
                verify_inventory()
                yield coordinator
    finally:
        if owner is not None:
            owner.close()


@contextmanager
def paper_execution_transition(
    path: str | os.PathLike[str],
    identity: str,
) -> Iterator[None]:
    """Keep standalone paper executions distinct from control updates."""
    admitted = require_paper_write_lanes(
        path,
        identity,
        lane_sets=(("runner", "execution"),),
        verify_inventory=True,
    )
    if admitted:
        yield
    else:
        with _standalone_paper_lane(path, ".paper-execution.lock", timeout=0.0, reentrant=False):
            yield


@contextmanager
def paper_control_transition(
    path: str | os.PathLike[str],
    identity: str,
) -> Iterator[None]:
    """Serialize cooperating control updates for a paper fund."""
    admitted = require_paper_write_lanes(
        path,
        identity,
        lane_sets=(("control",), ("runner", "execution")),
    )
    if not admitted:
        entered = False
        try:
            with _standalone_paper_control(path):
                entered = True
                yield
        except WriterConflict as exc:
            if entered:
                raise
            raise PaperControlBusy("Paper control admission is occupied.") from exc
        return
    directory = Path(os.path.abspath(os.fspath(path)))
    with RootContext.open(directory.parent.parent) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            if admission.lane_is_held("control", identity):
                yield
            else:
                entered = False
                try:
                    with admission.control_lane(identity, timeout=MAX_CONTROL_WAIT_SECONDS):
                        entered = True
                        yield
                except WriterConflict as exc:
                    if entered:
                        raise
                    raise PaperControlBusy("Paper control admission is occupied.") from exc


@contextmanager
def paper_halt_transition(
    path: str | os.PathLike[str],
    identity: str,
) -> Iterator[None]:
    with _paper_auxiliary_lane(
        path,
        identity,
        lane="halt",
        lane_sets=(("halt",), ("control",), ("deployment",), ("runner", "execution")),
        standalone_lock=".paper-halt.lock",
    ):
        yield


@contextmanager
def paper_audit_transition(
    path: str | os.PathLike[str],
    identity: str,
    *,
    halt_event: bool = False,
) -> Iterator[None]:
    lane_sets = (("control",), ("runner", "execution"))
    if halt_event:
        lane_sets = (("halt",),) + lane_sets
    with _paper_auxiliary_lane(
        path,
        identity,
        lane="audit",
        lane_sets=lane_sets,
        standalone_lock=".paper-audit.lock",
    ):
        yield


@contextmanager
def _paper_auxiliary_lane(
    path: str | os.PathLike[str],
    identity: str,
    *,
    lane: str,
    lane_sets: tuple[tuple[str, ...], ...],
    standalone_lock: str,
) -> Iterator[None]:
    admitted = require_paper_write_lanes(path, identity, lane_sets=lane_sets)
    if not admitted:
        with _standalone_paper_lane(path, standalone_lock, timeout=MAX_CONTROL_WAIT_SECONDS, reentrant=True):
            yield
        return
    directory = Path(os.path.abspath(os.fspath(path)))
    with RootContext.open(directory.parent.parent) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            if admission.lane_is_held(lane, identity):
                yield
            elif lane == "halt":
                with admission.halt_lane(identity, timeout=MAX_CONTROL_WAIT_SECONDS):
                    yield
            else:
                with admission.audit_lane(identity, timeout=MAX_CONTROL_WAIT_SECONDS):
                    yield


@contextmanager
def _standalone_paper_control(path: str | os.PathLike[str]) -> Iterator[None]:
    with _standalone_paper_lane(path, ".paper-control.lock", timeout=MAX_CONTROL_WAIT_SECONDS, reentrant=True):
        yield


@contextmanager
def _standalone_paper_lane(
    path: str | os.PathLike[str],
    relative: str,
    *,
    timeout: float,
    reentrant: bool,
) -> Iterator[None]:
    from hedge_fund import paths

    _require_current_process()
    directory = Path(os.path.abspath(os.fspath(path)))
    configured = paths.root_context(required=False)
    if configured is not None:
        try:
            directory.relative_to(configured.path)
        except ValueError:
            pass
        else:
            raise AdmissionError("Standalone paper admission cannot bypass a configured root.")
    with RootContext.open(directory) as root:
        lock_key = _thread_lock_key(root, relative)
        held = _held_locks()
        if lock_key in held:
            if not reentrant:
                raise WriterConflict("Admission lane is occupied.")
            held[lock_key] += 1
            try:
                yield
            finally:
                held[lock_key] -= 1
            return
        with _local_lane(lock_key, timeout) as deadline:
            handle = root.open_lock_file(relative, mode=0o600)
            acquired = False
            token = None
            try:
                root.revalidate()
                token = _acquire_os_lock(handle, _remaining(deadline))
                acquired = True
                root.revalidate()
                held[lock_key] = 1
                yield
            finally:
                held.pop(lock_key, None)
                try:
                    if acquired and os.getpid() == _ADMISSION_PROCESS_ID:
                        _release_os_lock(handle, token)
                finally:
                    handle.close()


class PaperApprovalAdmission:
    """A scoped inventory proof tied to the held registry and control lanes."""

    def __init__(self, admission: AdmissionCoordinator, identity: str, *, _seal: object) -> None:
        if _seal is not _APPROVAL_SEAL:
            raise TypeError("paper verdict proofs require verified admission")
        self._admission = admission
        self._identity = _resource_identity(identity)
        self._active = True

    def matches(self, path: str | os.PathLike[str], identity: str) -> bool:
        try:
            self._admission.require_root_owner()
        except AdmissionError:
            return False
        candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
        expected = os.path.normcase(os.path.abspath(os.fspath(self._admission.root.path / "paper" / identity)))
        return self._active and _resource_identity(identity) == self._identity and candidate == expected and self._admission.lane_is_held("registry") and self._admission.lane_is_held("control", identity)


@contextmanager
def paper_approval_transition(
    admission: AdmissionCoordinator,
    identity: str,
) -> Iterator[PaperApprovalAdmission]:
    """Verify inventory before taking the short-lived human verdict lane."""
    if not isinstance(admission, AdmissionCoordinator):
        raise TypeError("paper verdict admission requires a root coordinator")
    if admission.lane_is_held("control", identity):
        raise WriterConflict("paper verdict admission must precede the control lane")
    from hedge_fund.runtime.handover import verify_root_inventory

    with admission.registry_lock(timeout=MAX_LOCK_WAIT_SECONDS):
        verify_root_inventory(admission.root)
        with admission.control_lane(identity, timeout=MAX_CONTROL_WAIT_SECONDS):
            proof = PaperApprovalAdmission(admission, identity, _seal=_APPROVAL_SEAL)
            try:
                yield proof
            finally:
                proof._active = False


def require_paper_write_lanes(
    path: str | os.PathLike[str],
    identity: str,
    *,
    lane_sets: tuple[tuple[str, ...], ...],
    paper_root: bool = False,
    verify_inventory: bool = False,
) -> bool:
    """Require one held lane set for a conventional enrolled paper path."""
    if not isinstance(path, (str, os.PathLike)):
        raise AdmissionError("paper path must be text or path-like")
    if type(paper_root) is not bool or type(verify_inventory) is not bool:
        raise AdmissionError("paper admission flags must be booleans")
    if not isinstance(lane_sets, tuple) or not lane_sets:
        raise AdmissionError("paper admission lane sets are invalid")
    allowed_lanes = {"deployment", "runner", "execution", "control", "halt"}
    for lane_set in lane_sets:
        if not isinstance(lane_set, tuple) or not lane_set or any(not isinstance(lane, str) for lane in lane_set) or len(set(lane_set)) != len(lane_set) or any(lane not in allowed_lanes for lane in lane_set):
            raise AdmissionError("paper admission lane sets are invalid")
    try:
        candidate = Path(os.path.abspath(os.fspath(path)))
    except (TypeError, ValueError, OSError) as exc:
        raise AdmissionError("paper path is invalid") from exc
    if paper_root:
        if not _is_paper_component(candidate.name):
            return False
        root_path = candidate.parent
    else:
        if not _is_paper_component(candidate.parent.name):
            return False
        resource = _resource_identity(identity)
        if _resource_identity(candidate.name) != resource:
            raise AdmissionError("paper path identity does not match the fund")
        root_path = candidate.parent.parent
    if paper_root:
        resource = _resource_identity(identity)

    try:
        root = RootContext.open(root_path)
    except RootConfigurationError as exc:
        if isinstance(exc.__cause__, FileNotFoundError) and not _handover_marker_may_exist(root_path):
            return False
        raise OwnershipUnknown("Conventional paper root identity is invalid.") from exc
    except UnsupportedFilesystemError as exc:
        if _handover_marker_may_exist(root_path):
            raise OwnershipUnknown("Enrolled paper root identity is unavailable.") from exc
        return False
    except RootPathError as exc:
        raise OwnershipUnknown("Conventional paper root identity is invalid.") from exc
    except OSError as exc:
        if _handover_marker_may_exist(root_path):
            raise OwnershipUnknown("Enrolled paper root identity is unavailable.") from exc
        return False

    try:
        from hedge_fund.runtime.handover import (
            require_enrollment,
            root_is_enrolled,
            verify_root_inventory,
        )

        if not root_is_enrolled(root):
            for marker in (LOCK_DIRECTORY, OWNER_LOCK_PATH):
                try:
                    root.file_info(marker)
                except FileNotFoundError:
                    continue
                except Exception as exc:
                    raise OwnershipUnknown("Paper admission state is unavailable.") from exc
                raise OwnershipUnknown("Admission state exists without a handover record.")
            return False
        try:
            private_storage_verified = root.verify_private_storage()
        except Exception as exc:
            raise OwnershipUnknown("Private root storage cannot be verified.") from exc
        if not private_storage_verified:
            raise OwnershipUnknown("Private root storage is not verified.")
        try:
            require_enrollment(root)
        except Exception as exc:
            raise OwnershipUnknown("Paper root enrollment is invalid.") from exc
        _require_protocol_native_authority(root)
        if verify_inventory:
            try:
                verify_root_inventory(root)
            except Exception as exc:
                raise AdmissionError("Paper ledger inventory differs from offline handover.") from exc

        coordinator = AdmissionCoordinator(root)
        if not any(all(coordinator.lane_is_held(lane, resource) for lane in lane_set) for lane_set in lane_sets):
            raise WriterConflict("Enrolled paper write requires a held admission lane.")
        return True
    finally:
        root.close()


def _resource_identity(identity: str) -> str:
    if not isinstance(identity, str):
        raise AdmissionError("deployment identity must be text")
    try:
        return ensure_unique_resource_name(identity, [])
    except RootPathError as exc:
        raise AdmissionError("deployment identity is invalid.") from exc


def _validate_timeout(value: float, maximum: float) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0 or value > maximum:
        raise ValueError(f"timeout must be between 0 and {maximum} seconds")
    return float(value)


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


@contextmanager
def _local_lane(key: tuple[tuple[int, ...], str], timeout: float) -> Iterator[float]:
    _require_current_process()
    # FIFO prevents local pollers from barging; OS lock still grants authority.
    deadline = time.monotonic() + timeout
    ticket = threading.Event()
    with _LOCAL_LANES_GUARD:
        queue = _LOCAL_LANES.setdefault(key, deque())
        queue.append(ticket)
        if len(queue) == 1:
            ticket.set()
    try:
        if not ticket.wait(_remaining(deadline)):
            raise WriterConflict("Admission lane is occupied.")
        yield deadline
    finally:
        if os.getpid() == _ADMISSION_PROCESS_ID:
            with _LOCAL_LANES_GUARD:
                queue.remove(ticket)
                if queue:
                    queue[0].set()
                else:
                    del _LOCAL_LANES[key]


def _lock_filename(key: str) -> str:
    if key == "registry":
        return "registry.lock"
    if not isinstance(key, str) or ":" not in key:
        raise AdmissionError("admission lane is invalid")
    namespace, identity = key.split(":", 1)
    if namespace not in {"deployment", "runner", "execution", "control", "halt", "audit", "research", "service"} or not identity:
        raise AdmissionError("admission lane is invalid")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{namespace}-{digest}.lock"


def _acquire_os_lock(handle, timeout: float, *, exclusive: bool = True):
    deadline = time.monotonic() + timeout
    while True:
        acquired, token = _try_acquire_os_lock(handle, exclusive=exclusive)
        if acquired:
            return token
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WriterConflict("Admission lane is occupied.")
        time.sleep(min(_LOCK_POLL_SECONDS, remaining))


def _try_acquire_os_lock(handle, *, exclusive: bool = True) -> tuple[bool, object | None]:
    if handle.fd is not None and sys.platform.startswith("linux"):
        import fcntl

        try:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle.fd, mode | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return False, None
            raise
        return True, None
    if handle.handle is not None and os.name == "nt":
        kernel32 = _windows_lock_api()
        overlapped = _Overlapped()
        flags = 0x00000001
        if exclusive:
            flags |= 0x00000002
        if kernel32.LockFileEx(
            ctypes.c_void_p(handle.handle),
            flags,
            0,
            1,
            0,
            ctypes.byref(overlapped),
        ):
            return True, overlapped
        error = ctypes.get_last_error()
        if error == 33:
            return False, None
        raise ctypes.WinError(error)
    raise UnsupportedFilesystemError("OS lock primitive is unsupported")


def _release_os_lock(handle, token) -> None:
    if handle.fd is not None and sys.platform.startswith("linux"):
        import fcntl

        fcntl.flock(handle.fd, fcntl.LOCK_UN)
        return
    if handle.handle is not None and os.name == "nt":
        if not isinstance(token, _Overlapped):
            raise AdmissionError("Windows lock state is invalid")
        kernel32 = _windows_lock_api()
        if not kernel32.UnlockFileEx(
            ctypes.c_void_p(handle.handle),
            0,
            1,
            0,
            ctypes.byref(token),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return
    raise UnsupportedFilesystemError("OS unlock primitive is unsupported")


def _windows_lock_api():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    overlapped = ctypes.POINTER(_Overlapped)
    kernel32.LockFileEx.argtypes = [
        handle,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        overlapped,
    ]
    kernel32.LockFileEx.restype = ctypes.c_int
    kernel32.UnlockFileEx.argtypes = [
        handle,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        overlapped,
    ]
    kernel32.UnlockFileEx.restype = ctypes.c_int
    return kernel32


def _held_locks() -> dict[tuple[tuple[int, ...], str], int]:
    _require_current_process()
    held = getattr(_LOCK_STATE, "held", None)
    if held is None:
        held = {}
        _LOCK_STATE.held = held
    return held


def _thread_lock_key(root: RootContext, relative: str) -> tuple[tuple[int, ...], str]:
    return tuple(root._root_identity), relative


def _is_paper_component(value: str) -> bool:
    return value == "paper" or (os.name == "nt" and value.casefold() == "paper")


def _handover_marker_may_exist(root_path: Path) -> bool:
    marker = root_path / PRIVATE_ROOT / "handover.json"
    try:
        marker.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True
