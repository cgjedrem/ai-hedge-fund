"""run — the unattended loop at both cadences, driven by a fake clock and
canned prints; and tick on a bar, the same session by hand."""

import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from importlib import import_module

import pytest

from hedge_fund.backtesting.test_fund import FakeDataClient, SERIES
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.paper import deploy, Ledger, NothingDue, PID_FILE, redo, tick
from hedge_fund.paper.test_tick import build_fund
from hedge_fund.pipeline.session import FundHalted
from hedge_fund.pipeline.test_clock import Tape
from hedge_fund.pipeline.test_stages import FakeAnalyst

DAY, NEXT = "2024-06-04", "2024-06-05"
BARS = ["13:00:00", "13:05:00", "13:10:00"]  # a three-bar window, 13:00–13:10, every 5m
runner_module = import_module("hedge_fund.paper.runner")


@pytest.fixture(autouse=True)
def registered_fakes(monkeypatch):
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)


def _spec(**overrides):
    data = {
        "schema_version": 2,
        "name": "bars",
        "strategies": [{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}],
        "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
        "capital": 100_000,
        "costs": {"spread_bps": 0, "commission_per_share": 0},
        "rebalance": "minute",
        "interval": 5,
        "window": {"start": "13:00", "end": "13:10"},
        **overrides,
    }
    if data.get("broker") == "saxo":
        data.setdefault("saxo_account_key", "sim-account-1")
    return FundSpec(**data)


def _at(day, hhmmss):
    return datetime.fromisoformat(f"{day}T{hhmmss}").replace(tzinfo=NEW_YORK)


def _tape(now):
    path = {"AAPL": {}, "SPY": {}}
    for i, (day, bar) in enumerate((d, b) for d in (DAY, NEXT) for b in BARS):
        path["AAPL"][f"{day}T{bar}"] = 100.0 + i
        path["SPY"][f"{day}T{bar}"] = 500.0
    return Tape(path, now=now)


def test_legacy_runner_rejects_missing_handover_with_admission_artifacts(
    tmp_path,
    monkeypatch,
):
    from hedge_fund.runtime.handover import enroll_fresh, HANDOVER_PATH
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "former-enrolled-root"
    root.mkdir()
    directory = root / "paper" / "alpha"
    with RootContext.open(root) as context:
        enroll_fresh(context)
        directory.mkdir(parents=True)
        (root / HANDOVER_PATH).unlink()
        monkeypatch.setattr(
            runner_module,
            "load_deployed",
            lambda *_args, **_kwargs: pytest.fail(
                "legacy runner reached deployed-fund loading",
            ),
        )

        with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
            runner_module.run(directory, object())


class Loop:
    """Drives `run`: sleeping moves the fake clock; stops after N records,
    or when the clock passes *until* (a runaway loop in a test ends there)."""

    def __init__(self, directory, tape, *, records=1, until=None):
        self.directory, self.tape = directory, tape
        self.stop = threading.Event()
        self.records, self.events = [], []
        self._wanted = records
        self._until = until or _at(NEXT, "23:00:00")

    def __call__(self):
        deployed = runner_module.load_deployed(self.directory)
        fund = build_fund(deployed.spec)
        loop = runner_module._run_bars if deployed.spec.is_intraday else runner_module._run_days
        loop(
            self.directory,
            deployed,
            self.tape,
            fund,
            broker=None,
            stop=self.stop,
            build_fund=build_fund,
            now=lambda: self.tape.now,
            sleep=self._sleep,
            on_record=self._record,
            on_event=lambda k, f: self.events.append((k, f)),
        )

    def _sleep(self, seconds):
        self.tape.now += timedelta(seconds=seconds)
        if self.tape.now > self._until:
            self.stop.set()

    def _record(self, record):
        self.records.append(record)
        if len(self.records) >= self._wanted:
            self.stop.set()


