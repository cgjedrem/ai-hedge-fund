"""The CLI: configuration preflight, the backtest command, and the paper flow."""

import hashlib
import importlib
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from hedge_fund import paths, run
from hedge_fund.data import sessions
from hedge_fund.fund import custom_strategy, FundSpec


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """No credentials, no HTTP, user dirs under tmp, fakes for the engine."""
    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient
    from hedge_fund.fund import Fund

    tick_module = importlib.import_module("hedge_fund.paper.tick")

    class OfflineClient(FakeDataClient):
        def __init__(self):
            super().__init__({ticker: {"2025-01-06": 100, "2025-01-07": 100, "2025-01-08": 110, "2025-01-13": 110}
                              for ticker in ("AAPL", "MSFT", "SPY")})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def build_fund(spec, blind=False):
        return Fund(spec, models={s.name: [FakeAnalyst(m.name, {"AAPL": .8, "MSFT": -.6}) for m in s.models]
                                  for s in spec.strategies})

    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(run, "Fund", build_fund)
    monkeypatch.setattr(tick_module, "Fund", build_fund)
    monkeypatch.setattr(run, "make_data_client", OfflineClient)
    monkeypatch.setattr(run, "CachedDataClient", lambda client, **kwargs: client)
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path / "paper")
    monkeypatch.setattr(paths, "RESEARCH_DIR", tmp_path / "research")

    def set_today(day):
        y, m, d = map(int, day.split("-"))

        class Clock:
            @staticmethod
            def now(tz):
                return datetime(y, m, d, 12, tzinfo=tz)
        monkeypatch.setattr(sessions, "datetime", Clock)
    set_today("2025-01-14")
    return set_today


def _mandate(tmp_path, mode="long_short", name="mixed"):
    spec = FundSpec(schema_version=2, name=name, strategies=[custom_strategy(["buffett", "druckenmiller"])],
                    risk={"max_position_pct": .25, "max_gross_exposure": 1})
    spec.strategies[0].blend.mode = mode
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump()))
    return path


def _main(monkeypatch, *argv):
    root = Path(run.PAPER_DIR).parent if run.PAPER_DIR is not None else Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    monkeypatch.setattr(sys, "argv", ["aihf", "--root", str(root), *argv])
    run.main()


@pytest.mark.parametrize("command", ["backtest", "create"])
@pytest.mark.parametrize("unversioned", [False, True])
def test_cli_rejects_invalid_configuration_before_clients(tmp_path, monkeypatch, capsys, command, unversioned):
    spec = FundSpec(schema_version=2, name="mixed", strategies=[custom_strategy(["buffett", "druckenmiller"])],
                    risk={"max_position_pct": .25, "max_gross_exposure": 1})
    data = spec.model_dump()
    if unversioned:
        data.pop("schema_version")
    else:
        data["strategies"][0]["blend"]["mode"] = "invalid"
    path = tmp_path / "fund.yaml"
    path.write_text(yaml.safe_dump(data))
    original = path.read_bytes()
    forbidden = Mock(side_effect=AssertionError("external activity"))
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(run, "Fund", forbidden)
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "deploy", forbidden)
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path / "paper")
    argv = (["backtest", str(path), "--universe", "AAPL"] if command == "backtest"
            else ["paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL"])
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)
    assert exc.value.code == 2
    assert forbidden.call_count == 0
    output = capsys.readouterr()
    assert output.out == ""
    assert ("older format" if unversioned else "blend.mode") in output.err
    assert path.read_bytes() == original
    assert not (tmp_path / "paper").exists()


def test_no_arguments_launches_the_app(monkeypatch):
    launched = Mock()
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: None)
    monkeypatch.setitem(sys.modules, "hedge_fund.tui.app", Mock(HedgeFundApp=lambda: launched))
    _main(monkeypatch)
    launched.run.assert_called_once()


