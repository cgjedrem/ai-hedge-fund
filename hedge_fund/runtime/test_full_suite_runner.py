import ctypes
import errno
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from hedge_fund.test_support.network_guard import (
    child_test_environment,
    guarded_test_python_command,
)

_RUNNER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_full_suite.py"
_RUNNER_SPEC = importlib.util.spec_from_file_location("_aihf_test_run_full_suite", _RUNNER_PATH)
if _RUNNER_SPEC is None or _RUNNER_SPEC.loader is None:
    raise ImportError(f"could not load test runner from {_RUNNER_PATH}")
runner = importlib.util.module_from_spec(_RUNNER_SPEC)
sys.modules[_RUNNER_SPEC.name] = runner
_RUNNER_SPEC.loader.exec_module(runner)


def _write_lock(path, pid, command_line):
    path.write_text(
        json.dumps({"pid": pid, "command_line": command_line}),
        encoding="utf-8",
    )


def test_lock_reclaims_unlocked_live_pid_record(tmp_path):
    lock_path = tmp_path / "runner.lock"
    owner_pid = os.getpid()
    _write_lock(lock_path, owner_pid, "python active_runner.py")
    notices = []

    lock = runner.acquire_instance_lock(
        lock_path,
        "python new_runner.py",
        pid=9001,
        notice=notices.append,
    )
    try:
        assert notices == [f"Reclaiming unlocked runner lock record for PID {owner_pid}."]
        assert json.loads(lock_path.read_text(encoding="utf-8")) == {
            "pid": 9001,
            "command_line": "python new_runner.py",
        }
    finally:
        lock.release()

    assert lock_path.read_bytes() == b""


def test_lock_reclaims_existing_record_with_notice(tmp_path):
    lock_path = tmp_path / "runner.lock"
    _write_lock(lock_path, 8123, "python dead_runner.py")
    notices = []

    lock = runner.acquire_instance_lock(
        lock_path,
        "python new_runner.py",
        pid=9001,
        notice=notices.append,
    )
    try:
        assert notices == ["Reclaiming unlocked runner lock record for PID 8123."]
    finally:
        lock.release()

    assert lock_path.read_bytes() == b""


def test_lock_refuses_held_advisory_lock(tmp_path):
    lock_path = tmp_path / "runner.lock"
    first = runner.acquire_instance_lock(
        lock_path,
        "python first_runner.py",
        pid=os.getpid(),
        notice=lambda message: None,
    )
    try:
        with pytest.raises(runner.AlreadyRunningError, match="runner lock is held"):
            runner.acquire_instance_lock(
                lock_path,
                "python second_runner.py",
                pid=os.getpid() + 1,
                notice=lambda message: None,
            )
    finally:
        first.release()