def test_a_day_of_bars_decides_fills_and_checkpoints(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    loop = Loop(directory, tape, records=3)
    loop()
    ledger = Ledger(directory)
    assert [r.session for r in loop.records] == [f"{DAY}T{b}" for b in BARS]
    assert ledger.sessions() == [r.session for r in loop.records]
    first, second, third = loop.records
    assert first.decision is not None and first.executed is None
    assert second.executed is not None and second.executed.fills[0].price == 101.0
    assert second.executed.execution_policy == "next_bar" and second.positions == {"AAPL": 990.099}
    assert third.marks == {"AAPL": 102.0} and third.snapshot_times["AAPL"] == "2024-06-04T17:10:00Z"
    assert ledger.checkpoint_path(DAY).exists()
    assert [k for k, _ in loop.events] == [] and [e["kind"] for e in ledger.events()] == ["tick", "tick", "tick", "checkpoint"]
    assert ledger.replay(100_000) == ledger.replay(100_000, full=True)


def test_legacy_runner_denies_before_broker_construction(tmp_path, monkeypatch):
    directory = tmp_path / "saxo-not-read"
    monkeypatch.setattr(
        runner_module,
        "build_broker",
        lambda *_args, **_kwargs: pytest.fail("disabled runner built a broker"),
    )
    monkeypatch.setattr(
        runner_module,
        "load_deployed",
        lambda *_args, **_kwargs: pytest.fail("disabled runner loaded a deployment"),
    )

    with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
        runner_module.run(directory, _tape(_at(DAY, "12:00:00")))


def test_saxo_runner_skips_a_late_closing_bar_after_market_close(tmp_path, monkeypatch):
    spec = _spec(broker="saxo", interval=30, window={"start": "09:30", "end": "15:59"})
    from hedge_fund.brokers.test_saxo_doubles import write_fake_sim_deployment

    directory = write_fake_sim_deployment("saxo-late-close", spec, ["AAPL"], root=tmp_path)
    deployed = runner_module.load_deployed(directory)
    tape = _tape(_at(DAY, "16:10:00"))
    stop = threading.Event()
    waits = []

    monkeypatch.setattr(runner_module, "next_session", lambda *args, **kwargs: f"{DAY}T15:59:00")
    monkeypatch.setattr(runner_module, "_run", lambda *args, **kwargs: pytest.fail("Saxo must not trade after the close"))

    def wait_for(target, now, sleep):
        waits.append(target)
        stop.set()

    monkeypatch.setattr(runner_module, "_wait_for", wait_for)
    runner_module._run_bars(
        directory,
        deployed,
        tape,
        build_fund,
        broker=object(),
        stop=stop,
        build_fund=None,
        on_record=None,
        on_event=None,
        now=lambda: tape.now,
        sleep=lambda _: None,
    )

    assert waits == [runner_module.next_bar(tape.now, spec.interval_seconds, spec.window)]


def test_saxo_runner_passes_the_bar_date_cutoff_to_order_submission(tmp_path, monkeypatch):
    spec = _spec(broker="saxo", interval=1, window={"start": "09:30", "end": "15:59"})
    from hedge_fund.brokers.test_saxo_doubles import write_fake_sim_deployment

    directory = write_fake_sim_deployment("saxo-cutoff", spec, ["AAPL"], root=tmp_path)
    deployed = runner_module.load_deployed(directory)
    tape = _tape(_at(DAY, "15:59:00"))
    stop = threading.Event()
    windows = []

    class GuardedBroker:
        active = False

        @contextmanager
        def order_submission_window(self, cutoff, now):
            windows.append((cutoff, now()))
            self.active = True
            try:
                yield
            finally:
                self.active = False

    broker = GuardedBroker()

    def run_session(*args, **kwargs):
        assert broker.active
        stop.set()
        return object()

    monkeypatch.setattr(runner_module, "_run", run_session)
    runner_module._run_bars(
        directory,
        deployed,
        tape,
        build_fund,
        broker=broker,
        stop=stop,
        build_fund=None,
        on_record=None,
        on_event=None,
        now=lambda: tape.now,
        sleep=lambda _: None,
    )

    assert windows == [(_at(DAY, "16:00:00"), tape.now)]
    assert not broker.active


def test_a_late_start_skips_to_the_current_bar_and_logs_the_gap(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    Loop(directory, tape, records=3)()
    # Away for a day; back thirty seconds into tomorrow's 13:05 bar.
    tape.now = _at(NEXT, "13:05:30")
    loop = Loop(directory, tape, records=1)
    loop()
    record = loop.records[0]
    assert record.session == f"{NEXT}T13:05:00"
    assert loop.events == [("gap", {"from": f"{DAY}T13:10:00", "to": f"{NEXT}T13:05:00", "bars_skipped": 1})]
    # The pending decision from yesterday's close was refreshed at 13:00 today, then executed.
    assert record.executed.original_assessment.as_of == f"{DAY}T13:10:00"
    assert record.executed.refreshed_assessment.as_of == f"{NEXT}T13:00:00"
    assert record.executed.fills == [] and record.positions == {"AAPL": 990.099}  # same view, same book
    assert Ledger(directory).replay(100_000).last_session == record.session


def test_an_evening_start_does_not_mark_the_close_at_tonights_print(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "18:00:00"))
    loop = Loop(directory, tape, records=1)
    loop()
    assert loop.records[0].session == f"{NEXT}T13:00:00"
    assert loop.events == []  # nothing recorded before it: no gap to speak of


def test_a_day_the_benchmark_has_not_printed_is_skipped_once_and_quietly(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    Loop(directory, tape, records=3)()
    del tape.path["SPY"][f"{NEXT}T13:00:00"], tape.path["SPY"][f"{NEXT}T13:05:00"]
    tape.now = _at(NEXT, "13:00:00")
    loop = Loop(directory, tape, records=1)
    loop()
    assert loop.records[0].session == f"{NEXT}T13:10:00"  # SPY printed again by then
    kinds = [k for k, _ in loop.events]
    assert kinds == ["gap", "gap"]
    assert "market closed" in loop.events[0][1]["reason"] and loop.events[1][1]["bars_skipped"] == 2


def test_a_failed_bar_halts_the_fund_like_a_failed_tick(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    Loop(directory, tape, records=1)()
    del tape.path["AAPL"]  # the next bar cannot be valued: no AAPL prints at all
    tape.path["AAPL"] = {}
    loop = Loop(directory, tape, records=1)
    with pytest.raises(ValueError):
        loop()
    ledger = Ledger(directory)
    assert ledger.halted().startswith(f"tick {DAY}T13:05:00 failed")
    with pytest.raises(FundHalted):
        Loop(directory, tape, records=1)()


def test_redo_runs_a_bar_again_at_the_prices_it_saw(tmp_path):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    loop = Loop(directory, tape, records=3)
    loop()
    tape.snapshot_calls.clear()
    again = redo(directory, tape, build_fund=build_fund)
    assert tape.snapshot_calls == []  # no new prints were taken
    assert again.session == loop.records[2].session and again.marks == loop.records[2].marks
    assert again.hash == loop.records[2].hash  # same prints, same analysts: the same record
    ledger = Ledger(directory)
    assert ledger.replay(100_000).last_session == again.session
    assert [e["kind"] for e in ledger.events()][-3:] == ["redo", "tick", "checkpoint"]
    assert ledger.checkpoint_path(DAY).exists()  # the closing bar, run again, closes the day again
    assert ledger.replay(100_000) == ledger.replay(100_000, full=True)

    def bearish(spec):
        return Fund(spec, models={"solo": [FakeAnalyst("a", {"AAPL": -1})]})

    flipped = redo(directory, tape, build_fund=bearish)
    assert flipped.decision.final_weights == {"AAPL": -1.0} and flipped.hash != again.hash
    assert len(list((directory / "ledger" / "superseded").glob("*.json"))) == 2


def test_tick_runs_the_current_bar_by_hand_at_the_print_taken_now(tmp_path):
    """Enter on a minute fund is the same verb as on a daily one: the next
    session, which is the latest bar boundary passed. Pressed late, the bar
    is recorded at the print taken now, and the record says when that was.
    A holiday is nothing due; the closing bar checkpoints the day."""
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    tape = _tape(_at(DAY, "12:00:00"))
    with pytest.raises(NothingDue, match="no bar yet; next 13:00:00 ET"):
        tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)

    tape.now = _at(DAY, "13:00:00")
    first = tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)
    assert first.session == f"{DAY}T13:00:00" and first.decision is not None
    with pytest.raises(NothingDue, match=f"no bar after {DAY}T13:00:00; next 13:05:00 ET"):
        tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)

    tape.now = _at(DAY, "13:07:30")  # two and a half minutes into the 13:05 bar
    second = tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)
    assert second.session == f"{DAY}T13:05:00" and second.executed.fills[0].price == 101.0
    assert second.snapshot_times["AAPL"] == "2024-06-04T17:05:00Z"  # the latest print on the tape, as taken

    tape.now = _at(DAY, "13:10:00")
    third = tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)
    ledger = Ledger(directory)
    assert third.session == f"{DAY}T13:10:00" and ledger.checkpoint_path(DAY).exists()
    assert [e["kind"] for e in ledger.events()] == ["tick", "tick", "tick", "checkpoint"]

    del tape.path["SPY"][f"{NEXT}T13:00:00"]  # the market has not opened tomorrow by the first bar
    tape.now = _at(NEXT, "13:00:00")
    with pytest.raises(NothingDue, match="SPY has not printed today"):
        tick(directory, tape, build_fund=build_fund, now=lambda: tape.now)
    assert ledger.sessions()[-1] == third.session


