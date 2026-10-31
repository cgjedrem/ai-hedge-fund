"""Fixed-root identity, confined I/O."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import re
import stat
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath


class RootPathError(ValueError):
    """Path escapes or root identity changes."""


class RootConfigurationError(RootPathError):
    """Explicit root missing or invalid."""


class UnsupportedFilesystemError(RootPathError):
    """Filesystem identity or access primitives unsupported."""


@dataclass(frozen=True)
class FilesystemIdentity:
    filesystem: str
    device: str
    local: bool
    cloud_synced: bool


@dataclass(frozen=True)
class RootFileInfo:
    size: int
    mtime_ns: int


@dataclass
class RootLockHandle:
    """Owned root-relative lock-file handle."""

    fd: int | None = field(default=None, repr=False)
    handle: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (self.fd is None) == (self.handle is None):
            raise ValueError("exactly one OS handle is required")

    def close(self) -> None:
        if self.fd is not None:
            descriptor = self.fd
            self.fd = None
            os.close(descriptor)
        if self.handle is not None:
            handle = self.handle
            self.handle = None
            _close_windows_handles((handle,))

    def __enter__(self) -> RootLockHandle:
        if self.fd is None and self.handle is None:
            raise RootPathError("lock-file handle is closed")
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


class _ByHandleInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_ulong),
        ("creation", _FileTime),
        ("access", _FileTime),
        ("write", _FileTime),
        ("volume", ctypes.c_ulong),
        ("size_high", ctypes.c_ulong),
        ("size_low", ctypes.c_ulong),
        ("links", ctypes.c_ulong),
        ("index_high", ctypes.c_ulong),
        ("index_low", ctypes.c_ulong),
    ]


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.GetFileInformationByHandle.argtypes = [handle, ctypes.POINTER(_ByHandleInfo)]
    kernel32.GetFileInformationByHandle.restype = ctypes.c_int
    kernel32.ReadFile.argtypes = [
        handle,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_void_p,
    ]
    kernel32.ReadFile.restype = ctypes.c_int
    kernel32.WriteFile.argtypes = [
        handle,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_void_p,
    ]
    kernel32.WriteFile.restype = ctypes.c_int
    kernel32.FlushFileBuffers.argtypes = [handle]
    kernel32.FlushFileBuffers.restype = ctypes.c_int
    kernel32.SetFileInformationByHandle.argtypes = [
        handle,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel32.SetFileInformationByHandle.restype = ctypes.c_int
    return kernel32


def validate_filesystem(identity: FilesystemIdentity) -> None:
    if not isinstance(identity, FilesystemIdentity) or not isinstance(identity.filesystem, str) or not isinstance(identity.device, str) or type(identity.local) is not bool or type(identity.cloud_synced) is not bool:
        raise UnsupportedFilesystemError("filesystem identity is unavailable")
    filesystem = identity.filesystem.casefold()
    if filesystem not in {"ntfs", "ext4"} or not identity.device or identity.local is not True or identity.cloud_synced is not False:
        raise UnsupportedFilesystemError("root requires local NTFS or ext4")


def _canonical_component_identity(base: str) -> str:
    if base.casefold().endswith(".yaml"):
        base = base[:-5]
    elif base.casefold().endswith(".yml"):
        base = base[:-4]
    return unicodedata.normalize("NFC", base).casefold()


def _resource_identity(name: str) -> str:
    parts = _relative_parts(name)
    if len(parts) != 1:
        raise RootPathError("resource name must be one path component")
    identity = _canonical_component_identity(parts[0])
    if not identity:
        raise RootPathError("resource name is empty")
    return identity


def ensure_unique_resource_name(name: str, existing: list[str] | tuple[str, ...]) -> str:
    if not isinstance(name, str) or not isinstance(existing, (list, tuple)):
        raise RootPathError("resource names must be a text list")
    if any(not isinstance(candidate, str) for candidate in existing):
        raise RootPathError("resource names must be text")
    identity = _resource_identity(name)
    if any(_resource_identity(candidate) == identity for candidate in existing):
        raise RootPathError("resource name already exists")
    return identity


def _validate_component(part: str) -> None:
    if not part or part in {".", ".."}:
        raise RootPathError("path traversal is not allowed")
    if part[-1] in {".", " "}:
        raise RootPathError("trailing dots and spaces are not allowed")
    if "\x00" in part or ":" in part:
        raise RootPathError("invalid path component")
    device_name = part.split(".", 1)[0].upper()
    if device_name in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", device_name):
        raise RootPathError("reserved path component")
    if _canonical_component_identity(part) in {
        "watchtower",
        "watchtower-weekly",
        "umbrella",
    }:
        raise RootPathError("protected path identity")


def _relative_parts(value: str | os.PathLike[str]) -> tuple[str, ...]:
    try:
        text = os.fspath(value)
    except TypeError:
        raise RootPathError("relative path must be text") from None
    if not isinstance(text, str) or not text or "\x00" in text:
        raise RootPathError("relative path must be non-empty text")
    windows = PureWindowsPath(text)
    if Path(text).is_absolute() or windows.is_absolute() or windows.drive or text.startswith(("/", "\\")):
        raise RootPathError("absolute paths are not allowed")
    parts = tuple(re.split(r"[\\/]", text))
    for part in parts:
        _validate_component(part)
    return parts


def _root_parts(value: str | os.PathLike[str]) -> tuple[Path, tuple[str, ...], str]:
    try:
        raw = os.fspath(value)
    except TypeError:
        raise RootConfigurationError("an explicit absolute root is required") from None
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise RootConfigurationError("an explicit absolute root is required")

    if os.name == "nt":
        if raw.startswith(("\\\\", "//")):
            raise RootConfigurationError("UNC and device roots are unsupported")
        windows = PureWindowsPath(raw)
        if not windows.is_absolute() or not windows.drive:
            raise RootConfigurationError("root must be an absolute local path")
        parts = windows.parts[1:]
        anchor = windows.anchor
        candidate = Path(os.path.normpath(raw))
    else:
        path = Path(raw)
        if not path.is_absolute():
            raise RootConfigurationError("root must be an absolute local path")
        if ".." in path.parts:
            raise RootConfigurationError("root traversal is not allowed")
        parts = path.parts[1:]
        anchor = path.anchor
        candidate = Path(os.path.normpath(raw))

    if not parts:
        raise RootConfigurationError("filesystem root cannot be a data root")
    try:
        for part in parts:
            _validate_component(part)
    except RootPathError as exc:
        raise RootConfigurationError(str(exc)) from None
    return candidate, tuple(parts), anchor


def _namespace_identity() -> str:
    if sys.platform.startswith("linux"):
        try:
            return f"pid:{os.readlink('/proc/self/ns/pid')};mnt:{os.readlink('/proc/self/ns/mnt')}"
        except OSError:
            return "unknown"
    return f"host:{platform.node()}"


def _boot_identity() -> str:
    if sys.platform.startswith("linux"):
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        except OSError:
            return "unknown"
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        boot_epoch = int(__import__("time").time() - kernel32.GetTickCount64() / 1000)
        return f"{platform.node()}:{boot_epoch}"
    return "unknown"


@dataclass
class RootContext:
    path: Path
    filesystem: FilesystemIdentity
    device_identity: str
    host_identity: str
    boot_identity: str
    namespace_identity: str
    _root_identity: tuple[int, ...] = field(repr=False)
    _fd: int | None = field(default=None, repr=False)
    _handles: tuple[int, ...] = field(default=(), repr=False)
    _closed: bool = field(default=False, repr=False)

    @classmethod
    def open(cls, root: str | os.PathLike[str] | None) -> RootContext:
        if root is None:
            raise RootConfigurationError("an explicit absolute root is required")
        path, parts, anchor = _root_parts(root)
        if os.name == "nt":
            try:
                handles = _open_windows_chain(path, parts, anchor)
            except FileNotFoundError as exc:
                raise RootConfigurationError("root must already exist") from exc
            try:
                identity = _windows_handle_identity(handles[-1])
                filesystem, device = _windows_filesystem_identity(path, anchor)
                validate_filesystem(filesystem)
            except BaseException:
                _close_windows_handles(handles)
                raise
            return cls(
                path=path,
                filesystem=filesystem,
                device_identity=device,
                host_identity=platform.node(),
                boot_identity=_boot_identity(),
                namespace_identity=_namespace_identity(),
                _root_identity=identity,
                _handles=handles,
            )
        if sys.platform.startswith("linux"):
            try:
                fd = _open_posix_chain(parts)
            except FileNotFoundError as exc:
                raise RootConfigurationError("root must already exist") from exc
            try:
                filesystem, device = _posix_filesystem_identity(fd)
                validate_filesystem(filesystem)
                info = os.fstat(fd)
            except BaseException:
                os.close(fd)
                raise
            return cls(
                path=path,
                filesystem=filesystem,
                device_identity=device,
                host_identity=platform.node(),
                boot_identity=_boot_identity(),
                namespace_identity=_namespace_identity(),
                _root_identity=(info.st_dev, info.st_ino),
                _fd=fd,
            )
        raise UnsupportedFilesystemError("platform filesystem primitives are unsupported")

    @property
    def dotenv_path(self) -> Path:
        return self.path / ".env"

    def __enter__(self) -> RootContext:
        self._require_open()
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._handles:
            _close_windows_handles(self._handles)
            self._handles = ()

    def revalidate(self) -> None:
        self._require_open()
        if os.name == "nt":
            try:
                current = _open_windows_chain(
                    self.path,
                    PureWindowsPath(str(self.path)).parts[1:],
                    PureWindowsPath(str(self.path)).anchor,
                )
            except OSError as exc:
                raise RootPathError("root identity changed") from exc
            try:
                if _windows_handle_identity(current[-1]) != self._root_identity:
                    raise RootPathError("root identity changed")
            finally:
                _close_windows_handles(current)
            return

        parts = Path(self.path).parts[1:]
        try:
            current_fd = _open_posix_chain(parts)
        except OSError as exc:
            raise RootPathError("root identity changed") from exc
        try:
            info = os.fstat(current_fd)
            if (info.st_dev, info.st_ino) != self._root_identity:
                raise RootPathError("root identity changed")
        finally:
            os.close(current_fd)

    def resolve(self, relative: str | os.PathLike[str]) -> Path:
        parts = _relative_parts(relative)
        self.revalidate()
        return self.path.joinpath(*parts)

    def read_bytes(self, relative: str | os.PathLike[str]) -> bytes:
        parts = _relative_parts(relative)
        self.revalidate()
        if os.name == "nt":
            result = _windows_read_relative(self._handles[-1], parts)
        else:
            result = _posix_read_relative(self._fd, parts)
        self.revalidate()
        return result

    def write_bytes(
        self,
        relative: str | os.PathLike[str],
        data: bytes,
        *,
        mode: int = 0o600,
    ) -> Path:
        parts = _relative_parts(relative)
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise ValueError("mode must contain permission bits")
        self.revalidate()
        if os.name == "nt":
            _windows_write_relative(self._handles[-1], parts, data)
        else:
            _posix_write_relative(self._fd, parts, data, mode)
        self.revalidate()
        return self.path.joinpath(*parts)

    def mkdir(
        self,
        relative: str | os.PathLike[str],
        *,
        parents: bool = True,
        mode: int = 0o700,
    ) -> Path:
        parts = _relative_parts(relative)
        if type(parents) is not bool:
            raise TypeError("parents must be a bool")
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise ValueError("mode must contain permission bits")
        self.revalidate()
        if os.name == "nt":
            _windows_mkdir_relative(self._handles[-1], parts, parents=parents)
        else:
            _posix_mkdir_relative(self._fd, parts, parents=parents, mode=mode)
        self.revalidate()
        return self.path.joinpath(*parts)

    def file_info(self, relative: str | os.PathLike[str]) -> RootFileInfo:
        parts = _relative_parts(relative)
        self.revalidate()
        if os.name == "nt":
            result = _windows_file_info(self._handles[-1], parts)
        else:
            result = _posix_file_info(self._fd, parts)
        self.revalidate()
        return result

    def open_lock_file(
        self,
        relative: str | os.PathLike[str],
        *,
        mode: int = 0o600,
    ) -> RootLockHandle:
        parts = _relative_parts(relative)
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise ValueError("mode must contain permission bits")
        self.revalidate()
        if os.name == "nt":
            handle = _windows_open_lock_relative(self._handles[-1], parts)
            try:
                self.revalidate()
            except BaseException:
                _close_windows_handles((handle,))
                raise
            return RootLockHandle(handle=handle)
        if sys.platform.startswith("linux"):
            descriptor = _posix_open_lock_relative(self._fd, parts, mode)
            try:
                self.revalidate()
            except BaseException:
                os.close(descriptor)
                raise
            return RootLockHandle(fd=descriptor)
        raise UnsupportedFilesystemError("platform lock handles are unsupported")

    def _require_open(self) -> None:
        if self._closed:
            raise RootPathError("root context is closed")


def _open_posix_chain(parts: tuple[str, ...]) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise UnsupportedFilesystemError("no-follow directory opens are unsupported")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open("/", flags)
    try:
        for part in parts:
            child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        return parent
    except OSError as exc:
        os.close(parent)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RootPathError("root contains a reparse path") from exc
        raise


def _posix_filesystem_identity(fd: int) -> tuple[FilesystemIdentity, str]:
    if not sys.platform.startswith("linux"):
        raise UnsupportedFilesystemError("only Linux ext4 is supported")
    buffer = ctypes.create_string_buffer(256)
    libc = ctypes.CDLL(None, use_errno=True)
    fstatfs = libc.fstatfs
    fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
    fstatfs.restype = ctypes.c_int
    if fstatfs(fd, ctypes.byref(buffer)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    magic = ctypes.c_long.from_buffer(buffer).value
    filesystem = "ext4" if magic == 0xEF53 else f"unknown:{magic:x}"
    info = os.fstat(fd)
    return (
        FilesystemIdentity(
            filesystem=filesystem,
            device=str(info.st_dev),
            local=filesystem == "ext4",
            cloud_synced=False,
        ),
        str(info.st_dev),
    )


def _posix_parent_fd(root_fd: int, parents: tuple[str, ...]) -> int:
    if root_fd is None:
        raise RootPathError("root context is closed")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.dup(root_fd)
    try:
        for part in parents:
            child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        return parent
    except OSError as exc:
        os.close(parent)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RootPathError("reparse paths are not allowed") from exc
        raise


def _posix_mkdir_relative(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    parents: bool,
    mode: int,
) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            create = parents or index == len(parts) - 1
            if create:
                try:
                    os.mkdir(part, mode, dir_fd=parent)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RootPathError("reparse paths are not allowed") from exc
        raise
    finally:
        os.close(parent)


def _posix_file_info(root_fd: int, parts: tuple[str, ...]) -> RootFileInfo:
    parent_fd = _posix_parent_fd(root_fd, parts[:-1])
    try:
        info = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise RootPathError("only regular files can be inspected")
        return RootFileInfo(size=info.st_size, mtime_ns=info.st_mtime_ns)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RootPathError("reparse paths are not allowed") from exc
        raise
    finally:
        os.close(parent_fd)


def _posix_read_relative(root_fd: int, parts: tuple[str, ...]) -> bytes:
    parent_fd = _posix_parent_fd(root_fd, parts[:-1])
    try:
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise RootPathError("reparse paths are not allowed") from exc
            raise
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise RootPathError("only regular files can be read")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    finally:
        os.close(parent_fd)


def _posix_open_lock_relative(
    root_fd: int | None,
    parts: tuple[str, ...],
    mode: int,
) -> int:
    if root_fd is None:
        raise RootPathError("root context is closed")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise UnsupportedFilesystemError("no-follow file opens are unsupported")
    parent_fd = _posix_parent_fd(root_fd, parts[:-1])
    descriptor = None
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(parts[-1], flags, mode, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RootPathError("only regular lock files are supported")
        os.fchmod(descriptor, mode)
        os.set_inheritable(descriptor, False)
        result = descriptor
        descriptor = None
        return result
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RootPathError("reparse paths are not allowed") from exc
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _posix_write_relative(
    root_fd: int,
    parts: tuple[str, ...],
    data: bytes,
    mode: int,
) -> None:
    parent_fd = _posix_parent_fd(root_fd, parts[:-1])
    temporary = f".{parts[-1]}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    descriptor = None
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            mode,
            dir_fd=parent_fd,
        )
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary,
            parts[-1],
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(parent_fd)


def _open_windows_chain(
    path: Path,
    parts: tuple[str, ...],
    anchor: str,
) -> tuple[int, ...]:
    kernel32 = _kernel32()
    handle_type = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        handle_type,
    ]
    kernel32.CreateFileW.restype = handle_type
    root = kernel32.CreateFileW(
        anchor,
        0x0001 | 0x0080 | 0x00100000,
        0x0001 | 0x0002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    if root == handle_type(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    handles = [root]
    try:
        _validate_windows_handle(root, directory=True)
        parent = root
        for part in parts:
            child = _nt_open_child(parent, part, directory=True)
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            handles.append(child)
            parent = child
        return tuple(handles)
    except BaseException:
        _close_windows_handles(tuple(handles))
        raise


def _windows_handle_identity(handle: int) -> tuple[int, ...]:
    kernel32 = _kernel32()
    info = _ByHandleInfo()
    if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    identity = (info.volume, (info.index_high << 32) | info.index_low)
    return identity


def _validate_windows_handle(handle: int, *, directory: bool) -> None:
    kernel32 = _kernel32()
    info = _ByHandleInfo()
    if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    is_directory = bool(info.attributes & 0x10)
    if info.attributes & 0x400 or is_directory != directory:
        raise RootPathError("reparse or mismatched path component")


def _nt_open_child(
    parent: int,
    name: str,
    *,
    directory: bool,
    disposition: int = 1,
    access: int | None = None,
) -> int:
    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ushort),
            ("maximum_length", ctypes.c_ushort),
            ("buffer", ctypes.c_wchar_p),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("root_directory", ctypes.c_void_p),
            ("object_name", ctypes.POINTER(UnicodeString)),
            ("attributes", ctypes.c_ulong),
            ("security_descriptor", ctypes.c_void_p),
            ("security_quality_of_service", ctypes.c_void_p),
        ]

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_ulong,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = ctypes.c_ulong
    handle = ctypes.c_void_p()
    name_buffer = ctypes.create_unicode_buffer(name)
    encoded_length = len(name.encode("utf-16-le"))
    unicode_name = UnicodeString(
        encoded_length,
        encoded_length + 2,
        ctypes.cast(name_buffer, ctypes.c_wchar_p),
    )
    attributes = ObjectAttributes(
        ctypes.sizeof(ObjectAttributes),
        parent,
        ctypes.pointer(unicode_name),
        0x40 | 0x1000,
        None,
        None,
    )
    status_block = IoStatusBlock()
    if access is None:
        access = 0x0001 | 0x0080 | 0x00100000
    options = 0x00200000 | 0x00000020 | (0x00000001 if directory else 0x00000040)
    status = ntdll.NtCreateFile(
        ctypes.byref(handle),
        access,
        ctypes.byref(attributes),
        ctypes.byref(status_block),
        None,
        0,
        0x0001 | 0x0002,
        disposition,
        options,
        None,
        0,
    )
    if status < 0:
        dos_error = ntdll.RtlNtStatusToDosError(status)
        if dos_error in {errno.ELOOP, 4390, 4392}:
            raise RootPathError("reparse paths are not allowed")
        raise ctypes.WinError(dos_error)
    return handle.value


def _windows_mkdir_relative(
    root_handle: int,
    parts: tuple[str, ...],
    *,
    parents: bool,
) -> None:
    parent = root_handle
    owned_parent = None
    try:
        for index, part in enumerate(parts):
            create = parents or index == len(parts) - 1
            child = _nt_open_child(
                parent,
                part,
                directory=True,
                disposition=3 if create else 1,
            )
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            if owned_parent is not None:
                _close_windows_handles((owned_parent,))
            owned_parent = child
            parent = child
    finally:
        if owned_parent is not None:
            _close_windows_handles((owned_parent,))


def _windows_file_info(
    root_handle: int,
    parts: tuple[str, ...],
) -> RootFileInfo:
    parent = root_handle
    owned_parent = None
    try:
        for part in parts[:-1]:
            child = _nt_open_child(parent, part, directory=True)
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            if owned_parent is not None:
                _close_windows_handles((owned_parent,))
            owned_parent = child
            parent = child
        handle = _nt_open_child(parent, parts[-1], directory=False)
        try:
            _validate_windows_handle(handle, directory=False)
            info = _ByHandleInfo()
            kernel32 = _kernel32()
            if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            ticks = (info.write.high << 32) | info.write.low
            return RootFileInfo(
                size=(info.size_high << 32) | info.size_low,
                mtime_ns=(ticks - 116444736000000000) * 100,
            )
        finally:
            _close_windows_handles((handle,))
    finally:
        if owned_parent is not None:
            _close_windows_handles((owned_parent,))


def _windows_filesystem_identity(
    path: Path,
    anchor: str,
) -> tuple[FilesystemIdentity, str]:
    kernel32 = _kernel32()
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetDriveTypeW.restype = ctypes.c_uint
    local = kernel32.GetDriveTypeW(anchor) == 3
    filesystem_name = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_ulong()
    maximum_component = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    kernel32.GetVolumeInformationW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_wchar_p,
        ctypes.c_ulong,
    ]
    if not kernel32.GetVolumeInformationW(
        anchor,
        None,
        0,
        ctypes.byref(serial),
        ctypes.byref(maximum_component),
        ctypes.byref(flags),
        filesystem_name,
        len(filesystem_name),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    cloud_synced = _windows_cloud_synced(path)
    identity = FilesystemIdentity(
        filesystem=filesystem_name.value,
        device=f"{anchor}:{serial.value:08x}",
        local=local,
        cloud_synced=cloud_synced,
    )
    return identity, identity.device


def _windows_cloud_synced(path: Path) -> bool:
    try:
        cloud_api = ctypes.WinDLL("CldApi.dll")
    except OSError as exc:
        raise UnsupportedFilesystemError("cloud-root detection is unavailable") from exc
    query = cloud_api.CfGetSyncRootInfoByPath
    query.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    query.restype = ctypes.c_long
    buffer = ctypes.create_string_buffer(4096)
    returned = ctypes.c_ulong()
    result = query(
        str(path),
        0,
        ctypes.byref(buffer),
        len(buffer),
        ctypes.byref(returned),
    )
    status = result & 0xFFFFFFFF
    if status == 0:
        return True
    if status == 0x80070186:
        return False
    raise UnsupportedFilesystemError("cloud-root status could not be verified")


def _windows_read_relative(root_handle: int, parts: tuple[str, ...]) -> bytes:
    parent = root_handle
    owned_parent = None
    try:
        for part in parts[:-1]:
            child = _nt_open_child(parent, part, directory=True)
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            if owned_parent is not None:
                _close_windows_handles((owned_parent,))
            owned_parent = child
            parent = child
        descriptor = _nt_open_child(parent, parts[-1], directory=False)
        try:
            _validate_windows_handle(descriptor, directory=False)
            return _windows_read_handle(descriptor)
        finally:
            _close_windows_handles((descriptor,))
    finally:
        if owned_parent is not None:
            _close_windows_handles((owned_parent,))


def _windows_open_lock_relative(root_handle: int, parts: tuple[str, ...]) -> int:
    parent = root_handle
    owned_parent = None
    descriptor = None
    try:
        for part in parts[:-1]:
            child = _nt_open_child(parent, part, directory=True)
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            if owned_parent is not None:
                _close_windows_handles((owned_parent,))
            owned_parent = child
            parent = child
        descriptor = _nt_open_child(
            parent,
            parts[-1],
            directory=False,
            disposition=3,
            access=0x0001 | 0x0002 | 0x0080 | 0x00100000,
        )
        _validate_windows_handle(descriptor, directory=False)
        result = descriptor
        descriptor = None
        return result
    finally:
        if descriptor is not None:
            _close_windows_handles((descriptor,))
        if owned_parent is not None:
            _close_windows_handles((owned_parent,))


def _windows_read_handle(handle: int) -> bytes:
    kernel32 = _kernel32()
    chunks = []
    while True:
        buffer = ctypes.create_string_buffer(65536)
        count = ctypes.c_ulong()
        if not kernel32.ReadFile(
            handle,
            buffer,
            len(buffer),
            ctypes.byref(count),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not count.value:
            return b"".join(chunks)
        chunks.append(buffer.raw[: count.value])


def _windows_write_relative(
    root_handle: int,
    parts: tuple[str, ...],
    data: bytes,
) -> None:
    parent = root_handle
    owned_parent = None
    temporary = f".{parts[-1]}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    handle = None
    try:
        for part in parts[:-1]:
            child = _nt_open_child(parent, part, directory=True)
            try:
                _validate_windows_handle(child, directory=True)
            except BaseException:
                _close_windows_handles((child,))
                raise
            if owned_parent is not None:
                _close_windows_handles((owned_parent,))
            owned_parent = child
            parent = child
        handle = _nt_open_child(
            parent,
            temporary,
            directory=False,
            disposition=2,
            access=0x40000000 | 0x00010000 | 0x00000080 | 0x00100000,
        )
        _windows_write_handle(handle, data)
        _windows_rename_handle(handle, parent, parts[-1])
    except BaseException:
        if handle is not None:
            _windows_delete_handle(handle)
        raise
    finally:
        if handle is not None:
            _close_windows_handles((handle,))
        if owned_parent is not None:
            _close_windows_handles((owned_parent,))


def _windows_write_handle(handle: int, data: bytes) -> None:
    kernel32 = _kernel32()
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + 65536]
        buffer = ctypes.create_string_buffer(chunk)
        written = ctypes.c_ulong()
        if not kernel32.WriteFile(
            handle,
            buffer,
            len(chunk),
            ctypes.byref(written),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if written.value == 0:
            raise OSError("short write")
        offset += written.value
    if not kernel32.FlushFileBuffers(handle):
        raise ctypes.WinError(ctypes.get_last_error())


def _windows_rename_handle(handle: int, parent: int, name: str) -> None:
    class IoStatusBlock(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    class RenameInformation(ctypes.Structure):
        _fields_ = [
            ("replace", ctypes.c_ubyte),
            ("root_directory", ctypes.c_void_p),
            ("name_length", ctypes.c_ulong),
            ("name", ctypes.c_wchar * 1),
        ]

    encoded = name.encode("utf-16-le")
    offset = RenameInformation.name.offset
    buffer = ctypes.create_string_buffer(offset + len(encoded))
    info = ctypes.cast(buffer, ctypes.POINTER(RenameInformation)).contents
    info.replace = 1
    info.root_directory = parent
    info.name_length = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + offset, encoded, len(encoded))
    status_block = IoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSetInformationFile.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
    ]
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = ctypes.c_ulong
    status = ntdll.NtSetInformationFile(
        handle,
        ctypes.byref(status_block),
        ctypes.byref(buffer),
        len(buffer),
        10,
    )
    if status < 0:
        dos_error = ntdll.RtlNtStatusToDosError(status)
        raise ctypes.WinError(dos_error)


def _windows_delete_handle(handle: int) -> None:
    class DispositionInfo(ctypes.Structure):
        _fields_ = [("delete_file", ctypes.c_ubyte)]

    info = DispositionInfo(1)
    kernel32 = _kernel32()
    if not kernel32.SetFileInformationByHandle(
        handle,
        4,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _close_windows_handles(handles: tuple[int, ...]) -> None:
    kernel32 = _kernel32()
    for handle in reversed(handles):
        if handle and not kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())
