"""The ledger: append-only, hash-chained, replayable; and the kill switch."""

import json
from pathlib import Path

import pytest

from hedge_fund.backtesting.fund import backtest_fund
from hedge_fund.backtesting.test_fund import (
    FakeAnalyst,
    FakeDataClient,
    SERIES,
    WEEKDAYS,
)
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.pipeline.session import FundState, SessionRecord

_DECISION_HASH = "0" * 64


@pytest.fixture(autouse=True)
def registered_fakes(monkeypatch):
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)


@pytest.fixture
def records():
    spec = FundSpec(schema_version=2, name="ledger-fund", strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}], risk={"max_position_pct": 1, "max_gross_exposure": 1}, capital=100_000, costs={"spread_bps": 0, "commission_per_share": 0})
    fund = Fund(spec, models={"solo": [FakeAnalyst("a", {"AAPL": 1})]})
    return backtest_fund(fund, WEEKDAYS[0], WEEKDAYS[4], FakeDataClient(SERIES), ["AAPL"]).records


def test_append_then_replay_rebuilds_the_state(tmp_path, records):
    ledger = Ledger(tmp_path)
    ledger.init()
    assert ledger.sessions() == [] and ledger.latest() is None
    assert ledger.replay(100_000) == FundState.initial(100_000)

    for record in records:
        path = ledger.append(record)
        assert path == tmp_path / "ledger" / f"{record.session}.json"
    assert ledger.sessions() == WEEKDAYS[:5]
    assert ledger.latest() == records[-1]
    assert ledger.read(WEEKDAYS[1]) == records[1]
    assert ledger.records() == records

    state = ledger.replay(100_000)
    assert state.positions == {"AAPL": 500} and state.cash == 0
    assert state.last_session == WEEKDAYS[4]
    assert state.pending is None  # Friday is not a rebalance session
    assert state.prev_hash == records[-1].hash
    assert state.halted is None


def test_append_refuses_duplicates_gaps_and_bad_hashes(tmp_path, records):
    ledger = Ledger(tmp_path)
    ledger.append(records[0])
    with pytest.raises(LedgerError, match="already recorded"):
        ledger.append(records[0])
    with pytest.raises(LedgerError, match="does not chain"):
        ledger.append(records[2])  # skipped records[1]
    tampered = records[1].model_copy(update={"nav": 1.0})
    with pytest.raises(LedgerError, match="hash does not match"):
        ledger.append(tampered)
    ledger.append(records[1])
    backdated = records[2].model_copy(update={"session": "2024-05-31"})
    backdated.hash = backdated.compute_hash()
    with pytest.raises(LedgerError, match="not after"):
        ledger.append(backdated)
    assert ledger.sessions() == WEEKDAYS[:2]


def test_replay_detects_an_edited_record(tmp_path, records):
    ledger = Ledger(tmp_path)
    for record in records[:3]:
        ledger.append(record)
    path = ledger.path(WEEKDAYS[1])
    data = json.loads(path.read_text())
    data["cash"] = 999.0
    path.write_text(json.dumps(data))
    with pytest.raises(LedgerError, match="altered"):
        ledger.replay(100_000)


def test_replay_detects_a_missing_link(tmp_path, records):
    ledger = Ledger(tmp_path)
    for record in records[:3]:
        ledger.append(record)
    ledger.path(WEEKDAYS[1]).unlink()
    with pytest.raises(LedgerError, match="chain broken at session 2024-06-05"):
        ledger.replay(100_000)


def _bar(session, prev=None, nav=100_000.0):
    """A hand-made bar record chained to *prev*."""
    record = SessionRecord(
        fund="bars",
        session=session,
        universe=["AAPL"],
        nav=nav,
        cash=nav,
        positions={},
        marks={},
        benchmark="SPY",
        benchmark_close=500.0,
        rebalance=True,
        prev_hash=prev.hash if prev else None,
        code_version="test",
        mandate_hash="m",
        snapshot_times={"SPY": "2026-10-05T14:00:00Z"},
    )
    record.hash = record.compute_hash()
    return record


def _chain(sessions):
    records, prev = [], None
    for i, session in enumerate(sessions):
        prev = _bar(session, prev, nav=100_000.0 + i)
        records.append(prev)
    return records


MONDAY = ["2026-10-05T09:30:00", "2026-10-05T09:35:00", "2026-10-05T16:00:00"]
TUESDAY = ["2026-10-06T09:30:00", "2026-10-06T16:00:00"]


