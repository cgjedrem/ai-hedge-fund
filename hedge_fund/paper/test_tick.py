"""tick — deploy, advance one session at a time, and halt on failure."""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from importlib import import_module
from pathlib import Path
from threading import current_thread, Event, Thread

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
    LedgerError,
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

paper_tick_module = import_module("hedge_fund.paper.tick")
root_module = import_module("hedge_fund.runtime.root")

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
    commission_bps: 0.0
    min_commission_per_order: 0.0
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


def _pre_expiry_receipt_payload(receipt):
    payload = receipt.model_dump(mode="python", exclude={"receipt_id", "issued_at", "valid_until"})
    legacy = type(receipt).model_construct(**payload, receipt_id="0" * 64)
    payload["receipt_id"] = legacy.compute_receipt_id()
    return type(receipt).model_validate(payload).model_dump(mode="json", exclude={"issued_at", "valid_until"})


def _deploy_owned_paper_test_fund(root, spec):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.runtime.root import RootContext
    from hedge_fund.test_support.handover import enroll_synthetic_root

    enroll_synthetic_root(root)
    with RootContext.open(root) as context:
        context.mkdir("paper")
        with RootOwnerLease.acquire(context) as owner:
            admission = AdmissionCoordinator(context, owner_lease=owner)
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=context.path / "paper")
            record_ledger_head(context, "alpha", admission=admission)
    return directory


@contextmanager
def _owned_paper_lane(directory, fund):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    root_path = Path(directory).parents[1]
    with RootContext.open(root_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.manual_session(fund, timeout=0):
                yield admission


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


def test_legacy_deploy_creates_a_missing_paper_root(tmp_path, SPEC):
    root = tmp_path / "new-root"
    directory = deploy("alpha", SPEC, ["AAPL"], root=root / "paper")

    assert directory == root / "paper" / "alpha"
    assert directory.is_dir()
    assert not (root / "runtime").exists()


def test_default_approval_deploy_yaml_matches_pre_feature_bytes(tmp_path, SPEC):
    assert not SPEC.approval_required
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    expected = LEGACY_FUND_YAML.replace("{created}", datetime.now().date().isoformat()).replace("\n", os.linesep).encode("utf-8")

    assert (directory / "fund.yaml").read_bytes() == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        ".",
        "..",
        "a/b",
        "-lead",
        ".hidden",
        "sp ace",
        "watchtower.",
        "watchtower ",
        "CON",
        "nul.txt",
        "COM1",
        "LPT9.yaml",
    ],
)
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


def test_tick_request_id_replays_record_and_conflicts_on_changed_payload(tmp_path, clock, SPEC):
    from hedge_fund.paper.ledger import PaperRequestConflict

    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    clock("2024-06-04")
    data_calls = []

    class CountingClient(FakeDataClient):
        def get_prices(self, ticker, start_date, end_date, **kwargs):
            data_calls.append((ticker, start_date, end_date))
            return super().get_prices(ticker, start_date, end_date, **kwargs)

    client = CountingClient(SERIES)
    record = tick(
        directory,
        client,
        build_fund=build_fund,
        request_id="cli-tick-alpha-001",
        expected_head=None,
    )
    calls_after_commit = list(data_calls)

    replayed = tick(
        directory,
        client,
        build_fund=build_fund,
        request_id="cli-tick-alpha-001",
        expected_head=None,
    )

    assert replayed.hash == record.hash
    assert data_calls == calls_after_commit
    with pytest.raises(PaperRequestConflict, match="request identity conflicts"):
        tick(
            directory,
            client,
            session=record.session,
            build_fund=build_fund,
            request_id="cli-tick-alpha-001",
            expected_head=None,
        )


def test_tick_fast_path_outcome_includes_session(tmp_path, clock, SPEC):
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)

    clock("2024-06-04")

    with _owned_paper_lane(directory, "alpha"):
        record = _tick(directory)
        replayed = tick(
            directory,
            FakeDataClient(SERIES),
            session=record.session,
            expected_head=record.hash,
            build_fund=build_fund,
            request_id="tick-fast-path-replay",
        )

    event = next(event for event in Ledger(directory).events() if event.get("request_id") == "tick-fast-path-replay")
    assert replayed.hash == record.hash
    assert event["kind"] == "tick"
    assert event["session"] == record.session


@pytest.mark.parametrize("request_id", ["fresh-tick", None])
def test_new_identity_intent_fence_refuses_before_tick_effects(tmp_path, clock, SPEC, request_id):
    from hedge_fund.paper.ledger import UnresolvedTickIntentRefusal

    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    clock("2024-06-04")
    ledger = Ledger(directory)
    intent_digest = ledger.tick_request_digest(
        "interrupted-tick",
        expected_head=None,
        session=None,
    )
    ledger.log_event(
        "tick_intent",
        request_id="interrupted-tick",
        request_action="tick",
        request_digest=intent_digest,
        expected_head=None,
        requested_session=None,
        session="2024-06-03",
        durable=True,
    )
    events_before = ledger.events()
    broker_before = (directory / "broker.json").read_bytes()

    with pytest.raises(UnresolvedTickIntentRefusal) as refused:
        tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            request_id=request_id,
            expected_head=None,
        )

    assert refused.value.fields == {
        "reason": "unresolved-tick-intent",
        "fund": "alpha",
        "intent_request_id": "interrupted-tick",
        "intent_session": "2024-06-03",
        "recovery": "reconcile-tick-request",
    }
    assert ledger.events() == events_before
    assert ledger.sessions() == []
    assert (directory / "broker.json").read_bytes() == broker_before


def test_same_identity_intent_retry_uses_existing_reconciliation_lookup(tmp_path, clock, SPEC):
    from hedge_fund.paper.ledger import PaperReconciliationRequired

    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    clock("2024-06-04")
    ledger = Ledger(directory)
    request_id = "interrupted-tick"
    request_digest = ledger.tick_request_digest(request_id, expected_head=None, session=None)
    ledger.log_event(
        "tick_intent",
        request_id=request_id,
        request_action="tick",
        request_digest=request_digest,
        expected_head=None,
        requested_session=None,
        session="2024-06-03",
        durable=True,
    )
    events_before = ledger.events()
    broker_before = (directory / "broker.json").read_bytes()

    with pytest.raises(PaperReconciliationRequired, match="outcome is uncertain"):
        tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            request_id=request_id,
            expected_head=None,
        )

    assert ledger.events() == events_before
    assert (directory / "broker.json").read_bytes() == broker_before


def test_orphaned_intent_reconciliation_admits_new_tick(tmp_path, clock, SPEC):
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-05")
    ledger = Ledger(directory)
    request_id = "crashed-tick-001"
    request_digest = ledger.tick_request_digest(
        request_id,
        expected_head=None,
        session=None,
    )
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            request_action="tick",
            request_digest=request_digest,
            expected_head=None,
            requested_session=None,
            session="2024-06-04",
            durable=True,
        )

        state = ledger.replay(SPEC.capital, full=True)
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            state,
            ledger.latest(),
            intent_request_id=request_id,
        )
        assert snapshot.preview.recoverable is True
        confirmation = TickIntentReconciliationConfirmation(
            request_id="reconcile-crashed-tick-001",
            intent_request_id=request_id,
            intent_digest=snapshot.preview.intent_digest,
            preview_digest=snapshot.preview.preview_digest,
            decision="confirm-paper-book-matches-ledger",
        )
        receipt_id = ledger.reconcile_tick_intent(
            SPEC.capital,
            confirmation=confirmation,
            operator="cli",
        )

    assert receipt_id
    assert ledger.unresolved_tick_intents() == ()
    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-04",
            expected_head=None,
            build_fund=build_fund,
            request_id="tick-after-reconciliation",
        )
    assert record.session == "2024-06-04"


def test_orphaned_approval_consumption_reconciliation_allows_resume_and_next_tick(tmp_path, clock, SPEC):
    from hedge_fund.runtime.admission import (
        AdmissionCoordinator,
        paper_approval_transition,
        RootOwnerLease,
    )
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )
    from hedge_fund.runtime.root import RootContext

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = _deploy_owned_paper_test_fund(tmp_path, spec)
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    assert first.decision is not None

    root_path = Path(directory).parents[1]
    with RootContext.open(root_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with paper_approval_transition(admission, "alpha") as proof:
                approval = ledger.set_approval("approve", first.decision.as_of, first.hash, "cli", admission=proof)

    clock("2024-06-05")
    request_id = "crashed-after-consume"
    session = "2024-06-04"
    request_digest = ledger.tick_request_digest(request_id, expected_head=first.hash, session=session)
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            request_action="tick",
            request_digest=request_digest,
            expected_head=first.hash,
            requested_session=session,
            session=session,
            durable=True,
        )
        ledger.log_event(
            "consume",
            decision_as_of=approval["decision_as_of"],
            decision_hash=approval["decision_hash"],
            approval_verdict=approval["verdict"],
            approval_by=approval["by"],
            approval_id=approval["approval_id"],
            session=session,
            durable=True,
        )
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            ledger.replay(spec.capital, full=True),
            ledger.latest(),
            intent_request_id=request_id,
        )
        assert snapshot.preview.recoverable is True
        assert len(snapshot.preview.approval_journal_event_digests) == 1
        confirmation = TickIntentReconciliationConfirmation(
            request_id="reconcile-consumed-intent",
            intent_request_id=request_id,
            intent_digest=snapshot.preview.intent_digest,
            preview_digest=snapshot.preview.preview_digest,
            decision="confirm-paper-book-matches-ledger",
        )
        ledger.reconcile_tick_intent(spec.capital, confirmation=confirmation, operator="cli")

    assert ledger.unresolved_tick_intents() == ()
    resolved = next(event for event in ledger.events() if event.get("kind") == "tick_intent_resolved")
    assert resolved["receipt"]["approval_journal_event_digests"] == list(snapshot.preview.approval_journal_event_digests)
    with _owned_paper_lane(directory, "alpha"):
        ledger.halt("synthetic consumption recovery check")
        ledger.resume(spec.capital, approval_required=True)
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session=session,
            expected_head=first.hash,
            build_fund=build_fund,
            request_id="tick-after-consumption-resolution",
        )
    assert ledger.halted() is None
    assert record.session == session


@pytest.mark.parametrize("mismatch", ["session", "decision_as_of"])
def test_tick_intent_reconciliation_preview_blocks_unrelated_orphaned_consumption(tmp_path, clock, SPEC, mismatch):
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
    )

    clock("2024-06-04")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)

    clock("2024-06-05")
    request_id = "intent-with-unrelated-consume"
    session = "2024-06-04"
    request_digest = ledger.tick_request_digest(request_id, expected_head=first.hash, session=session)
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            request_action="tick",
            request_digest=request_digest,
            expected_head=first.hash,
            requested_session=session,
            session=session,
            durable=True,
        )
        ledger.log_event(
            "consume",
            decision_as_of=first.decision.as_of if mismatch == "session" else "2024-06-02",
            decision_hash=first.hash,
            approval_verdict="approve",
            approval_by="cli",
            approval_id="a" * 32,
            session="2024-06-05" if mismatch == "session" else session,
            durable=True,
        )
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            ledger.replay(SPEC.capital, full=True),
            ledger.latest(),
            intent_request_id=request_id,
        )

    assert snapshot.preview.recoverable is False
    assert snapshot.preview.reason == "approval-journal-incomplete"