@pytest.mark.parametrize("mode", ["long_only", "long_short", "dollar_neutral"])
def test_backtest_prints_json_and_files_a_research_copy(tmp_path, monkeypatch, capsys, offline, mode):
    path = _mandate(tmp_path, mode)
    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL,MSFT", "--start", "2025-01-06", "--end", "2025-01-13")
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["dates"] == ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-13"]
    # Monday decides, Tuesday executes; the next Monday decides again.
    assert [r["executed"] is not None for r in result["records"]] == [False, True, False, False]
    assert result["records"][-1]["decision"] is not None
    cycle = result["records"][1]["executed"]
    assert cycle["positions"]["AAPL"] > 0
    assert (cycle["positions"].get("MSFT", 0) < 0) == (mode != "long_only")
    if mode == "dollar_neutral":
        assert sum(cycle["final_weights"].values()) == pytest.approx(0)
    assert "1 rebalances" in output.err and "sessions" in output.err
    saved = list((tmp_path / "research").glob("mixed-2025-01-06-2025-01-13-*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text()) == result
    assert not (tmp_path / "paper").exists()  # research never touches the paper funds


def test_backtest_defaults_end_to_the_latest_completed_session(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL", "--start", "2025-01-06")
    result = json.loads(capsys.readouterr().out)
    assert result["end"] == "2025-01-13"


def test_backtest_without_rebalance_key_defaults_to_weekly(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.pipeline import session as pipeline_session

    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate.pop("rebalance")
    path.write_text(yaml.safe_dump(mandate))
    # Freeze revision stamp → compare CLI JSON across commits.
    monkeypatch.setattr(pipeline_session, "code_version", lambda: "2.6.1+cd662f4")

    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL,MSFT", "--start", "2025-01-06", "--end", "2025-01-13")
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert result["rebalance"] == "weekly"
    assert "1 rebalances" in output.err
    assert hashlib.sha256(output.out.encode()).hexdigest() == "8dbc24919e7ae535220364a45f9f9c8b04863f6afa4ad07c1db1872275f38623"


def test_backtest_rebalance_override_changes_monthly_cycle_count(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.backtesting.test_fund import FakeDataClient

    dates = ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-13", "2025-02-03", "2025-02-04", "2025-02-10", "2025-03-03"]
    series = {ticker: {day: 100.0 + index for index, day in enumerate(dates)} for ticker in ("AAPL", "MSFT", "SPY")}

    class MultiMonthClient(FakeDataClient):
        def __init__(self):
            super().__init__(series)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(run, "make_data_client", MultiMonthClient)
    path = _mandate(tmp_path)
    original = path.read_bytes()
    args = ("backtest", str(path), "--universe", "AAPL,MSFT", "--start", dates[0], "--end", dates[-1])
    offline("2025-03-04")

    _main(monkeypatch, *args)
    weekly = json.loads(capsys.readouterr().out)
    _main(monkeypatch, *args, "--rebalance", "monthly")
    monthly = json.loads(capsys.readouterr().out)

    assert weekly["rebalance"] == "weekly"
    assert monthly["rebalance"] == "monthly"
    assert monthly["metrics"]["n_cycles"] < weekly["metrics"]["n_cycles"]
    assert path.read_bytes() == original


def test_paper_create_rebalance_override_is_frozen_and_reported(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    original = path.read_bytes()

    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "daily")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "alpha" / "fund.yaml").read_text())

    assert output.out == ""
    assert "daily" in output.err
    assert deployed["spec"]["rebalance"] == "daily"
    assert path.read_bytes() == original


@pytest.mark.parametrize("command", ["backtest", "create"])
def test_invalid_rebalance_override_is_usage_error_before_engine_work(tmp_path, monkeypatch, capsys, offline, command):
    forbidden = Mock(side_effect=AssertionError("engine work ran before argument validation"))
    monkeypatch.setattr(run, "load_spec", forbidden)
    monkeypatch.setattr(run, "Fund", forbidden)
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "deploy", forbidden)
    argv = (
        ["backtest", "unused.yaml", "--universe", "AAPL", "--rebalance", "hourly"]
        if command == "backtest"
        else ["paper", "create", "alpha", "--mandate", "unused.yaml", "--universe", "AAPL", "--rebalance", "hourly"]
    )

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)

    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert "hourly" in output.err
    assert all(value in output.err for value in ("minute", "daily", "weekly", "monthly"))
    assert forbidden.call_count == 0


def test_paper_create_overrides_minute_to_daily_without_minute_fields(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate.update(rebalance="minute", interval=0.5, window={"start": "09:30", "end": "12:00"})
    path.write_text(yaml.safe_dump(mandate))
    original = path.read_bytes()

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "daily")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "fast" / "fund.yaml").read_text())
    deployed_spec = deployed["spec"]

    assert output.out == ""
    assert "daily" in output.err
    assert deployed_spec["rebalance"] == "daily"
    assert "interval" not in deployed_spec and "window" not in deployed_spec
    assert path.read_bytes() == original