class DailyTape(FakeDataClient):
    """Daily closes, and a clock the test moves."""

    def __init__(self, series, *, now):
        super().__init__(series)
        self.now = now


def test_a_daily_fund_is_run_unattended_too_catching_up_after_each_midnight(tmp_path):
    """The same loop at the daily cadence: every session that has become
    due since it last looked, oldest first, then sleep to the turn of the
    day. A fresh fund starts at the latest completed close, as a tick would."""
    spec = FundSpec(**{**_spec().model_dump(exclude={"interval", "window"}), "rebalance": "daily"})
    directory = deploy("daily", spec, ["AAPL"], root=tmp_path)
    tape = DailyTape(SERIES, now=_at("2024-06-04", "12:00:00"))
    loop = Loop(directory, tape, records=1)
    loop()
    assert [r.session for r in loop.records] == ["2024-06-03"]  # Tuesday noon: Monday is the latest close

    tape.now = _at("2024-06-06", "23:30:00")  # away two days; two closes have become due
    loop = Loop(directory, tape, records=2)
    loop()
    assert [r.session for r in loop.records] == ["2024-06-04", "2024-06-05"]
    assert loop.records[0].executed is not None and loop.records[0].positions == {"AAPL": 500}
    assert tape.now == _at("2024-06-06", "23:30:00")  # caught up without sleeping between them

    loop = Loop(directory, tape, records=1, until=_at("2024-06-08", "00:00:00"))
    loop()
    assert loop.records[0].session == "2024-06-06"  # nothing was due at 23:30; it slept to the turn of the day
    assert tape.now == _at("2024-06-07", "00:05:00")
    assert loop.events == [] and Ledger(directory).sessions() == ["2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06"]