def test_approval_consumption_without_intent_is_reviewable_and_resolvable(tmp_path, clock, SPEC):
    from hedge_fund.paper.ledger import PaperReconciliationRequired
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    clock("2024-06-04")
    with _owned_paper_lane(directory, "alpha"):
        latest = _tick(directory)
        ledger.log_event(
            "consume",
            decision_as_of=latest.session,
            decision_hash=latest.hash,
            approval_verdict="approve",
            approval_by="cli",
            approval_id="b" * 32,
            session=latest.session,
            durable=True,
        )
        approval_events = ledger.unresolved_approval_consumption_events(allow_unresolved_corruption=True)
        unresolved = ledger.unresolved_recovery_state()
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            ledger.replay(SPEC.capital, full=True),
            ledger.latest(),
        )

    assert snapshot.preview.required is True
    assert snapshot.preview.recoverable is True
    assert snapshot.preview.reason == "ready"
    assert snapshot.preview.intent_digest is None
    assert snapshot.preview.approval_journal_event_digests == (approval_events[0][0],)
    assert unresolved.required is True
    assert unresolved.approval_consumptions == approval_events
    with pytest.raises(PaperReconciliationRequired, match="approval consumption is incomplete"):
        ledger.require_ready_for_work(ledger.replay(SPEC.capital, full=True), approval_required=False)
    confirmation = TickIntentReconciliationConfirmation(
        request_id="resolve-unmatched-approval",
        intent_request_id=None,
        intent_digest=None,
        preview_digest=snapshot.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    with _owned_paper_lane(directory, "alpha"):
        receipt_id = ledger.reconcile_tick_intent(
            SPEC.capital,
            confirmation=confirmation,
            operator="cli",
        )
    with _owned_paper_lane(directory, "alpha"):
        replayed_receipt_id = ledger.reconcile_tick_intent(
            SPEC.capital,
            confirmation=confirmation,
            operator="cli",
        )

    assert receipt_id
    assert replayed_receipt_id == receipt_id
    assert ledger.unresolved_approval_consumption_events(allow_unresolved_corruption=True) == ()
    resolution = next(event for event in ledger.events() if event.get("kind") == "tick_intent_resolved")
    assert resolution["receipt"]["approval_journal_event_digests"] == [approval_events[0][0]]
    assert ledger.unresolved_recovery_state().required is False
    ledger.require_ready_for_work(ledger.replay(SPEC.capital, full=True), approval_required=False)


def test_intent_reconciliation_preview_digest_accepts_nan_event_field(tmp_path, clock, SPEC):
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-05")
    ledger = Ledger(directory)
    request_id = "nan-intent-event"
    request_digest = ledger.tick_request_digest(
        request_id,
        expected_head=None,
        session=None,
    )
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            request_action="tick",
            request_digest=request_digest,
            expected_head=None,
            requested_session=None,
            session="2024-06-04",
            diagnostic=float("nan"),
            durable=True,
        )

        state = ledger.replay(SPEC.capital, full=True)
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            state,
            ledger.latest(),
            intent_request_id=request_id,
        )

    assert snapshot.preview.intent_request_id == request_id
    assert snapshot.preview.preview_digest


@pytest.mark.parametrize("corruption", ["torn-line", "kindless-event"])
def test_corrupt_intent_history_reconciliation_preserves_prefix_and_admits_tick(tmp_path, clock, SPEC, corruption):
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-05")
    ledger = Ledger(directory)
    request_id = "crashed-tick-corrupt-history"
    request_digest = ledger.tick_request_digest(
        request_id,
        expected_head=None,
        session=None,
    )
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            request_action="tick",
            request_digest=request_digest,
            expected_head=None,
            requested_session=None,
            session="2024-06-04",
            durable=True,
        )
        with ledger.events_path.open("ab") as history:
            history.write(b'{"kind":' if corruption == "torn-line" else b'{"missing-kind":true}\n')
        prefix = ledger.events_path.read_bytes()
        state = ledger.replay(SPEC.capital, full=True)
        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            state,
            ledger.latest(),
            intent_request_id=request_id,
        )
        assert snapshot.preview.recoverable is True
        assert snapshot.preview.corrupt_event_digests
        confirmation = TickIntentReconciliationConfirmation(
            request_id="reconcile-corrupt-intent-001",
            intent_request_id=request_id,
            intent_digest=snapshot.preview.intent_digest,
            preview_digest=snapshot.preview.preview_digest,
            decision="confirm-paper-book-matches-ledger",
        )
        ledger.reconcile_tick_intent(
            SPEC.capital,
            confirmation=confirmation,
            operator="cli",
        )

    assert ledger.events_path.read_bytes().startswith(prefix)
    assert ledger.unresolved_tick_intents() == ()
    assert any(event["kind"] == "tick_intent_resolved" for event in ledger.events())
    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-04",
            expected_head=None,
            build_fund=build_fund,
            request_id="tick-after-corrupt-reconciliation",
        )
    assert record.session == "2024-06-04"


def test_legacy_intent_reconciliation_admits_new_tick(tmp_path, clock, SPEC):
    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-05")
    ledger = Ledger(directory)
    request_id = "legacy-crashed-tick"
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_intent",
            request_id=request_id,
            session="2024-06-04",
            durable=True,
        )

        snapshot = build_tick_intent_reconciliation_snapshot(
            directory,
            load_deployed(directory),
            ledger,
            ledger.replay(SPEC.capital, full=True),
            ledger.latest(),
            intent_request_id=request_id,
        )
        assert snapshot.preview.recoverable is True
        confirmation = TickIntentReconciliationConfirmation(
            request_id="reconcile-legacy-intent-001",
            intent_request_id=request_id,
            intent_digest=snapshot.preview.intent_digest,
            preview_digest=snapshot.preview.preview_digest,
            decision="confirm-paper-book-matches-ledger",
        )
        ledger.reconcile_tick_intent(
            SPEC.capital,
            confirmation=confirmation,
            operator="cli",
        )

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-04",
            expected_head=None,
            build_fund=build_fund,
            request_id="tick-after-legacy-reconciliation",
        )
    assert record.session == "2024-06-04"


def test_operation_effect_callback_runs_after_tick_intent(tmp_path, clock, SPEC):
    clock("2024-06-04")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    request_id = "effect-boundary-observation"
    observed = []

    def effect_started():
        events = ledger.events()
        assert any(event.get("kind") == "tick_intent" and event.get("request_id") == request_id for event in events)
        assert not any(event.get("kind") in {"tick", "tick_failed", "tick_aborted"} and event.get("request_id") == request_id for event in events)
        observed.append(True)

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            request_id=request_id,
            on_effect_started=effect_started,
        )

    assert record.session
    assert observed


def test_halt_before_effect_aborts_intent_then_resume_admits_new_tick(tmp_path, clock, SPEC, monkeypatch):
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    ledger = Ledger(directory)
    original_advance = paper_tick_module.advance

    def halt_before_effect(*_args, **kwargs):
        ledger.halt("mid-tick halt", request_id="halt-mid-tick-001")
        kwargs["before_effect"]()

    monkeypatch.setattr(paper_tick_module, "advance", halt_before_effect)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(FundHalted):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                expected_head=None,
                build_fund=build_fund,
                request_id="halted-intent-request",
            )

    aborted = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == "halted-intent-request"]
    assert len(aborted) == 1
    assert aborted[0]["no_effects"] is True
    assert not any(event.get("kind") == "tick_failed" and event.get("request_id") == "halted-intent-request" for event in ledger.events())
    assert ledger.unresolved_tick_intents() == ()
    with _owned_paper_lane(directory, "alpha"):
        ledger.resume(SPEC.capital)
    monkeypatch.setattr(paper_tick_module, "advance", original_advance)

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-03",
            expected_head=None,
            build_fund=build_fund,
            request_id="tick-after-halt-resume",
        )
    assert record.session == "2024-06-03"


def test_tui_resume_without_request_id_is_completed_before_tick_gate(tmp_path, clock, SPEC, monkeypatch):
    clock("2024-06-05")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        ledger.halt("operator pause")

    original_log_event = Ledger.log_event
    original_write_control = Ledger._write_control
    failed_completion = []
    clear_writes = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic TUI crash before Resume completion")
        return original_log_event(self, kind, **fields)

    def observe_clear_write(self, halted, reason, **kwargs):
        if halted is False:
            clear_writes.append(halted)
        return original_write_control(self, halted, reason, **kwargs)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    monkeypatch.setattr(Ledger, "_write_control", observe_clear_write)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(OSError, match="synthetic TUI crash"):
            ledger.resume(SPEC.capital, operator="tui")

    monkeypatch.setattr(paper_tick_module, "next_session", lambda *_args, **_kwargs: None)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(NothingDue):
            tick(directory, FakeDataClient(SERIES), build_fund=build_fund)

    completions = [event for event in ledger.events() if event["kind"] == "resume_completed"]
    assert len(completions) == 1
    assert "request_id" not in completions[0]
    assert clear_writes == [False]
    assert ledger.halted() is None
    assert ledger.unresolved_recovery_state().required is False


def test_tui_resume_dedup_matches_full_identity_across_tick(tmp_path, clock, SPEC, monkeypatch):
    clock("2024-06-04")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        ledger.halt("first operator pause")
        ledger.resume(SPEC.capital, operator="tui")
    first_resume = next(event for event in ledger.events() if event.get("kind") == "resume")

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-03",
            expected_head=None,
            build_fund=build_fund,
        )
    latest_head = ledger.latest().hash
    assert latest_head != first_resume.get("head_hash")
    assert record.session == "2024-06-03"

    with _owned_paper_lane(directory, "alpha"):
        ledger.halt("second operator pause")
    original_log_event = Ledger.log_event
    failed_completion = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic TUI crash before second Resume completion")
        return original_log_event(self, kind, **fields)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(OSError, match="second Resume completion"):
            ledger.resume(SPEC.capital, operator="tui")

    landed = ledger.landed_resume_intent()

    assert failed_completion == [True]
    assert ledger.halted() is None
    assert landed is not None
    assert landed["head_hash"] == latest_head
    assert len([event for event in ledger.events() if event.get("kind") == "resume"]) == 2
    with _owned_paper_lane(directory, "alpha"):
        completed = ledger.complete_landed_resume_intent()
    assert completed == {"name": directory.name, "halted": False, "reconciliation_id": None}
    assert ledger.unresolved_recovery_state().required is False


