"""Native process-incarnation identity for owned children."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


class ProcessIdentityError(RuntimeError):
    """Process identity could not be verified."""


_MAX_LINUX_IDENTITY_COUNTER = 2**64 - 1


def process_identity(pid: int) -> dict[str, Any]:
    if type(pid) is not int or pid <= 0:
        raise ProcessIdentityError("process identity input is invalid")
    if os.name == "nt":
        return _windows_process_identity(pid)
    if sys.platform.startswith("linux"):
        return _linux_process_identity(pid)
    raise ProcessIdentityError("process identity primitive is unsupported")


def current_process_identity() -> dict[str, Any]:
    return process_identity(os.getpid())


def identity_matches(pid: int, expected: object) -> bool:
    if not isinstance(expected, dict):
        return False
    try:
        return process_identity(pid) == expected
    except (OSError, ProcessIdentityError, ValueError):
        return False


def launch_command_digest(command: list[str]) -> str:
    """Digest the exact command form the native OS exposes for a child."""
    if not isinstance(command, list) or not command or any(not isinstance(value, str) for value in command):
        raise ProcessIdentityError("launch command is invalid")
    if os.name == "nt":
        canonical = subprocess.list2cmdline(command)
    else:
        canonical = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def process_launch_fingerprint(pid: int) -> dict[str, str]:
    """Return command/token (and Linux cwd) evidence for one live process."""
    if type(pid) is not int or pid <= 0:
        raise ProcessIdentityError("process fingerprint input is invalid")
    if os.name == "nt":
        return _windows_launch_fingerprint(pid)
    if sys.platform.startswith("linux"):
        return _linux_launch_fingerprint(pid)
    raise ProcessIdentityError("process fingerprint primitive is unsupported")


def current_user_identity() -> str:
    return process_launch_fingerprint(os.getpid())["user"]


def _windows_launch_fingerprint(pid: int) -> dict[str, str]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    ntdll.NtQueryInformationProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    advapi32.GetTokenInformation.restype = ctypes.c_int
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = ctypes.c_int

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ProcessIdentityError("process is not observable")
    try:
        # ProcessCommandLineInformation (60) returns a UNICODE_STRING followed by its buffer.
        needed = ctypes.c_ulong(0)
        size = 4096
        status = 0
        for _attempt in range(4):
            buffer = ctypes.create_string_buffer(size)
            status = ntdll.NtQueryInformationProcess(handle, 60, buffer, size, ctypes.byref(needed))
            if status == 0:
                break
            if needed.value <= size or needed.value > 1024 * 1024:
                raise ProcessIdentityError("process command line is unavailable")
            size = needed.value
        if status != 0:
            raise ProcessIdentityError("process command line is unavailable")
        length = ctypes.c_ushort.from_buffer(buffer, 0).value
        pointer = ctypes.c_void_p.from_buffer(buffer, ctypes.sizeof(ctypes.c_void_p)).value
        if not pointer or length % 2:
            raise ProcessIdentityError("process command line is malformed")
        command_line = ctypes.wstring_at(pointer, length // 2)

        token = ctypes.c_void_p()
        if not advapi32.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):
            raise ProcessIdentityError("process token is unavailable")
        try:
            token_size = ctypes.c_ulong(0)
            advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(token_size))
            if not 0 < token_size.value <= 4096:
                raise ProcessIdentityError("process token user is unavailable")
            token_buffer = ctypes.create_string_buffer(token_size.value)
            if not advapi32.GetTokenInformation(token, 1, token_buffer, token_size, ctypes.byref(token_size)):
                raise ProcessIdentityError("process token user is unavailable")
            sid = ctypes.c_void_p.from_buffer(token_buffer, 0).value
            text = ctypes.c_wchar_p()
            if not sid or not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise ProcessIdentityError("process token user is unavailable")
            try:
                user = text.value or ""
            finally:
                kernel32.LocalFree(text)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(handle)
    if not command_line or not user:
        raise ProcessIdentityError("process fingerprint is incomplete")
    return {
        "command_sha256": hashlib.sha256(command_line.encode("utf-8")).hexdigest(),
        "user": user,
    }


def _linux_launch_fingerprint(pid: int) -> dict[str, str]:
    proc = Path("/proc") / str(pid)
    try:
        raw = (proc / "cmdline").read_bytes()
        cwd = os.readlink(proc / "cwd")
        status = (proc / "status").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ProcessIdentityError("process fingerprint is unavailable") from exc
    if not raw.endswith(b"\0"):
        raise ProcessIdentityError("process command line is malformed")
    try:
        argv = [part.decode("utf-8") for part in raw[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise ProcessIdentityError("process command line is malformed") from exc
    user = None
    for line in status.splitlines():
        if line.startswith("Uid:"):
            fields = line.split()
            if len(fields) >= 3:
                user = f"uid:{fields[2]}"
            break
    if not argv or not user or not cwd.startswith("/") or cwd.endswith(" (deleted)"):
        raise ProcessIdentityError("process fingerprint is incomplete")
    return {
        "command_sha256": launch_command_digest(argv),
        "user": user,
        "cwd": cwd,
    }


def _windows_process_identity(pid: int) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    ]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created = _FileTime()
        exited = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        image_buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.c_ulong(len(image_buffer))
        if not kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            image_buffer,
            ctypes.byref(length),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        creation = (created.high << 32) | created.low
        image = os.path.normcase(os.path.abspath(image_buffer.value))
        return {
            "pid": pid,
            "creation_time": str(creation),
            "image": image,
            "host": os.environ.get("COMPUTERNAME", "").casefold(),
            "namespace": "windows-host",
        }
    finally:
        kernel32.CloseHandle(handle)


def _linux_process_stat_creation_time(stat_text: str) -> str:
    if not isinstance(stat_text, str):
        raise ProcessIdentityError("process stat record is malformed")
    closing_parenthesis = stat_text.rfind(")")
    if closing_parenthesis < 0:
        raise ProcessIdentityError("process stat record is malformed")
    tail = stat_text[closing_parenthesis + 2 :].split()
    if len(tail) <= 19:
        raise ProcessIdentityError("process stat record is malformed")
    creation = tail[19]
    if not creation.isascii() or not creation.isdecimal() or len(creation) > 20 or int(creation) <= 0 or int(creation) > _MAX_LINUX_IDENTITY_COUNTER:
        raise ProcessIdentityError("process creation time is unavailable")
    return creation


def _linux_process_identity(pid: int, *, proc_root: Path | None = None) -> dict[str, Any]:
    if type(pid) is not int or pid <= 0:
        raise ProcessIdentityError("process identity input is invalid")
    if proc_root is None:
        proc_root = Path("/proc")
    if not isinstance(proc_root, Path) or not proc_root.is_absolute():
        raise ProcessIdentityError("process identity proc root is invalid")
    proc = proc_root / str(pid)
    try:
        stat_text = (proc / "stat").read_text(encoding="ascii")
        creation = _linux_process_stat_creation_time(stat_text)
        namespace = str(os.stat(proc / "ns" / "pid").st_ino)
        image = os.readlink(proc / "exe")
        boot = (proc_root / "sys" / "kernel" / "random" / "boot_id").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, IndexError) as exc:
        raise ProcessIdentityError("process identity is unavailable") from exc
    if not namespace or not boot or not image or not os.path.isabs(image):
        raise ProcessIdentityError("process identity is incomplete")
    return {
        "pid": pid,
        "creation_time": creation,
        "image": image,
        "host": boot,
        "namespace": namespace,
    }