def test_legacy_runner_entrypoints_deny_before_pid_or_provider_effects(
    tmp_path,
    monkeypatch,
):
    directory = deploy("bars", _spec(), ["AAPL"], root=tmp_path)
    effects = []

    def forbidden(*_args, **_kwargs):
        effects.append(True)
        pytest.fail("disabled runner reached a provider, ledger, or process effect")

    for name in (
        "build_broker",
        "is_running",
        "load_deployed",
        "_read_pid",
    ):
        monkeypatch.setattr(runner_module, name, forbidden)
    monkeypatch.setattr(runner_module.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner_module.os, "kill", forbidden)
    monkeypatch.setattr(runner_module.signal, "signal", forbidden)

    class NoIODataClient:
        def get_prices(self, *_args, **_kwargs):
            forbidden()

    data = NoIODataClient()
    with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
        runner_module.run(directory, data)
    with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
        runner_module.serve(directory, data)
    with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
        runner_module.stop_runner(directory)

    assert effects == []
    assert not (directory / PID_FILE).exists()
    assert not (directory / "runner.log").exists()


def test_spawn_runner_denies_before_log_or_process_launch(tmp_path, monkeypatch):
    root = tmp_path / "root"
    directory = root / "paper" / "demo-alpha"
    directory.mkdir(parents=True)

    def forbidden_launch(*_args, **_kwargs):
        pytest.fail("disabled runner reached process launch")

    monkeypatch.setattr(runner_module.subprocess, "Popen", forbidden_launch)

    with pytest.raises(RuntimeError, match="Legacy paper runner is disabled"):
        runner_module.spawn_runner(directory, root=root)

    assert not (directory / "runner.log").exists()