def test_paper_create_overrides_day_grid_to_minute_with_standard_defaults(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate["rebalance"] = "daily"
    mandate.pop("interval", None)
    mandate.pop("window", None)
    path.write_text(yaml.safe_dump(mandate))
    original = path.read_bytes()

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "minute")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "fast" / "fund.yaml").read_text())
    deployed_spec = deployed["spec"]

    assert output.out == ""
    assert "every 1m" in output.err and "09:30–16:00 ET" in output.err
    assert deployed_spec["rebalance"] == "minute"
    assert deployed_spec["interval"] == 1.0
    assert deployed_spec["window"] == {"start": "09:30", "end": "16:00"}
    assert path.read_bytes() == original


@pytest.mark.parametrize("action", ["tick", "run"])
def test_deployed_fund_commands_do_not_accept_rebalance_override(capsys, action):
    parser = run._parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "--root",
                os.environ["HEDGE_FUND_TEST_ROOT"],
                "paper",
                action,
                "alpha",
                "--rebalance",
                "daily",
            ]
        )

    assert exc.value.code == 2
    assert "unrecognized arguments: --rebalance daily" in capsys.readouterr().err


def test_paper_flow_create_tick_status_halt_resume(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)

    set_today("2025-01-07")  # deployed Tuesday morning: Monday 01-06 is the latest close
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL, MSFT")
    err = capsys.readouterr().err
    assert "alpha" in err and "deployed" in err
    with pytest.raises(SystemExit):
        _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    assert "already exists" in capsys.readouterr().err

    _main(monkeypatch, "paper", "list")
    listed = capsys.readouterr().out
    assert "alpha" in listed and "not started" in listed

    _main(monkeypatch, "paper", "tick", "alpha")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-06" and record["decision"] is not None and record["executed"] is None
    assert "decided on" in output.err and "executes next close" in output.err

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")  # nothing new has closed
    assert exc.value.code == 1
    assert "no completed SPY session after 2025-01-06" in capsys.readouterr().err

    set_today("2025-01-08")
    _main(monkeypatch, "paper", "tick", "alpha")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-07" and record["executed"]["positions"]["AAPL"] > 0
    assert "executed" in output.err

    _main(monkeypatch, "paper", "status", "alpha")
    status = capsys.readouterr().out
    assert "alpha" in status and "2 sessions" in status and "last 2025-01-07" in status
    assert "AAPL:" in status and "book:" in status and "HALTED" not in status

    _main(monkeypatch, "paper", "halt", "alpha", "--reason", "operator review")
    _main(monkeypatch, "paper", "status", "alpha")
    assert "HALTED: operator review" in capsys.readouterr().out
    set_today("2025-01-09")
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")
    assert exc.value.code == 1 and "halted" in capsys.readouterr().err

    _main(monkeypatch, "paper", "resume", "alpha")
    _main(monkeypatch, "paper", "tick", "alpha")
    assert json.loads(capsys.readouterr().out)["session"] == "2025-01-08"
    _main(monkeypatch, "paper", "list")
    assert "3 sessions" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "status", "nobody")
    assert exc.value.code == 2 and "no paper fund named 'nobody'" in capsys.readouterr().err


