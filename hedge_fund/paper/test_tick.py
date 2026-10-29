"""tick — deploy, advance one session at a time, and halt on failure."""

import json
import os
from datetime import datetime

import pytest
import yaml

from hedge_fund.backtesting.fund import backtest_fund
from hedge_fund.backtesting.test_fund import (
    FakeAnalyst,
    FakeDataClient,
    SERIES,
    WEEKDAYS,
)
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.data import sessions
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import Fund, FundSpec, TradingWindow
from hedge_fund.paper import (
    assessment_dates,
    deploy,
    following_session,
    Ledger,
    list_deployed,
    load_deployed,
    next_session,
    NothingDue,
    redo,
    tick,
    validate_fund_name,
)
from hedge_fund.pipeline import DecisionRecord, FundState
from hedge_fund.pipeline.session import FundHalted

LEGACY_FUND_YAML = """schema_version: 2
name: alpha
spec:
  schema_version: 2
  name: paper-fund
  strategies:
  - name: solo
    display_name: null
    weight: 1.0
    models:
    - name: a
      weight: 1.0
      params: {}
    blend:
      method: conviction_weighted
      gross_target: 1.0
      mode: long_short
  risk:
    max_position_pct: 1.0
    max_gross_exposure: 1.0
  costs:
    spread_bps: 0.0
    commission_per_share: 0.0
  capital: 100000.0
  rebalance: weekly
  benchmark: SPY
universe:
- AAPL
broker: paper
created: '{created}'
"""


@pytest.fixture(autouse=True)
def registered_fakes(monkeypatch):
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)


@pytest.fixture
def clock(monkeypatch):
    """Pin 'now' so completed_through() is deterministic; returns a setter."""

    def set_today(day: str, hour: int = 12):
        y, m, d = map(int, day.split("-"))

        class Clock:
            @staticmethod
            def now(tz):
                return datetime(y, m, d, hour, tzinfo=tz)

        monkeypatch.setattr(sessions, "datetime", Clock)

    return set_today


@pytest.fixture
def SPEC(registered_fakes):
    return FundSpec(schema_version=2, name="paper-fund", strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}], risk={"max_position_pct": 1, "max_gross_exposure": 1}, capital=100_000, costs={"spread_bps": 0, "commission_per_share": 0})


def build_fund(spec):
    return Fund(spec, models={"solo": [FakeAnalyst("a", {"AAPL": 1})]})


def _tick(directory, session=None, data=None):
    return tick(directory, data or FakeDataClient(SERIES), session=session, build_fund=build_fund)


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------


def test_deploy_lays_out_the_fund_directory(tmp_path, SPEC):
    directory = deploy("alpha", SPEC, ["aapl", "AAPL", "msft"], root=tmp_path)
    assert directory == tmp_path / "alpha"
    deployed = load_deployed(directory)
    assert deployed.name == "alpha" and deployed.spec == SPEC
    assert deployed.universe == ["AAPL", "MSFT"] and deployed.broker == "paper"
    assert yaml.safe_load((directory / "fund.yaml").read_text())["spec"]["name"] == "paper-fund"
    assert json.loads((directory / "broker.json").read_text()) == {"cash": 100_000, "shares": {}}
    assert json.loads((directory / "control.json").read_text()) == {"halted": False}
    assert (directory / "ledger").is_dir() and Ledger(directory).sessions() == []
    assert list_deployed(tmp_path) == [directory]
    assert list_deployed(tmp_path / "nowhere") == []
    with pytest.raises(FileExistsError, match="already exists"):
        deploy("alpha", SPEC, ["AAPL"], root=tmp_path)


def test_default_approval_deploy_yaml_matches_pre_feature_bytes(tmp_path, SPEC):
    assert not SPEC.approval_required
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    expected = LEGACY_FUND_YAML.replace("{created}", datetime.now().date().isoformat()).replace("\n", os.linesep).encode("utf-8")

    assert (directory / "fund.yaml").read_bytes() == expected


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "-lead", ".hidden", "sp ace"])
def test_deploy_rejects_unsafe_names(tmp_path, bad, SPEC):
    with pytest.raises(ValueError, match="invalid fund name"):
        validate_fund_name(bad)
    with pytest.raises(ValueError):
        deploy(bad, SPEC, ["AAPL"], root=tmp_path)
    assert list_deployed(tmp_path) == []


def test_load_deployed_reports_the_path_on_bad_files(tmp_path, SPEC):
    (tmp_path / "fund.yaml").write_text("[oops")
    with pytest.raises(ValueError, match="fund.yaml"):
        load_deployed(tmp_path)
    (tmp_path / "fund.yaml").write_text("name: x\n")
    with pytest.raises(ValueError, match="spec"):
        load_deployed(tmp_path)