def test_bars_live_in_a_directory_per_day_and_list_in_chain_order(tmp_path):
    ledger = Ledger(tmp_path)
    for record in _chain(MONDAY + TUESDAY):
        ledger.append(record)
    assert ledger.path(MONDAY[1]) == tmp_path / "ledger" / "2026-10-05" / "093500.json"
    assert ledger.sessions() == MONDAY + TUESDAY
    assert ledger.days() == ["2026-10-05", "2026-10-06"]
    assert ledger.read(MONDAY[1]).session == MONDAY[1]
    assert [r.session for r in ledger.records(since="2026-10-06")] == TUESDAY
    assert ledger.replay(100_000).last_session == TUESDAY[-1]
    # A daily record and bar records can share a ledger's listing rules.
    assert ledger.sessions() == sorted(ledger.sessions())


def test_checkpoint_shortcuts_replay_and_is_ignored_once_the_chain_moves_under_it(tmp_path):
    ledger = Ledger(tmp_path)
    records = _chain(MONDAY + TUESDAY)
    for record in records[:3]:
        ledger.append(record)
    with pytest.raises(LedgerError, match="only a minute fund"):
        ledger.checkpoint(FundState.initial(1.0))
    with pytest.raises(LedgerError, match="does not match the chain's head"):
        ledger.checkpoint(ledger.replay(100_000, before=MONDAY[2]))
    monday_close = ledger.replay(100_000)
    path = ledger.checkpoint(monday_close)
    assert path == tmp_path / "ledger" / "2026-10-05" / "checkpoint.json"
    assert [e["kind"] for e in ledger.events()] == ["checkpoint"]
    for record in records[3:]:
        ledger.append(record)
    # From the checkpoint only Tuesday is read; the answer is the full walk's.
    read = []
    original = ledger.read
    ledger.read = lambda s: (read.append(s), original(s))[1]
    short = ledger.replay(100_000)
    assert read == [MONDAY[2], *TUESDAY] and short == ledger.replay(100_000, full=True)
    read.clear()
    assert ledger.replay(100_000, before=TUESDAY[1]).last_session == TUESDAY[0] and read == [MONDAY[2], TUESDAY[0]]
    read.clear()
    assert ledger.replay(100_000, before=MONDAY[1]).last_session == MONDAY[0] and read == [MONDAY[0]]
    # Rewinding past the checkpoint drops it; a stale one on disk is ignored.
    ledger.rewind()
    ledger.rewind()
    assert (tmp_path / "ledger" / "superseded" / f"2026-10-06T093000.{records[3].hash[:12]}.json").exists()
    ledger.rewind()
    assert not path.exists() and ledger.replay(100_000).last_session == MONDAY[1]
    path.write_text(monday_close.model_dump_json())
    assert ledger.replay(100_000).last_session == MONDAY[1]