def test_cli_resolves_relative_mandate_under_root(tmp_path, monkeypatch, capsys, offline):
    root_mandate = tmp_path / "mandates"
    root_mandate.mkdir()
    spec = FundSpec(
        schema_version=2,
        name="root-mandate",
        strategies=[custom_strategy(["buffett", "druckenmiller"])],
        risk={"max_position_pct": 0.25, "max_gross_exposure": 1},
    )
    (root_mandate / "root-mandate.yaml").write_text(yaml.safe_dump(spec.model_dump()))

    decoy = tmp_path / "cwd"
    (decoy / "mandates").mkdir(parents=True)
    (decoy / "mandates" / "root-mandate.yaml").write_text("not: a valid mandate")
    monkeypatch.chdir(decoy)

    _main(
        monkeypatch,
        "backtest",
        "mandates/root-mandate.yaml",
        "--universe",
        "AAPL",
        "--start",
        "2025-01-06",
        "--end",
        "2025-01-08",
    )

    output = capsys.readouterr()
    assert "root-mandate" in output.err
    assert json.loads(output.out)["fund"] == "root-mandate"


def test_paper_minute_fund_ticks_and_runs_like_a_daily_one(tmp_path, monkeypatch, capsys, offline):
    """The CLI verbs are the same at every cadence: `tick` runs the session
    that is due (for a minute fund, the current bar at the print taken now)
    and `run` leaves a runner on the fund."""
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.paper import PID_FILE
    from hedge_fund.pipeline.test_clock import Tape
    spec = FundSpec(schema_version=2, name="bars", strategies=[custom_strategy(["buffett"])],
                    risk={"max_position_pct": .25, "max_gross_exposure": 1},
                    rebalance="minute", interval=0.5, window={"start": "09:30", "end": "12:00"})
    path = tmp_path / "bars.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump()))

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL")
    err = " ".join(capsys.readouterr().err.split())  # the console wraps; read it as one line
    assert "every 30s" in err and "09:30–12:00 ET" in err
    assert "aihf paper tick fast` to run one session" in err and "aihf paper run fast` to leave it running" in err

    class CliTape(Tape):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    tape = CliTape({"AAPL": {"2025-01-07T09:30:00": 100.0, "2025-01-07T09:30:30": 101.0},
                    "SPY": {"2025-01-07T09:30:00": 500.0}},
                   now=datetime(2025, 1, 7, 9, 30, 40, tzinfo=NEW_YORK))  # 10s into the 09:30:30 bar
    monkeypatch.setattr(run, "make_data_client", lambda: tape)
    tick_module = importlib.import_module("hedge_fund.paper.tick")

    class Clock(datetime):  # the tick's wall clock is the tape's; everything else is datetime's
        @classmethod
        def now(cls, tz=None):
            return tape.now.astimezone(tz)

    monkeypatch.setattr(tick_module, "datetime", Clock)

    _main(monkeypatch, "paper", "tick", "fast")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-07T09:30:30" and record["decision"] is not None
    assert "decided on" in output.err and "executes next bar" in output.err

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "fast")  # no new bar yet
    assert exc.value.code == 1
    assert "no bar after 2025-01-07T09:30:30; next 09:31:00 ET" in capsys.readouterr().err

    _main(monkeypatch, "paper", "stop", "fast")
    assert "not running" in capsys.readouterr().err
    _main(monkeypatch, "paper", "list")
    listed = capsys.readouterr().out
    assert "every 30s" in listed and "running" not in listed

    # `run` is the serve loop; stand in for it and check the wiring around it.
    seen = {}

    def fake_serve(directory, data, *, on_record, on_event):
        seen["pid"] = directory / PID_FILE
        on_event("gap", {"from": None, "to": "2025-01-07T09:30:00", "bars_skipped": 3})
    monkeypatch.setattr(run, "serve", fake_serve)
    _main(monkeypatch, "paper", "run", "fast")
    err = capsys.readouterr().err
    assert "fast" in err and "every 30s" in err and "gap start → 2025-01-07T09:30:00  3 bars skipped" in err
    assert "stopped" in err

    (seen["pid"]).write_text(str(os.getpid()))
    _main(monkeypatch, "paper", "list")
    assert "running" in capsys.readouterr().out
    monkeypatch.setattr(run, "stop_runner", lambda directory: True)
    _main(monkeypatch, "paper", "stop", "fast")
    assert "asked to stop" in capsys.readouterr().err