# ---------------------------------------------------------------------------
# next_session
# ---------------------------------------------------------------------------


def test_next_session_is_latest_completed_for_a_fresh_fund_and_the_next_one_after(clock, SPEC):
    clock("2024-06-13")  # completed through 06-12
    data = FakeDataClient(SERIES)
    assert next_session(data, SPEC, None) == "2024-06-12"
    assert next_session(data, SPEC, "2024-06-07") == "2024-06-10"
    assert next_session(data, SPEC, "2024-06-12") is None
    clock("2024-06-03")  # nothing completed inside the series yet
    assert next_session(data, SPEC, None) is None


def test_next_session_of_a_minute_fund_is_the_latest_bar_passed_and_asks_nothing_of_the_market(SPEC):
    spec = SPEC.model_copy(update={"rebalance": "minute", "interval": 5.0, "window": TradingWindow(start="13:00", end="13:10")})
    at = lambda hhmmss: datetime.fromisoformat(f"2024-06-04T{hhmmss}").replace(tzinfo=NEW_YORK)  # noqa: E731
    assert next_session(None, spec, None, now=lambda: at("12:59:59")) is None
    assert next_session(None, spec, None, now=lambda: at("13:07:30")) == "2024-06-04T13:05:00"
    assert next_session(None, spec, "2024-06-04T13:05:00", now=lambda: at("13:07:30")) is None
    assert next_session(None, spec, "2024-06-04T13:05:00", now=lambda: at("13:10:00")) == "2024-06-04T13:10:00"
    assert next_session(None, spec, "2024-06-04T13:10:00", now=lambda: at("18:00:00")) is None  # the day is done
    assert following_session(spec, "2024-06-04T13:10:00", at("18:00:00")) == "Wed 13:00:00 ET"
    assert following_session(SPEC, "2024-06-07", at("18:00:00")) == "2024-06-10 close"  # a Friday: Monday


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def test_ticks_advance_one_session_each_and_match_the_backtest(tmp_path, clock, SPEC):
    clock("2024-06-04")  # the fund is deployed Tuesday morning: Monday is the latest close
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)

    monday = _tick(directory)
    assert monday.session == "2024-06-03" and monday.rebalance
    assert monday.decision is not None and monday.executed is None
    with pytest.raises(NothingDue, match="after 2024-06-03"):
        _tick(directory)

    clock("2024-06-06")  # two closes have gone by; ticks catch up one at a time
    tuesday = _tick(directory)
    assert tuesday.session == "2024-06-04"
    assert tuesday.executed.execution_as_of == "2024-06-04"
    assert tuesday.positions == {"AAPL": 500}
    assert json.loads((directory / "broker.json").read_text()) == {"cash": 0, "shares": {"AAPL": 500}}
    wednesday = _tick(directory)
    assert wednesday.session == "2024-06-05" and wednesday.executed is None

    assert Ledger(directory).sessions() == WEEKDAYS[:3]
    replayed = backtest_fund(build_fund(SPEC), WEEKDAYS[0], WEEKDAYS[2], FakeDataClient(SERIES), ["AAPL"])
    assert Ledger(directory).records() == replayed.records
    kinds = [e["kind"] for e in Ledger(directory).events()]
    assert kinds == ["tick", "tick", "tick"]