def test_tick_retries_landed_resume_after_transient_audit_probe(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.paper.ledger import AuditObservationUnavailable

    clock("2024-06-05")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        ledger.halt("operator pause")

    original_log_event = Ledger.log_event
    failed_completion = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic TUI crash before Resume completion")
        return original_log_event(self, kind, **fields)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(OSError, match="synthetic TUI crash"):
            ledger.resume(SPEC.capital, operator="tui")

    original_events = Ledger.events
    failed_probe = []

    def unavailable_once(self):
        if self.directory == directory and not failed_probe:
            failed_probe.append(True)
            raise AuditObservationUnavailable("synthetic audit contention")
        return original_events(self)

    monkeypatch.setattr(Ledger, "events", unavailable_once)
    monkeypatch.setattr(paper_tick_module, "next_session", lambda *_args, **_kwargs: None)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(NothingDue):
            tick(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert ledger.halted() is None
    assert len([event for event in ledger.events() if event["kind"] == "halt"]) == 1
    assert failed_probe == [True]
    assert ledger.halted() is None
    assert len([event for event in ledger.events() if event["kind"] == "resume_completed"]) == 1
    assert ledger.unresolved_recovery_state().required is False


def test_pre_expiry_failure_receipt_keeps_fund_tickable(tmp_path, clock, SPEC):
    from hedge_fund.runtime.reconciliation import (
        build_reconciliation_snapshot,
        failure_digest,
        ReconciliationReceipt,
        unresolved_tick_failures,
    )

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    ledger = Ledger(directory)

    clock("2024-06-05")
    failure_time = "2024-06-05T00:00:00+00:00"
    with _owned_paper_lane(directory, "alpha"):
        ledger.log_event(
            "tick_failed",
            time=failure_time,
            session="2024-06-04",
            error="synthetic pre-expiry failure",
            expected_head=first.hash,
            operation_id="a" * 32,
            request_id="pre-expiry-failed-tick",
            capture_id="b" * 32,
            capture_digest="c" * 64,
            transmitted_fills=[],
            durable=True,
        )
        ledger.halt("synthetic pre-expiry failure")
        deployed = load_deployed(directory)
        state = ledger.replay(SPEC.capital, full=True)
        snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, ledger.latest())
        receipt = ReconciliationReceipt.create(
            failure_event=snapshot.failure_event,
            request_id="pre-expiry-recovery",
            current_head=snapshot.preview.current_head,
            broker_book_sha256=snapshot.preview.broker_book_sha256,
            fill_identity_sha256=snapshot.preview.fill_identity_sha256,
            operator="web",
            recorded_at=failure_time,
        )
        legacy_payload = _pre_expiry_receipt_payload(receipt)
        ledger.log_event(
            "reconciliation",
            time=failure_time,
            receipt=legacy_payload,
            durable=True,
        )
        resume_fields = {
            "head_hash": first.hash,
            "by": "web",
            "reconciliation_id": legacy_payload["receipt_id"],
        }
        ledger.log_event("resume", time=failure_time, **resume_fields, durable=True)
        ledger.log_event("resume_effect_intent", time=failure_time, **resume_fields, durable=True)
        ledger._write_control(False, None)
        ledger.log_event(
            "resume_completed",
            time=failure_time,
            **resume_fields,
            result={"name": "alpha", "halted": False, "reconciliation_id": legacy_payload["receipt_id"]},
            durable=True,
        )

    events = ledger.events()
    failure_event = next(event for event in events if event.get("kind") == "tick_failed")
    receipt_event = next(event for event in events if event.get("kind") == "reconciliation")
    resume_event = next(event for event in events if event.get("kind") == "resume")
    legacy_receipt = ReconciliationReceipt.model_validate(receipt_event["receipt"])
    assert "issued_at" not in receipt_event["receipt"]
    assert "valid_until" not in receipt_event["receipt"]
    assert receipt_event["receipt"]["failure_id"] == failure_digest(failure_event)
    assert legacy_receipt.issued_at is None
    assert legacy_receipt.matches_failure(failure_event)
    assert resume_event["reconciliation_id"] == legacy_receipt.receipt_id
    assert unresolved_tick_failures([failure_event, receipt_event, resume_event]) == []
    assert unresolved_tick_failures(events) == []
    assert ledger.unresolved_recovery_state().required is False
    with _owned_paper_lane(directory, "alpha"):
        later = _tick(directory)
    assert later.session == "2024-06-04"
    assert ledger.latest().session == later.session


def test_preflight_busy_after_intent_records_abort_and_same_identity_retries(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.admission import PaperPreflightBusy

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    ledger = Ledger(directory)
    original_run = paper_tick_module._run
    attempts = 0

    def busy_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PaperPreflightBusy("synthetic busy control")
        return original_run(*args, **kwargs)

    monkeypatch.setattr(paper_tick_module, "_run", busy_once)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(PaperPreflightBusy):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                expected_head=None,
                build_fund=build_fund,
                request_id="retryable-intent-request",
            )

    assert ledger.unresolved_tick_intents() == ()
    assert any(event.get("kind") == "tick_aborted" for event in ledger.events())
    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-03",
            expected_head=None,
            build_fund=build_fund,
            request_id="retryable-intent-request",
        )
    assert record.session == "2024-06-03"


def test_control_busy_after_intent_records_abort_and_same_identity_retries(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime import admission as admission_module

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    ledger = Ledger(directory)
    request_id = "control-busy-intent"
    original_transition = admission_module.paper_control_transition
    injected = False

    @contextmanager
    def busy_after_intent(path, identity):
        nonlocal injected
        if not injected and any(item.request_id == request_id for item in ledger.unresolved_tick_intents()):
            injected = True
            raise admission_module.PaperControlBusy("synthetic control contention")
        with original_transition(path, identity):
            yield

    monkeypatch.setattr(admission_module, "paper_control_transition", busy_after_intent)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(admission_module.PaperPreflightBusy):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                expected_head=None,
                build_fund=build_fund,
                request_id=request_id,
            )

    assert injected
    assert ledger.halted() is None
    aborted = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id]
    assert len(aborted) == 1
    assert aborted[0]["no_effects"] is True

    monkeypatch.setattr(admission_module, "paper_control_transition", original_transition)
    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-03",
            expected_head=None,
            build_fund=build_fund,
            request_id=request_id,
        )
    assert record.session == "2024-06-03"
    assert ledger.halted() is None


def test_pre_effect_intent_ledger_guard_failure_records_abort_without_halt(tmp_path, clock, SPEC, monkeypatch):
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    ledger = Ledger(directory)
    request_id = "pre-effect-ledger-guard"
    original_guard = Ledger._require_completed_redo
    injected = False

    def fail_after_intent(self, *args, **kwargs):
        nonlocal injected
        if not injected and any(item.request_id == request_id for item in self.unresolved_tick_intents()):
            injected = True
            raise LedgerError("synthetic pre-effect guard failure")
        return original_guard(self, *args, **kwargs)

    monkeypatch.setattr(Ledger, "_require_completed_redo", fail_after_intent)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(LedgerError, match="synthetic pre-effect guard failure"):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                expected_head=None,
                build_fund=build_fund,
                request_id=request_id,
            )

    assert injected
    assert ledger.halted() is None
    aborted = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id]
    assert len(aborted) == 1
    assert aborted[0]["no_effects"] is True


def test_intent_halt_in_approval_preflight_aborts_and_allows_same_identity_retry(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    directory = _deploy_owned_paper_test_fund(tmp_path, spec)
    clock("2024-06-04")
    ledger = Ledger(directory)
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    clock("2024-06-05")
    request_id = "approval-preflight-halt"

    def halt_after_intent(progress):
        if progress == 35:
            ledger.halt("synthetic approval-preflight halt", request_id="approval-preflight-halt-control")

    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(FundHalted):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-04",
                expected_head=first.hash,
                build_fund=build_fund,
                request_id=request_id,
                on_progress=halt_after_intent,
            )

    aborted = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id]
    assert len(aborted) == 1
    assert aborted[0]["no_effects"] is True
    assert not any(event.get("kind") == "tick_failed" and event.get("request_id") == request_id for event in ledger.events())
    with _owned_paper_lane(directory, "alpha"):
        ledger.resume(spec.capital)
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-04",
            expected_head=first.hash,
            build_fund=build_fund,
            request_id=request_id,
        )
    assert record.session == "2024-06-04"
    assert ledger.halted() is None


def test_cli_shaped_tick_races_web_logical_operation_submission(tmp_path, clock, SPEC):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta, timezone
    from threading import Barrier

    from hedge_fund.pipeline.session import code_version, mandate_hash
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.capture import freeze_capture
    from hedge_fund.runtime.configuration import resolve_settings
    from hedge_fund.runtime.operations import (
        DuplicateLogicalOperationRefusal,
        OperationStore,
        StalePreview,
    )
    from hedge_fund.runtime.root import RootContext

    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC.model_copy(update={"name": "alpha"}))
    clock("2024-06-04")
    session = "2024-06-03"
    barrier = Barrier(2)
    now = datetime.now(timezone.utc)
    with RootContext.open(tmp_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            deployed = load_deployed(directory)
            store = OperationStore(root, admission=admission)
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(deployed.spec),
                universe=tuple(deployed.universe),
                broker="paper",
                settings=resolve_settings(root),
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=deployed.spec.model_dump(mode="json"),
            )
            preview = store.create_preview(
                action="paper-tick",
                subject_id="alpha",
                expected_head=None,
                due_set=(session,),
                capture=capture,
                operator_session="synthetic-web-operator",
                payload={"kind": "manual-tick", "session": session, "expected_head": None},
                now=now,
                expires_at=now + timedelta(minutes=5),
            )

            def submit_web_operation():
                barrier.wait(timeout=5)

                def current_state():
                    latest = Ledger(directory).latest()
                    return (latest.hash if latest is not None else None, (session,))

                try:
                    accepted = store.accept_request(
                        request_id="web-logical-race",
                        action="paper-tick",
                        subject_id="alpha",
                        preview_id=preview.preview_id,
                        preview_digest=preview.digest,
                        confirmation_token=preview.confirmation_token,
                        operator_session="synthetic-web-operator",
                        expected_head=None,
                        due_set=(session,),
                        payload={"kind": "manual-tick", "session": session, "expected_head": None},
                        now=now,
                        current_state_resolver=current_state,
                    )
                except StalePreview:
                    return "stale"
                return ("accepted", accepted)

            def run_cli_shaped_tick():
                barrier.wait(timeout=5)
                try:
                    with admission.manual_session("alpha", timeout=5):
                        record = tick(
                            directory,
                            FakeDataClient(SERIES),
                            session=session,
                            expected_head=None,
                            build_fund=build_fund,
                            request_id="cli-logical-race",
                            operation_store=store,
                        )
                except DuplicateLogicalOperationRefusal:
                    return "duplicate"
                return ("completed", record)

            with ThreadPoolExecutor(max_workers=2) as executor:
                web_future = executor.submit(submit_web_operation)
                cli_future = executor.submit(run_cli_shaped_tick)
                web_result = web_future.result(timeout=30)
                cli_result = cli_future.result(timeout=30)

    assert (web_result == "stale" and isinstance(cli_result, tuple) and cli_result[0] == "completed") or (isinstance(web_result, tuple) and web_result[0] == "accepted" and cli_result == "duplicate")
    assert len(Ledger(directory).sessions()) == (1 if isinstance(cli_result, tuple) else 0)


def test_redo_supersedes_intent_without_becoming_a_duplicate_request(tmp_path, clock, SPEC):
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    clock("2024-06-04")
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.log_event(
        "tick_intent",
        request_id="interrupted-after-append",
        request_action="tick",
        request_digest="4" * 64,
        expected_head=first.prev_hash,
        requested_session=first.session,
        session=first.session,
        durable=True,
    )

    replayed = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert replayed.session == first.session
    assert Ledger(directory).unresolved_tick_intents() == ()


def test_pre_effect_intent_failure_aborts_and_same_identity_retries(tmp_path, clock, SPEC):
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-04")
    build_calls = []
    request_id = "cli-tick-alpha-failed"

    def failing_build(_spec):
        build_calls.append(True)
        raise RuntimeError("synthetic pipeline failure")

    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(RuntimeError, match="synthetic pipeline failure"):
            tick(
                directory,
                FakeDataClient(SERIES),
                build_fund=failing_build,
                request_id=request_id,
                expected_head=None,
            )

    ledger = Ledger(directory)
    abort = next(event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id)
    assert abort["no_effects"] is True
    assert ledger.halted() is None
    assert build_calls == [True]

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            request_id=request_id,
            expected_head=None,
        )

    assert record.session == "2024-06-03"
    assert ledger.halted() is None


def test_tick_request_id_keeps_nothing_due_terminal(tmp_path, clock, SPEC):
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    clock("2024-06-04")
    unavailable = FakeDataClient({})

    with pytest.raises(NothingDue):
        tick(
            directory,
            unavailable,
            build_fund=build_fund,
            request_id="cli-tick-alpha-no-work",
            expected_head=None,
        )

    with pytest.raises(NothingDue):
        tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            request_id="cli-tick-alpha-no-work",
            expected_head=None,
        )

    assert Ledger(directory).sessions() == []


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
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")

    clock("2024-06-05")
    executed = _tick(directory)

    assert executed.executed is not None
    assert executed.executed.execution_as_of == "2024-06-04"
    assert executed.positions == {"AAPL": 500}
    assert ledger.approval() is None
    assert [event["kind"] for event in ledger.events()] == ["tick", "approve", "consume", "tick"]


