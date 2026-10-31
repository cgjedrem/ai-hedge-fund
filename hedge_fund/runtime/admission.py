"""Root-scoped cross-process writer admission."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import math
import os
import sys
import time
from contextlib import contextmanager, ExitStack
from enum import Enum
from typing import Iterator

from hedge_fund.runtime.root import ensure_unique_resource_name, RootContext, RootPathError, UnsupportedFilesystemError

PROTOCOL_VERSION = 1
LOCK_DIRECTORY = f"runtime/admission/v{PROTOCOL_VERSION}"
MAX_LOCK_WAIT_SECONDS = 5.0
MAX_CONTROL_WAIT_SECONDS = 0.5
_LOCK_POLL_SECONDS = 0.01


class AdmissionError(RuntimeError):
    """Admission input or OS primitive failed."""


class OwnershipUnknown(AdmissionError):
    """Root writer ownership is not verified."""


class WriterConflict(AdmissionError):
    """Another writer owns the requested lane."""


class OwnershipState(str, Enum):
    VERIFIED = "verified"
    UNKNOWN = "unknown"
    LEGACY = "legacy"


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("internal", ctypes.c_size_t),
        ("internal_high", ctypes.c_size_t),
        ("offset", ctypes.c_ulong),
        ("offset_high", ctypes.c_ulong),
        ("event", ctypes.c_void_p),
    ]


class AdmissionCoordinator:
    """Acquire versioned root and deployment writer lanes."""

    def __init__(
        self,
        root: RootContext,
        *,
        ownership: OwnershipState = OwnershipState.UNKNOWN,
    ) -> None:
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")
        if not isinstance(ownership, OwnershipState):
            raise TypeError("ownership must be an OwnershipState")
        root.revalidate()
        self._root = root
        self._ownership = ownership

    @contextmanager
    def registry_lock(self, *, timeout: float = 0.0) -> Iterator[None]:
        with self._lock("registry", timeout=timeout):
            yield

    @contextmanager
    def registry_read_lock(self, *, timeout: float = 0.0) -> Iterator[None]:
        """Serialize snapshots without writer-ownership authority."""
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        relative = f"{LOCK_DIRECTORY}/{_lock_filename('registry')}"
        self._root.revalidate()
        try:
            self._root.file_info(relative)
            handle = self._root.open_lock_file(relative, mode=0o600)
        except Exception:
            raise AdmissionError("existing registry lock is unavailable") from None
        acquired = False
        token = None
        try:
            self._root.revalidate()
            token = _acquire_os_lock(handle, wait)
            acquired = True
            self._root.revalidate()
            yield
        finally:
            try:
                if acquired:
                    _release_os_lock(handle, token)
            finally:
                handle.close()

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
    def manual_session(
        self,
        identity: str,
        *,
        timeout: float = 0.0,
    ) -> Iterator[None]:
        resource = _resource_identity(identity)
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        with ExitStack() as stack:
            stack.enter_context(self._lock(f"runner:{resource}", timeout=0.0))
            stack.enter_context(self._lock(f"execution:{resource}", timeout=wait))
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
        self._require_verified_owner()
        wait = _validate_timeout(timeout, MAX_LOCK_WAIT_SECONDS)
        filename = _lock_filename(key)
        self._root.mkdir(LOCK_DIRECTORY, parents=True, mode=0o700)
        handle = self._root.open_lock_file(
            f"{LOCK_DIRECTORY}/{filename}",
            mode=0o600,
        )
        acquired = False
        token = None
        try:
            self._root.revalidate()
            token = _acquire_os_lock(handle, wait)
            acquired = True
            self._root.revalidate()
            yield
        finally:
            try:
                if acquired:
                    _release_os_lock(handle, token)
            finally:
                handle.close()

    def _require_verified_owner(self) -> None:
        if self._ownership is not OwnershipState.VERIFIED:
            raise OwnershipUnknown("Writer ownership is unknown.")
        self._root.revalidate()


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


def _lock_filename(key: str) -> str:
    if key == "registry":
        return "registry.lock"
    if not isinstance(key, str) or ":" not in key:
        raise AdmissionError("admission lane is invalid")
    namespace, identity = key.split(":", 1)
    if namespace not in {"deployment", "runner", "execution", "control"} or not identity:
        raise AdmissionError("admission lane is invalid")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{namespace}-{digest}.lock"


def _acquire_os_lock(handle, timeout: float):
    deadline = time.monotonic() + timeout
    while True:
        acquired, token = _try_acquire_os_lock(handle)
        if acquired:
            return token
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WriterConflict("Admission lane is occupied.")
        time.sleep(min(_LOCK_POLL_SECONDS, remaining))


def _try_acquire_os_lock(handle) -> tuple[bool, object | None]:
    if handle.fd is not None and sys.platform.startswith("linux"):
        import fcntl

        try:
            fcntl.flock(handle.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return False, None
            raise
        return True, None
    if handle.handle is not None and os.name == "nt":
        kernel32 = _windows_lock_api()
        overlapped = _Overlapped()
        if kernel32.LockFileEx(
            ctypes.c_void_p(handle.handle),
            0x00000001 | 0x00000002,
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