def test_kill_switch_round_trips_and_logs(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.init()
    assert ledger.halted() is None
    assert json.loads(ledger.control_path.read_text()) == {"halted": False}
    ledger.halt("drawdown breach")
    assert ledger.halted() == "drawdown breach"
    assert ledger.replay(1.0).halted == "drawdown breach"
    assert [e["kind"] for e in ledger.events()] == ["halt"]
    assert ledger.events()[0]["reason"] == "drawdown breach"
    assert all("time" in e for e in ledger.events())


def test_resume_clears_manual_halt_after_full_replay(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.init()
    ledger.halt("operator pause")

    ledger.resume(capital=100_000)

    assert ledger.halted() is None
    assert [event["kind"] for event in ledger.events()] == ["halt", "resume", "resume_effect_intent", "resume_completed"]


def test_resume_does_not_repeat_after_uncertain_control_write_without_request_id(tmp_path, monkeypatch):
    ledger = Ledger(tmp_path)
    ledger.init()
    ledger.halt("operator pause")
    attempts = []

    def fail_clear(self, halted, reason, **kwargs):
        if halted is False:
            attempts.append(halted)
            raise OSError("synthetic Resume control write failure")
        raise AssertionError("unexpected Halt write")

    monkeypatch.setattr(Ledger, "_write_control", fail_clear)
    with pytest.raises(OSError, match="synthetic Resume control write failure"):
        ledger.resume(capital=100_000)
    with pytest.raises(LedgerError, match="Resume control write outcome is uncertain"):
        ledger.resume(capital=100_000)

    assert attempts == [False]
    assert ledger.halted() == "operator pause"
    assert [event["kind"] for event in ledger.events()] == ["halt", "resume", "resume_effect_intent"]


def test_audit_observation_without_a_writer_is_read_only(tmp_path):
    directory = tmp_path / "fund with spaces"
    directory.mkdir()
    ledger = Ledger(directory)
    assert ledger.events() == []
    assert list(directory.iterdir()) == []

    ledger.events_path.write_text('{"kind":', encoding="utf-8")
    before = ledger.events_path.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        ledger.events()
    assert ledger.events_path.read_bytes() == before
    assert list(directory.iterdir()) == [ledger.events_path]


def test_audit_append_rejects_hardlinked_event_file(tmp_path):
    import os

    from hedge_fund.runtime.root import RootPathError

    directory = tmp_path / "paper" / "alpha"
    directory.mkdir(parents=True)
    ledger = Ledger(directory)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"protected\n")
    os.link(outside, ledger.events_path)

    with pytest.raises(RootPathError, match="single-link regular file"):
        ledger.log_event("synthetic")

    assert outside.read_bytes() == b"protected\n"
    assert ledger.events_path.read_bytes() == b"protected\n"


def test_initialization_cannot_overwrite_a_concurrent_halt(tmp_path, monkeypatch):
    import time
    from threading import Event, Thread

    from hedge_fund.paper import ledger as ledger_module
    from hedge_fund.runtime import admission
    from hedge_fund.runtime.root import RootContext

    directory = tmp_path / "alpha"
    directory.mkdir()
    ledger = Ledger(directory)
    with RootContext.open(directory) as root:
        halt_key = admission._thread_lock_key(root, ".paper-halt.lock")
    initializing = Event()
    halt_written = Event()
    release = Event()
    failures = []
    write_atomic = ledger_module.write_atomic

    def pause_initial_control(path, text, **kwargs):
        if Path(path) == ledger.control_path and json.loads(text) == {"halted": False}:
            initializing.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release initialization")
        result = write_atomic(path, text, **kwargs)
        if Path(path) == ledger.control_path and json.loads(text).get("halted") is True:
            halt_written.set()
        return result

    def initialize():
        try:
            ledger.init()
        except BaseException as exc:
            failures.append(exc)

    def halt():
        try:
            ledger.halt("synthetic emergency")
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(ledger_module, "write_atomic", pause_initial_control)
    initializer = Thread(target=initialize, name="fund-initializer")
    stopper = Thread(target=halt, name="fund-halter")
    initializer.start()
    try:
        assert initializing.wait(timeout=10), failures
        stopper.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with admission._LOCAL_LANES_GUARD:
                waiting_for_init = len(admission._LOCAL_LANES.get(halt_key, ())) >= 2
            if halt_written.is_set() or waiting_for_init:
                break
            time.sleep(0.005)
        assert halt_written.is_set() or waiting_for_init, failures
    finally:
        release.set()
        initializer.join(timeout=10)
        if stopper.ident is not None:
            stopper.join(timeout=10)
    assert not initializer.is_alive() and not stopper.is_alive()
    assert failures == []
    assert ledger.halted() == "synthetic emergency"


def test_approval_mailbox_round_trips_and_logs(tmp_path):
    ledger = Ledger(tmp_path)

    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    approved = ledger.approval()
    assert approved is not None
    assert approved["verdict"] == "approve"
    assert approved["decision_as_of"] == "2026-10-05"
    assert approved["decision_hash"] == _DECISION_HASH
    assert approved["by"] == "cli"
    assert set(approved) == {"verdict", "decision_as_of", "decision_hash", "decided_at", "by", "approval_id"}
    assert [event["kind"] for event in ledger.events()] == ["approve"]
    assert ledger.events()[0]["decision_as_of"] == "2026-10-05"
    assert ledger.events()[0]["decision_hash"] == _DECISION_HASH
    assert ledger.events()[0]["approval_id"] == approved["approval_id"]

    ledger.set_approval("reject", "2026-10-06", "1" * 64, "tui")
    rejected = ledger.approval()
    assert rejected is not None and rejected["verdict"] == "reject"
    assert [event["kind"] for event in ledger.events()] == ["approve", "reject"]
    assert ledger.events()[1]["by"] == "tui"


def test_web_approval_actor_round_trips_without_changing_cli_or_tui_values(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-07", "2" * 64, "web")

    approval = ledger.approval()

    assert approval is not None and approval["by"] == "web"
    assert ledger.events()[0]["by"] == "web"


def test_approval_mailbox_missing_corrupt_and_wrong_verdict_are_absent(tmp_path):
    ledger = Ledger(tmp_path)
    path = tmp_path / "pending-approval.json"
    assert ledger.approval() is None

    path.write_text("{broken")
    assert ledger.approval() is None

    path.write_text(json.dumps({"verdict": "yay", "decision_as_of": "2026-10-05", "decision_hash": _DECISION_HASH, "decided_at": "2026-10-29T22:00:00+00:00", "by": "cli"}))
    assert ledger.approval() is None


def test_approval_mailbox_unreadable_file_is_absent(tmp_path):
    (tmp_path / "pending-approval.json").mkdir()
    assert Ledger(tmp_path).approval() is None


def test_approval_fails_closed_when_expiry_history_is_unreadable(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.events_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(LedgerError, match="approval history is unavailable"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert ledger.approval() is None


@pytest.mark.parametrize("mailbox", ["stale", "malformed"])
def test_resolution_checks_history_even_when_mailbox_does_not_match(tmp_path, mailbox):
    ledger = Ledger(tmp_path)
    if mailbox == "stale":
        ledger.set_approval("approve", "2026-10-04", "1" * 64, "cli")
    else:
        ledger.approval_path.write_text("{invalid", encoding="utf-8")
    with ledger.events_path.open("a", encoding="utf-8") as events:
        events.write("{invalid-json\n")

    with pytest.raises(LedgerError, match="approval history is unavailable"):
        ledger.resolve_approval("2026-10-05", _DECISION_HASH)


def test_resolution_rejects_an_expiry_missing_its_decision_hash(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    with ledger.events_path.open("a", encoding="utf-8") as events:
        events.write(json.dumps({"time": "2026-10-05T00:00:00+00:00", "kind": "expire", "decision_as_of": "2026-10-05"}) + "\n")

    with pytest.raises(LedgerError, match="approval history is unavailable"):
        ledger.resolve_approval("2026-10-05", _DECISION_HASH)


def test_failed_approval_audit_cannot_leave_an_actionable_new_verdict(tmp_path, monkeypatch):
    ledger = Ledger(tmp_path)

    def fail_audit(*_args, **_kwargs):
        raise OSError("synthetic event append failure")

    monkeypatch.setattr(ledger, "log_event", fail_audit)
    with pytest.raises(OSError, match="synthetic event append failure"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    resolved, _ = ledger.resolve_approval("2026-10-05", _DECISION_HASH)
    assert resolved is None


def test_failed_mailbox_replacement_does_not_reuse_an_old_identical_vote(tmp_path, monkeypatch):
    from hedge_fund.paper import ledger as ledger_module

    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    old_mailbox = ledger.approval()
    write_atomic = ledger_module.write_atomic

    def fail_mailbox(path, text, **kwargs):
        if path == ledger.approval_path:
            raise OSError("synthetic mailbox replacement failure")
        return write_atomic(path, text, **kwargs)

    monkeypatch.setattr(ledger_module, "write_atomic", fail_mailbox)
    with pytest.raises(OSError, match="synthetic mailbox replacement failure"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert ledger.approval() == old_mailbox
    resolved, stale = ledger.resolve_approval("2026-10-05", _DECISION_HASH)
    assert resolved is None and stale == old_mailbox


def test_failed_final_mailbox_acknowledgement_expires_a_published_verdict(tmp_path, monkeypatch):
    from hedge_fund.paper import ledger as ledger_module

    ledger = Ledger(tmp_path)
    write_atomic = ledger_module.write_atomic

    def fail_after_publication(path, text, **kwargs):
        result = write_atomic(path, text, **kwargs)
        if path == ledger.approval_path and "pending" not in json.loads(text):
            raise OSError("synthetic lost publication acknowledgement")
        return result

    monkeypatch.setattr(ledger_module, "write_atomic", fail_after_publication)
    with pytest.raises(OSError, match="synthetic lost publication acknowledgement"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert ledger.resolve_approval("2026-10-05", _DECISION_HASH)[0] is None
    assert ledger.approval() is None
    assert ledger.events()[-1]["kind"] == "expire"


def test_uncertain_publication_and_failed_expiry_halt_for_reconciliation(tmp_path, monkeypatch):
    from hedge_fund.paper import ledger as ledger_module

    ledger = Ledger(tmp_path)
    write_atomic = ledger_module.write_atomic
    log_event = ledger.log_event

    def fail_after_publication(path, text, **kwargs):
        result = write_atomic(path, text, **kwargs)
        if path == ledger.approval_path and "pending" not in json.loads(text):
            raise OSError("synthetic lost publication acknowledgement")
        return result

    def fail_expiry(kind, **fields):
        if kind == "expire":
            raise OSError("synthetic expiry failure")
        return log_event(kind, **fields)

    monkeypatch.setattr(ledger_module, "write_atomic", fail_after_publication)
    monkeypatch.setattr(ledger, "log_event", fail_expiry)
    with pytest.raises(LedgerError, match="outcome is uncertain; fund halted for reconciliation"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert ledger.halted() == "verdict publication outcome requires reconciliation"


def test_failed_publication_expiry_and_halt_leave_a_blocking_guard(tmp_path, monkeypatch):
    from hedge_fund.paper import ledger as ledger_module

    ledger = Ledger(tmp_path)
    write_atomic = ledger_module.write_atomic
    log_event = ledger.log_event

    def fail_after_publication(path, text, **kwargs):
        result = write_atomic(path, text, **kwargs)
        if path == ledger.approval_path and "pending" not in json.loads(text):
            raise OSError("synthetic lost publication acknowledgement")
        return result

    def fail_expiry(kind, **fields):
        if kind == "expire":
            raise OSError("synthetic expiry failure")
        return log_event(kind, **fields)

    def fail_halt(_reason):
        raise OSError("synthetic halt failure")

    monkeypatch.setattr(ledger_module, "write_atomic", fail_after_publication)
    monkeypatch.setattr(ledger, "log_event", fail_expiry)
    monkeypatch.setattr(ledger, "halt", fail_halt)
    with pytest.raises(LedgerError, match="halt outcomes are uncertain"):
        ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert json.loads(ledger.approval_publication_path.read_text(encoding="utf-8"))["state"] == "pending"
    with pytest.raises(LedgerError, match="publication is incomplete"):
        Ledger(tmp_path).resolve_approval("2026-10-05", _DECISION_HASH)
    with pytest.raises(LedgerError, match="publication is incomplete"):
        Ledger(tmp_path).set_approval("reject", "2026-10-05", _DECISION_HASH, "cli")


@pytest.mark.parametrize(
    "contents",
    [
        "{invalid",
        '{"version": 1, "state": []}',
        '{"version": 1, "state": [], "approval_id": "' + "a" * 32 + '"}',
    ],
)
def test_corrupt_transition_guard_blocks_approval_resolution(tmp_path, contents):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    ledger.approval_publication_path.write_text(contents, encoding="utf-8")

    with pytest.raises(LedgerError, match="publication state"):
        ledger.resolve_approval("2026-10-05", _DECISION_HASH)


def test_committed_publication_mismatching_mailbox_requires_reconciliation(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    mailbox = ledger.approval()
    mailbox["approval_id"] = "b" * 32
    ledger.approval_path.write_text(json.dumps(mailbox), encoding="utf-8")

    with pytest.raises(LedgerError, match="publication and mailbox disagree"):
        ledger.resolve_approval("2026-10-05", _DECISION_HASH)


@pytest.mark.parametrize("action", ["preflight", "replacement"])
def test_committed_publication_mismatch_blocks_paper_work_and_replacement(tmp_path, action):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    mailbox = ledger.approval()
    mailbox["approval_id"] = "b" * 32
    ledger.approval_path.write_text(json.dumps(mailbox), encoding="utf-8")
    marker = ledger.approval_publication_path.read_bytes()
    original_mailbox = ledger.approval_path.read_bytes()
    original_events = ledger.events_path.read_bytes()

    with pytest.raises(LedgerError, match="publication and mailbox disagree"):
        if action == "preflight":
            ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)
        else:
            ledger.set_approval("reject", "2026-10-05", _DECISION_HASH, "cli")

    assert ledger.approval_publication_path.read_bytes() == marker
    assert ledger.approval_path.read_bytes() == original_mailbox
    assert ledger.events_path.read_bytes() == original_events


@pytest.mark.parametrize("mismatch", [None, "decision", "session", "verdict", "actor", "approval_id"])
def test_consumption_completion_requires_matching_audit_identity(tmp_path, mismatch):
    ledger = Ledger(tmp_path)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": "approve",
        "approval_by": "cli",
        "approval_id": "a" * 32,
    }
    ledger.log_event("consume", durable=True, **fields)
    completion = dict(fields)
    if mismatch == "decision":
        completion["decision_hash"] = "1" * 64
    elif mismatch == "session":
        completion["session"] = "2026-10-07"
    elif mismatch == "verdict":
        completion["approval_verdict"] = "reject"
    elif mismatch == "actor":
        completion["approval_by"] = "web"
    elif mismatch == "approval_id":
        completion["approval_id"] = "b" * 32
    ledger.log_event("tick", **completion)

    if mismatch is None:
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)
    else:
        with pytest.raises(LedgerError, match="consumption is incomplete"):
            ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)


def test_consumption_requires_one_completion_per_attempt(tmp_path):
    ledger = Ledger(tmp_path)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": "approve",
        "approval_by": "cli",
        "approval_id": "a" * 32,
    }
    ledger.log_event("consume", durable=True, **fields)
    ledger.log_event("consume", durable=True, **fields)
    ledger.log_event("tick", **fields)
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)
    ledger.log_event("tick", **fields)
    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)


@pytest.mark.parametrize("verdict", ["approve", "reject"])
def test_identifierless_consume_does_not_match_an_identified_tick(tmp_path, verdict):
    ledger = Ledger(tmp_path)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": verdict,
        "approval_by": "cli",
    }
    ledger.log_event("consume", durable=True, **fields)
    ledger.log_event("tick", approval_id="a" * 32, **fields)
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)


def test_repeated_legacy_rejection_attempts_need_distinct_completion_ticks(tmp_path):
    ledger = Ledger(tmp_path)
    legacy = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "by": "cli",
        "consumed": True,
    }
    completion = {
        "decision_as_of": legacy["decision_as_of"],
        "decision_hash": legacy["decision_hash"],
        "session": legacy["session"],
        "approval_verdict": "reject",
        "approval_by": "cli",
    }
    ledger.log_event("reject", **legacy)
    ledger.log_event("reject", **legacy)
    ledger.log_event("tick", **completion)
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)
    ledger.log_event("tick", **completion)
    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)


