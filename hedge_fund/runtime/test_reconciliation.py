import pytest
from pydantic import ValidationError

from hedge_fund.brokers.models import Order
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.fund import FundSpec
from hedge_fund.paper import deploy, Ledger, LedgerError, load_deployed
from hedge_fund.runtime.reconciliation import (
    build_reconciliation_snapshot,
    failure_digest,
    ReconciliationConfirmation,
    ReconciliationReceipt,
    unresolved_tick_failures,
    verify_reconciliation_receipt,
)


def _failure_recovery_context(tmp_path, monkeypatch):
    import hedge_fund.paper.ledger as ledger_module
    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)
    recorded_at = "2024-06-03T00:00:00+00:00"
    monkeypatch.setattr(ledger_module, "_now", lambda: recorded_at)
    spec = FundSpec(
        schema_version=2,
        name="paper-fund",
        strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
    )
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    ledger.log_event(
        "tick_failed",
        session="2024-06-03",
        error="synthetic failure",
        expected_head=None,
        operation_id="a" * 32,
        request_id="tick-expiry",
        capture_id="b" * 32,
        capture_digest="c" * 64,
    )
    ledger.halt("synthetic failure")
    state = ledger.replay(spec.capital, full=True)
    latest = ledger.latest()
    snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, latest)
    return spec, directory, deployed, ledger, state, latest, snapshot


def test_reconciliation_receipt_binds_failure_head_book_capture_and_operator():
    failure = {
        "kind": "tick_failed",
        "time": "2026-11-05T08:00:00+00:00",
        "session": "2026-11-04",
        "expected_head": "a" * 64,
        "request_id": "tick-1",
        "operation_id": "b" * 32,
        "capture_id": "c" * 32,
        "capture_digest": "d" * 64,
    }

    receipt = ReconciliationReceipt.create(
        failure_event=failure,
        request_id="recover-1",
        current_head="a" * 64,
        broker_book_sha256="e" * 64,
        fill_identity_sha256="f" * 64,
        operator="web",
        recorded_at="2026-11-05T08:01:00+00:00",
    )

    assert receipt.schema_version == 1
    assert receipt.failure_id == failure_digest(failure)
    assert receipt.expected_head == "a" * 64
    assert receipt.current_head == "a" * 64
    assert receipt.operation_id == "b" * 32
    assert receipt.failed_request_id == "tick-1"
    assert receipt.capture_id == "c" * 32
    assert receipt.capture_digest == "d" * 64
    assert receipt.operator == "web"
    assert receipt.receipt_id == receipt.compute_receipt_id()

    event = {"kind": "reconciliation", "receipt": receipt.model_dump(mode="json")}
    assert unresolved_tick_failures([failure, event]) == [failure]
    resume = {"kind": "resume", "reconciliation_id": receipt.receipt_id, "time": "2026-11-05T08:01:00+00:00"}
    assert unresolved_tick_failures([failure, event, resume]) == []

    changed_failure = {**failure, "expected_head": "0" * 64}
    assert unresolved_tick_failures([changed_failure, event, resume]) == [changed_failure]

    altered = receipt.model_dump(mode="json")
    altered["current_head"] = "0" * 64
    with pytest.raises(ValidationError):
        ReconciliationReceipt.model_validate(altered)