def test_spawn_runner_rejects_root_mismatch_before_launch(tmp_path, monkeypatch):
    root = tmp_path / "root"
    directory = root / "paper" / "demo-alpha"
    directory.mkdir(parents=True)

    def forbidden_launch(*_args, **_kwargs):
        raise AssertionError("mismatched runner root reached process launch")

    monkeypatch.setattr(runner_module.subprocess, "Popen", forbidden_launch)

    with pytest.raises(ValueError, match="outside the configured root"):
        runner_module.spawn_runner(directory, root=tmp_path / "other")

    assert not (directory / "runner.log").exists()


def test_enrolled_root_blocks_legacy_runner_start_and_pid_signaling(tmp_path, monkeypatch):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import enroll_fresh, record_ledger_head
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", _spec(name="alpha"), ["AAPL"], root=root / "paper")
            record_ledger_head(context, "alpha", admission=admission)
        finally:
            owner.close()

    pid_file = directory / PID_FILE
    pid_file.write_text("999999999", encoding="utf-8")
    pid_before = pid_file.read_bytes()

    def forbidden(*_args, **_kwargs):
        pytest.fail("legacy runner attempted process control")

    monkeypatch.setattr(runner_module.subprocess, "Popen", forbidden)
    monkeypatch.setattr(runner_module.os, "kill", forbidden)

    with pytest.raises(RuntimeError, match="Legacy paper runner"):
        runner_module.spawn_runner(directory, root=root)
    with pytest.raises(RuntimeError, match="Legacy paper runner"):
        runner_module.serve(directory, _tape(_at(DAY, "13:00:00")))
    with pytest.raises(RuntimeError, match="Legacy paper runner"):
        runner_module.stop_runner(directory)
    with pytest.raises(RuntimeError, match="Legacy paper runner"):
        runner_module.run(directory, _tape(_at(DAY, "13:00:00")))

    assert pid_file.read_bytes() == pid_before
    assert not (directory / "runner.log").exists()


def test_is_running_never_sends_console_control_events(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    from hedge_fund.paper import runner as runner_module
    from hedge_fund.test_support.network_guard import (
        child_test_environment,
        guarded_test_python_command,
    )

    def forbidden(*_args):
        raise AssertionError("os.kill(pid, 0) is CTRL_C_EVENT on Windows and interrupts the whole console")

    if sys.platform == "win32":
        monkeypatch.setattr(runner_module.os, "kill", forbidden)
    pid_file = tmp_path / PID_FILE
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    assert runner_module.is_running(tmp_path)
    child = subprocess.Popen(guarded_test_python_command("-c", "pass"), env=child_test_environment())
    assert child.wait(timeout=30) == 0
    pid_file.write_text(str(child.pid), encoding="utf-8")
    assert not runner_module.is_running(tmp_path)
    for invalid in ("0", "-1", "999999999", "not-a-pid"):
        pid_file.write_text(invalid, encoding="utf-8")
        assert not runner_module.is_running(tmp_path)


def test_a_one_second_fund_runs_each_second_bar_once_in_order(tmp_path):
    seconds = ["13:00:00", "13:00:01", "13:00:02"]
    path = {"AAPL": {f"{DAY}T{s}": 100.0 + i for i, s in enumerate(seconds)}, "SPY": {f"{DAY}T{s}": 500.0 for s in seconds}}
    directory = deploy("bars", _spec(interval=1 / 60, window={"start": "13:00", "end": "13:01"}), ["AAPL"], root=tmp_path)
    tape = Tape(path, now=_at(DAY, "12:59:59"))
    loop = Loop(directory, tape, records=3)
    loop()

    assert [record.session for record in loop.records] == [f"{DAY}T{s}" for s in seconds]
    assert Ledger(directory).sessions() == [record.session for record in loop.records]
    assert loop.events == []
    with pytest.raises(NothingDue):
        tick(directory, tape, build_fund=build_fund, now=lambda: _at(DAY, "13:00:02"))
