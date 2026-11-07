"""PID 1 supervisor for a read-only-first web child."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_STOP_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 0.1


class ChildShutdownTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class SupervisorOptions:
    root: Path
    port: int = 8876
    enable_writes_after_trust: bool = False
    enable_network_after_trust: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError("root must be an absolute path")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if type(self.enable_writes_after_trust) is not bool:
            raise TypeError("write capability option must be boolean")
        if type(self.enable_network_after_trust) is not bool:
            raise TypeError("network capability option must be boolean")


def _web_command(
    options: SupervisorOptions,
    *,
    activated: bool,
    authority_check: Callable[[Path], bool],
    executable: str,
) -> list[str]:
    if not isinstance(options, SupervisorOptions):
        raise TypeError("supervisor options are required")
    if type(activated) is not bool:
        raise TypeError("activation state must be boolean")
    if not callable(authority_check):
        raise TypeError("authority check must be callable")
    if not isinstance(executable, str) or not executable or "\0" in executable:
        raise ValueError("web executable is invalid")

    command = [executable, "--root", str(options.root), "--port", str(options.port)]
    if not activated or not options.enable_writes_after_trust:
        return command
    trusted = authority_check(options.root)
    if type(trusted) is not bool:
        raise TypeError("authority check must return a boolean")
    if not trusted:
        return command

    command.append("--allow-writes")
    if options.enable_network_after_trust:
        command.append("--enable-network")
    return command


def _current_write_authority(root: Path) -> bool:
    from hedge_fund.runtime.handover import (
        enrollment_status,
        HandoverError,
        TRUSTED_SINGLE_WRITER_AUTHORITY,
        write_authority,
    )
    from hedge_fund.runtime.root import RootContext, RootPathError

    try:
        with RootContext.open(root) as context:
            status = enrollment_status(context, verify_inventory=True)
            if status["state"] != "enrolled":
                print(
                    f"web write activation denied ({status['reason'] or status['state']}); child remains read-only",
                    file=sys.stderr,
                    flush=True,
                )
                return False
            authority = write_authority(context)
            if not isinstance(authority, dict) or authority.get("authority") != TRUSTED_SINGLE_WRITER_AUTHORITY:
                reason = "handover-unavailable"
                if isinstance(authority, dict):
                    reason = authority.get("reason") or authority.get("authority") or reason
                print(
                    f"web write activation denied ({reason}); child remains read-only",
                    file=sys.stderr,
                    flush=True,
                )
                return False
            return True
    except (HandoverError, OSError, RootPathError) as exc:
        print(
            f"web write activation check unavailable ({type(exc).__name__}); child remains read-only",
            file=sys.stderr,
            flush=True,
        )
        return False


def _reap_adopted_children(current_child_pid: int | None = None) -> int:
    if current_child_pid is not None and (type(current_child_pid) is not int or current_child_pid <= 0):
        raise ValueError("current child PID must be a positive integer")
    if os.name != "posix":
        return 0
    required = ("P_ALL", "WEXITED", "WNOHANG", "WNOWAIT", "waitid", "waitpid")
    if any(not hasattr(os, name) for name in required):
        raise RuntimeError("safe adopted-child reaping requires POSIX waitid(WNOWAIT)")

    options = os.WEXITED | os.WNOHANG | os.WNOWAIT
    reaped = 0
    while True:
        try:
            # WNOWAIT keeps Popen-owned status available for its next poll or wait.
            status = os.waitid(os.P_ALL, 0, options)
        except ChildProcessError:
            return reaped
        except InterruptedError:
            continue
        if status is None or status.si_pid == 0:
            return reaped
        child_pid = status.si_pid
        if type(child_pid) is not int or child_pid <= 0:
            return reaped
        if child_pid == current_child_pid:
            return reaped
        try:
            waited_pid, _ = os.waitpid(child_pid, os.WNOHANG)
        except ChildProcessError:
            continue
        except InterruptedError:
            continue
        if waited_pid != child_pid:
            return reaped
        reaped += 1


def _terminate_child(process: subprocess.Popen, timeout: float) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        process.terminate()
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ChildShutdownTimeout(f"web child PID {process.pid} did not exit within {timeout:g}s after SIGKILL") from exc


def _run_supervisor(
    options: SupervisorOptions,
    *,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    signal_api=signal,
    sleep: Callable[[float], None] = time.sleep,
    terminate_child: Callable[[subprocess.Popen, float], None] = _terminate_child,
    reap_children: Callable[[int | None], int] = _reap_adopted_children,
    authority_check: Callable[[Path], bool] = _current_write_authority,
    executable: str = "aihf-web",
) -> int:
    if not isinstance(options, SupervisorOptions):
        raise TypeError("supervisor options are required")
    if not callable(reap_children):
        raise TypeError("child reaper must be callable")

    stopping = False
    requested_activation: bool | None = None
    child_shutdown_failed = False
    previous_handlers = {}
    child = None

    def handle_signal(signum, _frame) -> None:
        nonlocal stopping, requested_activation
        if signum == signal_api.SIGHUP:
            requested_activation = True
        elif signum == signal_api.SIGUSR1:
            requested_activation = False
        else:
            stopping = True

    def stop(process: subprocess.Popen) -> None:
        nonlocal child_shutdown_failed
        try:
            terminate_child(process, _STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            child_shutdown_failed = True
            raise ChildShutdownTimeout(f"web child PID {process.pid} did not stop within {_STOP_TIMEOUT_SECONDS:g}s after SIGKILL") from exc
        except ChildShutdownTimeout:
            child_shutdown_failed = True
            raise
        reap_children(None)

    def launch(*, activated: bool):
        nonlocal child
        if stopping:
            return None
        if activated and requested_activation is False:
            return None
        command = _web_command(
            options,
            activated=activated,
            authority_check=authority_check,
            executable=executable,
        )
        if stopping or (activated and requested_activation is False):
            return None
        try:
            process = popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            if not stopping:
                print(f"web child could not start ({type(exc).__name__})", file=sys.stderr, flush=True)
            return None
        child = process
        if stopping or (activated and requested_activation is False):
            stop(process)
            child = None
            return None
        return process

    result = 127
    try:
        for signum in (
            signal_api.SIGHUP,
            signal_api.SIGUSR1,
            signal_api.SIGINT,
            signal_api.SIGTERM,
        ):
            previous_handlers[signum] = signal_api.signal(signum, handle_signal)

        child = launch(activated=False)
        while True:
            if stopping:
                if child is not None:
                    stop(child)
                    child = None
                result = 0
                break
            if requested_activation is not None:
                activated = requested_activation
                requested_activation = None
                if child is not None:
                    stop(child)
                    child = None
                if stopping:
                    result = 0
                    break
                child = launch(activated=activated)
                if child is None:
                    if stopping:
                        result = 0
                        break
                    if requested_activation is not None:
                        continue
                    result = 127
                    break
                continue
            if child is None:
                result = 127
                break
            returncode = child.poll()
            if returncode is not None:
                child = None
                reap_children(None)
                result = returncode
                break
            reap_children(child.pid)
            sleep(_POLL_SECONDS)
    except ChildShutdownTimeout as exc:
        print(f"web supervisor shutdown failed: {exc}", file=sys.stderr, flush=True)
        result = 1
    finally:
        if child is not None and not child_shutdown_failed:
            if child.poll() is None:
                try:
                    stop(child)
                except ChildShutdownTimeout as exc:
                    print(f"web supervisor shutdown failed: {exc}", file=sys.stderr, flush=True)
                    result = 1
            else:
                reap_children(None)
        for signum, previous in previous_handlers.items():
            signal_api.signal(signum, previous)
    return result


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihf-web-supervisor",
        description="Keep the web child read-only until explicit runtime trust.",
    )
    parser.add_argument("--root", type=Path, required=True, help="existing absolute data root")
    parser.add_argument("--port", type=_port, default=8876, help="loopback port (default: 8876)")
    parser.add_argument(
        "--enable-writes-after-trust",
        action="store_true",
        help="allow child writes only after explicit trust and SIGHUP",
    )
    parser.add_argument(
        "--enable-network-after-trust",
        action="store_true",
        help="allow child network only with verified write authority after SIGHUP",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if os.name != "posix" or not hasattr(signal, "SIGHUP") or not hasattr(signal, "SIGUSR1"):
        parser.error("PID 1 supervision requires POSIX signals; trusted web mode is disabled")
    try:
        options = SupervisorOptions(
            root=args.root,
            port=args.port,
            enable_writes_after_trust=args.enable_writes_after_trust,
            enable_network_after_trust=args.enable_network_after_trust,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    executable = shutil.which("aihf-web") or "aihf-web"
    return _run_supervisor(options, executable=executable)


if __name__ == "__main__":
    raise SystemExit(main())
