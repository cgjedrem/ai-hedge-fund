import os
from pathlib import Path

import pytest

from hedge_fund.web import supervisor


class _FakeSignals:
    SIGHUP = 1
    SIGINT = 2
    SIGTERM = 15

    def __init__(self):
        self.handlers = {
            self.SIGHUP: object(),
            self.SIGINT: object(),
            self.SIGTERM: object(),
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
        authority_check=lambda _root: pytest.fail("read-only startup checked authority"),
        executable="aihf-web",
    )

    assert result == 23
    assert len(commands) == 1
    assert "--allow-writes" not in commands[0]
    assert signals.handlers == previous_handlers


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
