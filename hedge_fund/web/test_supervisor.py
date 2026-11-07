import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hedge_fund.web import supervisor


class _FakeSignals:
    SIGHUP = 1
    SIGINT = 2
    SIGTERM = 15
    SIGUSR1 = 10

    def __init__(self):
        self.handlers = {
            self.SIGHUP: object(),
            self.SIGINT: object(),
            self.SIGTERM: object(),
            self.SIGUSR1: object(),
        }

    def signal(self, signum, handler):
        previous = self.handlers[signum]
        self.handlers[signum] = handler
        return previous


class _FakeProcess:
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode


def _options(root: Path, **updates):
    values = {
        "root": root,
        "port": 8876,
        "enable_writes_after_trust": True,
        "enable_network_after_trust": True,
    }
    values.update(updates)
    return supervisor.SupervisorOptions(**values)


def test_web_child_starts_read_only_until_explicit_reload(tmp_path):
    authority_checks = []

    def authority_check(root):
        authority_checks.append(root)
        return True

    options = _options(tmp_path)
    initial = supervisor._web_command(
        options,
        activated=False,
        authority_check=authority_check,
        executable="aihf-web",
    )
    assert initial == ["aihf-web", "--root", str(tmp_path), "--port", "8876"]
    assert authority_checks == []

    activated = supervisor._web_command(
        options,
        activated=True,
        authority_check=authority_check,
        executable="aihf-web",
    )
    assert activated == [
        "aihf-web",
        "--root",
        str(tmp_path),
        "--port",
        "8876",
        "--allow-writes",
        "--enable-network",
    ]
    assert authority_checks == [tmp_path]


def test_web_child_stays_read_only_when_current_runtime_is_not_trusted(tmp_path):
    command = supervisor._web_command(
        _options(tmp_path),
        activated=True,
        authority_check=lambda _root: False,
        executable="aihf-web",
    )

    assert "--allow-writes" not in command
    assert "--enable-network" not in command


def test_web_child_does_not_hide_authority_check_errors(tmp_path):
    def authority_check(_root):
        raise OSError("synthetic authority failure")

    with pytest.raises(OSError, match="synthetic authority failure"):
        supervisor._web_command(
            _options(tmp_path),
            activated=True,
            authority_check=authority_check,
            executable="aihf-web",
        )


def test_current_authority_failure_is_reported_and_denied(tmp_path, monkeypatch, capsys):
    from hedge_fund.runtime import handover

    def unavailable(*_args, **_kwargs):
        raise handover.HandoverError("synthetic authority unavailable")

    monkeypatch.setattr(handover, "enrollment_status", unavailable)

    assert supervisor._current_write_authority(tmp_path) is False
    assert "HandoverError" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("authority", "expected"),
    [
        ({"authority": "protocol-native", "reason": None}, False),
        ({"authority": "operator-trusted-single-writer", "reason": None}, True),
    ],
)
def test_current_authority_requires_explicit_single_writer_trust(tmp_path, monkeypatch, authority, expected):
    from hedge_fund.runtime import handover

    monkeypatch.setattr(
        handover,
        "enrollment_status",
        lambda *_args, **_kwargs: {"state": "enrolled", "reason": None},
    )
    monkeypatch.setattr(handover, "write_authority", lambda _root: authority)

    assert supervisor._current_write_authority(tmp_path) is expected


def test_network_capability_requires_write_opt_in_and_verified_trust(tmp_path):
    options = _options(tmp_path, enable_writes_after_trust=False)
    command = supervisor._web_command(
        options,
        activated=True,
        authority_check=lambda _root: True,
        executable="aihf-web",
    )

    assert "--allow-writes" not in command
    assert "--enable-network" not in command