@pytest.mark.skipif(os.name != "nt", reason="Windows byte-range lock reader")
def test_external_reader_can_read_lock_record_while_runner_holds_lock(tmp_path):
    lock_path = tmp_path / "runner.lock"
    command_line = "python active_runner.py --deselect " + ("hedge_fund/test_example.py::test_case " * 100)
    lock = runner.acquire_instance_lock(
        lock_path,
        command_line,
        pid=os.getpid(),
        notice=lambda message: None,
    )
    try:
        code = f"from pathlib import Path; print(Path({str(lock_path)!r}).read_text(encoding='utf-8'))"
        result = subprocess.run(
            guarded_test_python_command("-c", code),
            env=child_test_environment(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        record = json.loads(result.stdout)
        assert record["pid"] == os.getpid()
        assert len(record["command_line"]) <= 64
    finally:
        lock.release()


def test_lock_record_caps_long_command_line_before_windows_lock_byte(tmp_path):
    lock_path = tmp_path / "runner.lock"
    command_line = "python run_full_suite.py --deselect " + ("test_case " * 500)
    lock = runner.acquire_instance_lock(
        lock_path,
        command_line,
        pid=9001,
        notice=lambda message: None,
    )
    try:
        raw_record = lock_path.read_bytes()
        record = json.loads(raw_record)

        assert len(raw_record) < runner.WINDOWS_LOCK_OFFSET
        assert record["pid"] == 9001
        assert record["command_line"] == command_line[:64]
    finally:
        lock.release()


def test_command_line_uses_short_script_identity(monkeypatch, tmp_path):
    script_path = tmp_path / "scripts" / "run_full_suite.py"
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [str(script_path), "--", "-k", "many pytest args"],
    )

    assert runner._command_line() == "run_full_suite.py"


def test_terminate_refuses_pid_not_returned_by_process():
    class Process:
        pid = 1234

        def poll(self):
            return None

    with pytest.raises(runner.RunnerError, match="refusing to terminate"):
        runner.terminate_process_tree(Process(), 4321)


def test_posix_termination_signals_group_after_parent_exits(monkeypatch):
    calls = []

    class Process:
        pid = 1234
        waited = False

        def poll(self):
            return 0

        def wait(self, timeout=None):
            self.waited = True

    def killpg(pid, sig):
        calls.append((pid, sig))
        if sig == 0:
            raise ProcessLookupError

    process = Process()
    monkeypatch.setattr(runner, "os", SimpleNamespace(name="posix", killpg=killpg))

    runner.terminate_process_tree(process, process.pid)

    assert calls[0] == (process.pid, signal.SIGTERM)
    assert process.waited is True


def test_terminate_stops_launched_process():
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(
        guarded_test_python_command("-c", "import time; time.sleep(60)"),
        env=child_test_environment(),
        **options,
    )
    try:
        runner.terminate_process_tree(process, process.pid)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill tree path")
def test_windows_termination_stops_descendant(tmp_path):
    child_pid_path = tmp_path / "child.pid"
    child_code = "import subprocess, sys, time\n" "child = subprocess.Popen([sys.executable, '-S', '-c', 'import time; time.sleep(60)'])\n" f"open({str(child_pid_path)!r}, 'w', encoding='utf-8').write(str(child.pid))\n" "time.sleep(60)\n"
    process = subprocess.Popen(
        guarded_test_python_command("-c", child_code),
        env=child_test_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 5.0
        while not child_pid_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))

        runner.terminate_process_tree(process, process.pid)

        assert process.poll() is not None
        deadline = time.monotonic() + 5.0
        while _pid_is_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _pid_is_running(child_pid)
    finally:
        if process.poll() is None:
            try:
                runner.terminate_process_tree(process, process.pid)
            except runner.RunnerError:
                process.kill()
                process.wait(timeout=5)
        if child_pid is not None and _pid_is_running(child_pid):
            subprocess.run(
                ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "================== 4 passed, 2 failed, 1 skipped in 0.42s ==================",
            runner.TestCounts(passed=4, failed=2, skipped=1),
        ),
        ("3 errors in 0.01s", runner.TestCounts(errors=3)),
        ("2 passed, 1 error in 1.2s", runner.TestCounts(passed=2, errors=1)),
        ("2 xfailed in 0.02s", runner.TestCounts()),
        ("no tests ran in 0.01s", runner.TestCounts()),
        ("no tests collected in 0.01s", runner.TestCounts()),
        ("no tests collected", runner.TestCounts()),
        ("collection started; still running", None),
    ],
)
def test_parse_pytest_summary(output, expected):
    assert runner.parse_pytest_summary(output) == expected


def test_parse_pytest_summary_tracks_deselected_counts():
    counts = runner.parse_pytest_summary("2 deselected in 0.01s")

    assert counts is not None
    assert getattr(counts, "deselected", None) == 2


def test_chunk_started_event_precedes_each_process_launch(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    chunk_paths = [
        repo / "hedge_fund" / "test_first.py",
        repo / "hedge_fund" / "test_second.py",
    ]
    chunk_paths[0].parent.mkdir(parents=True)
    for chunk_path in chunk_paths:
        chunk_path.write_text("", encoding="utf-8")
    progress_path = tmp_path / "progress.jsonl"
    stdout = io.StringIO()
    monkeypatch.setattr(runner.sys, "stdout", stdout)
    launched_events = []

    def process_factory(command, **kwargs):
        records = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]
        event = records[-1]
        assert event["status"] == "chunk_started"
        assert event["chunk_index"] == len(launched_events) + 1
        assert event["expected_chunks"] == 2
        assert event["total_chunks"] == 2
        assert event["completed_chunks"] == len(launched_events)
        assert json.loads(stdout.getvalue().splitlines()[-1]) == event
        launched_events.append(event)

        process = SimpleNamespace(pid=5100 + len(launched_events), returncode=0)
        process.communicate = lambda timeout=None: ("1 passed in 0.01s\n", None)
        process.poll = lambda: process.returncode
        return process

    result = runner.run_chunks(
        repo,
        chunk_paths,
        sys.executable,
        [],
        60.0,
        10.0,
        progress_path,
        "run-start-events",
        process_factory=process_factory,
        monotonic=lambda: 0.0,
    )

    progress_events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]
    started_events = [event for event in progress_events if event["status"] == "chunk_started"]
    printed_events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith("{")]
    assert result.incomplete is False
    assert [event["chunk"] for event in started_events] == [
        "hedge_fund/test_first.py",
        "hedge_fund/test_second.py",
    ]
    assert [event["chunk_index"] for event in started_events] == [1, 2]
    assert [event["completed_chunks"] for event in started_events] == [0, 1]
    assert [event["expected_chunks"] for event in started_events] == [2, 2]
    assert printed_events == started_events