def test_each_consumption_pairs_with_only_one_rejection_audit(tmp_path):
    ledger = Ledger(tmp_path)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": "reject",
        "approval_by": "cli",
        "approval_id": "a" * 32,
    }
    audit = {
        "decision_as_of": fields["decision_as_of"],
        "decision_hash": fields["decision_hash"],
        "session": fields["session"],
        "by": "cli",
        "consumed": True,
    }
    ledger.log_event("consume", durable=True, **fields)
    ledger.log_event("reject", **audit)
    ledger.log_event("reject", **audit)
    ledger.log_event("tick", **fields)
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)
    ledger.log_event("tick", **fields)
    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)


@pytest.mark.parametrize("approval_id", [None, "a" * 32])
def test_rejection_audit_and_consume_are_one_attempt(tmp_path, approval_id):
    ledger = Ledger(tmp_path)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": "reject",
        "approval_by": "cli",
    }
    if approval_id is not None:
        fields["approval_id"] = approval_id
    ledger.log_event("consume", durable=True, **fields)
    ledger.log_event(
        "reject",
        decision_as_of=fields["decision_as_of"],
        decision_hash=fields["decision_hash"],
        session=fields["session"],
        by="cli",
        consumed=True,
    )
    ledger.log_event("tick", **fields)
    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)