def _offline_tick(directory):
    with run.make_data_client() as raw:
        run.tick(directory, run.CachedDataClient(raw))


def _disable_status_animation(monkeypatch):
    monkeypatch.setattr(run.Console, "status", lambda *args, **kwargs: nullcontext())


def test_paper_create_approval_and_approve_commands_show_status(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")

    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    created = capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    deployed = yaml.safe_load((directory / "fund.yaml").read_text())
    assert deployed["spec"]["approval_required"] is True
    assert "approval" in created.err.lower()

    _offline_tick(directory)
    _main(monkeypatch, "paper", "status", "alpha")
    status = capsys.readouterr().out
    assert "awaiting approval" in status and "AAPL:" in status
    _main(monkeypatch, "paper", "list")
    assert "awaiting approval" in capsys.readouterr().out

    _main(monkeypatch, "paper", "approve", "alpha")
    approved = capsys.readouterr()
    mailbox = json.loads((directory / "pending-approval.json").read_text())
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    assert mailbox["verdict"] == "approve" and mailbox["by"] == "cli"
    assert [event["kind"] for event in events] == ["tick", "approve"]
    assert "approved" in approved.err.lower()


def test_paper_approve_now_executes_when_a_session_is_due(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    set_today("2025-01-08")
    _disable_status_animation(monkeypatch)
    _main(monkeypatch, "paper", "approve", "alpha", "--now")
    output = capsys.readouterr()

    record = json.loads(output.out)
    assert record["session"] == "2025-01-07"
    assert record["executed"] is not None
    assert not (directory / "pending-approval.json").exists()
    assert "executed" in output.err.lower()


def test_paper_approve_now_without_a_due_session_schedules_next_close(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    _disable_status_animation(monkeypatch)
    _main(monkeypatch, "paper", "approve", "alpha", "--now")
    output = capsys.readouterr()

    assert output.out == ""
    assert "will execute at the next close" in output.err.lower()
    assert json.loads((directory / "pending-approval.json").read_text())["verdict"] == "approve"


def test_paper_reject_records_verdict_and_event(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    _main(monkeypatch, "paper", "reject", "alpha")
    rejected = capsys.readouterr()

    assert json.loads((directory / "pending-approval.json").read_text())["verdict"] == "reject"
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    assert [event["kind"] for event in events] == ["tick", "reject"]
    assert "rejected" in rejected.err.lower()


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_when_gate_is_off(tmp_path, monkeypatch, capsys, offline, action):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    capsys.readouterr()
    _offline_tick(tmp_path / "paper" / "alpha")

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 2
    assert "approval gate is not enabled for 'alpha'" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_when_nothing_is_pending(tmp_path, monkeypatch, capsys, offline, action):
    path = _mandate(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 2
    assert "nothing is awaiting approval for 'alpha'" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_halted_funds_without_touching_control(tmp_path, monkeypatch, capsys, offline, action):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)
    _main(monkeypatch, "paper", "halt", "alpha", "--reason", "operator review")
    capsys.readouterr()
    control_before = (directory / "control.json").read_bytes()

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 1
    assert "alpha is halted: operator review" in capsys.readouterr().err
    assert (directory / "control.json").read_bytes() == control_before
    assert not (directory / "pending-approval.json").exists()
