import importlib

import pytest

from hedge_fund.backtesting.test_fund import FakeDataClient, SERIES
from hedge_fund.brokers.models import Order
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.paper import NothingDue
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger

_DECISION = "confirm-paper-book-matches-ledger"
paper_tick_module = importlib.import_module("hedge_fund.paper.tick")


def _failed_web_tick(write_client, demo_root):
    client, _headers = write_client
    name = "demo-quality"
    directory = demo_root / "paper" / name
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    latest = ledger.latest()
    assert latest is not None

    service = client.app.state.service
    with service._paper_manual_lane(name):
        broker = PaperBroker(directory / "broker.json", deployed.spec.costs)
        broker.place_order(Order(ticker="AAPL", side="buy", quantity=100, price=100))
    with service._paper_control_lane(name):
        ledger.log_event(
            "tick_failed",
            session="2024-06-06",
            error="synthetic ambiguous tick",
            expected_head=latest.hash,
            operation_id="a" * 32,
            request_id="tick-synthetic",
            capture_id="b" * 32,
            capture_digest="c" * 64,
        )
    service.halt_fund(name, "synthetic ambiguous tick", "halt-ambiguous-tick-001")
    return client, ledger


def test_web_recovery_uses_reviewed_preview_and_retries_same_request(write_client, demo_root):
    client, _ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    sessions_before = Ledger(demo_root / "paper" / "demo-quality").sessions()

    preview_response = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    )

    assert preview_response.status_code == 200
    preview_result = preview_response.json()
    preview = preview_result["preview"]
    assert preview_result["halted"] == "synthetic ambiguous tick"
    assert preview_result["resume_allowed"] is True
    assert preview["required"] is True
    assert preview["recoverable"] is True
    assert preview["reason"] == "ready"
    request = {
        "request_id": "recover-web-1",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }

    resumed = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )
    repeated = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    assert resumed.status_code == 200
    assert resumed.json()["halted"] is False
    assert resumed.json()["reconciliation_id"] == repeated.json()["reconciliation_id"]
    assert repeated.status_code == 200
    assert ledger.halted() is None
    assert ledger.sessions() == sessions_before
    assert sum(event["kind"] == "reconciliation" for event in ledger.events()) == 1
    assert sum(event["kind"] == "resume" for event in ledger.events()) == 1


def test_web_resume_retries_after_control_clear_before_completion(write_client, demo_root, monkeypatch):
    client, ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    preview_response = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    request = {
        "request_id": "resume-after-clear-crash",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }
    original_log_event = Ledger.log_event
    original_write_control = Ledger._write_control
    failed_completion = []
    clear_writes = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and fields.get("request_id") == request["request_id"] and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic crash before Resume completion")
        return original_log_event(self, kind, **fields)

    def observe_clear_write(self, halted, reason, **kwargs):
        if halted is False:
            clear_writes.append(halted)
        return original_write_control(self, halted, reason, **kwargs)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    monkeypatch.setattr(Ledger, "_write_control", observe_clear_write)
    first = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )

    assert first.status_code == 423
    assert first.json()["code"] == "reconciliation-required"
    assert ledger.halted() is None
    assert len(ledger.unresolved_recovery_state().resume_intents) == 1
    retried = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )

    assert retried.status_code == 200
    assert retried.json()["halted"] is False
    assert clear_writes == [False]
    assert len([event for event in ledger.events() if event["kind"] == "resume_completed"]) == 1
    assert ledger.unresolved_recovery_state().required is False


def test_tick_attempt_completes_landed_resume_before_readiness_gate(write_client, demo_root, monkeypatch):
    client, ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    preview = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    ).json()["preview"]
    request = {
        "request_id": "resume-tick-between-crash-and-retry",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }
    original_log_event = Ledger.log_event
    original_write_control = Ledger._write_control
    failed_completion = []
    clear_writes = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and fields.get("request_id") == request["request_id"] and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic crash before Resume completion")
        return original_log_event(self, kind, **fields)

    def observe_clear_write(self, halted, reason, **kwargs):
        if halted is False:
            clear_writes.append(halted)
        return original_write_control(self, halted, reason, **kwargs)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    monkeypatch.setattr(Ledger, "_write_control", observe_clear_write)
    first = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )
    assert first.status_code == 423
    assert first.json()["code"] == "reconciliation-required"
    assert ledger.halted() is None
    assert len(ledger.unresolved_recovery_state().resume_intents) == 1

    monkeypatch.setattr(paper_tick_module, "next_session", lambda *_args, **_kwargs: None)
    service = client.app.state.service
    with service._paper_manual_lane("demo-quality"):
        with pytest.raises(NothingDue):
            paper_tick_module.tick(
                demo_root / "paper" / "demo-quality",
                FakeDataClient(SERIES),
            )

    retried = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json={"request_id": request["request_id"]},
    )
    assert retried.status_code == 200
    assert retried.json()["halted"] is False
    assert ledger.halted() is None
    assert clear_writes == [False]
    assert len([event for event in ledger.events() if event["kind"] == "resume_completed"]) == 1
    assert ledger.unresolved_recovery_state().required is False