def test_chunk_result_keeps_existing_positional_field_order():
    result = runner.ChunkResult(
        "hedge_fund/test_one.py",
        "passed",
        1,
        2,
        3,
        4,
        1.25,
        17,
        None,
        True,
    )

    assert result.duration_seconds == 1.25
    assert result.returncode == 17
    assert result.timeout_scope is None
    assert result.summary_found is True
    assert result.deselected is None


@pytest.mark.parametrize(
    ("output", "expected_status", "expected_deselected"),
    [
        ("2 deselected in 0.01s", "deselected", 2),
        ("no tests ran in 0.01s", "no_tests", 0),
        ("no tests collected in 0.01s", "no_tests", 0),
    ],
)
def test_deselected_and_no_tests_chunks_are_non_errors(tmp_path, output, expected_status, expected_deselected):
    repo = tmp_path / "repo"
    chunk = repo / "hedge_fund" / "test_empty.py"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("", encoding="utf-8")

    class Process:
        pid = 1234
        returncode = 5

        def communicate(self, timeout=None):
            return output, None

        def poll(self):
            return self.returncode

    commands = []

    def process_factory(command, **kwargs):
        commands.append(command)
        return Process()

    events = []
    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        60.0,
        10.0,
        tmp_path / "progress.jsonl",
        "run-empty",
        process_factory=process_factory,
        monotonic=lambda: 0.0,
        progress_writer=lambda path, event: events.append(event),
    )

    chunk_result = result.chunks[0]
    assert chunk_result.status == expected_status
    assert chunk_result.deselected == expected_deselected
    assert result.incomplete is False
    assert result.runner_errors == []
    summary = runner.build_summary("run-empty", "start", "finish", 1.0, result)
    assert summary["deselected"] == expected_deselected
    assert runner.summary_exit_code(summary) == 0
    assert "--color=no" in commands[0]
    assert events[0]["status"] == "chunk_started"
    assert events[0]["completed_chunks"] == 0
    assert events[0]["expected_chunks"] == 1
    assert events[1]["completed_chunks"] == 1
    assert events[1]["current_chunk"] == "hedge_fund/test_empty.py"


@pytest.mark.parametrize(
    "output",
    [
        "captured output says no tests ran\n1 passed in 0.1s\n",
        "captured output says no tests collected\n1 passed in 0.1s\n",
        "captured output says 5 deselected in 0.1s\n1 passed in 0.2s\n",
    ],
)
def test_chunk_status_uses_final_pytest_summary_line(tmp_path, output):
    repo = tmp_path / "repo"
    chunk = repo / "hedge_fund" / "test_output.py"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("", encoding="utf-8")

    class Process:
        pid = 1235
        returncode = 0

        def communicate(self, timeout=None):
            return output, None

        def poll(self):
            return self.returncode

    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        60.0,
        10.0,
        tmp_path / "progress.jsonl",
        "run-output-summary",
        process_factory=lambda command, **kwargs: Process(),
        monotonic=lambda: 0.0,
        progress_writer=lambda path, event: None,
    )

    assert result.chunks[0].status == "passed"
    assert result.chunks[0].passed == 1
    assert result.chunks[0].deselected == 0


