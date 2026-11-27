"""Run pytest files serially; bound subprocess lifetimes."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import math
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_MINUTES = 90.0
DEFAULT_CHUNK_TIMEOUT_MINUTES = 10.0
POETRY_RESOLVE_TIMEOUT_SECONDS = 10.0
TERMINATE_GRACE_SECONDS = 5.0
POST_TERMINATE_WAIT_SECONDS = 5.0
_SUMMARY_DURATION_RE = re.compile(r"\bin\s+\d+(?:\.\d+)?s\b")
_SUMMARY_COUNT_RE = re.compile(r"(?<![\w-])(?P<count>\d+)\s+(?P<kind>passed|failed|skipped|errors?|xfailed|xpassed)\b")


class RunnerError(RuntimeError):
    """Runner-level failure."""


class AlreadyRunningError(RunnerError):
    """Another runner owns the lock."""


@dataclass(frozen=True)
class TestCounts:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0


@dataclass
class ChunkResult:
    chunk: str
    status: str
    passed: int | None = None
    failed: int | None = None
    skipped: int | None = None
    errors: int | None = None
    duration_seconds: float = 0.0
    returncode: int | None = None
    timeout_scope: str | None = None
    summary_found: bool = False


@dataclass
class ExecutionResult:
    chunks: list[ChunkResult] = field(default_factory=list)
    incomplete: bool = False
    last_completed_chunk: str | None = None
    runner_errors: list[str] = field(default_factory=list)


class InstanceLock:
    """Hold advisory lock and owner record until release."""

    def __init__(self, path: Path, handle, pid: int, command_line: str):
        self.path = path
        self._handle = handle
        self.pid = pid
        self.command_line = command_line

    def __enter__(self) -> InstanceLock:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.release()
        return False

    def release(self) -> None:
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        try:
            _unlock_file(handle)
        finally:
            handle.close()


def default_state_dir(repo_root: Path = REPO_ROOT) -> Path:
    """Return temp state path keyed to repo worktree."""
    resolved = repo_root.resolve()
    repo_key = hashlib.sha256(os.fsencode(str(resolved))).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "ai-hedge-fund-full-suite" / repo_key


def _read_lock_record(handle) -> dict[str, object] | None:
    handle.seek(0)
    raw = handle.read().lstrip(b"\0").strip()
    if not raw:
        return None
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError("runner lock record is malformed; inspect or remove it manually") from exc
    if not isinstance(record, dict):
        raise RunnerError("runner lock record is malformed; inspect or remove it manually")
    pid = record.get("pid")
    command_line = record.get("command_line")
    if type(pid) is not int or pid <= 0 or not isinstance(command_line, str) or not command_line:
        raise RunnerError("runner lock record is malformed; inspect or remove it manually")
    return {"pid": pid, "command_line": command_line}


def _try_lock_file(handle) -> bool:
    if os.name == "nt":
        import msvcrt

        if os.fstat(handle.fileno()).st_size == 0:
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or getattr(exc, "winerror", None) in {32, 33}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _unlock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _pid_is_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                return False
            if exc.errno == errno.EPERM:
                return True
            raise
        return True

    if pid > 0xFFFFFFFF:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    open_process.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = open_process(0x1000, 0, pid)
    if handle:
        close_handle(handle)
        return True
    error_code = ctypes.get_last_error()
    if error_code == 5:
        return True
    if error_code in {6, 87}:
        return False
    raise OSError(error_code, "OpenProcess failed while checking runner PID", pid)


def acquire_instance_lock(
    path: Path,
    command_line: str,
    *,
    pid: int | None = None,
    is_alive: Callable[[int], bool] | None = None,
    notice: Callable[[str], None] | None = None,
) -> InstanceLock:
    """Acquire lock; reclaim only records whose PID is dead."""
    lock_path = Path(path).expanduser().resolve()
    owner_pid = os.getpid() if pid is None else pid
    if type(owner_pid) is not int or owner_pid <= 0:
        raise ValueError("pid must be a positive integer")
    if not isinstance(command_line, str) or not command_line:
        raise ValueError("command_line must be a non-empty string")
    alive = _pid_is_alive if is_alive is None else is_alive
    notify = (lambda message: print(message, file=sys.stderr, flush=True)) if notice is None else notice
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    handle = os.fdopen(descriptor, "r+b")
    locked = False
    try:
        if not _try_lock_file(handle):
            raise AlreadyRunningError(f"runner lock is held: {lock_path}")
        locked = True
        existing = _read_lock_record(handle)
        if existing is not None:
            existing_pid = int(existing["pid"])
            if alive(existing_pid):
                raise AlreadyRunningError(f"runner lock belongs to live PID {existing_pid}: {existing['command_line']}")
            notify(f"Reclaiming stale runner lock for dead PID {existing_pid}.")
        record = json.dumps({"pid": owner_pid, "command_line": command_line}, sort_keys=True).encode("utf-8")
        handle.seek(0)
        handle.write(record)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
        return InstanceLock(lock_path, handle, owner_pid, command_line)
    except Exception:
        if locked:
            try:
                _unlock_file(handle)
            except OSError:
                pass
        handle.close()
        raise


def resolve_poetry_python(
    repo_root: Path,
    *,
    fallback: str | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Resolve Poetry venv interpreter; fall back to current Python."""
    fallback_python = sys.executable if fallback is None else fallback
    run_command = subprocess.run if run is None else run
    try:
        result = run_command(
            ["poetry", "env", "info", "-p"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=POETRY_RESOLVE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return fallback_python
    if result.returncode != 0:
        return fallback_python
    env_path = result.stdout.strip()
    if not env_path:
        return fallback_python
    executable = Path(env_path) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(executable) if executable.is_file() else fallback_python


def discover_test_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Find pytest's default test filename patterns under hedge_fund."""
    test_root = repo_root / "hedge_fund"
    if not test_root.is_dir():
        raise RunnerError(f"test directory does not exist: {test_root}")
    files = set(test_root.rglob("test_*.py"))
    files.update(test_root.rglob("*_test.py"))
    return sorted(files, key=lambda path: path.as_posix().casefold())


def parse_pytest_summary(output: str) -> TestCounts | None:
    """Parse final pytest count line; ignore child exit status."""
    if not isinstance(output, str):
        raise TypeError("output must be a string")
    parsed: TestCounts | None = None
    for line in output.splitlines():
        if not _SUMMARY_DURATION_RE.search(line):
            continue
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        found = False
        for match in _SUMMARY_COUNT_RE.finditer(line):
            kind = match.group("kind")
            key = "errors" if kind in {"error", "errors"} else kind
            if key in counts:
                counts[key] += int(match.group("count"))
            found = True
        if found:
            parsed = TestCounts(**counts)
    return parsed


def aggregate_counts(chunks: Iterable[ChunkResult]) -> dict[str, int]:
    """Sum known pytest counts; unknown timed-out counts add zero."""
    totals = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for chunk in chunks:
        for key in totals:
            count = getattr(chunk, key)
            if count is None:
                continue
            if type(count) is not int or count < 0:
                raise ValueError(f"{key} count must be a non-negative integer or None")
            totals[key] += count
    return totals


def calculate_timeout_budget(
    remaining_wall_seconds: float,
    remaining_chunk_seconds: float,
) -> tuple[float, str]:
    """Use earliest deadline; report whether run or chunk bound wins."""
    if not math.isfinite(remaining_wall_seconds) or not math.isfinite(remaining_chunk_seconds):
        raise ValueError("timeout budgets must be finite")
    if remaining_wall_seconds <= 0:
        return 0.0, "wall"
    if remaining_chunk_seconds <= 0:
        return 0.0, "chunk"
    if remaining_wall_seconds <= remaining_chunk_seconds:
        return remaining_wall_seconds, "wall"
    return remaining_chunk_seconds, "chunk"


def _process_group_exists(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_process_tree(process, launched_pid: int) -> None:
    """Terminate launched pytest process and descendants."""
    if type(launched_pid) is not int or launched_pid <= 0 or process.pid != launched_pid:
        raise RunnerError("refusing to terminate a PID not returned by the launched pytest process")
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(launched_pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=TERMINATE_GRACE_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=POST_TERMINATE_WAIT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise RunnerError(f"could not terminate pytest process tree for PID {launched_pid}") from exc
        if result.returncode != 0:
            raise RunnerError(f"taskkill failed for launched pytest PID {launched_pid}")
        try:
            process.wait(timeout=POST_TERMINATE_WAIT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            try:
                process.wait(timeout=POST_TERMINATE_WAIT_SECONDS)
            except subprocess.TimeoutExpired as wait_exc:
                raise RunnerError(f"pytest PID {launched_pid} did not terminate") from wait_exc
            raise RunnerError(f"pytest process tree termination exceeded its bound for PID {launched_pid}") from exc
        return

    try:
        os.killpg(launched_pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=POST_TERMINATE_WAIT_SECONDS)
        return
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while _process_group_exists(launched_pid) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.05)
    if _process_group_exists(launched_pid):
        os.killpg(launched_pid, signal.SIGKILL)
    try:
        process.wait(timeout=POST_TERMINATE_WAIT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(f"pytest PID {launched_pid} did not terminate") from exc


def _as_text(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _emit_output(output: str | bytes | None) -> None:
    text = _as_text(output)
    if not text:
        return
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def append_progress_event(path: Path, event: dict[str, object]) -> None:
    """Append one flushed JSONL event."""
    progress_path = Path(path).expanduser()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _result_counts(counts: TestCounts | None) -> dict[str, int | None]:
    if counts is None:
        return {"passed": None, "failed": None, "skipped": None, "errors": None}
    return asdict(counts)


def _result_event(run_id: str, result: ChunkResult) -> dict[str, object]:
    event: dict[str, object] = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "chunk": result.chunk,
        "status": result.status,
        "passed": result.passed,
        "failed": result.failed,
        "skipped": result.skipped,
        "errors": result.errors,
        "duration_seconds": round(result.duration_seconds, 3),
    }
    if result.timeout_scope is not None:
        event["timeout_scope"] = result.timeout_scope
    return event


def run_chunks(
    repo_root: Path,
    test_files: Sequence[Path],
    python_executable: str,
    pytest_args: Sequence[str],
    timeout_seconds: float,
    chunk_timeout_seconds: float,
    progress_file: Path,
    run_id: str,
    *,
    process_factory: Callable[..., object] | None = None,
    monotonic: Callable[[], float] | None = None,
    terminator: Callable[[object, int], None] | None = None,
    progress_writer: Callable[[Path, dict[str, object]], None] | None = None,
) -> ExecutionResult:
    """Run each file once; stop on runner errors or any timeout."""
    for value, name in ((timeout_seconds, "timeout_seconds"), (chunk_timeout_seconds, "chunk_timeout_seconds")):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
    if not python_executable:
        raise ValueError("python_executable must not be empty")
    if not run_id:
        raise ValueError("run_id must not be empty")
    popen = subprocess.Popen if process_factory is None else process_factory
    clock = time.monotonic if monotonic is None else monotonic
    stop_tree = terminate_process_tree if terminator is None else terminator
    write_event = append_progress_event if progress_writer is None else progress_writer
    repo = Path(repo_root).resolve()
    result = ExecutionResult()
    started = clock()
    wall_deadline = started + timeout_seconds

    def record(chunk_result: ChunkResult) -> bool:
        result.chunks.append(chunk_result)
        try:
            write_event(progress_file, _result_event(run_id, chunk_result))
        except OSError as exc:
            result.incomplete = True
            result.runner_errors.append(f"could not append progress event for {chunk_result.chunk}: {exc}")
            return False
        return True

    for test_file in test_files:
        chunk_started = clock()
        if wall_deadline - chunk_started <= 0:
            result.incomplete = True
            result.runner_errors.append(f"wall-clock timeout before {test_file}; last completed chunk: {result.last_completed_chunk or 'none'}")
            break
        chunk_deadline = chunk_started + chunk_timeout_seconds
        try:
            chunk_name = Path(test_file).resolve().relative_to(repo).as_posix()
        except ValueError:
            chunk_name = str(Path(test_file))
        command = [python_executable, "-m", "pytest", *pytest_args, str(test_file)]
        process_options: dict[str, object] = {
            "cwd": str(repo),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            process_options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            process_options["start_new_session"] = True
        try:
            process = popen(command, **process_options)
        except OSError as exc:
            duration = max(0.0, clock() - chunk_started)
            chunk_result = ChunkResult(
                chunk=chunk_name,
                status="error",
                duration_seconds=duration,
            )
            result.incomplete = True
            result.runner_errors.append(f"could not start pytest for {chunk_name}: {exc}")
            record(chunk_result)
            break

        launched_pid = process.pid
        current_time = clock()
        wait_seconds, timeout_scope = calculate_timeout_budget(
            wall_deadline - current_time,
            chunk_deadline - current_time,
        )
        try:
            if wait_seconds <= 0:
                raise subprocess.TimeoutExpired(command, timeout=0)
            output, _ = process.communicate(timeout=wait_seconds)
        except subprocess.TimeoutExpired as exc:
            output = ""
            try:
                stop_tree(process, launched_pid)
            except Exception as terminate_exc:
                result.runner_errors.append(f"failed to terminate pytest process tree for PID {launched_pid}: {terminate_exc}")
                try:
                    if process.poll() is None:
                        process.kill()
                except OSError:
                    pass
            try:
                output, _ = process.communicate(timeout=POST_TERMINATE_WAIT_SECONDS)
            except subprocess.TimeoutExpired as wait_exc:
                output = wait_exc.output or exc.output or ""
                result.runner_errors.append(f"pytest PID {launched_pid} remained after termination")
            except OSError as wait_exc:
                output = exc.output or ""
                result.runner_errors.append(f"could not collect pytest output after timeout: {wait_exc}")
            output = _as_text(output) or _as_text(exc.output)
            _emit_output(output)
            counts = parse_pytest_summary(output)
            count_values = _result_counts(counts)
            chunk_result = ChunkResult(
                chunk=chunk_name,
                status="timeout",
                **count_values,
                duration_seconds=max(0.0, clock() - chunk_started),
                returncode=process.poll(),
                timeout_scope=timeout_scope,
                summary_found=counts is not None,
            )
            result.incomplete = True
            timeout_label = "wall-clock" if timeout_scope == "wall" else "per-chunk"
            result.runner_errors.append(f"{timeout_label} timeout in {chunk_name}; last completed chunk: {result.last_completed_chunk or 'none'}")
            record(chunk_result)
            break
        except KeyboardInterrupt:
            try:
                stop_tree(process, launched_pid)
            except Exception as terminate_exc:
                result.runner_errors.append(f"failed to terminate interrupted pytest PID {launched_pid}: {terminate_exc}")
            try:
                output, _ = process.communicate(timeout=POST_TERMINATE_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                output = ""
            _emit_output(output)
            counts = parse_pytest_summary(_as_text(output))
            chunk_result = ChunkResult(
                chunk=chunk_name,
                status="interrupted",
                **_result_counts(counts),
                duration_seconds=max(0.0, clock() - chunk_started),
                returncode=process.poll(),
                summary_found=counts is not None,
            )
            result.incomplete = True
            result.runner_errors.append(f"pytest interrupted in {chunk_name}; last completed chunk: {result.last_completed_chunk or 'none'}")
            record(chunk_result)
            break
        except Exception as exc:
            try:
                if process.poll() is None:
                    stop_tree(process, launched_pid)
            except Exception as terminate_exc:
                result.runner_errors.append(f"failed to terminate pytest PID {launched_pid}: {terminate_exc}")
            chunk_result = ChunkResult(
                chunk=chunk_name,
                status="error",
                duration_seconds=max(0.0, clock() - chunk_started),
                returncode=process.poll(),
            )
            result.incomplete = True
            result.runner_errors.append(f"pytest execution failed for {chunk_name}: {exc}")
            record(chunk_result)
            break

        output = _as_text(output)
        _emit_output(output)
        counts = parse_pytest_summary(output)
        returncode = process.returncode
        if counts is None:
            status = "error"
            result.incomplete = True
            result.runner_errors.append(f"pytest summary missing for {chunk_name}; return code {returncode}")
        elif counts.failed:
            status = "failed"
            result.last_completed_chunk = chunk_name
        elif counts.errors:
            status = "error"
            result.last_completed_chunk = chunk_name
        else:
            status = "passed"
            result.last_completed_chunk = chunk_name
        chunk_result = ChunkResult(
            chunk=chunk_name,
            status=status,
            **_result_counts(counts),
            duration_seconds=max(0.0, clock() - chunk_started),
            returncode=returncode,
            summary_found=counts is not None,
        )
        if not record(chunk_result):
            break
    return result


def build_summary(
    run_id: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    result: ExecutionResult,
) -> dict[str, object]:
    totals = aggregate_counts(result.chunks)
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_duration_seconds": round(duration_seconds, 3),
        **totals,
        "incomplete": result.incomplete,
        "last_completed_chunk": result.last_completed_chunk,
        "runner_errors": list(result.runner_errors),
        "chunks": [asdict(chunk) for chunk in result.chunks],
    }


def summary_exit_code(summary: dict[str, object]) -> int:
    if summary["incomplete"] or summary["runner_errors"]:
        return 2
    if summary["failed"] or summary["errors"]:
        return 1
    return 0


def write_summary(path: Path, summary: dict[str, object]) -> None:
    """Write final JSON summary."""
    summary_path = Path(path).expanduser()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _positive_minutes(value: str) -> float:
    try:
        minutes = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number of minutes") from exc
    if not math.isfinite(minutes) or minutes <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number of minutes")
    return minutes


def build_parser(repo_root: Path = REPO_ROOT) -> argparse.ArgumentParser:
    state_dir = default_state_dir(repo_root)
    parser = argparse.ArgumentParser(
        description="Run hedge_fund pytest files serially with per-file and whole-run deadlines.",
        epilog=("Exit codes: 0 = all chunks produced summaries with no reported failures/errors; " "1 = pytest summaries report failures/errors; 2 = runner error or timeout. " "Summary counts override anomalous pytest process exit codes. " "Pass pytest options after --, for example: -- -q -k runtime."),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--timeout-minutes",
        type=_positive_minutes,
        default=DEFAULT_TIMEOUT_MINUTES,
        metavar="N",
        help="Hard wall-clock limit for the full run.",
    )
    parser.add_argument(
        "--chunk-timeout-minutes",
        type=_positive_minutes,
        default=DEFAULT_CHUNK_TIMEOUT_MINUTES,
        metavar="N",
        help="Maximum runtime for each per-file pytest invocation.",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=state_dir / "progress.jsonl",
        help="Append-only per-chunk progress JSONL path.",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=state_dir / "summary.json",
        help="Final run summary JSON path.",
    )
    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw_args:
        separator = raw_args.index("--")
        runner_args, pytest_args = raw_args[:separator], raw_args[separator + 1 :]
    else:
        runner_args, pytest_args = raw_args, []
    args = build_parser().parse_args(runner_args)
    return args, pytest_args


def _command_line() -> str:
    command = [sys.executable, *sys.argv]
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main(argv: Sequence[str] | None = None) -> int:
    args, pytest_args = parse_arguments(argv)
    progress_file = args.progress_file.expanduser().resolve()
    summary_file = args.summary_file.expanduser().resolve()
    state_dir = default_state_dir(REPO_ROOT)
    lock_file = state_dir / "runner.lock"
    if progress_file == summary_file or progress_file == lock_file or summary_file == lock_file:
        print("progress, summary, and lock paths must be different", file=sys.stderr)
        return 2
    if progress_file.exists() and progress_file.is_dir():
        print(f"progress path is a directory: {progress_file}", file=sys.stderr)
        return 2
    if summary_file.exists() and summary_file.is_dir():
        print(f"summary path is a directory: {summary_file}", file=sys.stderr)
        return 2
    try:
        lock = acquire_instance_lock(lock_file, _command_line())
    except (RunnerError, OSError) as exc:
        print(f"runner error: {exc}", file=sys.stderr)
        return 2

    with lock:
        started_at = _timestamp()
        started_monotonic = time.monotonic()
        run_id = uuid.uuid4().hex
        try:
            test_files = discover_test_files(REPO_ROOT)
            if not test_files:
                raise RunnerError("no pytest files found under hedge_fund")
            python_executable = resolve_poetry_python(REPO_ROOT)
            remaining_timeout = args.timeout_minutes * 60.0 - (time.monotonic() - started_monotonic)
            if remaining_timeout <= 0:
                result = ExecutionResult(incomplete=True, runner_errors=["wall-clock timeout before first pytest chunk"])
            else:
                result = run_chunks(
                    REPO_ROOT,
                    test_files,
                    python_executable,
                    pytest_args,
                    remaining_timeout,
                    args.chunk_timeout_minutes * 60.0,
                    progress_file,
                    run_id,
                )
        except KeyboardInterrupt:
            result = ExecutionResult(incomplete=True, runner_errors=["runner interrupted before suite completion"])
        except Exception as exc:
            result = ExecutionResult(incomplete=True, runner_errors=[f"runner error: {exc}"])
        finished_at = _timestamp()
        summary = build_summary(
            run_id,
            started_at,
            finished_at,
            max(0.0, time.monotonic() - started_monotonic),
            result,
        )
        try:
            write_summary(summary_file, summary)
        except OSError as exc:
            print(f"runner error: could not write summary {summary_file}: {exc}", file=sys.stderr)
            return 2
        code = summary_exit_code(summary)
        print("Suite summary: " f"{summary['passed']} passed, {summary['failed']} failed, " f"{summary['skipped']} skipped, {summary['errors']} errors; " f"incomplete={summary['incomplete']}; exit={code}")
        return code


if __name__ == "__main__":
    raise SystemExit(main())