def test_web_reconciliation_exposes_landed_resume_identity_after_reload(write_client, demo_root, monkeypatch):
    client, ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    preview = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    ).json()["preview"]
    request = {
        "request_id": "resume-journal-discovered",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }
    original_log_event = Ledger.log_event
    failed_completion = []

    def interrupt_before_completion(self, kind, **fields):
        if kind == "resume_completed" and fields.get("request_id") == request["request_id"] and not failed_completion:
            failed_completion.append(True)
            raise OSError("synthetic crash before Resume completion")
        return original_log_event(self, kind, **fields)

    monkeypatch.setattr(Ledger, "log_event", interrupt_before_completion)
    first = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=request,
    )
    assert first.status_code == 423
    assert ledger.halted() is None

    recovered = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    )
    assert recovered.status_code == 200
    recovery = recovered.json()
    assert recovery["halted"] is None
    assert recovery["resume_allowed"] is True
    assert recovery["resume_completion_required"] is True
    assert recovery["resume_request_id"] == request["request_id"]
    intent = ledger.unresolved_recovery_state().resume_intents[0]
    assert recovery["resume_request_id"] == intent["request_id"]

    retried = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json={"request_id": recovery["resume_request_id"]},
    )
    assert retried.status_code == 200
    assert retried.json()["halted"] is False
    assert ledger.unresolved_recovery_state().required is False


def test_web_resume_rejects_preview_after_local_book_changes(write_client, demo_root):
    client, ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    preview_response = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    confirmation = {
        "request_id": "recover-web-stale-1",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }
    deployed = load_deployed(demo_root / "paper" / "demo-quality")
    service = client.app.state.service
    with service._paper_manual_lane("demo-quality"):
        PaperBroker(demo_root / "paper" / "demo-quality" / "broker.json", deployed.spec.costs).place_order(Order(ticker="AAPL", side="buy", quantity=1, price=100))

    resumed = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=confirmation,
    )

    assert resumed.status_code == 409
    assert resumed.json()["code"] == "stale-preview"
    assert ledger.halted() == "synthetic ambiguous tick"
    assert not any(event["kind"] in {"reconciliation", "resume"} for event in ledger.events())


def test_web_resume_rechecks_book_after_receipt_issuance(write_client, demo_root, monkeypatch):
    client, ledger = _failed_web_tick(write_client, demo_root)
    headers = write_client[1]
    preview_response = client.get(
        "/api/paper/demo-quality/reconciliation",
        headers={"host": "127.0.0.1"},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    confirmation = {
        "request_id": "recover-web-rebind-1",
        "failure_id": preview["failure_id"],
        "preview_digest": preview["preview_digest"],
        "decision": _DECISION,
    }
    original_log_event = Ledger.log_event
    original_cash = PaperBroker.cash
    receipt_issued = []

    def append_then_change_book(self, kind, **fields):
        result = original_log_event(self, kind, **fields)
        if kind == "reconciliation" and fields["receipt"]["request_id"] == confirmation["request_id"] and not receipt_issued:
            receipt_issued.append(True)
        return result

    def change_book_after_issue(self):
        cash = original_cash(self)
        return cash - 1 if receipt_issued else cash

    monkeypatch.setattr(Ledger, "log_event", append_then_change_book)
    monkeypatch.setattr(PaperBroker, "cash", change_book_after_issue)
    resumed = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json=confirmation,
    )

    assert receipt_issued == [True]
    assert resumed.status_code == 423
    assert resumed.json()["code"] == "reconciliation-required"
    assert sum(event["kind"] == "reconciliation" for event in ledger.events()) == 1
    assert ledger.halted() == "synthetic ambiguous tick"
    assert not any(event["kind"] in {"resume", "resume_effect_intent"} for event in ledger.events())