@pytest.mark.parametrize("change", ["replacement", "head"])
def test_approval_observation_detects_a_changed_verdict_or_head(tmp_path, records, monkeypatch, change):
    ledger = Ledger(tmp_path)
    ledger.append(records[0])
    state = ledger.replay(100_000)
    assert state.pending is not None
    expected = ledger.set_approval("approve", state.pending.as_of, state.prev_hash, "cli")
    assert ledger.observe_approval_for_display(state, approval_required=True) == expected

    resolve = ledger.resolve_approval
    changed = False

    def resolve_then_change(*args, **kwargs):
        nonlocal changed
        result = resolve(*args, **kwargs)
        if not changed:
            changed = True
            if change == "replacement":
                ledger.set_approval("reject", state.pending.as_of, state.prev_hash, "web")
            else:
                ledger.append(records[1])
        return result

    monkeypatch.setattr(ledger, "resolve_approval", resolve_then_change)
    with pytest.raises(LedgerError, match="changed during observation"):
        ledger.observe_approval_for_display(state, approval_required=True)
    assert changed


@pytest.mark.parametrize("approval_id", [None, "a" * 32])
def test_legacy_rejection_audit_requires_a_matching_tick(tmp_path, approval_id):
    ledger = Ledger(tmp_path)
    ledger.log_event(
        "reject",
        decision_as_of="2026-10-05",
        decision_hash=_DECISION_HASH,
        session="2026-10-06",
        by="cli",
        consumed=True,
    )
    with pytest.raises(LedgerError, match="consumption is incomplete"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)
    fields = {
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "session": "2026-10-06",
        "approval_verdict": "reject",
        "approval_by": "cli",
    }
    if approval_id is not None:
        fields["approval_id"] = approval_id
    ledger.log_event("tick", **fields)
    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=True)