def test_weekly_redo_invalidates_approval_for_changed_decision(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    assert original.session == "2024-06-03" and original.decision is not None
    ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")

    bearish = redo(
        directory,
        FakeDataClient(SERIES),
        build_fund=lambda fund_spec: Fund(
            fund_spec,
            models={"solo": [FakeAnalyst("a", {"AAPL": -1})]},
        ),
    )

    assert bearish.decision is not None
    assert bearish.decision.final_weights == {"AAPL": -1.0}
    assert bearish.hash != original.hash
    assert ledger.approval() is None

    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.session == "2024-06-04"
    assert skipped.executed is None
    assert skipped.positions == {}
    assert ledger.halted() is None
    assert any(event.get("reason") == "decision redone" for event in ledger.events() if event["kind"] == "expire")


def test_redo_expiry_blocks_mailbox_when_unlink_fails(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("mailbox is held")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)

    redone = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert redone.hash != original.hash
    assert ledger.approval() is not None
    assert any(event.get("reason") == "decision redone" for event in ledger.events() if event["kind"] == "expire")
    assert any(event["kind"] == "approval_clear_failed" for event in ledger.events())

    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.executed is None
    assert ledger.halted() is None


def test_redo_rejects_corrupt_history_before_stale_mailbox_can_execute(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")
    ledger.events_path.write_text(ledger.events_path.read_text() + "{invalid-json\n")
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("synthetic mailbox unlink failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)
    original_book = (directory / "broker.json").read_bytes()

    with pytest.raises(LedgerError, match="approval history is unavailable"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert ledger.latest().hash == original.hash
    assert (directory / "broker.json").read_bytes() == original_book
    assert ledger.approval()["decision_hash"] == original.hash


@pytest.mark.parametrize("mailbox", ["matching", "stale", "malformed"])
def test_corrupt_approval_history_stops_a_normal_tick_before_execution(tmp_path, clock, SPEC, mailbox):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")
    if mailbox == "stale":
        value = ledger.approval()
        value["decision_as_of"] = "2024-06-02"
        ledger.approval_path.write_text(json.dumps(value), encoding="utf-8")
    elif mailbox == "malformed":
        ledger.approval_path.write_text("{invalid", encoding="utf-8")
    ledger.events_path.write_text(ledger.events_path.read_text() + "{invalid-json\n")
    original_book = (directory / "broker.json").read_bytes()

    clock("2024-06-05")
    with pytest.raises(LedgerError, match="approval history is unavailable"):
        _tick(directory)

    assert ledger.latest().hash == original.hash
    assert (directory / "broker.json").read_bytes() == original_book
    assert ledger.halted() == "approval journal requires reconciliation"


def test_redo_records_expiry_before_a_failed_rewind(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("synthetic mailbox unlink failure")
        return unlink(path, *args, **kwargs)

    def fail_rewind(_self):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)
    monkeypatch.setattr(Ledger, "rewind", fail_rewind)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        redo(directory, FakeDataClient(SERIES), build_fund=lambda _spec: pytest.fail("provider work started"))

    resolved, stale = ledger.resolve_approval(original.decision.as_of, original.hash)
    assert resolved is None and stale is not None
    assert ledger.latest().hash == original.hash
    assert ledger._latest_approval_event(original.decision.as_of, original.hash, strict=True)["kind"] == "expire"


def test_each_identical_gated_redo_gets_a_new_approval_identity(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)
    first = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    second = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert len({original.hash, first.hash, second.hash}) == 3
    assert original.redo_nonce is None
    assert first.redo_nonce and second.redo_nonce and first.redo_nonce != second.redo_nonce
    assert ledger.replay(spec.capital).prev_hash == second.hash
    with pytest.raises(LedgerError, match="expired"):
        ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")
    with pytest.raises(LedgerError, match="expired"):
        ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    ledger.set_approval("approve", second.decision.as_of, second.hash, "cli")

    clock("2024-06-05")
    assert _tick(directory).executed is not None


def test_redo_replays_consumed_gated_approval_for_same_decision(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    monday = _tick(directory)
    assert monday.decision is not None
    ledger.set_approval("approve", monday.decision.as_of, monday.hash, "cli")

    clock("2024-06-05")
    tuesday = _tick(directory)
    assert tuesday.executed is not None
    assert tuesday.positions == {"AAPL": 500}
    assert ledger.approval() is None

    clock("2024-06-06")
    redone = redo(
        directory,
        FakeDataClient(SERIES),
        build_fund=lambda fund_spec: Fund(
            fund_spec,
            models={"solo": [FakeAnalyst("a", {"AAPL": -1})]},
        ),
    )

    assert redone.executed is not None
    assert redone.executed.execution_as_of == tuesday.session
    assert redone.positions == tuesday.positions
    tick_events = [event for event in ledger.events() if event["kind"] == "tick"]
    assert tick_events[-1]["approval_verdict"] == "approve"
    assert tick_events[-1]["decision_as_of"] == monday.decision.as_of
    assert tick_events[-1]["decision_hash"] == monday.hash


@pytest.mark.parametrize("verdict", ["approve", "reject"])
def test_redo_replays_consumed_approval_when_later_mailbox_cannot_be_removed(tmp_path, clock, SPEC, monkeypatch, verdict):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval(verdict, first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    assert (second.executed is not None) is (verdict == "approve")
    assert second.decision is not None
    ledger.set_approval("approve", second.decision.as_of, second.hash, "cli")
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("synthetic mailbox unlink failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)
    redone = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert (redone.executed is not None) is (verdict == "approve")
    if redone.executed is not None:
        assert redone.executed.execution_as_of == second.session
    assert redone.positions == second.positions
    assert ledger.approval()["decision_hash"] == second.hash


def test_redo_requires_consumed_approval_evidence_before_rewinding(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    assert second.executed is not None
    events = [event for event in ledger.events() if not (event["kind"] == "tick" and event["session"] == second.session)]
    ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    book = (directory / "broker.json").read_bytes()

    with pytest.raises(LedgerError, match="redo consumed approval is unavailable"):
        redo(directory, FakeDataClient(SERIES), build_fund=lambda _spec: pytest.fail("provider work started"))

    assert ledger.latest().hash == second.hash
    assert (directory / "broker.json").read_bytes() == book
    assert not (directory / "ledger" / "superseded").exists()


def test_redo_does_not_drop_an_incompletely_audited_consumed_rejection(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("reject", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    assert second.executed is None
    events = [event for event in ledger.events() if not (event["kind"] == "tick" and event["session"] == second.session)]
    ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    book = (directory / "broker.json").read_bytes()

    with pytest.raises(LedgerError, match="redo consumed approval is unavailable"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert ledger.latest().hash == second.hash
    assert (directory / "broker.json").read_bytes() == book
    assert not (directory / "ledger" / "superseded").exists()


def test_redo_replays_legacy_consumed_approval_without_an_identifier(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    events = [event for event in ledger.events() if event["kind"] != "consume"]
    for event in events:
        event.pop("approval_id", None)
    ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    redone = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert redone.executed is not None
    assert redone.positions == second.positions


@pytest.mark.parametrize("verdict", ["approve", "reject", None])
def test_consumption_is_synced_before_provider_or_broker_effects(tmp_path, clock, SPEC, monkeypatch, verdict):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    if verdict is not None:
        ledger.set_approval(verdict, first.decision.as_of, first.hash, "cli")
    synced = []
    advance = paper_tick_module.advance

    if os.name == "nt":
        append = root_module._windows_append_handle

        def observe_append(handle, data, *, durable):
            result = append(handle, data, durable=durable)
            if durable:
                synced.append(handle)
            return result

        monkeypatch.setattr(root_module, "_windows_append_handle", observe_append)
    else:
        fsync = os.fsync

        def observe_sync(fd):
            result = fsync(fd)
            synced.append(fd)
            return result

        monkeypatch.setattr(os, "fsync", observe_sync)

    def require_sync_before_advance(*args, **kwargs):
        assert synced, "approval consumption was not synced before effects"
        assert ledger.events()[-1]["kind"] == ("expire" if verdict is None else "consume")
        return advance(*args, **kwargs)

    monkeypatch.setattr(paper_tick_module, "advance", require_sync_before_advance)
    clock("2024-06-05")
    assert (_tick(directory).executed is not None) is (verdict == "approve")


@pytest.mark.parametrize("verdict", ["approve", "reject", None])
def test_failed_consumption_sync_halts_before_effects(tmp_path, clock, SPEC, monkeypatch, verdict):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    if verdict is not None:
        ledger.set_approval(verdict, first.decision.as_of, first.hash, "cli")
    book = (directory / "broker.json").read_bytes()

    if os.name == "nt":
        append = root_module._windows_append_handle

        def fail_sync(handle, data, *, durable):
            if durable:
                append(handle, data, durable=False)
                raise OSError("synthetic event sync failure")
            return append(handle, data, durable=durable)

        monkeypatch.setattr(root_module, "_windows_append_handle", fail_sync)
    else:

        def fail_sync(_fd):
            raise OSError("synthetic event sync failure")

        monkeypatch.setattr(os, "fsync", fail_sync)
    clock("2024-06-05")
    with pytest.raises(OSError, match="synthetic event sync failure"):
        tick(directory, FakeDataClient(SERIES), build_fund=lambda _spec: pytest.fail("fund was constructed"))

    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book


def test_busy_audit_admission_before_consumption_does_not_halt(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime import admission as admission_module

    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    before_book = (directory / "broker.json").read_bytes()
    before_events = ledger.events()
    resolved = Event()
    continue_tick = Event()
    errors = []
    original_resolve = Ledger.resolve_approval

    def pause_after_resolving(self, *args, **kwargs):
        approval = original_resolve(self, *args, **kwargs)
        if current_thread().name == "audit-busy-tick":
            resolved.set()
            if not continue_tick.wait(timeout=10):
                raise TimeoutError("test did not release approval resolution")
        return approval

    def run_tick():
        try:
            _tick(directory)
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(Ledger, "resolve_approval", pause_after_resolving)
    monkeypatch.setattr(admission_module, "MAX_CONTROL_WAIT_SECONDS", 0.1)
    clock("2024-06-05")
    worker = Thread(target=run_tick, name="audit-busy-tick")
    worker.start()
    try:
        assert resolved.wait(timeout=10), errors
        with admission_module.paper_audit_transition(directory, "alpha"):
            continue_tick.set()
            worker.join(timeout=10)
            assert not worker.is_alive()
    finally:
        continue_tick.set()
        worker.join(timeout=10)

    assert ledger.halted() is None
    assert ledger.sessions() == [first.session]
    assert ledger.events() == before_events
    assert (directory / "broker.json").read_bytes() == before_book
    assert len(errors) == 1 and isinstance(errors[0], admission_module.PaperPreflightBusy)


def test_audit_failure_after_consumption_admission_still_halts(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.admission import WriterConflict
    from hedge_fund.runtime.root import RootContext

    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    original_append = RootContext.append_bytes
    failed = False

    def fail_inside_audit(root, relative, data, *args, **kwargs):
        nonlocal failed
        if Path(relative).name == "events.jsonl" and not failed:
            failed = True
            raise WriterConflict("synthetic failure after audit admission")
        return original_append(root, relative, data, *args, **kwargs)

    monkeypatch.setattr(RootContext, "append_bytes", fail_inside_audit)
    clock("2024-06-05")
    with pytest.raises(WriterConflict, match="after audit admission"):
        _tick(directory)

    assert failed
    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.sessions() == [first.session]


def test_unfinished_consumption_requires_reconciliation_before_retry(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    approval = ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    ledger.log_event(
        "consume",
        decision_as_of=first.decision.as_of,
        decision_hash=first.hash,
        approval_verdict="approve",
        approval_by="cli",
        approval_id=approval["approval_id"],
        session="2024-06-04",
        durable=True,
    )
    book = (directory / "broker.json").read_bytes()
    clock("2024-06-05")

    with pytest.raises(LedgerError, match="consumption is incomplete"):
        tick(directory, FakeDataClient(SERIES), build_fund=lambda _spec: pytest.fail("fund was constructed"))

    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book


def test_redo_cannot_expire_an_unfinished_consumption(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    approval = ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    ledger.log_event(
        "consume",
        decision_as_of=first.decision.as_of,
        decision_hash=first.hash,
        approval_verdict="approve",
        approval_by="cli",
        approval_id=approval["approval_id"],
        session="2024-06-05",
        durable=True,
    )
    book = (directory / "broker.json").read_bytes()

    with pytest.raises(LedgerError, match="consumption is incomplete"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    relevant = [event for event in ledger.events() if event.get("decision_hash") == first.hash]
    assert relevant[-1]["kind"] == "consume"
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book
    assert not (directory / "ledger" / "superseded").exists()


def test_unfinished_consumption_denies_before_due_session_data(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    approval = ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    ledger.log_event(
        "consume",
        decision_as_of=first.decision.as_of,
        decision_hash=first.hash,
        approval_verdict="approve",
        approval_by="cli",
        approval_id=approval["approval_id"],
        session="2024-06-05",
        durable=True,
    )

    class NoPreflightData(FakeDataClient):
        def get_prices(self, *_args, **_kwargs):
            pytest.fail("unfinished consumption reached the data provider")

    clock("2024-06-05")
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        tick(directory, NoPreflightData(SERIES), build_fund=build_fund)
    assert ledger.halted() == "approval journal requires reconciliation"


@pytest.mark.parametrize("verdict", ["approve", "reject"])
@pytest.mark.parametrize("rebalance", ["daily", "weekly"])
def test_unfinished_consumption_after_ledger_advance_blocks_next_work(tmp_path, clock, SPEC, verdict, rebalance):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": rebalance})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval(verdict, first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    assert (second.decision is not None) is (rebalance == "daily")
    events = [event for event in ledger.events() if not (event["kind"] == "tick" and event["session"] == second.session)]
    ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    assert any(event["kind"] == "consume" and event["session"] == second.session for event in events)
    book = (directory / "broker.json").read_bytes()

    class NoPreflightData(FakeDataClient):
        def get_prices(self, *_args, **_kwargs):
            pytest.fail("unfinished consumption reached the data provider")

    clock("2024-06-06")
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        tick(directory, NoPreflightData(SERIES), build_fund=build_fund)

    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.latest().hash == second.hash
    assert (directory / "broker.json").read_bytes() == book


def test_explicit_session_retry_does_not_hide_unfinished_consumption(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    events = [event for event in ledger.events() if not (event["kind"] == "tick" and event["session"] == second.session)]
    ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    class NoPreflightData(FakeDataClient):
        def get_prices(self, *_args, **_kwargs):
            pytest.fail("explicit retry reached a data provider")

    with pytest.raises(LedgerError, match="consumption is incomplete"):
        _tick(directory, session=second.session, data=NoPreflightData(SERIES))
    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.latest().hash == second.hash


def test_standalone_retry_does_not_halt_a_live_tick(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.admission import WriterConflict

    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    entered = Event()
    proceed = Event()
    results = []
    errors = []
    advance = paper_tick_module.advance

    def blocked_advance(*args, **kwargs):
        entered.set()
        if not proceed.wait(10):
            raise AssertionError("test did not release the active tick")
        return advance(*args, **kwargs)

    def run_tick():
        try:
            results.append(_tick(directory))
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(paper_tick_module, "advance", blocked_advance)
    worker = Thread(target=run_tick, daemon=True)
    worker.start()
    try:
        assert entered.wait(10)
        with pytest.raises(WriterConflict):
            _tick(directory, session=first.session)
        assert ledger.halted() is None
    finally:
        proceed.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert errors == []
    assert len(results) == 1
    assert ledger.halted() is None


def test_standalone_execution_lock_blocks_another_process_but_not_halt(tmp_path, clock, SPEC, owned_test_process):
    from hedge_fund.runtime.admission import paper_execution_transition

    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    script = f"""
from pathlib import Path
from hedge_fund.paper.ledger import Ledger
from hedge_fund.runtime.admission import WriterConflict, paper_execution_transition

directory = Path({str(directory)!r})
try:
    with paper_execution_transition(directory, "alpha"):
        raise AssertionError("concurrent execution was admitted")
except WriterConflict:
    pass
Ledger(directory).halt("synthetic emergency")
"""
    with paper_execution_transition(directory, directory.name):
        child = owned_test_process(script)
        assert child.wait(timeout=20) == 0
        assert Ledger(directory).halted() == "synthetic emergency"

    child = owned_test_process(
        f"""
from pathlib import Path
from hedge_fund.runtime.admission import paper_execution_transition
with paper_execution_transition(Path({str(directory)!r}), "alpha"):
    pass
"""
    )
    assert child.wait(timeout=20) == 0


@pytest.mark.parametrize("transition", ["publication", "redo"])
def test_explicit_retry_rechecks_transition_markers_under_control(tmp_path, clock, SPEC, monkeypatch, transition):
    from hedge_fund.runtime import admission

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    control = admission.paper_control_transition
    injected = False

    @contextmanager
    def interrupted_before_control(path, identity):
        nonlocal injected
        if not injected:
            injected = True
            with control(path, identity):
                if transition == "publication":
                    ledger._write_approval_publication("a" * 32, "pending")
                else:
                    ledger.begin_redo(first)
        with control(path, identity):
            yield

    monkeypatch.setattr(admission, "paper_control_transition", interrupted_before_control)
    expected = "publication is incomplete" if transition == "publication" else "interrupted redo"
    with pytest.raises(LedgerError, match=expected):
        _tick(directory, session=first.session)
    assert injected
    assert ledger.halted() == "approval journal requires reconciliation"


def test_explicit_retry_waits_for_live_publication(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime import admission

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    control = admission.paper_control_transition
    pending = Event()
    attempting = Event()
    release = Event()
    finished = Event()
    results = []
    errors = []

    @contextmanager
    def observe_retry_control(path, identity):
        if current_thread().name == "explicit-retry":
            attempting.set()
        with control(path, identity):
            yield

    def publish():
        try:
            with control(directory, directory.name):
                ledger._write_approval_publication("a" * 32, "pending")
                pending.set()
                if not release.wait(10):
                    raise TimeoutError("test did not release publication")
                ledger._write_approval_publication("a" * 32, "committed")
        except BaseException as exc:
            errors.append(exc)

    def retry():
        try:
            results.append(_tick(directory, session=first.session))
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    monkeypatch.setattr(admission, "paper_control_transition", observe_retry_control)
    publisher = Thread(target=publish, daemon=True)
    retrier = Thread(target=retry, name="explicit-retry", daemon=True)
    publisher.start()
    try:
        assert pending.wait(10)
        retrier.start()
        if not attempting.wait(5):
            assert not finished.is_set(), f"retry exited before control admission: {errors!r}"
            pytest.fail("retry did not attempt control admission")
        assert not finished.is_set()
    finally:
        release.set()
        publisher.join(timeout=10)
        if retrier.ident is not None:
            retrier.join(timeout=10)
    assert not publisher.is_alive()
    assert not retrier.is_alive()
    assert errors == []
    assert [record.hash for record in results] == [first.hash]
    assert ledger.halted() is None


@pytest.mark.parametrize("operation", ["tick", "redo", "run"])
def test_new_work_waits_for_live_approval_publication(tmp_path, clock, SPEC, monkeypatch, operation):
    from hedge_fund.runtime import admission

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    clock("2024-06-05")
    pending = Event()
    start_publisher = Event()
    attempting = Event()
    release = Event()
    finished = Event()
    failures = []
    records = []
    control = admission.paper_control_transition
    next_session = paper_tick_module.next_session

    @contextmanager
    def observe_control(path, identity):
        if current_thread().name == "new-paper-work" and pending.is_set():
            attempting.set()
        with control(path, identity):
            yield

    def publish():
        try:
            if not start_publisher.wait(timeout=10):
                raise TimeoutError("test did not start publisher")
            with control(directory, directory.name):
                ledger._write_approval_publication("a" * 32, "pending")
                pending.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release publisher")
                ledger._write_approval_publication("a" * 32, "committed")
        except BaseException as exc:
            failures.append(exc)

    def delayed_due(*args, **kwargs):
        start_publisher.set()
        if not pending.wait(timeout=10):
            raise TimeoutError("publisher did not reach pending state")
        return next_session(*args, **kwargs)

    def work():
        try:
            if operation == "redo":
                records.append(redo(directory, FakeDataClient(SERIES), build_fund=build_fund))
            else:
                records.append(_tick(directory))
        except BaseException as exc:
            failures.append(exc)
        finally:
            finished.set()

    monkeypatch.setattr(admission, "paper_control_transition", observe_control)
    if operation == "run":
        monkeypatch.setattr(paper_tick_module, "next_session", delayed_due)
    publisher = Thread(target=publish, name="live-publisher")
    worker = Thread(target=work, name="new-paper-work")
    publisher.start()
    try:
        if operation != "run":
            start_publisher.set()
            assert pending.wait(timeout=10), failures
        worker.start()
        assert attempting.wait(timeout=3), f"work exited before control admission: {failures!r}"
        assert not finished.is_set()
    finally:
        release.set()
        publisher.join(timeout=10)
        if worker.ident is not None:
            worker.join(timeout=10)
    assert not publisher.is_alive() and not worker.is_alive()
    assert failures == []
    assert len(records) == 1
    assert ledger.halted() is None
    if operation == "tick":
        assert records[0].session > first.session


def test_owned_child_exit_after_append_blocks_new_work(tmp_path, clock, SPEC, owned_test_process):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    script = f"""
import os
from datetime import datetime
from pathlib import Path
from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
from hedge_fund.data import sessions
from hedge_fund.fund import Fund
from hedge_fund.paper import tick
from hedge_fund.paper.ledger import Ledger
from hedge_fund.signals import ALPHA_MODEL_REGISTRY

class Clock:
    @staticmethod
    def now(tz):
        return datetime(2024, 6, 5, 12, tzinfo=tz)

sessions.datetime = Clock
ALPHA_MODEL_REGISTRY["a"] = FakeAnalyst
log_event = Ledger.log_event
def exit_before_tick_audit(self, kind, **fields):
    if kind == "tick":
        os._exit(73)
    return log_event(self, kind, **fields)
Ledger.log_event = exit_before_tick_audit
def build_fund(spec):
    return Fund(spec, models={{"solo": [FakeAnalyst("a", {{"AAPL": 1}})]}})
try:
    tick(Path({str(directory)!r}), FakeDataClient(SERIES), build_fund=build_fund)
except BaseException as exc:
    Path({str(directory)!r}, "child-error.txt").write_text(f"{{type(exc).__name__}}: {{exc}}", encoding="utf-8")
    raise
"""
    child = owned_test_process(script)
    result = child.wait(timeout=20)
    diagnostic = directory / "child-error.txt"
    assert result == 73, diagnostic.read_text(encoding="utf-8") if diagnostic.exists() else f"child exit {result}"
    second = ledger.latest()
    assert second.hash != first.hash
    assert second.decision is not None
    assert any(event["kind"] == "consume" and event["session"] == second.session for event in ledger.events())
    assert not any(event["kind"] == "tick" and event["session"] == second.session for event in ledger.events())

    class NoPreflightData(FakeDataClient):
        def get_prices(self, *_args, **_kwargs):
            pytest.fail("unfinished consumption reached the data provider")

    clock("2024-06-06")
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        tick(directory, NoPreflightData(SERIES), build_fund=build_fund)
    assert ledger.halted() == "approval journal requires reconciliation"
    assert ledger.latest().hash == second.hash

    from hedge_fund.runtime.reconciliation import (
        build_tick_intent_reconciliation_snapshot,
        TickIntentReconciliationConfirmation,
    )

    snapshot = build_tick_intent_reconciliation_snapshot(
        directory,
        load_deployed(directory),
        ledger,
        ledger.replay(spec.capital, full=True),
        ledger.latest(),
    )
    assert snapshot.preview.required is True
    assert snapshot.preview.recoverable is True
    assert snapshot.preview.reason == "ready"
    assert snapshot.preview.expected_head == first.hash
    assert snapshot.preview.current_head == second.hash
    assert snapshot.preview.head_matches_intent is True
    assert snapshot.preview.book_matches_ledger is True

    confirmation = TickIntentReconciliationConfirmation(
        request_id="recover-owned-child-exit",
        intent_request_id=None,
        intent_digest=None,
        preview_digest=snapshot.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    receipt_id = ledger.reconcile_tick_intent(spec.capital, confirmation=confirmation, operator="cli")
    resolved = next(event for event in ledger.events() if event.get("kind") == "tick_intent_resolved")
    receipt = resolved["receipt"]

    assert receipt_id == receipt["receipt_id"]
    assert receipt["expected_head"] == first.hash
    assert receipt["current_head"] == second.hash
    assert receipt["broker_book_sha256"] == snapshot.preview.broker_book_sha256
    ledger.resume(spec.capital, approval_required=True)
    assert ledger.halted() is None
    assert ledger.unresolved_approval_consumption_events(allow_unresolved_corruption=True) == ()
    assert ledger.unresolved_recovery_state().required is False


def test_interrupted_redo_blocks_new_work_after_owned_child_exit(tmp_path, clock, SPEC, owned_test_process):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    script = f"""
import os
from pathlib import Path
from hedge_fund.backtesting.test_fund import FakeAnalyst
from hedge_fund.paper import redo
from hedge_fund.signals import ALPHA_MODEL_REGISTRY
ALPHA_MODEL_REGISTRY["a"] = FakeAnalyst
redo(Path({str(directory)!r}), None, on_rewind=lambda _record: os._exit(73))
"""
    child = owned_test_process(script)
    assert child.wait(timeout=20) == 73
    assert ledger.latest() is None
    assert json.loads(ledger.redo_state_path.read_text(encoding="utf-8"))["state"] == "pending"

    class NoPreflightData(FakeDataClient):
        def get_prices(self, *_args, **_kwargs):
            pytest.fail("interrupted redo reached the data provider")

    clock("2024-06-05")
    with pytest.raises(LedgerError, match="interrupted redo"):
        tick(directory, NoPreflightData(SERIES), build_fund=build_fund)
    with pytest.raises(LedgerError, match="interrupted redo"):
        redo(directory, NoPreflightData(SERIES), build_fund=build_fund)
    assert ledger.latest() is None
    superseded = list((directory / "ledger" / "superseded").glob(f"{first.session}.{first.hash[:12]}*.json"))
    assert len(superseded) == 1


def test_redo_completion_failure_keeps_recovery_guard(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.paper import ledger as ledger_module

    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    _tick(directory)
    write_atomic = ledger_module.write_atomic

    def fail_completion(path, text, **kwargs):
        if path == ledger.redo_state_path and json.loads(text)["state"] == "completed":
            raise OSError("synthetic redo completion failure")
        return write_atomic(path, text, **kwargs)

    monkeypatch.setattr(ledger_module, "write_atomic", fail_completion)
    with pytest.raises(OSError, match="synthetic redo completion failure"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert json.loads(ledger.redo_state_path.read_text(encoding="utf-8"))["state"] == "pending"
    assert ledger.halted() == "redo failed after rewind"
    with pytest.raises(LedgerError, match="interrupted redo"):
        _tick(directory)


def test_redo_failure_with_unavailable_halt_requires_reconciliation_and_keeps_cause(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.paper.tick import PaperReconciliationRequired

    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    _tick(directory)
    original = OSError("synthetic redo failure after rewind")

    def fail_after_rewind(_record):
        raise original

    def fail_halt(self, reason):
        raise OSError("synthetic emergency halt failure")

    monkeypatch.setattr(Ledger, "halt", fail_halt)
    with pytest.raises(PaperReconciliationRequired, match="offline reconciliation is required") as raised:
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund, on_rewind=fail_after_rewind)

    assert raised.value.__cause__ is original


def test_successful_redo_records_completion_and_allows_next_tick(tmp_path, clock, SPEC):
    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    original = _tick(directory)

    redone = redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    marker = json.loads(ledger.redo_state_path.read_text(encoding="utf-8"))
    assert marker["state"] == "completed"
    assert marker["source_hash"] == original.hash
    assert marker["result_hash"] == redone.hash
    clock("2024-06-05")
    assert _tick(directory).session == "2024-06-04"


@pytest.mark.parametrize(
    "contents",
    [
        "{invalid",
        '{"version": 1, "state": [], "redo_id": "' + "a" * 32 + '", "source_session": "2024-06-03", "source_hash": "' + "b" * 64 + '", "result_hash": null}',
    ],
)
def test_invalid_redo_guard_blocks_new_work(tmp_path, clock, SPEC, contents):
    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    _tick(directory)
    ledger.redo_state_path.write_text(contents, encoding="utf-8")

    with pytest.raises(LedgerError, match="redo state"):
        _tick(directory)
    with pytest.raises(LedgerError, match="redo state"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)


def test_halt_after_consumption_stops_execution_before_advance(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    book = (directory / "broker.json").read_bytes()
    build_broker = paper_tick_module.build_broker

    def halt_while_initializing(*args, **kwargs):
        broker = build_broker(*args, **kwargs)
        ledger.halt("synthetic emergency")
        return broker

    monkeypatch.setattr(paper_tick_module, "build_broker", halt_while_initializing)
    clock("2024-06-05")
    with pytest.raises(FundHalted):
        _tick(directory)

    assert ledger.halted() == "synthetic emergency"
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book


@pytest.mark.parametrize("halt_at", ["advance", "order"])
def test_halt_before_effect_admission_stops_execution(tmp_path, clock, SPEC, monkeypatch, halt_at):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    book = (directory / "broker.json").read_bytes()
    advance = paper_tick_module.advance

    def halt_at_boundary(*args, **kwargs):
        if halt_at == "advance":
            ledger.halt("synthetic emergency")
        else:
            check = kwargs["before_effect"]
            calls = 0

            def halt_before_order():
                nonlocal calls
                calls += 1
                if calls == 2:
                    ledger.halt("synthetic emergency")
                check()

            kwargs["before_effect"] = halt_before_order
        return advance(*args, **kwargs)

    monkeypatch.setattr(paper_tick_module, "advance", halt_at_boundary)
    clock("2024-06-05")
    with pytest.raises(FundHalted):
        _tick(directory)
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book


def test_halt_after_first_order_prevents_second_order(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True})
    client = FakeDataClient({**SERIES, "MSFT": SERIES["AAPL"]})
    directory = deploy("alpha", spec, ["AAPL", "MSFT"], root=tmp_path)
    ledger = Ledger(directory)

    def build_two_ticker_fund(selected):
        return Fund(selected, models={"solo": [FakeAnalyst("a", {"AAPL": 0.5, "MSFT": 0.5})]})

    clock("2024-06-04")
    first = tick(directory, client, build_fund=build_two_ticker_fund)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    place_order = PaperBroker.place_order
    submitted = []

    def halt_after_fill(broker, order):
        fill = place_order(broker, order)
        submitted.append(order.ticker)
        ledger.halt("synthetic emergency")
        return fill

    monkeypatch.setattr(PaperBroker, "place_order", halt_after_fill)
    clock("2024-06-05")
    with pytest.raises(FundHalted):
        tick(directory, client, build_fund=build_two_ticker_fund)
    assert len(submitted) == 1
    assert ledger.halted() == "synthetic emergency"
    assert ledger.latest().hash == first.hash
    assert ledger._latest_approval_event(first.decision.as_of, first.hash, strict=True)["kind"] == "consume"


def test_legacy_halt_after_fill_journals_failure_bound_to_transmitted_fills(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        build_reconciliation_snapshot,
        failure_digest,
    )

    spec = SPEC.model_copy(update={"approval_required": True})
    client = FakeDataClient({**SERIES, "MSFT": SERIES["AAPL"]})
    directory = deploy("alpha", spec, ["AAPL", "MSFT"], root=tmp_path)
    ledger = Ledger(directory)

    def build_two_ticker_fund(selected):
        return Fund(selected, models={"solo": [FakeAnalyst("a", {"AAPL": 0.5, "MSFT": 0.5})]})

    clock("2024-06-04")
    first = tick(directory, client, build_fund=build_two_ticker_fund)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    place_order = PaperBroker.place_order
    transmitted_fills = []

    def halt_after_fill(broker, order):
        fill = place_order(broker, order)
        transmitted_fills.append(
            {
                "order": order.model_dump(mode="json"),
                "fill": fill.model_dump(mode="json"),
            }
        )
        ledger.halt("synthetic emergency")
        return fill

    monkeypatch.setattr(PaperBroker, "place_order", halt_after_fill)
    clock("2024-06-05")
    with pytest.raises(FundHalted):
        tick(directory, client, build_fund=build_two_ticker_fund)

    failure = next(event for event in ledger.events() if event["kind"] == "tick_failed")
    assert len(transmitted_fills) == 1
    assert "request_id" not in failure
    assert failure["session"] == "2024-06-04"
    assert failure["expected_head"] == first.hash
    assert failure["transmitted_fills"] == transmitted_fills
    snapshot = build_reconciliation_snapshot(directory, load_deployed(directory), ledger, ledger.replay(spec.capital, full=True), ledger.latest())
    assert snapshot.failure_event == failure
    assert snapshot.preview.required is True
    assert snapshot.preview.failure_id == failure_digest(failure)
    assert snapshot.preview.recoverable is False


def test_legacy_zero_effect_halt_does_not_require_reconciliation(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.reconciliation import build_reconciliation_snapshot

    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)

    def halt_before_effect(*_args, **_kwargs):
        ledger.halt("synthetic pre-effect halt")
        raise FundHalted("synthetic pre-effect halt")

    monkeypatch.setattr(paper_tick_module, "advance", halt_before_effect)
    with pytest.raises(FundHalted, match="synthetic pre-effect halt"):
        _tick(directory)

    assert not any(event["kind"] in {"tick_failed", "tick_aborted"} for event in ledger.events())
    snapshot = build_reconciliation_snapshot(directory, load_deployed(directory), ledger, ledger.replay(SPEC.capital, full=True), ledger.latest())
    assert snapshot.preview.required is False
    assert snapshot.failure_event is None


def test_halt_before_refresh_prevents_new_assessment(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.pipeline import stages

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-08")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    assert first.session == "2024-06-07"
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    advance = paper_tick_module.advance

    def halt_at_refresh(*args, **kwargs):
        check = kwargs["before_effect"]
        calls = 0

        def guarded():
            nonlocal calls
            calls += 1
            if calls == 2:
                ledger.halt("synthetic emergency")
            check()

        kwargs["before_effect"] = guarded
        return advance(*args, **kwargs)

    def no_refresh(*_args, **_kwargs):
        pytest.fail("assessment started after Halt")

    monkeypatch.setattr(paper_tick_module, "advance", halt_at_refresh)
    monkeypatch.setattr(stages, "assess_fund", no_refresh)
    clock("2024-06-11")
    with pytest.raises(FundHalted):
        _tick(directory)
    assert ledger.latest().hash == first.hash


def test_standalone_verdict_cannot_change_during_consumption(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.admission import AdmissionError

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    read_verdict = Event()
    release = Event()
    failures = []
    records = []
    resolve = Ledger.resolve_approval

    def pause_after_resolution(current, *args, **kwargs):
        result = resolve(current, *args, **kwargs)
        if current.directory == directory and current_thread().name == "standalone-tick":
            read_verdict.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release standalone tick")
        return result

    def run_tick():
        try:
            records.append(_tick(directory))
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(Ledger, "resolve_approval", pause_after_resolution)
    clock("2024-06-05")
    worker = Thread(target=run_tick, name="standalone-tick")
    worker.start()
    try:
        assert read_verdict.wait(timeout=10), failures
        try:
            ledger.set_approval("reject", first.decision.as_of, first.hash, "cli")
            rejection_accepted = True
        except AdmissionError:
            rejection_accepted = False
    finally:
        release.set()
        worker.join(timeout=15)

    assert not worker.is_alive()
    assert failures == []
    assert len(records) == 1
    assert not rejection_accepted or records[0].executed is None


def test_standalone_control_lock_blocks_a_separate_process(tmp_path, clock, SPEC, owned_test_process):
    from hedge_fund.runtime.admission import WriterConflict

    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    locked = tmp_path / "child-locked"
    release = tmp_path / "release-child"
    failure = tmp_path / "child-failure"
    script = f"""
import time
from pathlib import Path
from hedge_fund.runtime.admission import paper_control_transition

directory = Path({str(directory)!r})
locked = Path({str(locked)!r})
release = Path({str(release)!r})
failure = Path({str(failure)!r})
try:
    with paper_control_transition(directory, "alpha"):
        locked.write_text("locked", encoding="utf-8")
        deadline = time.monotonic() + 15
        while not release.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("parent did not release control")
            time.sleep(0.01)
except BaseException as exc:
    failure.write_text(type(exc).__name__ + ": " + str(exc), encoding="utf-8")
    raise
"""
    child = owned_test_process(script)
    try:
        deadline = time.monotonic() + 15
        while not locked.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert locked.exists(), failure.read_text(encoding="utf-8") if failure.exists() else "child did not lock"
        with pytest.raises(WriterConflict):
            ledger.set_approval("reject", first.decision.as_of, first.hash, "cli")
    finally:
        release.write_text("release", encoding="utf-8")
    assert child.wait(timeout=15) == 0, failure.read_text(encoding="utf-8") if failure.exists() else "child failed"
    assert ledger.approval()["verdict"] == "approve"


@pytest.mark.parametrize("failure", ["broker", "fund"])
def test_initialization_failure_after_consumption_halts_before_retry(tmp_path, clock, SPEC, monkeypatch, failure):
    spec = SPEC.model_copy(update={"approval_required": True})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    book = (directory / "broker.json").read_bytes()

    def fail_initialization(*_args, **_kwargs):
        raise OSError("synthetic initialization failure")

    if failure == "broker":
        monkeypatch.setattr(paper_tick_module, "build_broker", fail_initialization)
    clock("2024-06-05")
    with pytest.raises(OSError, match="synthetic initialization failure"):
        tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=fail_initialization if failure == "fund" else build_fund,
        )

    assert ledger.halted() is not None
    assert ledger.latest().hash == first.hash
    assert (directory / "broker.json").read_bytes() == book


@pytest.mark.parametrize("failure", ["restore", "redo-event"])
def test_redo_failure_after_rewind_halts_the_fund(tmp_path, clock, SPEC, monkeypatch, failure):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    ledger = Ledger(directory)
    first = _tick(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    clock("2024-06-05")
    second = _tick(directory)
    assert second.executed is not None
    log_event = Ledger.log_event

    def fail_restore(*_args, **_kwargs):
        raise OSError("synthetic redo failure")

    def fail_redo_event(current, kind, **fields):
        if kind == "redo":
            raise OSError("synthetic redo failure")
        return log_event(current, kind, **fields)

    if failure == "restore":
        monkeypatch.setattr(PaperBroker, "restore", fail_restore)
    else:
        monkeypatch.setattr(Ledger, "log_event", fail_redo_event)
    with pytest.raises(OSError, match="synthetic redo failure"):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)

    assert ledger.halted() is not None
    assert ledger.latest().hash == first.hash
    assert ledger.path(second.session).exists() is False


def test_gate_rejects_matching_verdict_without_trading(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    book_before = json.loads((directory / "broker.json").read_text())
    ledger = Ledger(directory)
    ledger.set_approval("reject", first.decision.as_of, first.hash, "tui")

    clock("2024-06-05")
    rejected = _tick(directory)

    assert rejected.executed is None
    assert rejected.decision is not None and rejected.decision.as_of == rejected.session
    assert json.loads((directory / "broker.json").read_text()) == book_before
    assert ledger.approval() is None
    assert [event["kind"] for event in ledger.events()] == ["tick", "reject", "consume", "reject", "tick"]
    assert ledger.events()[3]["consumed"] is True


def test_gate_ignores_and_clears_stale_approval(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", "2024-06-02", first.hash, "cli")

    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.executed is None
    assert skipped.decision is not None
    assert ledger.approval() is None
    expiry = next(event for event in ledger.events() if event["kind"] == "expire")
    assert expiry["decision_as_of"] == first.decision.as_of
    assert expiry["reason"] == "stale verdict"


def test_verdict_written_after_gate_read_cannot_authorize_replacement_decision(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    read_approval = Ledger.approval

    def write_after_read(current):
        approval = read_approval(current)
        if current.directory == directory and approval is None:
            current.set_approval("approve", first.decision.as_of, first.hash, "tui")
        return approval

    monkeypatch.setattr(Ledger, "approval", write_after_read)
    clock("2024-06-05")
    skipped = _tick(directory)

    assert skipped.session == "2024-06-04" and skipped.executed is None
    assert skipped.decision is not None
    assert ledger.approval()["decision_as_of"] == first.decision.as_of
    assert ledger.approval()["decision_hash"] == first.hash

    monkeypatch.setattr(Ledger, "approval", read_approval)
    clock("2024-06-06")
    next_session = _tick(directory)

    assert next_session.executed is None
    assert ledger.approval() is None
    expiry = ledger.events()[-2]
    assert expiry["kind"] == "expire"
    assert expiry["reason"] == "stale verdict"
    assert expiry["decision_hash"] == skipped.hash


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


def test_redo_request_id_replays_result_and_conflicts_on_changed_head(tmp_path, clock, SPEC):
    from hedge_fund.paper.ledger import PaperRequestConflict

    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    original = _tick(directory)
    build_calls = []

    def counted_build(spec):
        build_calls.append(True)
        return build_fund(spec)

    request = {
        "request_id": "cli-redo-alpha-001",
        "expected_head": original.hash,
    }
    record = redo(directory, FakeDataClient(SERIES), build_fund=counted_build, **request)
    replayed = redo(directory, FakeDataClient(SERIES), build_fund=counted_build, **request)

    assert replayed.hash == record.hash
    assert build_calls == [True]
    with pytest.raises(PaperRequestConflict, match="request identity conflicts"):
        redo(
            directory,
            FakeDataClient(SERIES),
            build_fund=counted_build,
            request_id=request["request_id"],
            expected_head="0" * 64,
        )


def test_redo_refuses_a_halted_fund_and_leaves_it_untouched(tmp_path, clock, SPEC):
    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    Ledger(directory).halt("looking into it")
    with pytest.raises(FundHalted):
        redo(directory, FakeDataClient(SERIES), build_fund=build_fund)
    assert Ledger(directory).latest() == first
    assert not (directory / "ledger" / "superseded").exists()


def test_failure_inside_advance_stays_halted_without_reconciliation_receipt(tmp_path, clock, SPEC, monkeypatch):
    clock("2024-06-05")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    with _owned_paper_lane(directory, "alpha"):
        _tick(directory)  # 06-04, decision made
    clock("2024-06-06")

    def fail_after_effect_boundary(*_args, **kwargs):
        kwargs["before_order"]()
        kwargs["before_effect"]()
        raise ValueError("synthetic post-effect failure")

    monkeypatch.setattr(paper_tick_module, "advance", fail_after_effect_boundary)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(ValueError, match="synthetic post-effect failure"):
            _tick(directory)
    ledger = Ledger(directory)
    assert ledger.halted().startswith("tick 2024-06-05 failed: ValueError")
    assert [e["kind"] for e in ledger.events()] == ["tick", "tick_failed", "halt"]
    assert ledger.sessions() == ["2024-06-04"]
    control_before = ledger.control_path.read_bytes()
    events_before = ledger.events_path.read_bytes()
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(LedgerError, match="verified reconciliation receipt"):
            ledger.resume(SPEC.capital)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(FundHalted):
            _tick(directory)
    assert ledger.sessions() == ["2024-06-04"]
    assert ledger.control_path.read_bytes() == control_before
    assert ledger.events_path.read_bytes() == events_before


def test_pre_effect_intent_execution_error_aborts_and_same_identity_retries(tmp_path, clock, SPEC):
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    clock("2024-06-05")
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    clock("2024-06-06")
    series = {ticker: dict(values) for ticker, values in SERIES.items()}
    del series["AAPL"]["2024-06-05"]
    ledger = Ledger(directory)
    request_id = "pre-effect-missing-price"

    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(ValueError, match="AAPL: missing close on 2024-06-05"):
            tick(
                directory,
                FakeDataClient(series),
                build_fund=build_fund,
                expected_head=first.hash,
                request_id=request_id,
            )

    aborted = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id]
    assert len(aborted) == 1
    assert aborted[0]["no_effects"] is True
    assert not any(event.get("kind") == "tick_failed" and event.get("request_id") == request_id for event in ledger.events())
    assert ledger.halted() is None
    assert ledger.sessions() == ["2024-06-04"]

    with _owned_paper_lane(directory, "alpha"):
        record = tick(
            directory,
            FakeDataClient(SERIES),
            build_fund=build_fund,
            expected_head=first.hash,
            request_id=request_id,
        )

    assert record.session == "2024-06-05"
    assert ledger.halted() is None


def test_pre_effect_intent_abort_binds_manual_operation_and_capture(tmp_path, clock, SPEC):
    clock("2024-06-05")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    clock("2024-06-06")
    series = {ticker: dict(values) for ticker, values in SERIES.items()}
    del series["AAPL"]["2024-06-05"]
    request_id = "manual-pre-effect-abort"

    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(ValueError, match="AAPL: missing close on 2024-06-05"):
            tick(
                directory,
                FakeDataClient(series),
                build_fund=build_fund,
                expected_head=first.hash,
                operation_id="a" * 32,
                request_id=request_id,
                capture_id="b" * 32,
                capture_digest="c" * 64,
            )

    aborted = next(event for event in Ledger(directory).events() if event.get("kind") == "tick_aborted" and event.get("request_id") == request_id)
    assert aborted["expected_head"] == first.hash
    assert aborted["operation_id"] == "a" * 32
    assert aborted["capture_id"] == "b" * 32
    assert aborted["capture_digest"] == "c" * 64
    assert aborted["no_effects"] is True


def test_tick_failure_event_binds_manual_operation_and_capture(tmp_path, clock, SPEC, monkeypatch):
    clock("2024-06-05")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    with _owned_paper_lane(directory, "alpha"):
        first = _tick(directory)
    clock("2024-06-06")

    def fail_after_effect_boundary(*_args, **kwargs):
        kwargs["before_order"]()
        kwargs["before_effect"]()
        raise ValueError("synthetic failure after effect boundary")

    monkeypatch.setattr(paper_tick_module, "advance", fail_after_effect_boundary)

    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(ValueError, match="synthetic failure after effect boundary"):
            tick(
                directory,
                FakeDataClient(SERIES),
                build_fund=build_fund,
                expected_head=first.hash,
                operation_id="a" * 32,
                request_id="web-tick-1",
                capture_id="b" * 32,
                capture_digest="c" * 64,
            )

    failure = next(event for event in Ledger(directory).events() if event["kind"] == "tick_failed")
    assert failure["expected_head"] == first.hash
    assert failure["operation_id"] == "a" * 32
    assert failure["request_id"] == "web-tick-1"
    assert failure["capture_id"] == "b" * 32
    assert failure["capture_digest"] == "c" * 64


def test_intent_outcome_lookup_failure_does_not_duplicate_tick_failure_or_block_recovery(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        build_reconciliation_snapshot,
        ReconciliationConfirmation,
    )

    clock("2024-06-04")
    directory = _deploy_owned_paper_test_fund(tmp_path, SPEC)
    ledger = Ledger(directory)
    original_run = paper_tick_module._run
    original_events = Ledger.events
    request_id = "single-failure-outcome"

    def write_failure_then_raise(*args, **kwargs):
        target_ledger = args[2]
        attempt = kwargs["operation_context"]
        target_ledger.log_event(
            "tick_failed",
            **attempt,
            session=args[4],
            error="synthetic failure already recorded",
            durable=True,
        )
        target_ledger.halt("synthetic failure already recorded")
        raise RuntimeError("synthetic failure already recorded")

    def fail_failure_observation(self):
        events = original_events(self)
        if any(event.get("kind") == "tick_failed" and event.get("request_id") == request_id for event in events):
            raise OSError("synthetic outcome lookup failure")
        return events

    monkeypatch.setattr(paper_tick_module, "_run", write_failure_then_raise)
    monkeypatch.setattr(Ledger, "events", fail_failure_observation)
    with _owned_paper_lane(directory, "alpha"):
        with pytest.raises(RuntimeError, match="synthetic failure already recorded"):
            tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                expected_head=None,
                build_fund=build_fund,
                request_id=request_id,
            )
    monkeypatch.setattr(paper_tick_module, "_run", original_run)
    monkeypatch.setattr(Ledger, "events", original_events)

    failures = [event for event in ledger.events() if event.get("kind") == "tick_failed" and event.get("request_id") == request_id]
    assert len(failures) == 1
    assert ledger.unresolved_tick_intents() == ()
    state = ledger.replay(SPEC.capital, full=True)
    preview = build_reconciliation_snapshot(
        directory,
        load_deployed(directory),
        ledger,
        state,
        ledger.latest(),
    )
    assert preview.preview.recoverable is True
    confirmation = ReconciliationConfirmation(
        request_id="resume-single-failure-outcome",
        failure_id=preview.preview.failure_id,
        preview_digest=preview.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    with _owned_paper_lane(directory, "alpha"):
        ledger.resume(
            SPEC.capital,
            reconciliation=confirmation.model_dump(mode="json"),
            request_id=confirmation.request_id,
            operator="cli",
        )
        record = tick(
            directory,
            FakeDataClient(SERIES),
            session="2024-06-03",
            expected_head=None,
            build_fund=build_fund,
            request_id="new-id-after-outcome-recovery",
        )
    assert record.session == "2024-06-03"
    assert ledger.halted() is None


def test_fill_then_append_failure_stays_halted_without_fabricated_ledger_success(tmp_path, clock, SPEC, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        build_reconciliation_snapshot,
        ReconciliationConfirmation,
    )

    clock("2024-06-05")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    original_append = Ledger.append

    def fail_append(self, record):
        raise OSError("synthetic append failure after fill")

    monkeypatch.setattr(Ledger, "append", fail_append)
    clock("2024-06-06")
    with pytest.raises(OSError, match="synthetic append failure after fill"):
        _tick(directory)
    monkeypatch.setattr(Ledger, "append", original_append)

    ledger = Ledger(directory)
    assert ledger.latest() == first
    assert ledger.sessions() == [first.session]
    assert PaperBroker(directory / "broker.json").positions()
    state = ledger.replay(SPEC.capital, full=True)
    preview = build_reconciliation_snapshot(directory, load_deployed(directory), ledger, state, ledger.latest())
    confirmation = ReconciliationConfirmation(
        request_id="recover-fill-1",
        failure_id=preview.preview.failure_id,
        preview_digest=preview.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )

    with pytest.raises(LedgerError, match="not reconcilable"):
        ledger.resume(SPEC.capital, reconciliation=confirmation, operator="web")

    assert ledger.halted() is not None
    assert ledger.sessions() == [first.session]
    assert not any(event["kind"] in {"reconciliation", "resume"} for event in ledger.events())


def test_gated_approval_survives_failed_advance_and_resume_denial(tmp_path, clock, SPEC, monkeypatch):
    spec = SPEC.model_copy(update={"approval_required": True, "rebalance": "daily"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory)
    ledger = Ledger(directory)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    verdict = ledger.approval()
    real_advance = paper_tick_module.advance

    def fail_advance(*args, **kwargs):
        raise ValueError("fixture advance failure")

    monkeypatch.setattr(paper_tick_module, "advance", fail_advance)
    clock("2024-06-05")
    with pytest.raises(ValueError, match="fixture advance failure"):
        _tick(directory)

    assert ledger.halted() is not None
    assert ledger.approval() == verdict
    assert ledger.sessions() == ["2024-06-03"]

    with pytest.raises(LedgerError, match="reconciliation"):
        ledger.resume(spec.capital, approval_required=True)
    monkeypatch.setattr(paper_tick_module, "advance", real_advance)
    with pytest.raises(FundHalted):
        _tick(directory)
    assert ledger.sessions() == ["2024-06-03"]
    assert ledger.approval() == verdict
    assert [event["kind"] for event in ledger.events()][-1] == "halt"


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


def _enrolled_paper_directory(root: Path, spec: FundSpec) -> Path:
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import enroll_fresh, record_ledger_head
    from hedge_fund.runtime.root import RootContext

    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy(
                    "alpha",
                    spec,
                    ["AAPL"],
                    root=root / "paper",
                )
            record_ledger_head(context, "alpha", admission=admission)
        finally:
            owner.close()
    return directory


def test_enrolled_deploy_requires_a_held_deployment_lane(tmp_path, SPEC):
    from hedge_fund.runtime.admission import AdmissionError
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "enrolled"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)

    with pytest.raises(AdmissionError, match="admission"):
        deploy("alpha", SPEC, ["AAPL"], root=root / "paper")

    assert not (root / "paper" / "alpha").exists()


def test_enrolled_tick_redo_and_ledger_writes_require_admission(tmp_path, SPEC):
    from hedge_fund.runtime.admission import AdmissionError

    directory = _enrolled_paper_directory(tmp_path / "enrolled", SPEC)
    ledger = Ledger(directory)
    control_before = ledger.control_path.read_bytes()

    with pytest.raises(AdmissionError, match="admission"):
        tick(directory, object())
    with pytest.raises(AdmissionError, match="admission"):
        redo(directory, object())
    with pytest.raises(LedgerError, match="admission"):
        ledger.append(object())
    with pytest.raises(LedgerError, match="admission"):
        ledger.halt("unadmitted")
    with pytest.raises(LedgerError, match="admission"):
        ledger.resume(1.0)
    with pytest.raises(LedgerError, match="admission"):
        ledger.set_approval("approve", "2024-06-03", "0" * 64, "cli")
    with pytest.raises(LedgerError, match="admission"):
        ledger.clear_approval()
    with pytest.raises(LedgerError, match="admission"):
        ledger.log_event("unadmitted")

    assert ledger.sessions() == []
    assert ledger.control_path.read_bytes() == control_before
    assert not ledger.events_path.exists()


def test_enrolled_tick_rejects_inventory_drift_before_data_access(tmp_path, SPEC):
    from hedge_fund.runtime.admission import (
        AdmissionCoordinator,
        AdmissionError,
        RootOwnerLease,
    )
    from hedge_fund.runtime.root import RootContext

    directory = _enrolled_paper_directory(tmp_path / "enrolled", SPEC)
    root = RootContext.open(directory.parent.parent)
    owner = RootOwnerLease.acquire(root)
    admission = AdmissionCoordinator(root, owner_lease=owner)
    ledger = Ledger(directory)
    (directory / "fund.yaml").write_bytes((directory / "fund.yaml").read_bytes() + b"\n")
    before = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}

    class UnavailableDataClient:
        def __getattr__(self, _name):
            raise AssertionError("tick accessed data before verifying the enrolled inventory")

    try:
        with admission.manual_session("alpha", timeout=0):
            with pytest.raises(AdmissionError, match="inventory"):
                tick(directory, UnavailableDataClient())
        after = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        assert after == before
        assert ledger.sessions() == []
    finally:
        owner.close()
        root.close()


# ---------------------------------------------------------------------------
# cadence regressions (T026)
# ---------------------------------------------------------------------------


def test_weekly_cadence_records_every_session_oldest_first_and_rebalances_once_per_iso_week(tmp_path, clock, SPEC):
    spec = SPEC.model_copy(update={"rebalance": "weekly"})
    clock("2024-06-04")
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    assert _tick(directory).session == "2024-06-03"

    clock("2024-06-12")  # a reviewed backlog of six closes, run strictly oldest first
    backlog = [_tick(directory) for _ in range(6)]
    with pytest.raises(NothingDue):
        _tick(directory)

    assert [record.session for record in backlog] == ["2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07", "2024-06-10", "2024-06-11"]
    assert [record.rebalance for record in backlog] == [False, False, False, False, True, False]
    assert Ledger(directory).sessions() == WEEKDAYS[:7]


def test_monthly_cadence_skips_market_holidays_and_rebalances_at_the_month_open(tmp_path, clock, SPEC):
    days = ["2024-05-23", "2024-05-24", "2024-05-28", "2024-05-29", "2024-05-30", "2024-05-31", "2024-06-03", "2024-06-04"]  # 05-27 Memorial Day
    series = {"SPY": {day: 100.0 for day in days}, "AAPL": {day: 200.0 + i for i, day in enumerate(days)}}
    spec = SPEC.model_copy(update={"rebalance": "monthly"})
    clock("2024-05-25")  # Saturday: Friday is the latest completed close
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    first = _tick(directory, data=FakeDataClient(series))
    assert first.session == "2024-05-24" and first.rebalance

    clock("2024-06-05")
    owed = []
    while True:
        try:
            owed.append(_tick(directory, data=FakeDataClient(series)))
        except NothingDue:
            break

    assert [record.session for record in owed] == days[2:]
    assert [record.session for record in owed if record.rebalance] == ["2024-06-03"]
    assert "2024-05-27" not in Ledger(directory).sessions()


def test_explicit_backfill_cannot_skip_or_reorder_the_owed_backlog_and_recorded_dates_are_idempotent(tmp_path, clock, SPEC):
    clock("2024-06-04")
    directory = deploy("alpha", SPEC, ["AAPL"], root=tmp_path)
    _tick(directory)
    clock("2024-06-08")

    for skipped in ("2024-06-05", "2024-06-07"):
        with pytest.raises(ValueError, match="not the next unrecorded session \\(2024-06-04\\)"):
            _tick(directory, session=skipped)
    assert Ledger(directory).sessions() == ["2024-06-03"]
    assert [_tick(directory, session=day).session for day in ("2024-06-04", "2024-06-05")] == ["2024-06-04", "2024-06-05"]
    recorded = Ledger(directory).read("2024-06-03")
    assert _tick(directory, session="2024-06-03") == recorded  # recorded history is returned, never re-run
    assert Ledger(directory).sessions() == ["2024-06-03", "2024-06-04", "2024-06-05"]


def test_one_second_minute_cadence_is_keyed_to_the_second_and_late_runs_take_the_latest_bar(SPEC):
    spec = FundSpec.model_validate({**SPEC.model_dump(mode="json"), "rebalance": "minute", "interval": 1 / 60, "window": {"start": "13:00", "end": "13:01"}})
    assert spec.interval_seconds == 1
    at = lambda hhmmss, micro=0: datetime.fromisoformat(f"2024-06-04T{hhmmss}").replace(microsecond=micro, tzinfo=NEW_YORK)  # noqa: E731

    assert next_session(None, spec, None, now=lambda: at("12:59:59", 999_999)) is None
    assert next_session(None, spec, None, now=lambda: at("13:00:00", 700_000)) == "2024-06-04T13:00:00"
    assert next_session(None, spec, "2024-06-04T13:00:00", now=lambda: at("13:00:00", 999_999)) is None
    assert next_session(None, spec, "2024-06-04T13:00:00", now=lambda: at("13:00:01")) == "2024-06-04T13:00:01"
    assert next_session(None, spec, "2024-06-04T13:00:01", now=lambda: at("13:00:07", 500_000)) == "2024-06-04T13:00:07"
    assert next_session(None, spec, "2024-06-04T13:00:59", now=lambda: at("13:05:00")) == "2024-06-04T13:01:00"
    assert next_session(None, spec, "2024-06-04T13:01:00", now=lambda: at("15:00:00")) is None
    with pytest.raises(ValueError, match="floor is 1 second"):
        FundSpec.model_validate({**SPEC.model_dump(mode="json"), "rebalance": "minute", "interval": 0.5 / 60, "window": {"start": "13:00", "end": "13:01"}})