def test_gate_expires_unapproved_decision_and_continues(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    book_before = json.loads((directory / "broker.json").read_text())

    clock("2024-06-05")
    skipped = _tick(directory)

    ledger = Ledger(directory)
    assert skipped.executed is None
    assert skipped.decision is not None and skipped.decision.as_of == skipped.session
    assert json.loads((directory / "broker.json").read_text()) == book_before
    assert ledger.sessions() == ["2024-06-03", "2024-06-04"]
    assert ledger.replay(spec.capital).pending == skipped.decision
    assert ledger.halted() is None
    assert [event["kind"] for event in ledger.events()] == ["tick", "expire", "tick"]
    expiry = ledger.events()[1]
    assert expiry["decision_as_of"] == first.decision.as_of
    assert expiry["reason"] == "no verdict"


def test_gate_executes_matching_approval_once(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", first.decision.as_of, "cli")

    clock("2024-06-05")
    executed = _tick(directory)

    assert executed.executed is not None
    assert executed.executed.execution_as_of == "2024-06-04"
    assert executed.positions == {"AAPL": 500}
    assert ledger.approval() is None
    assert [event["kind"] for event in ledger.events()] == ["tick", "approve", "tick"]


def test_gate_rejects_matching_verdict_without_trading(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    book_before = json.loads((directory / "broker.json").read_text())
    ledger = Ledger(directory)
    ledger.set_approval("reject", first.decision.as_of, "tui")

    clock("2024-06-05")
    rejected = _tick(directory)

    assert rejected.executed is None
    assert rejected.decision is not None and rejected.decision.as_of == rejected.session
    assert json.loads((directory / "broker.json").read_text()) == book_before
    assert ledger.approval() is None
    assert [event["kind"] for event in ledger.events()] == ["tick", "reject", "reject", "tick"]
    assert ledger.events()[2]["consumed"] is True


def test_gate_ignores_and_clears_stale_approval(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", "2024-06-02", "cli")

    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.executed is None
    assert skipped.decision is not None
    assert ledger.approval() is None
    expiry = next(event for event in ledger.events() if event["kind"] == "expire")
    assert expiry["decision_as_of"] == first.decision.as_of
    assert expiry["reason"] == "stale verdict"


def test_verdict_written_during_session_waits_for_next_session(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    _tick(directory)
    ledger = Ledger(directory)
    read_approval = Ledger.approval

    def write_after_read(current):
        approval = read_approval(current)
        if current.directory == directory and approval is None:
            current.set_approval("approve", "2024-06-04", "tui")
        return approval

    monkeypatch.setattr(Ledger, "approval", write_after_read)
    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.session == "2024-06-04" and skipped.executed is None
    assert skipped.decision is not None
    assert ledger.approval()["decision_as_of"] == skipped.decision.as_of

    monkeypatch.setattr(Ledger, "approval", read_approval)
    clock("2024-06-06")
    executed = _tick(directory)

    assert executed.executed is not None
    assert executed.executed.as_of == skipped.decision.as_of
    assert ledger.approval() is None


def test_gate_off_keeps_auto_execution_without_reading_mailbox(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    _tick(directory)
    monkeypatch.setattr(Ledger, "approval", lambda self: pytest.fail("gate-off path read approval mailbox"))

    clock("2024-06-05")
    executed = _tick(directory)

    assert executed.executed is not None
    assert executed.positions == {"AAPL": 500}
    assert [event["kind"] for event in Ledger(directory).events()] == ["tick", "tick"]


def test_halt_precedes_approval_gate(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    _tick(directory)
    ledger = Ledger(directory)
    ledger.halt("manual review")
    control_before = ledger.control_path.read_bytes()
    monkeypatch.setattr(Ledger, "approval", lambda self: pytest.fail("halted path read approval mailbox"))

    with pytest.raises(FundHalted, match="manual review"):
        _tick(directory)

    assert ledger.control_path.read_bytes() == control_before
    assert not ledger.approval_path.exists()


def test_explicit_session_is_idempotent_and_must_be_the_next_one(tmp_path, clock, SPEC):
    clock("2024-06-06")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    first = _tick(directory)  # fresh fund: latest completed close, 06-05
    assert first.session == "2024-06-05"
    assert _tick(directory, session="2024-06-05") == first  # no-op, nothing appended
    assert Ledger(directory).sessions() == ["2024-06-05"]
    clock("2024-06-11")
    with pytest.raises(ValueError, match="not the next unrecorded session \\(2024-06-06\\)"):
        _tick(directory, session="2024-06-10")
    assert _tick(directory, session="2024-06-06").session == "2024-06-06"


def test_redo_runs_the_latest_session_again_and_replaces_its_record(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    with pytest.raises(NothingDue, match="nothing to run again"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    _tick(directory)  # 06-03: decided, long AAPL
    clock("2024-06-05")
    tuesday = _tick(directory)  # 06-04: bought 500 AAPL, decided again
    assert tuesday.positions == {"AAPL": 500} and tuesday.decision.final_weights == {"AAPL": 1.0}
    book_before = json.loads((directory / "broker.json").read_text())

    # Same analysts, same close: the redo reproduces the session exactly. The
    # point is the book — without the restore, the broker would still hold
    # Tuesday's 500 shares going in and the reconciliation would halt the fund.
    same = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    assert same == tuesday
    assert json.loads((directory / "broker.json").read_text()) == book_before
    kept = sorted((directory / "ledger" / "superseded").glob("*.json"))
    assert [p.name for p in kept] == [f"2024-06-04.{tuesday.hash[:12]}.json"]
    assert json.loads(kept[0].read_text())["hash"] == tuesday.hash

    # The analysts changed their minds by the evening: the 06-03 decision is
    # still what gets executed, but the new decision is different.
    bearish = redo(directory, FakeDataClient(SERIES), build_fund=lambda s: Fund(s, models={"solo": [FakeAnalyst("a", {"AAPL": -1})]}))
    assert bearish.session == "2024-06-04" and bearish.prev_hash == tuesday.prev_hash
    assert bearish.positions == {"AAPL": 500}  # executed the same pending decision
    assert bearish.decision.final_weights == {"AAPL": -1.0}  # but decided differently
    assert bearish.hash != tuesday.hash
    assert ledger.sessions() == ["2024-06-03", "2024-06-04"] and ledger.latest() == bearish
    assert ledger.replay(spec.capital).pending == bearish.decision  # the chain still verifies
    assert [e["kind"] for e in ledger.events()] == ["tick", "tick", "redo", "tick", "redo", "tick"]

    # The next real tick still finds 06-05 due and executes the redone decision.
    clock("2024-06-06")
    wednesday = _tick(directory)
    assert wednesday.session == "2024-06-05" and wednesday.executed.as_of == "2024-06-04"
    assert wednesday.positions == {"AAPL": -500}


def test_redo_refuses_a_halted_fund_and_leaves_it_untouched(tmp_path, clock, SPEC):
    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    Ledger(directory).halt("looking into it")
    with pytest.raises(FundHalted):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    assert Ledger(directory).latest() == first
    assert not (directory / "ledger" / "superseded").exists()


def test_failure_inside_advance_halts_the_fund_and_a_resume_clears_it(tmp_path, clock, SPEC):
    clock("2024-06-05")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    _tick(directory)  # 06-04, decision made
    clock("2024-06-06")
    series = {t: dict(v) for t, v in SERIES.items()}
    del series["AAPL"]["2024-06-05"]  # execution price missing at the next close
    with pytest.raises(ValueError, match="AAPL: missing close on 2024-06-05"):
        _tick(directory, data=FakeDataClient(series))
    ledger = Ledger(directory)
    assert ledger.halted().startswith("tick 2024-06-05 failed: ValueError")
    assert [e["kind"] for e in ledger.events()] == ["tick", "tick_failed", "halt"]
    assert ledger.sessions() == ["2024-06-04"]
    with pytest.raises(FundHalted):
        _tick(directory)  # data is fine again, but nobody has looked yet
    ledger.resume()
    assert _tick(directory).session == "2024-06-05"


def test_broker_drift_between_ticks_is_caught_and_halts(tmp_path, clock, SPEC):
    clock("2024-06-05")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    _tick(directory)
    book = json.loads((directory / "broker.json").read_text())
    book["cash"] -= 5
    (directory / "broker.json").write_text(json.dumps(book))
    clock("2024-06-06")
    from hedge_fund.pipeline.session import BookMismatch

    with pytest.raises(BookMismatch, match="cash"):
        _tick(directory)
    assert "BookMismatch" in Ledger(directory).halted()
    assert PaperBroker(directory / "broker.json").positions() == {}  # nothing traded


def test_assessment_dates_name_the_refresh_and_the_new_decision(SPEC):
    """A weekly fund. A Friday decision run at Tuesday's close is refreshed on
    Monday and followed by the week's new decision; a decision made at the
    previous close needs no refresh and mid-week no new decision; a fresh
    fund only decides."""
    friday = DecisionRecord.model_construct(as_of="2025-01-17")
    state = FundState(cash=100_000, last_session="2025-01-17", pending=friday)
    assert assessment_dates(state, "2025-01-21", SPEC) == ["2025-01-20", "2025-01-21"]
    monday = DecisionRecord.model_construct(as_of="2025-01-20")
    state = FundState(cash=100_000, last_session="2025-01-20", pending=monday)
    assert assessment_dates(state, "2025-01-21", SPEC) == []
    assert assessment_dates(FundState(cash=100_000), "2025-01-21", SPEC) == ["2025-01-21"]
    # On bars the refresh cutoff is the bar before, and every bar decides.
    spec = SPEC.model_copy(update={"rebalance": "minute", "interval": 5.0, "window": TradingWindow(start="13:00", end="13:10")})
    stale = DecisionRecord.model_construct(as_of="2025-01-17T13:10:00")
    state = FundState(cash=100_000, last_session="2025-01-17T13:10:00", pending=stale)
    assert assessment_dates(state, "2025-01-21T13:05:00", spec) == ["2025-01-21T13:00:00", "2025-01-21T13:05:00"]
    fresh = DecisionRecord.model_construct(as_of="2025-01-21T13:00:00")
    state = FundState(cash=100_000, last_session="2025-01-21T13:00:00", pending=fresh)
    assert assessment_dates(state, "2025-01-21T13:05:00", spec) == ["2025-01-21T13:05:00"]
