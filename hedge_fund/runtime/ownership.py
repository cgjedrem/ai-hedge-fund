"""Native process-incarnation identity for owned children."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


class ProcessIdentityError(RuntimeError):
    """Process identity could not be verified."""


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


def _linux_process_identity(pid: int) -> dict[str, Any]:
    proc = Path("/proc") / str(pid)
    try:
        stat_text = (proc / "stat").read_text(encoding="ascii")
        tail = stat_text[stat_text.rfind(")") + 2 :].split()
        if len(tail) <= 19:
            raise ProcessIdentityError("process stat record is malformed")
        creation = tail[19]
        namespace = str(os.stat(proc / "ns" / "pid").st_ino)
        image = os.path.realpath(proc / "exe")
        boot = (
            Path("/proc/sys/kernel/random/boot_id")
            .read_text(
                encoding="ascii",
            )
            .strip()
        )
    except (OSError, UnicodeError, IndexError) as exc:
        raise ProcessIdentityError("process identity is unavailable") from exc
    if not creation or not namespace or not boot:
        raise ProcessIdentityError("process identity is incomplete")
    return {
        "pid": pid,
        "creation_time": creation,
        "image": image,
        "host": boot,
        "namespace": namespace,
    }
