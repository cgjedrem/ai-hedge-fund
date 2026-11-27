import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from hedge_fund.test_support.network_guard import (
    child_test_environment,
    guarded_test_python_command,
)
from scripts import run_full_suite as runner


def _write_lock(path, pid, command_line):
    path.write_text(
        json.dumps({"pid": pid, "command_line": command_line}),
        encoding="utf-8",
    )


def test_lock_refuses_live_pid_without_overwriting_record(tmp_path):
    lock_path = tmp_path / "runner.lock"
    _write_lock(lock_path, 8123, "python active_runner.py")

    with pytest.raises(runner.AlreadyRunningError, match="8123"):
        runner.acquire_instance_lock(
            lock_path,
            "python new_runner.py",
            pid=9001,
            is_alive=lambda pid: pid == 8123,
            notice=lambda message: None,
        )

    assert json.loads(lock_path.read_text(encoding="utf-8")) == {
        "pid": 8123,
        "command_line": "python active_runner.py",
    }


def test_lock_reclaims_dead_pid_with_notice(tmp_path):
    lock_path = tmp_path / "runner.lock"
    _write_lock(lock_path, 8123, "python dead_runner.py")
    notices = []

    lock = runner.acquire_instance_lock(
        lock_path,
        "python new_runner.py",
        pid=9001,
        is_alive=lambda pid: False,
        notice=notices.append,
    )
    try:
        assert notices == ["Reclaiming stale runner lock for dead PID 8123."]
    finally:
        lock.release()

    assert json.loads(lock_path.read_text(encoding="utf-8")) == {
        "pid": 9001,
        "command_line": "python new_runner.py",
    }


def test_lock_refuses_held_advisory_lock(tmp_path):
    lock_path = tmp_path / "runner.lock"
    first = runner.acquire_instance_lock(
        lock_path,
        "python first_runner.py",
        pid=os.getpid(),
        is_alive=lambda pid: True,
        notice=lambda message: None,
    )
    try:
        with pytest.raises(runner.AlreadyRunningError, match="runner lock is held"):
            runner.acquire_instance_lock(
                lock_path,
                "python second_runner.py",
                pid=os.getpid() + 1,
                is_alive=lambda pid: False,
                notice=lambda message: None,
            )
    finally:
        first.release()


def test_terminate_refuses_pid_not_returned_by_process():
    class Process:
        pid = 1234

        def poll(self):
            return None

    with pytest.raises(runner.RunnerError, match="refusing to terminate"):
        runner.terminate_process_tree(Process(), 4321)


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
        while runner._pid_is_alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not runner._pid_is_alive(child_pid)
    finally:
        if process.poll() is None:
            try:
                runner.terminate_process_tree(process, process.pid)
            except runner.RunnerError:
                process.kill()
                process.wait(timeout=5)
        if child_pid is not None and runner._pid_is_alive(child_pid):
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
        ("no tests ran in 0.01s", None),
        ("collection started; still running", None),
    ],
)
def test_parse_pytest_summary(output, expected):
    assert runner.parse_pytest_summary(output) == expected


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
    assert events[0]["status"] == "timeout"
    assert events[0]["chunk"] == "hedge_fund/test_one.py"


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


def test_summary_counts_override_pytest_return_code():
    result = runner.ExecutionResult(
        chunks=[
            runner.ChunkResult(
                chunk="hedge_fund/test_a.py",
                status="passed",
                passed=3,
                failed=0,
                skipped=0,
                errors=0,
                returncode=1,
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

    assert runner.summary_exit_code(summary) == 0


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


def test_parse_arguments_splits_pytest_passthrough():
    args, pytest_args = runner.parse_arguments(["--timeout-minutes", "2", "--", "-q", "-k", "runtime"])

    assert args.timeout_minutes == 2.0
    assert pytest_args == ["-q", "-k", "runtime"]