def test_interrupted_redo_still_denies_unexpired_new_verdict(tmp_path, records):
    ledger = Ledger(tmp_path)
    original = records[0]
    ledger.append(original)
    ledger.begin_redo(original)

    with pytest.raises(LedgerError, match="interrupted redo"):
        ledger.set_approval("approve", original.decision.as_of, original.hash, "cli")


def test_standalone_approval_cannot_bypass_a_configured_root(tmp_path):
    from hedge_fund import paths
    from hedge_fund.runtime.admission import AdmissionError
    from hedge_fund.runtime.root import RootContext

    directory = tmp_path / "nonstandard" / "alpha"
    directory.mkdir(parents=True)
    with RootContext.open(tmp_path) as root:
        with paths.bound_root(root):
            with pytest.raises(AdmissionError, match="cannot bypass a configured root"):
                Ledger(directory).set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")

    assert not (directory / ".paper-control.lock").exists()
    assert not (directory / "pending-approval.json").exists()


def test_legacy_approval_with_matching_audit_remains_valid(tmp_path):
    ledger = Ledger(tmp_path)
    mailbox = {
        "verdict": "approve",
        "decision_as_of": "2026-10-05",
        "decision_hash": _DECISION_HASH,
        "decided_at": "2026-10-05T00:00:00+00:00",
        "by": "cli",
    }
    ledger.approval_path.write_text(json.dumps(mailbox), encoding="utf-8")
    ledger.log_event("approve", decision_as_of="2026-10-05", decision_hash=_DECISION_HASH, by="cli")

    assert ledger.resolve_approval("2026-10-05", _DECISION_HASH) == (mailbox, mailbox)


