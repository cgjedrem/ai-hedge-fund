import hashlib
from datetime import date, timedelta

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


def _append_legacy_fixture_session(ledger, spec, admission, session: str):
    from hedge_fund.pipeline.session import SessionRecord, mandate_hash

    with admission.manual_session(spec.name, timeout=0):
        latest = ledger.latest()
        record = SessionRecord(
            fund=spec.name,
            session=session,
            universe=["AAPL"],
            nav=spec.capital,
            cash=spec.capital,
            positions={},
            marks={},
            benchmark=spec.benchmark,
            benchmark_close=100,
            rebalance=False,
            prev_hash=latest.hash if latest is not None else None,
            code_version="synthetic-recovery-fixture",
            mandate_hash=mandate_hash(spec),
        )
        record.hash = record.compute_hash()
        ledger.append(record)
    return record


def _legacy_failure_recovery_fixture(
    tmp_path,
    *,
    failure_count: int = 3,
    post_effect_indices: set[int] | None = None,
):
    from hedge_fund.paper import deploy
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext
    from hedge_fund.test_support.handover import enroll_synthetic_root

    if type(failure_count) is not int or not 1 <= failure_count <= 10:
        raise ValueError("failure_count must be an integer from 1 to 10")
    post_effect_indices = set() if post_effect_indices is None else post_effect_indices
    if not isinstance(post_effect_indices, set) or any(type(index) is not int or index < 0 or index >= failure_count for index in post_effect_indices):
        raise ValueError("post_effect_indices must identify fixture failures")
    enroll_synthetic_root(tmp_path)
    spec = FundSpec(
        schema_version=2,
        name="legacy-paper",
        strategies=[{"name": "solo", "models": [{"name": "graham"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
    )
    with RootContext.open(tmp_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.deployment_lock(spec.name, timeout=0):
                directory = deploy(spec.name, spec, ["AAPL"], root=root.path / "paper")
            ledger = Ledger(directory)
            base_record = _append_legacy_fixture_session(ledger, spec, admission, "2024-06-01")
            failure_sessions = [date(2024, 6, 2) + timedelta(days=index) for index in range(failure_count)]
            with admission.manual_session(spec.name, timeout=0):
                for index, failed_session in enumerate(failure_sessions):
                    fields = {
                        "session": failed_session.isoformat(),
                        "error": f"synthetic legacy failure {index}",
                        "expected_head": base_record.hash,
                    }
                    if index in post_effect_indices:
                        fields["transmitted_fills"] = [{"synthetic": True}]
                    ledger.log_event("tick_failed", **fields)
            later_start = date(2024, 6, 2) + timedelta(days=failure_count)
            later_records = [
                _append_legacy_fixture_session(ledger, spec, admission, (later_start + timedelta(days=index)).isoformat())
                for index in range(2)
            ]
            verified_records = []
            state = ledger.replay(spec.capital, full=True, on_verified=verified_records.append)

    events = ledger.events()
    failures = [event for event in events if event.get("kind") == "tick_failed"]
    return {
        "root": tmp_path,
        "spec": spec,
        "directory": directory,
        "ledger": ledger,
        "base_record": base_record,
        "later_records": later_records,
        "verified_records": verified_records,
        "state": state,
        "latest": verified_records[-1] if verified_records else None,
        "failures": failures,
    }


def _legacy_failure_decision(fixture, *, failure_digests=None):
    from hedge_fund.runtime.reconciliation import LegacyFailureReconciliationDecision, failure_digest
    from hedge_fund.runtime.root import RootContext

    relative = f"paper/{fixture['spec'].name}/broker.json"
    with RootContext.open(fixture["root"]) as root:
        book_digest = hashlib.sha256(root.read_bytes(relative)).hexdigest()
    return LegacyFailureReconciliationDecision.create(
        failure_digests=failure_digests or [failure_digest(event) for event in fixture["failures"]],
        ledger_head=fixture["latest"].hash,
        book_digest=book_digest,
        operator="synthetic-operator",
        recorded_time="2026-11-17T11:05:00+01:00",
        attestation=True,
    )


def _legacy_fixture_file_bytes(fixture):
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(fixture["root"]) as root:
        return {
            path.relative_to(fixture["root"]).as_posix(): root.read_bytes(path.relative_to(fixture["root"]).as_posix())
            for path in fixture["directory"].rglob("*")
            if path.is_file()
        }


def _perturb_legacy_fixture_book(fixture, admission):
    with admission.manual_session(fixture["spec"].name, timeout=0):
        broker = PaperBroker(fixture["directory"] / "broker.json", fixture["spec"].costs)
        broker.place_order(Order(ticker="AAPL", side="buy", quantity=1, price=100))


def _append_corrupt_legacy_audit_event(fixture, admission):
    from hedge_fund.runtime.root import RootContext

    relative = f"paper/{fixture['spec'].name}/events.jsonl"
    with admission.manual_session(fixture["spec"].name, timeout=0):
        with RootContext.open(fixture["root"]) as root:
            root.append_bytes(relative, b"{corrupt synthetic audit event}\n")


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


def test_legacy_failure_fixture_is_enrolled_and_replays_later_sessions(tmp_path):
    fixture = _legacy_failure_recovery_fixture(tmp_path)
    failures = fixture["failures"]
    records = fixture["verified_records"]

    assert len(failures) == 3
    assert all(event.get("request_id") is None for event in failures)
    assert all("transmitted_fills" not in event for event in failures)
    assert all(event["expected_head"] == fixture["base_record"].hash for event in failures)
    assert [record.session for record in records] == [
        "2024-06-01",
        "2024-06-05",
        "2024-06-06",
    ]
    assert fixture["state"].prev_hash == fixture["latest"].hash
    assert fixture["state"].positions == {}
    assert fixture["state"].cash == fixture["spec"].capital


def test_legacy_failure_fixture_supports_post_effect_variant(tmp_path):
    fixture = _legacy_failure_recovery_fixture(tmp_path, post_effect_indices={1})

    assert "transmitted_fills" not in fixture["failures"][0]
    assert fixture["failures"][1]["transmitted_fills"] == [{"synthetic": True}]


def test_legacy_failure_fixture_supports_corrupt_book_and_head_variants(tmp_path):
    from hedge_fund.pipeline.session import BookMismatch, reconcile
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    original_head = fixture["latest"].hash
    with RootContext.open(tmp_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            advanced = _append_legacy_fixture_session(fixture["ledger"], fixture["spec"], admission, "2024-06-07")
            assert advanced.prev_hash == original_head
            state = fixture["ledger"].replay(fixture["spec"].capital, full=True)
            _perturb_legacy_fixture_book(fixture, admission)
            broker = PaperBroker(fixture["directory"] / "broker.json", fixture["spec"].costs)
            with pytest.raises(BookMismatch):
                reconcile(state, broker, fixture["spec"].name)
            _append_corrupt_legacy_audit_event(fixture, admission)

    _events, corrupt_digests = fixture["ledger"].recovery_events_with_unresolved_corruption()
    assert corrupt_digests


def test_legacy_failure_decision_resolves_the_exact_unkeyed_set(tmp_path):
    from hedge_fund.runtime.reconciliation import unresolved_tick_failures

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    decision = _legacy_failure_decision(fixture)
    event = {"kind": "legacy_failure_reconciliation", "decision": decision.model_dump(mode="json")}

    assert decision.failure_digests == [failure_digest(failure) for failure in fixture["failures"]]
    assert unresolved_tick_failures([*fixture["failures"], event]) == []


def test_legacy_failure_decision_replay_deduplicates_and_rejects_invalid_sets(tmp_path):
    from hedge_fund.runtime.reconciliation import unresolved_tick_failures

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    decision_event = {
        "kind": "legacy_failure_reconciliation",
        "decision": _legacy_failure_decision(fixture).model_dump(mode="json"),
    }

    assert unresolved_tick_failures([*fixture["failures"], decision_event, decision_event]) == []
    invalid = _legacy_failure_decision(
        fixture,
        failure_digests=[failure_digest(fixture["failures"][0]), "f" * 64],
    )
    invalid_event = {"kind": "legacy_failure_reconciliation", "decision": invalid.model_dump(mode="json")}
    assert unresolved_tick_failures([*fixture["failures"], invalid_event]) == fixture["failures"]
    partial = _legacy_failure_decision(fixture, failure_digests=[failure_digest(fixture["failures"][0])])
    partial_event = {"kind": "legacy_failure_reconciliation", "decision": partial.model_dump(mode="json")}
    assert unresolved_tick_failures([*fixture["failures"], partial_event]) == fixture["failures"]


def test_legacy_failure_decision_requires_attestation_unique_digests_and_aware_time(tmp_path):
    from hedge_fund.runtime.reconciliation import LegacyFailureReconciliationDecision

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    fields = _legacy_failure_decision(fixture).model_dump(mode="json", exclude={"schema_version", "decision_id"})

    with pytest.raises(ValidationError):
        LegacyFailureReconciliationDecision.create(**{**fields, "attestation": False})
    with pytest.raises(ValidationError):
        LegacyFailureReconciliationDecision.create(**{**fields, "failure_digests": [fields["failure_digests"][0]] * 2})
    with pytest.raises(ValidationError):
        LegacyFailureReconciliationDecision.create(**{**fields, "recorded_time": "2026-11-17T11:05:00"})


def test_legacy_failure_decision_append_preserves_existing_bytes(tmp_path):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    before = _legacy_fixture_file_bytes(fixture)
    decision = _legacy_failure_decision(fixture)
    with RootContext.open(tmp_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.control_lane(fixture["spec"].name, timeout=0):
                fixture["ledger"].record_legacy_failure_reconciliation(decision)

    after = _legacy_fixture_file_bytes(fixture)
    event_path = f"paper/{fixture['spec'].name}/events.jsonl"
    assert set(before) == set(after)
    for relative, old_bytes in before.items():
        if relative == event_path:
            assert after[relative].startswith(old_bytes)
            assert after[relative][len(old_bytes) :].count(b"\n") == 1
        else:
            assert after[relative] == old_bytes


def test_legacy_failure_decision_append_validates_input_and_requires_lane(tmp_path):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    fixture = _legacy_failure_recovery_fixture(tmp_path)
    before = _legacy_fixture_file_bytes(fixture)
    decision = _legacy_failure_decision(fixture)

    with pytest.raises(LedgerError):
        fixture["ledger"].record_legacy_failure_reconciliation(decision)

    with RootContext.open(tmp_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.control_lane(fixture["spec"].name, timeout=0):
                with pytest.raises(LedgerError):
                    fixture["ledger"].record_legacy_failure_reconciliation({"invalid": True})
                mutated = _legacy_failure_decision(fixture)
                mutated.failure_digests.append("f" * 64)
                with pytest.raises(LedgerError):
                    fixture["ledger"].record_legacy_failure_reconciliation(mutated)

    assert _legacy_fixture_file_bytes(fixture) == before


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
    assert receipt.issued_at == "2026-11-05T08:01:00+00:00"
    assert receipt.valid_until == "2026-11-05T08:31:00+00:00"

    event = {"kind": "reconciliation", "receipt": receipt.model_dump(mode="json")}
    assert unresolved_tick_failures([failure, event]) == [failure]
    resume_identity = {
        "head_hash": "a" * 64,
        "by": "web",
        "reconciliation_id": receipt.receipt_id,
        "request_id": receipt.request_id,
        "request_action": "resume",
        "request_digest": "e" * 64,
    }
    resume = {
        "kind": "resume",
        **resume_identity,
        "time": "2026-11-05T08:01:00+00:00",
    }
    assert unresolved_tick_failures([failure, event, resume]) == [failure]
    effect_intent = {"kind": "resume_effect_intent", **resume_identity}
    assert unresolved_tick_failures([failure, event, resume, effect_intent]) == []

    changed_failure = {**failure, "expected_head": "0" * 64}
    assert unresolved_tick_failures([changed_failure, event, resume, effect_intent]) == [changed_failure]

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


def test_fresh_receipts_authorize_at_presentation(tmp_path, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        TickIntentReconciliationPreview,
        TickIntentReconciliationReceipt,
        verify_tick_intent_reconciliation_receipt,
    )

    _spec, directory, deployed, ledger, state, latest, snapshot = _failure_recovery_context(tmp_path, monkeypatch)
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


def test_legacy_receipts_are_denied_at_presentation(tmp_path, monkeypatch):
    from hedge_fund.runtime.reconciliation import (
        TickIntentReconciliationPreview,
        TickIntentReconciliationReceipt,
        verify_tick_intent_reconciliation_receipt,
    )

    _spec, directory, deployed, ledger, state, latest, snapshot = _failure_recovery_context(tmp_path, monkeypatch)
    issued_at = "2024-06-03T00:00:00+00:00"
    failure_receipt = ReconciliationReceipt.create(
        failure_event=snapshot.failure_event,
        request_id="legacy-failure-presentation",
        current_head=snapshot.preview.current_head,
        broker_book_sha256=snapshot.preview.broker_book_sha256,
        fill_identity_sha256=snapshot.preview.fill_identity_sha256,
        operator="web",
        recorded_at=issued_at,
    )
    legacy_failure_receipt = _legacy_receipt(failure_receipt)
    with pytest.raises(ValueError, match="expiry|expired"):
        verify_reconciliation_receipt(directory, deployed, ledger, state, latest, legacy_failure_receipt, recorded_now="2024-06-03T00:01:00+00:00")

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
        request_id="legacy-intent-presentation",
        operator="web",
        recorded_at=issued_at,
    )
    legacy_intent_receipt = _legacy_receipt(intent_receipt)
    with pytest.raises(ValueError, match="expiry|expired"):
        verify_tick_intent_reconciliation_receipt(intent_preview, legacy_intent_receipt, recorded_now="2024-06-03T00:01:00+00:00")


def test_legacy_failure_receipt_replay_preserves_resolution(tmp_path, monkeypatch):
    _spec, _directory, _deployed, _ledger, _state, _latest, snapshot = _failure_recovery_context(tmp_path, monkeypatch)
    receipt = ReconciliationReceipt.create(
        failure_event=snapshot.failure_event,
        request_id="legacy-failure-replay",
        current_head=snapshot.preview.current_head,
        broker_book_sha256=snapshot.preview.broker_book_sha256,
        fill_identity_sha256=snapshot.preview.fill_identity_sha256,
        operator="web",
        recorded_at="2024-06-03T00:00:00+00:00",
    )
    legacy_receipt = _legacy_receipt(receipt)
    reconciliation = {
        "kind": "reconciliation",
        "receipt": legacy_receipt.model_dump(mode="json", exclude={"issued_at", "valid_until"}),
    }
    resume = {"kind": "resume", "reconciliation_id": legacy_receipt.receipt_id, "time": "2024-06-03T00:01:00+00:00"}

    assert unresolved_tick_failures([snapshot.failure_event, reconciliation, resume]) == []


def _legacy_receipt(receipt):
    receipt_type = type(receipt)
    payload = receipt.model_dump(mode="python", exclude={"receipt_id"})
    payload.pop("issued_at", None)
    payload.pop("valid_until", None)
    candidate = receipt_type.model_construct(**payload, receipt_id="0" * 64)
    payload["receipt_id"] = candidate.compute_receipt_id()
    return receipt_type.model_validate({**payload, "receipt_id": payload["receipt_id"]})