def test_nonzero_pytest_exit_with_summary_is_an_error(tmp_path):
    repo = tmp_path / "repo"
    chunk = repo / "hedge_fund" / "test_nonzero.py"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("", encoding="utf-8")

    class Process:
        pid = 1234
        returncode = 1

        def communicate(self, timeout=None):
            return "2 passed in 0.1s\n", None

        def poll(self):
            return self.returncode

    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        60.0,
        10.0,
        tmp_path / "progress.jsonl",
        "run-nonzero",
        process_factory=lambda command, **kwargs: Process(),
        monotonic=lambda: 0.0,
        progress_writer=lambda path, event: None,
    )

    assert result.chunks[0].status == "error"
    assert result.chunks[0].summary_found is True
    assert result.runner_errors
    summary = runner.build_summary("run-nonzero", "start", "finish", 1.0, result)
    assert runner.summary_exit_code(summary) == 2


def test_timeout_budget_uses_earliest_deadline():
    assert runner.calculate_timeout_budget(20.0, 5.0) == (5.0, "chunk")
    assert runner.calculate_timeout_budget(3.0, 5.0) == (3.0, "wall")
    assert runner.calculate_timeout_budget(0.0, 5.0) == (0.0, "wall")


def test_timeout_records_partial_counts_and_last_completed_chunk(tmp_path):
    class TimedOutProcess:
        pid = 4567
        returncode = None

        def __init__(self):
            self.communications = 0

        def communicate(self, timeout=None):
            self.communications += 1
            if self.communications == 1:
                raise subprocess.TimeoutExpired(["python", "-m", "pytest"], timeout, output="1 passed in 0.1s\n")
            self.returncode = -15
            return "1 passed in 0.1s\n", None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

    process = TimedOutProcess()
    terminated = []
    events = []
    repo = tmp_path / "repo"
    repo.mkdir()
    chunk = repo / "hedge_fund" / "test_one.py"
    chunk.parent.mkdir()
    chunk.write_text("", encoding="utf-8")

    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        60.0,
        1.0,
        tmp_path / "progress.jsonl",
        "run-1",
        process_factory=lambda command, **kwargs: process,
        monotonic=lambda: 0.0,
        terminator=lambda child, pid: terminated.append((child, pid)),
        progress_writer=lambda path, event: events.append(event),
    )

    assert result.incomplete
    assert result.last_completed_chunk is None
    assert result.chunks[0].status == "timeout"
    assert result.chunks[0].passed == 1
    assert result.chunks[0].timeout_scope == "chunk"
    assert terminated == [(process, process.pid)]
    assert events[0]["status"] == "chunk_started"
    assert events[1]["status"] == "timeout"
    assert events[1]["chunk"] == "hedge_fund/test_one.py"
    assert events[1]["completed_chunks"] == 0
    assert events[1]["expected_chunks"] == 1
    assert events[1]["current_chunk"] == "hedge_fund/test_one.py"


def test_wall_clock_timeout_through_run_chunks(tmp_path):
    class TimedOutProcess:
        pid = 4568
        returncode = None

        def __init__(self):
            self.communications = 0

        def communicate(self, timeout=None):
            self.communications += 1
            if self.communications == 1:
                raise subprocess.TimeoutExpired(["python", "-m", "pytest"], timeout)
            return "", None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

    process = TimedOutProcess()
    repo = tmp_path / "repo"
    repo.mkdir()
    chunk = repo / "hedge_fund" / "test_wall.py"
    chunk.parent.mkdir()
    chunk.write_text("", encoding="utf-8")

    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        1.0,
        60.0,
        tmp_path / "progress.jsonl",
        "run-wall",
        process_factory=lambda command, **kwargs: process,
        monotonic=lambda: 0.0,
        terminator=lambda child, pid: setattr(child, "returncode", -15),
        progress_writer=lambda path, event: None,
    )

    assert result.incomplete is True
    assert result.chunks[0].status == "timeout"
    assert result.chunks[0].timeout_scope == "wall"
    assert "wall-clock timeout" in result.runner_errors[0]