def test_web_resume_permission_denies_unresolved_resume_intent(write_client, demo_root):
    client, _headers = write_client
    name = "demo-quality"
    directory = demo_root / "paper" / name
    ledger = Ledger(directory)
    latest = ledger.latest()
    assert latest is not None
    service = client.app.state.service
    service.halt_fund(name, "synthetic unresolved Resume intent", "halt-resume-intent-001")
    with service._paper_control_lane(name):
        ledger.log_event("resume_effect_intent", head_hash=latest.hash, by="web", durable=True)

    response = client.get(
        f"/api/paper/{name}/reconciliation",
        headers={"host": "127.0.0.1"},
    )

    assert response.status_code == 200
    assert response.json()["halted"] == "synthetic unresolved Resume intent"
    assert response.json()["resume_allowed"] is False


def test_readiness_denial_keeps_recovery_snapshot_available(write_client, demo_root):
    client, _headers = write_client
    name = "demo-quality"
    directory = demo_root / "paper" / name
    ledger = Ledger(directory)
    latest = ledger.latest()
    assert latest is not None
    service = client.app.state.service
    with service._paper_control_lane(name):
        ledger.log_event(
            "consume",
            decision_as_of="2024-06-06",
            decision_hash=latest.hash,
            approval_verdict="approve",
            approval_by="cli",
            approval_id="d" * 32,
            session="2024-06-07",
        )

    snapshot_response = client.get(
        f"/api/paper/{name}",
        headers={"host": "127.0.0.1"},
    )
    recovery_response = client.get(
        f"/api/paper/{name}/reconciliation",
        headers={"host": "127.0.0.1"},
    )

    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()
    assert snapshot["ledger"]["ok"] is False
    assert snapshot["recovery_state"] == "reconciliation_required"
    assert recovery_response.status_code == 200
    assert recovery_response.json()["intent_preview"]["required"] is True


def test_approval_history_issue_stays_reconciliation_required_in_endpoint_and_fund_list(write_client, demo_root):
    client, ledger = _failed_web_tick(write_client, demo_root)
    name = "demo-quality"
    latest = ledger.latest()
    assert latest is not None
    service = client.app.state.service
    with service._paper_control_lane(name):
        ledger.log_event(
            "consume",
            decision_as_of="2024-06-06",
            decision_hash=latest.hash,
            approval_verdict="approve",
            approval_by="invalid-operator",
            approval_id="d" * 32,
            session="2024-06-07",
        )

    snapshot_response = client.get(
        f"/api/paper/{name}",
        headers={"host": "127.0.0.1"},
    )
    recovery_response = client.get(
        f"/api/paper/{name}/reconciliation",
        headers={"host": "127.0.0.1"},
    )
    home_response = client.get(
        "/api/home",
        headers={"host": "127.0.0.1"},
    )

    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["recovery_state"] == "reconciliation_required"
    assert recovery_response.status_code == 423
    assert recovery_response.json()["code"] == "reconciliation-required"
    assert home_response.status_code == 200
    paper = next(item for item in home_response.json()["paper_funds"] if item["name"] == name)
    assert paper["ledger_ok"] is False
    assert paper["recovery_state"] == "reconciliation_required"
    assert paper["halted"] == "synthetic ambiguous tick"


def test_corrupt_replay_stays_distinct_from_reconciliation_required(write_client, demo_root):
    import json

    client, _headers = write_client
    name = "demo-quality"
    directory = demo_root / "paper" / name
    ledger = Ledger(directory)
    latest = ledger.latest()
    assert latest is not None
    record_path = ledger.path(latest.session)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["hash"] = "0" * 64 if record["hash"] != "0" * 64 else "1" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    snapshot_response = client.get(
        f"/api/paper/{name}",
        headers={"host": "127.0.0.1"},
    )
    recovery_response = client.get(
        f"/api/paper/{name}/reconciliation",
        headers={"host": "127.0.0.1"},
    )

    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()
    assert snapshot["ledger"]["ok"] is False
    assert snapshot["recovery_state"] == "corrupt"
    assert recovery_response.status_code == 423
    assert recovery_response.json()["code"] == "replay-corrupt"