def test_sighup_restarts_only_web_child_and_preserves_supervisor_process(tmp_path):
    signals = _FakeSignals()
    previous_handlers = signals.handlers.copy()
    processes = []
    commands = []
    supervisor_pids = []
    events = []
    authority_checks = []

    def popen(command, **kwargs):
        commands.append(list(command))
        assert kwargs["start_new_session"] is True
        processes.append(_FakeProcess(1000 + len(processes)))
        supervisor_pids.append(os.getpid())
        return processes[-1]

    def terminate(process, _timeout):
        events.append(("terminated", process.pid))
        process.returncode = 0

    def authority_check(root):
        assert processes[0].returncode == 0
        events.append(("authority", root))
        authority_checks.append(root)
        return True

    fired_reload = False
    fired_stop = False

    def sleep(_seconds):
        nonlocal fired_reload, fired_stop
        if len(processes) == 1 and not fired_reload:
            fired_reload = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
        elif len(processes) == 2 and not fired_stop:
            fired_stop = True
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=authority_check,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 2
    assert "--allow-writes" not in commands[0]
    assert "--allow-writes" in commands[1]
    assert processes[0].pid != processes[1].pid
    assert len(set(supervisor_pids)) == 1
    assert len(authority_checks) == 1
    assert events.index(("terminated", processes[0].pid)) < events.index(("authority", tmp_path))
    assert signals.handlers == previous_handlers