def _pid_is_running(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "posix":
        stat_path = Path("/proc") / str(pid) / "stat"
        if stat_path.is_file():
            try:
                return stat_path.read_text(encoding="utf-8").split()[2] != "Z"
            except (OSError, IndexError):
                return False
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
    get_exit_code_process = kernel32.GetExitCodeProcess
    get_exit_code_process.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    get_exit_code_process.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = open_process(0x1000, 0, pid)
    if handle:
        try:
            exit_code = ctypes.c_uint32()
            if not get_exit_code_process(handle, ctypes.byref(exit_code)):
                raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed while checking test PID", pid)
            return exit_code.value == 259
        finally:
            close_handle(handle)
    error_code = ctypes.get_last_error()
    if error_code == 5:
        return True
    if error_code in {6, 87}:
        return False
    raise OSError(error_code, "OpenProcess failed while checking test PID", pid)


def test_timeout_kills_descendant_holding_stdout_after_parent_exits(tmp_path):
    child_pid_path = tmp_path / "child.pid"
    child_code = "import time; time.sleep(60)"
    parent_code = "import subprocess, sys\n" f"child = subprocess.Popen([sys.executable, '-S', '-c', {child_code!r}])\n" f"open({str(child_pid_path)!r}, 'w', encoding='utf-8').write(str(child.pid))\n" "print('1 passed in 0.1s', flush=True)\n"
    repo = tmp_path / "repo"
    chunk = repo / "hedge_fund" / "test_descendant.py"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("", encoding="utf-8")
    launched = []

    def process_factory(command, **kwargs):
        process = subprocess.Popen(
            guarded_test_python_command("-c", parent_code),
            env=child_test_environment(),
            **kwargs,
        )
        launched.append(process)
        return process

    timeout_terminations = []

    def terminate_after_timeout(process, pid):
        timeout_terminations.append(pid)
        runner.terminate_process_tree(process, pid)

    child_pid = None
    try:
        result = runner.run_chunks(
            repo,
            [chunk],
            sys.executable,
            [],
            10.0,
            2.0,
            tmp_path / "progress.jsonl",
            "run-descendant",
            process_factory=process_factory,
            terminator=terminate_after_timeout,
            progress_writer=lambda path, event: None,
        )
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        assert launched[0].poll() is not None
        assert result.chunks[0].status == "passed"
        assert result.chunks[0].returncode == 0
        assert result.incomplete is False
        assert result.runner_errors == []
        assert timeout_terminations == [launched[0].pid]

        deadline = time.monotonic() + 5.0
        while _pid_is_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _pid_is_running(child_pid)
    finally:
        if child_pid is None and child_pid_path.exists():
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        if child_pid is not None and _pid_is_running(child_pid):
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            else:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except OSError:
                    pass
        for process in launched:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def test_exited_pytest_with_unterminated_descendant_is_not_labeled_timeout(tmp_path):
    class Process:
        pid = 4570
        returncode = 0

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(["python", "-m", "pytest"], timeout, output="1 passed in 0.1s\n")

        def poll(self):
            return self.returncode

    repo = tmp_path / "repo"
    chunk = repo / "hedge_fund" / "test_descendant_cleanup.py"
    chunk.parent.mkdir(parents=True)
    chunk.write_text("", encoding="utf-8")

    def failed_terminator(process, launched_pid):
        raise runner.RunnerError("descendant cleanup failed")

    result = runner.run_chunks(
        repo,
        [chunk],
        sys.executable,
        [],
        60.0,
        1.0,
        tmp_path / "progress.jsonl",
        "run-cleanup-error",
        process_factory=lambda command, **kwargs: Process(),
        monotonic=lambda: 0.0,
        terminator=failed_terminator,
        progress_writer=lambda path, event: None,
    )

    assert result.chunks[0].status == "error"
    assert result.chunks[0].timeout_scope is None
    assert result.chunks[0].passed == 1
    assert result.incomplete is True
    assert any("descendant cleanup failed" in message for message in result.runner_errors)


def test_summary_aggregates_counts_and_timeout_is_incomplete():
    chunks = [
        runner.ChunkResult(
            chunk="hedge_fund/test_a.py",
            status="failed",
            passed=2,
            failed=1,
            skipped=0,
            errors=2,
            duration_seconds=1.25,
            returncode=0,
            summary_found=True,
        ),
        runner.ChunkResult(
            chunk="hedge_fund/test_b.py",
            status="timeout",
            passed=None,
            failed=None,
            skipped=None,
            errors=None,
            duration_seconds=4.0,
        ),
    ]
    result = runner.ExecutionResult(
        chunks=chunks,
        incomplete=True,
        last_completed_chunk="hedge_fund/test_a.py",
    )

    summary = runner.build_summary(
        "run-1",
        "2026-11-27T09:00:00+00:00",
        "2026-11-27T09:05:00+00:00",
        300.0,
        result,
    )

    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["skipped"] == 0
    assert summary["errors"] == 2
    assert summary["incomplete"] is True
    assert summary["last_completed_chunk"] == "hedge_fund/test_a.py"
    assert runner.summary_exit_code(summary) == 2


def test_summary_exit_code_keeps_unexplained_pytest_exit_as_runner_error():
    result = runner.ExecutionResult(
        chunks=[
            runner.ChunkResult(
                chunk="hedge_fund/test_a.py",
                status="error",
                passed=3,
                failed=0,
                skipped=0,
                errors=0,
                returncode=1,
                summary_found=True,
            )
        ],
        runner_errors=["pytest exited with code 1 despite a clean summary"],
        last_completed_chunk="hedge_fund/test_a.py",
    )
    summary = runner.build_summary(
        "run-1",
        "2026-11-27T09:00:00+00:00",
        "2026-11-27T09:01:00+00:00",
        60.0,
        result,
    )

    assert runner.summary_exit_code(summary) == 2


def test_failure_summary_maps_to_exit_one():
    result = runner.ExecutionResult(
        chunks=[
            runner.ChunkResult(
                chunk="hedge_fund/test_a.py",
                status="failed",
                passed=2,
                failed=1,
                skipped=0,
                errors=0,
                summary_found=True,
            )
        ],
        last_completed_chunk="hedge_fund/test_a.py",
    )
    summary = runner.build_summary(
        "run-1",
        "2026-11-27T09:00:00+00:00",
        "2026-11-27T09:01:00+00:00",
        60.0,
        result,
    )

    assert runner.summary_exit_code(summary) == 1


def test_resolve_poetry_uses_venv_interpreter(tmp_path):
    env_path = tmp_path / "venv"
    executable = env_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=str(env_path))

    assert runner.resolve_poetry_python(tmp_path, fallback="fallback-python", run=fake_run) == str(executable)
    assert calls[0][0] == ["poetry", "env", "info", "-p"]
    assert calls[0][1]["cwd"] == str(tmp_path)