def test_reconciliation_preview_requires_exact_local_paper_book(tmp_path, monkeypatch):
    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)
    spec = FundSpec(
        schema_version=2,
        name="paper-fund",
        strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
    )
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    ledger.log_event(
        "tick_failed",
        session="2024-06-03",
        error="synthetic failure",
        expected_head=None,
        operation_id="a" * 32,
        request_id="tick-1",
        capture_id="b" * 32,
        capture_digest="c" * 64,
    )
    ledger.halt("synthetic failure")
    state = ledger.replay(spec.capital, full=True)
    latest = ledger.latest()

    preview = build_reconciliation_snapshot(directory, deployed, ledger, state, latest)

    assert preview.preview.required is True
    assert preview.preview.recoverable is True
    assert preview.preview.reason == "ready"
    assert preview.preview.expected_head is None
    assert preview.preview.current_head is None
    assert preview.preview.book_matches_ledger is True
    assert preview.failure_event["request_id"] == "tick-1"

    PaperBroker(directory / "broker.json", spec.costs).place_order(Order(ticker="AAPL", side="buy", quantity=1, price=100))
    changed = build_reconciliation_snapshot(directory, deployed, ledger, state, latest)

    assert changed.preview.failure_id == preview.preview.failure_id
    assert changed.preview.recoverable is False
    assert changed.preview.reason == "broker-book-mismatch"
    assert changed.preview.book_matches_ledger is False
    assert changed.preview.preview_digest != preview.preview.preview_digest
    confirmation = ReconciliationConfirmation(
        request_id="recover-stale-1",
        failure_id=preview.preview.failure_id,
        preview_digest=preview.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    with pytest.raises(LedgerError, match="not reconcilable"):
        ledger.resume(spec.capital, reconciliation=confirmation, operator="web")
    assert ledger.halted() == "synthetic failure"
    assert not any(event["kind"] in {"reconciliation", "resume"} for event in ledger.events())


def test_resume_records_hash_bound_receipt_without_repeating_failed_work(tmp_path, monkeypatch):
    import hedge_fund.paper.ledger as ledger_module
    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)
    recorded_at = "2024-06-03T00:00:00+00:00"
    monkeypatch.setattr(ledger_module, "_now", lambda: recorded_at)
    spec = FundSpec(
        schema_version=2,
        name="paper-fund",
        strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
    )
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    ledger.log_event(
        "tick_failed",
        session="2024-06-03",
        error="synthetic failure",
        expected_head=None,
        operation_id="a" * 32,
        request_id="tick-1",
        capture_id="b" * 32,
        capture_digest="c" * 64,
    )
    ledger.halt("synthetic failure")
    state = ledger.replay(spec.capital, full=True)
    snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, ledger.latest())
    confirmation = ReconciliationConfirmation(
        request_id="recover-1",
        failure_id=snapshot.preview.failure_id,
        preview_digest=snapshot.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )

    receipt_id = ledger.resume(spec.capital, reconciliation=confirmation, operator="web")

    assert ledger.halted() is None
    assert ledger.sessions() == []
    events = ledger.events()
    reconciliation_events = [event for event in events if event["kind"] == "reconciliation"]
    resume_events = [event for event in events if event["kind"] == "resume"]
    assert len(reconciliation_events) == len(resume_events) == 1
    receipt = reconciliation_events[0]["receipt"]
    assert receipt["request_id"] == "recover-1"
    assert receipt["failure_id"] == snapshot.preview.failure_id
    assert receipt["expected_head"] is None
    assert receipt["current_head"] is None
    assert receipt["broker_book_sha256"] == snapshot.preview.broker_book_sha256
    assert receipt["fill_identity_sha256"] == snapshot.preview.fill_identity_sha256
    assert receipt["operation_id"] == "a" * 32
    assert receipt["capture_digest"] == "c" * 64
    assert receipt["issued_at"] == recorded_at
    assert receipt["valid_until"] == "2024-06-03T00:30:00+00:00"
    assert receipt_id == receipt["receipt_id"] == resume_events[0]["reconciliation_id"]

    monkeypatch.setattr(ledger_module, "_now", lambda: "2024-06-03T00:31:00+00:00")
    replayed = ledger.resume(spec.capital, reconciliation=confirmation, operator="web")

    assert replayed == receipt_id
    assert len([event for event in ledger.events() if event["kind"] == "reconciliation"]) == 1
    assert len([event for event in ledger.events() if event["kind"] == "resume"]) == 1
    assert ledger.sessions() == []
    assert ledger.unresolved_recovery_state().failures == ()