@pytest.mark.parametrize(
    "kind,fields",
    [
        ("approve", {"decision_as_of": "2024-06-03", "by": "cli"}),
        ("reject", {"decision_as_of": "2024-06-03", "by": "tui"}),
        ("expire", {"decision_as_of": "2024-06-03", "reason": "no verdict"}),
        (
            "reject",
            {"decision_as_of": "2024-06-03", "by": "cli", "consumed": True, "session": "2024-06-04"},
        ),
    ],
)
def test_pre_identity_approval_history_does_not_block_unrelated_work(tmp_path, records, kind, fields):
    ledger = Ledger(tmp_path)
    if fields.get("consumed"):
        source = records[0]
        assert source.decision is not None and source.decision.as_of == fields["decision_as_of"]
        rejected = records[1].model_copy(update={"executed": None})
        rejected.hash = rejected.compute_hash()
        ledger.append(source)
        ledger.append(rejected)
    ledger.log_event(kind, **fields)
    if fields.get("consumed"):
        ledger.log_event("tick", session=fields["session"], nav=100_000, executed=False, decided=True)

    ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)
    with pytest.raises(LedgerError, match="legacy|reconciliation"):
        ledger.resolve_approval("2024-06-03", _DECISION_HASH)


def test_incomplete_pre_identity_rejection_still_requires_reconciliation(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.log_event("reject", decision_as_of="2024-06-03", by="cli", consumed=True, session="2024-06-04")
    with pytest.raises(LedgerError):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)