def test_sigusr1_downgrades_before_revoke_and_hup_stays_read_only(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    events = []
    trusted = True
    sent_hup = False
    sent_downgrade = False
    sent_recheck = False
    sent_stop = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(1500 + len(processes))
        processes.append(process)
        return process

    def terminate(process, _timeout):
        process.returncode = 0
        events.append(("terminated", process.pid))

    def authority_check(_root):
        events.append(("authority", trusted))
        return trusted

    def sleep(_seconds):
        nonlocal trusted, sent_hup, sent_downgrade, sent_recheck, sent_stop
        if len(processes) == 1 and not sent_hup:
            sent_hup = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
        elif len(processes) == 2 and not sent_downgrade:
            sent_downgrade = True
            signals.handlers[signals.SIGUSR1](signals.SIGUSR1, None)
        elif len(processes) == 3 and not sent_recheck:
            trusted = False
            events.append(("cli-revoke",))
            sent_recheck = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
        elif len(processes) == 4 and not sent_stop:
            sent_stop = True
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=authority_check,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 4
    assert "--allow-writes" not in commands[0]
    assert "--allow-writes" in commands[1]
    assert "--allow-writes" not in commands[2]
    assert "--allow-writes" not in commands[3]
    assert events.index(("terminated", processes[1].pid)) < events.index(("cli-revoke",))
    assert events.index(("cli-revoke",)) < events.index(("authority", False))
    assert [event for event in events if event[0] == "authority"] == [
        ("authority", True),
        ("authority", False),
    ]


def test_sigusr1_during_authority_check_suppresses_write_child(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    authority_checks = []
    fired_hup = False
    fired_stop = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(1600 + len(processes))
        processes.append(process)
        return process

    def authority_check(_root):
        authority_checks.append(True)
        signals.handlers[signals.SIGUSR1](signals.SIGUSR1, None)
        return True

    def sleep(_seconds):
        nonlocal fired_hup, fired_stop
        if not fired_hup:
            fired_hup = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
        elif not fired_stop:
            fired_stop = True
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=lambda process, _timeout: setattr(process, "returncode", 0),
        reap_children=lambda _pid: 0,
        authority_check=authority_check,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 2
    assert all("--allow-writes" not in command for command in commands)
    assert authority_checks == [True]
    assert all(process.poll() == 0 for process in processes)


def test_sigterm_during_downgrade_does_not_start_read_only_child(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    authority_checks = []
    fired_hup = False
    fired_downgrade = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(1700 + len(processes))
        processes.append(process)
        return process

    def terminate(process, _timeout):
        process.returncode = 0
        if len(processes) > 1 and process is processes[1]:
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    def sleep(_seconds):
        nonlocal fired_hup, fired_downgrade
        if len(processes) == 1 and not fired_hup:
            fired_hup = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)
        elif len(processes) == 2 and not fired_downgrade:
            fired_downgrade = True
            signals.handlers[signals.SIGUSR1](signals.SIGUSR1, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=lambda root: authority_checks.append(root) or True,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 2
    assert "--allow-writes" not in commands[0]
    assert "--allow-writes" in commands[1]
    assert authority_checks == [tmp_path]


def test_sigterm_during_reload_does_not_start_another_child(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    authority_checks = []
    fired_reload = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(2000 + len(processes))
        processes.append(process)
        return process

    def terminate(process, _timeout):
        process.returncode = 0
        signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    def sleep(_seconds):
        nonlocal fired_reload
        if not fired_reload:
            fired_reload = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=lambda root: authority_checks.append(root) or True,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 1
    assert "--allow-writes" not in commands[0]
    assert authority_checks == []


def test_sigterm_during_authority_check_does_not_launch_child(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    fired_reload = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(2500 + len(processes))
        processes.append(process)
        return process

    def terminate(process, _timeout):
        process.returncode = 0

    def authority_check(_root):
        signals.handlers[signals.SIGTERM](signals.SIGTERM, None)
        return True

    def sleep(_seconds):
        nonlocal fired_reload
        if not fired_reload:
            fired_reload = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=authority_check,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 1
    assert "--allow-writes" not in commands[0]


def test_sigterm_during_spawn_terminates_new_child(tmp_path):
    signals = _FakeSignals()
    processes = []
    commands = []
    terminated = []
    fired_reload = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(2600 + len(processes))
        processes.append(process)
        if len(processes) == 2:
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)
        return process

    def terminate(process, _timeout):
        terminated.append(process.pid)
        process.returncode = 0

    def sleep(_seconds):
        nonlocal fired_reload
        if not fired_reload:
            fired_reload = True
            signals.handlers[signals.SIGHUP](signals.SIGHUP, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=lambda _root: True,
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 2
    assert "--allow-writes" in commands[1]
    assert terminated == [process.pid for process in processes]
    assert all(process.poll() == 0 for process in processes)


def test_sigterm_gracefully_stops_child_and_restores_handlers(tmp_path):
    signals = _FakeSignals()
    previous_handlers = signals.handlers.copy()
    processes = []
    commands = []
    terminated = []
    fired_stop = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(3000 + len(processes))
        processes.append(process)
        return process

    def terminate(process, _timeout):
        terminated.append(process.pid)
        process.returncode = 0

    def sleep(_seconds):
        nonlocal fired_stop
        if not fired_stop:
            fired_stop = True
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=terminate,
        reap_children=lambda _pid: 0,
        authority_check=lambda _root: pytest.fail("read-only startup checked authority"),
        executable="aihf-web",
    )

    assert result == 0
    assert len(commands) == 1
    assert "--allow-writes" not in commands[0]
    assert terminated == [processes[0].pid]
    assert signals.handlers == previous_handlers


def test_child_crash_propagates_exit_and_restores_handlers(tmp_path):
    signals = _FakeSignals()
    previous_handlers = signals.handlers.copy()
    processes = []
    commands = []
    slept = False

    def popen(command, **_kwargs):
        commands.append(list(command))
        process = _FakeProcess(4000 + len(processes))
        processes.append(process)
        return process

    def sleep(_seconds):
        nonlocal slept
        if not slept:
            slept = True
            processes[0].returncode = 23

    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=popen,
        signal_api=signals,
        sleep=sleep,
        terminate_child=lambda _process, _timeout: pytest.fail("exited child was terminated"),
        reap_children=lambda _pid: 0,
        authority_check=lambda _root: pytest.fail("read-only startup checked authority"),
        executable="aihf-web",
    )

    assert result == 23
    assert len(commands) == 1
    assert "--allow-writes" not in commands[0]
    assert signals.handlers == previous_handlers


def test_reaper_never_waits_for_active_popen_child(monkeypatch):
    waitpid_calls = []
    fake_os = SimpleNamespace(
        name="posix",
        P_ALL=0,
        WEXITED=1,
        WNOHANG=2,
        WNOWAIT=4,
        waitid=lambda *_args: SimpleNamespace(si_pid=4321),
        waitpid=lambda *args: waitpid_calls.append(args),
    )
    monkeypatch.setattr(supervisor, "os", fake_os)

    assert supervisor._reap_adopted_children(current_child_pid=4321) == 0
    assert waitpid_calls == []


def test_reaper_waits_only_for_exited_adopted_children(monkeypatch):
    pending = iter((SimpleNamespace(si_pid=4322), SimpleNamespace(si_pid=0)))
    waitid_calls = []
    waitpid_calls = []

    def waitid(*args):
        waitid_calls.append(args)
        return next(pending)

    def waitpid(pid, flags):
        waitpid_calls.append((pid, flags))
        return pid, 0

    fake_os = SimpleNamespace(
        name="posix",
        P_ALL=0,
        WEXITED=1,
        WNOHANG=2,
        WNOWAIT=4,
        waitid=waitid,
        waitpid=waitpid,
    )
    monkeypatch.setattr(supervisor, "os", fake_os)

    assert supervisor._reap_adopted_children(current_child_pid=4321) == 1
    assert waitid_calls[0] == (fake_os.P_ALL, 0, fake_os.WEXITED | fake_os.WNOHANG | fake_os.WNOWAIT)
    assert waitpid_calls == [(4322, fake_os.WNOHANG)]


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "waitid"), reason="POSIX waitid required")
def test_reaper_preserves_subprocess_popen_exit_status():
    program = "\n".join(
        (
            "import os, subprocess, sys, time",
            "from hedge_fund.web.supervisor import _reap_adopted_children",
            "child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.exit(37)'])",
            "while True:",
            "    status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)",
            "    if status is not None and status.si_pid:",
            "        break",
            "    time.sleep(0.01)",
            "assert _reap_adopted_children(child.pid) == 0",
            "print(child.wait(timeout=2))",
        )
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "37"


def test_child_shutdown_timeout_is_clear_and_nonzero(tmp_path, monkeypatch, capsys):
    signals = _FakeSignals()
    kill_signals = []
    waits = []
    fired_stop = False

    class _NeverExitProcess(_FakeProcess):
        def wait(self, timeout):
            waits.append(timeout)
            raise subprocess.TimeoutExpired(cmd="web-child", timeout=timeout)

    process = _NeverExitProcess(5432)

    def sleep(_seconds):
        nonlocal fired_stop
        if not fired_stop:
            fired_stop = True
            signals.handlers[signals.SIGTERM](signals.SIGTERM, None)

    monkeypatch.setattr(
        supervisor,
        "os",
        SimpleNamespace(killpg=lambda _pid, signum: kill_signals.append(signum)),
    )
    monkeypatch.setattr(supervisor, "signal", SimpleNamespace(SIGTERM=15, SIGKILL=9))
    result = supervisor._run_supervisor(
        _options(tmp_path),
        popen_factory=lambda *_args, **_kwargs: process,
        signal_api=signals,
        sleep=sleep,
        terminate_child=supervisor._terminate_child,
        reap_children=lambda _pid: 0,
        authority_check=lambda _root: pytest.fail("read-only startup checked authority"),
        executable="aihf-web",
    )

    assert result == 1
    assert kill_signals == [supervisor.signal.SIGTERM, supervisor.signal.SIGKILL]
    assert waits == [supervisor._STOP_TIMEOUT_SECONDS, supervisor._STOP_TIMEOUT_SECONDS]
    error = capsys.readouterr().err
    assert "web supervisor shutdown failed" in error
    assert "PID 5432" in error
    assert "after SIGKILL" in error


@pytest.mark.parametrize(
    "values",
    [
        {"port": True},
        {"port": 0},
        {"root": "relative"},
        {"root": Path("relative")},
        {"enable_writes_after_trust": 1},
        {"enable_network_after_trust": 1},
    ],
)
def test_supervisor_options_reject_invalid_capability_inputs(tmp_path, values):
    options = {**_options(tmp_path).__dict__, **values}

    with pytest.raises((TypeError, ValueError)):
        supervisor.SupervisorOptions(**options)


def test_supervisor_parser_rejects_invalid_port(tmp_path):
    with pytest.raises(SystemExit) as failure:
        supervisor._parser().parse_args(["--root", str(tmp_path), "--port", "65536"])

    assert failure.value.code == 2