@pytest.mark.parametrize("lost_kind", ["reconciliation", "resume"])
def test_resume_append_lost_ack_retries_same_request_without_repeating_work(tmp_path, monkeypatch, lost_kind):
    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY

    monkeypatch.setitem(ALPHA_MODEL_REGISTRY, "a", FakeAnalyst)
    spec = FundSpec(
        schema_version=2,
        name="paper-fund",
        strategies=[{"name": "solo", "models": [{"name": "a"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
    )
    directory = deploy("alpha", spec, ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    ledger.log_event(
        "tick_failed",
        session="2024-06-03",
        error="synthetic failure",
        expected_head=None,
        operation_id="a" * 32,
        request_id="tick-1",
        capture_id="b" * 32,
        capture_digest="c" * 64,
    )
    ledger.halt("synthetic failure")
    state = ledger.replay(spec.capital, full=True)
    preview = build_reconciliation_snapshot(directory, deployed, ledger, state, ledger.latest())
    confirmation = ReconciliationConfirmation(
        request_id="recover-lost-ack-1",
        failure_id=preview.preview.failure_id,
        preview_digest=preview.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    original_log_event = ledger.log_event

    def append_then_lose_ack(kind, **fields):
        result = original_log_event(kind, **fields)
        if kind == lost_kind:
            raise OSError(f"synthetic {kind} acknowledgment loss")
        return result

    monkeypatch.setattr(ledger, "log_event", append_then_lose_ack)
    with pytest.raises(OSError, match=f"synthetic {lost_kind} acknowledgment loss"):
        ledger.resume(spec.capital, reconciliation=confirmation, operator="web")

    assert ledger.halted() == "synthetic failure"
    assert len([event for event in ledger.events() if event["kind"] == "reconciliation"]) == 1
    assert len([event for event in ledger.events() if event["kind"] == "resume"]) == (1 if lost_kind == "resume" else 0)
    assert not [event for event in ledger.events() if event["kind"] == "resume_effect_intent"]
    monkeypatch.setattr(ledger, "log_event", original_log_event)

    receipt_id = ledger.resume(spec.capital, reconciliation=confirmation, operator="web")

    assert ledger.halted() is None
    assert ledger.sessions() == []
    assert len([event for event in ledger.events() if event["kind"] == "reconciliation"]) == 1
    assert len([event for event in ledger.events() if event["kind"] == "resume"]) == 1
    completed = [event for event in ledger.events() if event["kind"] == "resume_completed"]
    assert len(completed) == 1
    assert len([event for event in ledger.events() if event["kind"] == "resume_effect_intent"]) == 1
    assert receipt_id == completed[0]["result"]["reconciliation_id"]


def test_expired_failure_bound_receipt_is_denied(tmp_path, monkeypatch):
    import hedge_fund.paper.ledger as ledger_module

    spec, directory, deployed, ledger, state, latest, snapshot = _failure_recovery_context(tmp_path, monkeypatch)
    failure = snapshot.failure_event
    issued_at = "2024-06-03T00:00:00+00:00"
    receipt = ReconciliationReceipt.create(
        failure_event=failure,
        request_id="recover-expired",
        current_head=snapshot.preview.current_head,
        broker_book_sha256=snapshot.preview.broker_book_sha256,
        fill_identity_sha256=snapshot.preview.fill_identity_sha256,
        operator="web",
        recorded_at=issued_at,
    )

    with pytest.raises(ValueError, match="expired"):
        verify_reconciliation_receipt(directory, deployed, ledger, state, latest, receipt, recorded_now="2024-06-03T00:30:01+00:00")
    confirmation = ReconciliationConfirmation(
        request_id=receipt.request_id,
        failure_id=snapshot.preview.failure_id,
        preview_digest=snapshot.preview.preview_digest,
        decision="confirm-paper-book-matches-ledger",
    )
    ledger.log_event("reconciliation", time=issued_at, receipt=receipt.model_dump(mode="json"))
    monkeypatch.setattr(ledger_module, "_now", lambda: "2024-06-03T00:30:01+00:00")
    with pytest.raises(LedgerError, match="Reconciliation receipt"):
        ledger.resume(spec.capital, reconciliation=confirmation, operator="web")
    assert ledger.halted() == "synthetic failure"
    assert not any(event["kind"] == "resume" for event in ledger.events())
    reconciliation = {"kind": "reconciliation", "receipt": receipt.model_dump(mode="json")}
    resume = {"kind": "resume", "reconciliation_id": receipt.receipt_id, "time": "2024-06-03T00:30:01+00:00"}
    assert unresolved_tick_failures([failure, reconciliation, resume]) == [failure]


def test_expired_intent_bound_receipt_is_denied():
    from hedge_fund.runtime.reconciliation import (
        TickIntentReconciliationPreview,
        TickIntentReconciliationReceipt,
        verify_tick_intent_reconciliation_receipt,
    )

    preview = TickIntentReconciliationPreview.create(
        required=True,
        recoverable=True,
        reason="ready",
        intent_request_id="tick-intent-1",
        intent_session="2024-06-03",
        intent_digest="a" * 64,
        metadata_complete=True,
        expected_head=None,
        current_head=None,
        broker_book_sha256="b" * 64,
        fill_identity_sha256="c" * 64,
        book_matches_ledger=True,
        head_matches_intent=True,
    )
    receipt = TickIntentReconciliationReceipt.create(
        preview=preview,
        request_id="recover-intent-expired",
        operator="web",
        recorded_at="2024-06-03T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="expired"):
        verify_tick_intent_reconciliation_receipt(preview, receipt, recorded_now="2024-06-03T00:30:01+00:00")


def test_legacy_receipts_fail_closed_and_fresh_receipts_authorize(tmp_path, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        TickIntentReconciliationPreview,
        TickIntentReconciliationReceipt,
        verify_tick_intent_reconciliation_receipt,
    )

    spec, directory, deployed, ledger, state, latest, snapshot = _failure_recovery_context(tmp_path, monkeypatch)
    failure = snapshot.failure_event
    issued_at = "2024-06-03T00:00:00+00:00"
    failure_receipt = ReconciliationReceipt.create(
        failure_event=failure,
        request_id="recover-fresh",
        current_head=snapshot.preview.current_head,
        broker_book_sha256=snapshot.preview.broker_book_sha256,
        fill_identity_sha256=snapshot.preview.fill_identity_sha256,
        operator="web",
        recorded_at=issued_at,
    )
    assert failure_receipt.issued_at == issued_at
    assert failure_receipt.valid_until == "2024-06-03T00:30:00+00:00"
    verify_reconciliation_receipt(directory, deployed, ledger, state, latest, failure_receipt, recorded_now="2024-06-03T00:01:00+00:00")

    legacy_failure_receipt = _legacy_receipt(failure_receipt)
    with pytest.raises(ValueError, match="expiry|expired"):
        verify_reconciliation_receipt(directory, deployed, ledger, state, latest, legacy_failure_receipt, recorded_now="2024-06-03T00:01:00+00:00")
    legacy_reconciliation = {"kind": "reconciliation", "receipt": legacy_failure_receipt.model_dump(mode="json")}
    legacy_resume = {"kind": "resume", "reconciliation_id": legacy_failure_receipt.receipt_id, "time": "2024-06-03T00:01:00+00:00"}
    assert unresolved_tick_failures([failure, legacy_reconciliation, legacy_resume]) == [failure]

    intent_preview = TickIntentReconciliationPreview.create(
        required=True,
        recoverable=True,
        reason="ready",
        intent_request_id="tick-intent-1",
        intent_session="2024-06-03",
        intent_digest="a" * 64,
        metadata_complete=True,
        expected_head=None,
        current_head=None,
        broker_book_sha256="b" * 64,
        fill_identity_sha256="c" * 64,
        book_matches_ledger=True,
        head_matches_intent=True,
    )
    intent_receipt = TickIntentReconciliationReceipt.create(
        preview=intent_preview,
        request_id="recover-intent-fresh",
        operator="web",
        recorded_at=issued_at,
    )
    verify_tick_intent_reconciliation_receipt(intent_preview, intent_receipt, recorded_now="2024-06-03T00:01:00+00:00")

    legacy_intent_receipt = _legacy_receipt(intent_receipt)
    with pytest.raises(ValueError, match="expiry|expired"):
        verify_tick_intent_reconciliation_receipt(intent_preview, legacy_intent_receipt, recorded_now="2024-06-03T00:01:00+00:00")


def _legacy_receipt(receipt):
    receipt_type = type(receipt)
    payload = receipt.model_dump(mode="python", exclude={"receipt_id"})
    payload.pop("issued_at", None)
    payload.pop("valid_until", None)
    candidate = receipt_type.model_construct(**payload, receipt_id="0" * 64)
    payload["receipt_id"] = candidate.compute_receipt_id()
    return receipt_type.model_validate({**payload, "receipt_id": payload["receipt_id"]})