def test_progress_appends_one_jsonl_record_per_event(tmp_path):
    progress_path = tmp_path / "progress.jsonl"
    first = {"chunk": "hedge_fund/test_a.py", "status": "passed"}
    second = {"chunk": "hedge_fund/test_b.py", "status": "failed"}

    runner.append_progress_event(progress_path, first)
    runner.append_progress_event(progress_path, second)

    assert [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()] == [first, second]


def test_summary_writer_persists_json(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary = {"incomplete": True, "last_completed_chunk": "hedge_fund/test_a.py"}

    runner.write_summary(summary_path, summary)

    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_summary_writer_failure_preserves_previous_summary(tmp_path, monkeypatch):
    summary_path = tmp_path / "summary.json"
    previous_summary = b'{"run_id": "previous"}\n'
    summary_path.write_bytes(previous_summary)

    def fail_dump(summary, handle, **kwargs):
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(runner.json, "dump", fail_dump)

    with pytest.raises(RuntimeError, match="serialization failed"):
        runner.write_summary(summary_path, {"run_id": "new"})

    assert summary_path.read_bytes() == previous_summary
    assert list(tmp_path.iterdir()) == [summary_path]


def _configure_main_test(monkeypatch, tmp_path, run_chunks):
    repo_root = tmp_path / "repo"
    test_root = repo_root / "hedge_fund"
    test_root.mkdir(parents=True)
    test_file = test_root / "test_one.py"
    test_file.write_text("", encoding="utf-8")
    state_dir = tmp_path / "state"
    progress_file = tmp_path / "progress.jsonl"
    summary_file = tmp_path / "summary.json"
    monkeypatch.setattr(runner, "REPO_ROOT", repo_root)
    monkeypatch.setattr(runner, "default_state_dir", lambda repo_root=repo_root: state_dir)
    monkeypatch.setattr(runner, "resolve_poetry_python", lambda repo_root: sys.executable)
    monkeypatch.setattr(runner, "run_chunks", run_chunks)
    argv = [
        "--timeout-minutes",
        "1",
        "--progress-file",
        str(progress_file),
        "--summary-file",
        str(summary_file),
    ]
    return repo_root, test_file, state_dir, progress_file, summary_file, argv


def test_main_writes_start_event_summary_and_exit_code(tmp_path, monkeypatch, capfd):
    def fake_run_chunks(repo_root, test_files, python_executable, pytest_args, timeout_seconds, chunk_timeout_seconds, progress_file, run_id, **kwargs):
        assert repo_root == tmp_path / "repo"
        assert list(test_files) == [tmp_path / "repo" / "hedge_fund" / "test_one.py"]
        return runner.ExecutionResult(
            chunks=[
                runner.ChunkResult(
                    chunk="hedge_fund/test_one.py",
                    status="failed",
                    passed=2,
                    failed=1,
                    skipped=0,
                    errors=0,
                    returncode=1,
                    summary_found=True,
                )
            ],
            last_completed_chunk="hedge_fund/test_one.py",
        )

    _, _, state_dir, progress_file, summary_file, argv = _configure_main_test(monkeypatch, tmp_path, fake_run_chunks)

    assert runner.main(argv) == 1

    progress_events = [json.loads(line) for line in progress_file.read_text(encoding="utf-8").splitlines()]
    started_event = progress_events[0]
    assert started_event["status"] == "run_started"
    assert started_event["pid"] == os.getpid()
    assert started_event["progress_path"] == str(progress_file.resolve())
    assert started_event["summary_path"] == str(summary_file.resolve())
    assert started_event["lock_path"] == str((state_dir / "runner.lock").resolve())
    assert started_event["total_chunks"] == 1
    assert started_event["completed_chunks"] == 0
    assert started_event["expected_chunks"] == 1
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["run_id"] == started_event["run_id"]
    assert summary["failed"] == 1
    assert summary["started_at"]
    assert (state_dir / "runner.lock").read_bytes() == b""
    stdout_lines = capfd.readouterr().out.splitlines()
    assert json.loads(stdout_lines[0]) == started_event


def test_main_run_twice_releases_lock_record_without_stale_warning(tmp_path, monkeypatch, capfd):
    def fake_run_chunks(repo_root, test_files, python_executable, pytest_args, timeout_seconds, chunk_timeout_seconds, progress_file, run_id, **kwargs):
        return runner.ExecutionResult(
            chunks=[
                runner.ChunkResult(
                    chunk="hedge_fund/test_one.py",
                    status="passed",
                    passed=1,
                    failed=0,
                    skipped=0,
                    errors=0,
                    returncode=0,
                    summary_found=True,
                )
            ],
            last_completed_chunk="hedge_fund/test_one.py",
        )

    _, _, state_dir, progress_file, summary_file, argv = _configure_main_test(monkeypatch, tmp_path, fake_run_chunks)

    assert runner.main(argv) == 0
    assert runner.main(argv) == 0

    started_events = [json.loads(line) for line in progress_file.read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "run_started"]
    assert len(started_events) == 2
    assert started_events[0]["run_id"] != started_events[1]["run_id"]
    assert json.loads(summary_file.read_text(encoding="utf-8"))["run_id"] == started_events[1]["run_id"]
    assert (state_dir / "runner.lock").read_bytes() == b""
    assert "Reclaiming" not in capfd.readouterr().err


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, RuntimeError])
def test_main_preserves_partial_counts_when_chunk_runner_raises(tmp_path, monkeypatch, exception_type):
    def fake_run_chunks(repo_root, test_files, python_executable, pytest_args, timeout_seconds, chunk_timeout_seconds, progress_file, run_id, *, result, **kwargs):
        result.chunks.append(
            runner.ChunkResult(
                chunk="hedge_fund/test_one.py",
                status="passed",
                passed=3,
                failed=0,
                skipped=0,
                errors=0,
                returncode=0,
                summary_found=True,
            )
        )
        result.last_completed_chunk = "hedge_fund/test_one.py"
        raise exception_type("interrupted")

    _, _, _, _, summary_file, argv = _configure_main_test(monkeypatch, tmp_path, fake_run_chunks)

    assert runner.main(argv) == 2

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["passed"] == 3
    assert summary["incomplete"] is True
    assert summary["runner_errors"]


def test_parse_arguments_splits_pytest_passthrough():
    args, pytest_args = runner.parse_arguments(["--timeout-minutes", "2", "--", "-q", "-k", "runtime"])

    assert args.timeout_minutes == 2.0
    assert pytest_args == ["-q", "-k", "runtime"]


def test_timeout_default_and_runner_behavior_are_documented():
    args, _ = runner.parse_arguments([])
    help_text = runner.build_parser().format_help()

    assert args.timeout_minutes == 300.0
    assert "--timeout-minutes" in help_text
    assert "3.7 hours" in help_text
    assert "15-20 s" in help_text
    assert "outputs/spec005-test-*" in help_text
    assert "-qq" in help_text
    assert "started-but-stopped" in "".join(help_text.split())