def test_pre_identity_rejection_cannot_be_completed_without_its_ledger_record(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.log_event("reject", decision_as_of="2024-06-03", by="cli", consumed=True, session="2024-06-04")
    ledger.log_event("tick", session="2024-06-04", nav=100_000, executed=False, decided=True)
    with pytest.raises(LedgerError, match="reconciliation"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)


def test_pre_identity_event_after_bound_history_remains_invalid(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2024-06-03", _DECISION_HASH, "cli")
    ledger.log_event("reject", decision_as_of="2024-06-04", by="cli")
    with pytest.raises(LedgerError, match="approval history is unavailable"):
        ledger.require_ready_for_work(FundState.initial(100_000), approval_required=False)


def test_approval_clear_preserves_a_newer_verdict(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    original = ledger.approval()
    ledger.set_approval("reject", "2026-10-06", "1" * 64, "tui")
    newer = ledger.approval()

    ledger.clear_approval(expected=original)

    assert ledger.approval() == newer
    ledger.clear_approval()
    assert ledger.approval() is None


def test_approval_clear_logs_unlink_error(tmp_path, monkeypatch):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    approval = ledger.approval()
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("mailbox is held")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)

    assert ledger.clear_approval(expected=approval) is False
    assert ledger.approval() == approval
    event = ledger.events()[-1]
    assert event["kind"] == "approval_clear_failed"
    assert event["error"] == "PermissionError"


def test_approval_clear_surfaces_failure_to_record_an_unlink_error(tmp_path, monkeypatch):
    ledger = Ledger(tmp_path)
    ledger.set_approval("approve", "2026-10-05", _DECISION_HASH, "cli")
    approval = ledger.approval()
    unlink = Path.unlink

    def fail_approval_unlink(path, *args, **kwargs):
        if path == ledger.approval_path:
            raise PermissionError("synthetic mailbox unlink failure")
        return unlink(path, *args, **kwargs)

    def fail_audit(*_args, **_kwargs):
        raise OSError("synthetic audit failure")

    monkeypatch.setattr(Path, "unlink", fail_approval_unlink)
    monkeypatch.setattr(ledger, "log_event", fail_audit)
    with pytest.raises(OSError, match="synthetic audit failure"):
        ledger.clear_approval(expected=approval)


@pytest.mark.parametrize(
    "verdict,decision_as_of,decision_hash,by",
    [
        ("yay", "2026-10-05", _DECISION_HASH, "cli"),
        ("approve", "", _DECISION_HASH, "cli"),
        ("approve", "2026-10-05", "not-a-hash", "cli"),
        ("reject", "2026-10-05", _DECISION_HASH, "runner"),
        (None, "2026-10-05", _DECISION_HASH, "cli"),
    ],
)
def test_set_approval_validates_mailbox_values(tmp_path, verdict, decision_as_of, decision_hash, by):
    with pytest.raises(ValueError):
        Ledger(tmp_path).set_approval(verdict, decision_as_of, decision_hash, by)


def _compat_record(positions: dict[str, float]) -> SessionRecord:
    record = SessionRecord(
        fund="compat",
        session="2024-06-03",
        universe=["AAPL"],
        nav=100_000.0,
        cash=0.0,
        positions=positions,
        marks={"AAPL": 200.0},
        benchmark="SPY",
        benchmark_close=100.0,
        rebalance=True,
        code_version="test",
        mandate_hash="m",
    )
    record.hash = record.compute_hash()
    return record


def test_integral_positions_serialize_as_ints_so_old_ledgers_still_verify():
    record = _compat_record({"AAPL": 500})
    text = record.model_dump_json()
    assert '"positions":{"AAPL":500' in text and "500.0" not in text
    assert "redo_nonce" not in text and "redo_nonce" not in record.model_dump()
    # The hash is computed over that same serialization, so a record replayed
    # from a ledger written before fractional shares re-verifies exactly.
    assert SessionRecord.model_validate_json(text).compute_hash() == record.hash


def test_redo_identity_is_serialized_and_bound_to_the_record_hash():
    original = _compat_record({"AAPL": 500})
    redone = original.model_copy(update={"redo_nonce": "a" * 32})
    redone.hash = redone.compute_hash()
    text = redone.model_dump_json()

    assert '"redo_nonce":"' + "a" * 32 + '"' in text
    assert redone.hash != original.hash
    assert SessionRecord.model_validate_json(text).compute_hash() == redone.hash


def test_fractional_positions_round_trip_and_keep_their_hash():
    record = _compat_record({"AAPL": 0.7881})
    parsed = SessionRecord.model_validate_json(record.model_dump_json())
    assert parsed.positions == {"AAPL": 0.7881}
    assert parsed.compute_hash() == record.hash


def test_an_old_integer_share_ledger_replays_cleanly(tmp_path):
    record = _compat_record({"AAPL": 500})
    # Hand-write the JSON the way the pre-fractional engine did: int shares.
    old_style = json.dumps(json.loads(record.model_dump_json()), indent=2)
    assert '"AAPL": 500' in old_style and "500.0" not in old_style
    path = tmp_path / "ledger" / "2024-06-03.json"
    path.parent.mkdir(parents=True)
    path.write_text(old_style)
    state = Ledger(tmp_path).replay(100_000)
    assert state.positions == {"AAPL": 500} and state.cash == 0


def test_pre_approval_ledger_fixture_replays_with_full_hash_verification(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "pre_approval_record.json"
    record = fixture.read_bytes()
    assert b'"approval_required"' not in record
    ledger = Ledger(tmp_path)
    path = ledger.path("2025-01-21")
    path.parent.mkdir(parents=True)
    path.write_bytes(record)

    state = ledger.replay(100_000, full=True)

    assert state.last_session == "2025-01-21"
    assert state.prev_hash == "b5c627cd3d54021fff9d25e18a9710245e48c12bff752f8341d34e515b2615e3"
    assert state.pending is not None and state.pending.as_of == "2025-01-21"
    assert not state.pending.spec.approval_required
    assert "approval_required" not in state.pending.spec.model_dump()
