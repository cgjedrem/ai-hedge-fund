import json
from contextlib import contextmanager

import pytest
import yaml
from fastapi.testclient import TestClient

from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import ApprovalRequest
from hedge_fund.web.services import DeskService, ServiceError


@contextmanager
def _demo_control_lane(root, name):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(root) as context:
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.control_lane(name, timeout=0):
                yield
        finally:
            owner.close()


def _record_demo_head(root, name):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(root) as context:
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            record_ledger_head(context, name, admission=admission)
        finally:
            owner.close()


def test_approval_is_bound_to_the_displayed_timestamp_and_source_hash(write_client, demo_root):
    client, headers = write_client
    before = Ledger(demo_root / "paper" / "demo-quality").sessions()
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-bound-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    assert response.status_code == 200
    assert ledger.approval()["by"] == "web"
    assert ledger.approval()["decision_hash"] == pending["source_record_hash"]
    assert ledger.sessions() == before
    assert ledger.replay(100_000, full=True).pending.as_of == pending["decision_as_of"]


def test_approval_request_replay_returns_original_verdict_without_duplicate_event(write_client, demo_root, monkeypatch):
    client, headers = write_client
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]
    body = {
        "request_id": "approval-replay-001",
        "verdict": "approve",
        "decision_as_of": pending["decision_as_of"],
        "source_record_hash": pending["source_record_hash"],
    }

    first = client.post("/api/paper/demo-quality/approval", headers=headers, json=body)
    service = client.app.state.service
    monkeypatch.setattr(service, "_replay_paper_state", lambda *_args, **_kwargs: pytest.fail("committed request must not be replayed"))
    second = client.post("/api/paper/demo-quality/approval", headers=headers, json=body)

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    events = ledger.events()
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert ledger.approval()["approval_id"]
    assert sum(event.get("kind") == "approve" and event.get("request_id") == body["request_id"] for event in events) == 1
    assert sum(event.get("kind") == "approval_commit" and event.get("request_id") == body["request_id"] for event in events) == 1


def test_approval_request_id_conflicts_when_payload_changes(write_client, demo_root):
    client, headers = write_client
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]
    body = {
        "request_id": "approval-replay-conflict",
        "verdict": "approve",
        "decision_as_of": pending["decision_as_of"],
        "source_record_hash": pending["source_record_hash"],
    }
    first = client.post("/api/paper/demo-quality/approval", headers=headers, json=body)
    changed = {**body, "verdict": "reject"}
    second = client.post("/api/paper/demo-quality/approval", headers=headers, json=changed)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "request-conflict"
    assert Ledger(demo_root / "paper" / "demo-quality").approval()["verdict"] == "approve"


def test_stale_and_expired_approvals_fail_without_rebinding(write_client, demo_root):
    client, headers = write_client
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]
    stale = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-stale-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    with _demo_control_lane(demo_root, "demo-quality"):
        ledger.log_event(
            "expire",
            decision_as_of=pending["decision_as_of"],
            decision_hash=pending["source_record_hash"],
            reason="test expiry",
        )
    expired = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-expired-1",
            "verdict": "reject",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert expired.status_code == 409
    assert not ledger.approval()


@pytest.mark.parametrize("stale_reason", ["replacement", "expiry", "wrong_hash"])
def test_paper_detail_does_not_present_stale_mailbox_as_current(
    write_client, demo_root, monkeypatch, stale_reason
):
    from hedge_fund.paper import ledger as ledger_module

    client, headers = write_client
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]
    request = {
        "request_id": "approval-mailbox-1",
        "verdict": "approve",
        "decision_as_of": pending["decision_as_of"],
        "source_record_hash": pending["source_record_hash"],
    }
    response = client.post("/api/paper/demo-quality/approval", headers=headers, json=request)
    assert response.status_code == 200
    assert client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["approval"]["verdict"] == "approve"
    ledger = Ledger(demo_root / "paper" / "demo-quality")

    if stale_reason == "replacement":
        write_atomic = ledger_module.write_atomic

        def fail_mailbox(path, text, **kwargs):
            if path == ledger.approval_path:
                raise OSError("synthetic staged mailbox failure")
            return write_atomic(path, text, **kwargs)

        monkeypatch.setattr(ledger_module, "write_atomic", fail_mailbox)
        response = client.post(
            "/api/paper/demo-quality/approval",
            headers=headers,
            json={**request, "request_id": "approval-mailbox-replacement-1", "verdict": "reject"},
        )
        assert response.status_code == 409
    elif stale_reason == "expiry":
        with _demo_control_lane(demo_root, "demo-quality"):
            ledger.log_event(
                "expire",
                decision_as_of=pending["decision_as_of"],
                decision_hash=pending["source_record_hash"],
                reason="synthetic expiry",
                durable=True,
            )
    else:
        mailbox = ledger.approval()
        mailbox["decision_hash"] = "0" * 64 if pending["source_record_hash"] != "0" * 64 else "1" * 64
        with _demo_control_lane(demo_root, "demo-quality"):
            ledger.approval_path.write_text(json.dumps(mailbox), encoding="utf-8")

    assert ledger.approval() is not None
    after = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    assert after["approval"] is None
    assert after["pending"] == pending


def test_paper_detail_exposes_unfinished_approval_reconciliation(write_client, demo_root):
    client, headers = write_client
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]
    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-reconciliation-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )
    assert response.status_code == 200
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    approval = ledger.approval()
    with _demo_control_lane(demo_root, "demo-quality"):
        ledger.log_event(
            "consume",
            decision_as_of=approval["decision_as_of"],
            decision_hash=approval["decision_hash"],
            approval_verdict=approval["verdict"],
            approval_by=approval["by"],
            approval_id=approval["approval_id"],
            session="2025-01-07",
            durable=True,
        )

    after = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    assert not after["ledger"]["ok"]
    assert "reconciliation" in after["ledger"]["error"].lower()
    assert after["approval"] is None


def test_paper_detail_detects_consumption_during_verdict_read(write_client, demo_root, monkeypatch):
    client, headers = write_client
    before = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = before["pending"]
    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-consumption-race-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )
    assert response.status_code == 200
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    approval = ledger.approval()
    resolve = Ledger.resolve_approval
    consumed = False

    def consume_before_resolution(self, *args, **kwargs):
        nonlocal consumed
        if self.directory == ledger.directory and not consumed:
            consumed = True
            with _demo_control_lane(demo_root, "demo-quality"):
                ledger.log_event(
                    "consume",
                    decision_as_of=approval["decision_as_of"],
                    decision_hash=approval["decision_hash"],
                    approval_verdict=approval["verdict"],
                    approval_by=approval["by"],
                    approval_id=approval["approval_id"],
                    session="2025-01-07",
                    durable=True,
                )
        return resolve(self, *args, **kwargs)

    monkeypatch.setattr(Ledger, "resolve_approval", consume_before_resolution)
    after = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    assert consumed
    assert not after["ledger"]["ok"]
    assert "in progress or requires reconciliation" in after["ledger"]["error"].lower()
    assert after["approval"] is None


def test_approval_is_rejected_when_gate_is_disabled(write_client, demo_root):
    client, headers = write_client
    from hedge_fund.fund import load_spec
    from hedge_fund.web.schemas import DeployRequest

    service = client.app.state.service
    spec = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_copy(update={"name": "no-gate", "approval_required": False})
    service.create_mandate(spec.model_dump(mode="python"))
    service.deploy_mandate("no-gate", DeployRequest(universe=["AAPL", "MSFT"]))

    response = client.post(
        "/api/paper/no-gate/approval",
        headers=headers,
        json={
            "request_id": "approval-no-gate-1",
            "verdict": "approve",
            "decision_as_of": "2024-06-05",
            "source_record_hash": "0" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This fund does not require approval."
    assert not (demo_root / "paper" / "no-gate" / "pending-approval.json").exists()


def test_approval_is_rejected_for_halted_fund(write_client, demo_root):
    client, headers = write_client
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]
    with _demo_control_lane(demo_root, "demo-quality"):
        ledger.halt("test pause")

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-halted-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 423
    assert response.json()["detail"] == "Halted funds cannot accept a verdict."
    assert response.json()["code"] == "halted"
    assert response.json()["subject_id"] == "demo-quality"
    assert not ledger.approval()


@pytest.mark.parametrize("contents", ["{", "[]", "{}"])
def test_approval_is_rejected_when_control_is_unreadable(write_client, demo_root, contents):
    client, headers = write_client
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]
    control = demo_root / "paper" / "demo-quality" / "control.json"
    control.write_text(contents, encoding="utf-8")

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "request_id": "approval-control-corrupt-1",
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 423
    assert response.json()["detail"] == "Paper state is invalid (LedgerError)."
    assert response.json()["code"] == "replay-corrupt"
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()


def test_halt_and_resume_record_control_without_repeating_work(tmp_path):
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    with TestClient(
        create_app(root=root, allow_writes=True, demo=True),
        client=("127.0.0.1", 50000),
    ) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"request_id": "halt-manual-001", "reason": "operator pause"})
        current = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers, json={"request_id": "resume-manual-001"})

    ledger = Ledger(root / "paper" / "demo-quality")
    assert halted.status_code == 200
    assert current["halted"] == "operator pause"
    assert resumed.status_code == 200
    assert resumed.json() == {"name": "demo-quality", "halted": False, "reconciliation_id": None}
    assert ledger.halted() is None
    assert [event["kind"] for event in ledger.events()][-5:] == ["halt_intent", "halt", "resume", "resume_effect_intent", "resume_completed"]


def test_halt_request_replay_is_idempotent_and_payload_bound(write_client, demo_root):
    client, headers = write_client
    body = {"request_id": "halt-replay-001", "reason": "operator pause"}

    first = client.post("/api/paper/demo-quality/halt", headers=headers, json=body)
    repeated = client.post("/api/paper/demo-quality/halt", headers=headers, json=body)
    changed = client.post(
        "/api/paper/demo-quality/halt",
        headers=headers,
        json={**body, "reason": "different pause"},
    )

    events = Ledger(demo_root / "paper" / "demo-quality").events()
    assert first.status_code == repeated.status_code == 200
    assert repeated.json() == first.json()
    assert changed.status_code == 409
    assert changed.json()["code"] == "request-conflict"
    assert sum(event.get("kind") == "halt" and event.get("request_id") == body["request_id"] for event in events) == 1
    assert sum(event.get("kind") == "halt_intent" and event.get("request_id") == body["request_id"] for event in events) == 1


def test_halt_retries_an_uncommitted_intent_without_duplicate_audit(write_client, demo_root, monkeypatch):
    client, headers = write_client
    original = Ledger._write_control
    attempts = []

    def fail_before_control(self, halted, reason, **kwargs):
        attempts.append(halted)
        if len(attempts) == 1:
            raise OSError("synthetic control write failure")
        return original(self, halted, reason, **kwargs)

    monkeypatch.setattr(Ledger, "_write_control", fail_before_control)
    body = {"request_id": "halt-incomplete-intent-001", "reason": "operator pause"}

    first = client.post("/api/paper/demo-quality/halt", headers=headers, json=body)
    retry = client.post("/api/paper/demo-quality/halt", headers=headers, json=body)

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    events = ledger.events()
    assert first.status_code == 409
    assert retry.status_code == 200
    assert attempts == [True, True]
    assert ledger.halted() == body["reason"]
    assert sum(event.get("kind") == "halt_intent" and event.get("request_id") == body["request_id"] for event in events) == 1
    assert sum(event.get("kind") == "halt" and event.get("request_id") == body["request_id"] for event in events) == 1


def test_manual_resume_request_replay_returns_original_result_and_conflicts_on_payload_change(write_client, demo_root):
    client, headers = write_client
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    with _demo_control_lane(demo_root, "demo-quality"):
        ledger.halt("operator pause", request_id="halt-manual-resume-001")
    body = {"request_id": "resume-replay-001"}

    first = client.post("/api/paper/demo-quality/resume", headers=headers, json=body)
    repeated = client.post("/api/paper/demo-quality/resume", headers=headers, json=body)
    changed = client.post(
        "/api/paper/demo-quality/resume",
        headers=headers,
        json={
            **body,
            "failure_id": "a" * 64,
            "preview_digest": "b" * 64,
            "decision": "confirm-paper-book-matches-ledger",
        },
    )

    events = ledger.events()
    assert first.status_code == repeated.status_code == 200, (first.json(), repeated.json(), changed.json())
    assert repeated.json() == first.json()
    assert changed.status_code == 409
    assert changed.json()["code"] == "request-conflict"
    assert ledger.halted() is None
    assert sum(event.get("kind") == "resume_completed" and event.get("request_id") == body["request_id"] for event in events) == 1


def test_resume_does_not_repeat_after_uncertain_control_write(write_client, demo_root, monkeypatch):
    client, headers = write_client
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    with _demo_control_lane(demo_root, "demo-quality"):
        ledger.halt("operator pause", request_id="halt-before-uncertain-resume-001")
    original = Ledger._write_control
    attempts = []

    def fail_clear(self, halted, reason, **kwargs):
        attempts.append(halted)
        if halted is False:
            raise OSError("synthetic Resume control write failure")
        return original(self, halted, reason, **kwargs)

    monkeypatch.setattr(Ledger, "_write_control", fail_clear)
    body = {"request_id": "resume-uncertain-control-001"}
    first = client.post("/api/paper/demo-quality/resume", headers=headers, json=body)
    retry = client.post("/api/paper/demo-quality/resume", headers=headers, json=body)

    events = ledger.events()
    assert first.status_code == retry.status_code == 423
    assert first.json()["code"] == retry.json()["code"] == "reconciliation-required"
    assert attempts == [False]
    assert ledger.halted() == "operator pause"
    assert sum(event.get("kind") == "resume" and event.get("request_id") == body["request_id"] for event in events) == 1
    assert sum(event.get("kind") == "resume_effect_intent" and event.get("request_id") == body["request_id"] for event in events) == 1
    assert sum(event.get("kind") == "resume_completed" and event.get("request_id") == body["request_id"] for event in events) == 0


def test_halt_works_for_corrupt_ledger_but_resume_still_requires_valid_replay(demo_root):
    path = demo_root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["cash"] = 1
    path.write_text(json.dumps(record), encoding="utf-8")
    with TestClient(
        create_app(root=demo_root, allow_writes=True, demo=True),
        client=("127.0.0.1", 50000),
    ) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"request_id": "halt-corrupt-ledger-001", "reason": "ledger review"})
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers, json={"request_id": "resume-corrupt-ledger-001"})

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    assert halted.status_code == 200
    assert ledger.halted() == "ledger review"
    assert resumed.status_code == 423
    assert ledger.halted() == "ledger review"


def test_emergency_halt_recovers_an_unreadable_control_file(demo_root):
    control = demo_root / "paper" / "demo-quality" / "control.json"
    control.write_text("{", encoding="utf-8")
    with TestClient(
        create_app(root=demo_root, allow_writes=True, demo=True),
        client=("127.0.0.1", 50000),
    ) as client:
        capabilities = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1"},
        ).json()
        token = capabilities["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        halted = client.post(
            "/api/paper/demo-quality/halt",
            headers=headers,
            json={"request_id": "halt-control-recovery-001", "reason": "control recovery"},
        )

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    assert capabilities["read_only"] is True
    assert capabilities["writes"] is False
    assert capabilities["write_unavailable_reason"] == "ledger-drift"
    assert isinstance(token, str) and token
    assert halted.status_code == 200
    assert ledger.halted() == "control recovery"


def test_protected_name_guard_runs_before_fund_adapter(tmp_path, monkeypatch):
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
    app = create_app(root=tmp_path, allow_writes=True)
    service = app.state.service
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected fund adapter must not run")

    monkeypatch.setattr(service, "_paper_control_state", forbidden)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        response = client.post(
            "/api/paper/WATCHTOWER/halt",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": token,
            },
            json={"request_id": "halt-protected-001", "reason": "not allowed"},
        )

    assert response.status_code == 403
    assert not called
    assert not (tmp_path / "paper").exists()


def test_protected_windows_aliases_are_rejected_before_control_writes(tmp_path, monkeypatch):
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "temporary-root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
    app = create_app(root=root, allow_writes=True)
    service = app.state.service
    fund_dir = root / "paper" / "watchtower"
    fund_dir.mkdir(parents=True)
    control = fund_dir / "control.json"
    events = fund_dir / "events.jsonl"
    control.write_text('{"halted": false}\n', encoding="utf-8")
    events.write_text("", encoding="utf-8")
    before_control = control.read_bytes()
    before_events = events.read_bytes()
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected path must not reach a paper adapter")

    monkeypatch.setattr(service, "_paper_control_state", forbidden)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        canonical = client.post("/api/paper/watchtower/halt", headers=headers, json={"request_id": "halt-protected-002", "reason": "blocked"})
        trailing_dot = client.post("/api/paper/watchtower./halt", headers=headers, json={"request_id": "halt-protected-003", "reason": "blocked"})
        trailing_space = client.post("/api/paper/watchtower%20/halt", headers=headers, json={"request_id": "halt-protected-004", "reason": "blocked"})

    assert canonical.status_code == 403
    assert trailing_dot.status_code == 400
    assert trailing_space.status_code == 400
    assert not called
    assert control.read_bytes() == before_control
    assert events.read_bytes() == before_events
    assert not (fund_dir / "pending-approval.json").exists()


@pytest.mark.parametrize("action", ["approve", "halt", "resume", "runner-stop"])
def test_nonlocal_broker_mutations_stop_before_ledger_adapter(demo_root, monkeypatch, action):
    directory = demo_root / "paper" / "demo-quality"
    deployed_path = directory / "fund.yaml"
    deployed = yaml.safe_load(deployed_path.read_text(encoding="utf-8"))
    deployed["broker"] = "saxo"
    deployed_path.write_text(yaml.safe_dump(deployed, sort_keys=False), encoding="utf-8")
    _record_demo_head(demo_root, "demo-quality")
    pending = Ledger(directory).replay(
        deployed["spec"]["capital"],
        full=True,
    ).pending
    assert pending is not None
    request = ApprovalRequest(
        request_id="approval-nonlocal-1",
        verdict="approve",
        decision_as_of=pending.as_of,
        source_record_hash=Ledger(directory).replay(
            deployed["spec"]["capital"],
            full=True,
        ).prev_hash,
    )
    service = DeskService(demo_root, allow_writes=True)
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("non-local paper mutation reached the ledger adapter")

    monkeypatch.setattr("hedge_fund.web.services.Ledger", forbidden)
    try:
        with pytest.raises(ServiceError) as rejected:
            if action == "approve":
                service.approve("demo-quality", request)
            elif action == "halt":
                service.halt_fund("demo-quality", "must not write", "halt-nonlocal-001")
            elif action == "runner-stop":
                monkeypatch.setattr(service._runner_manager, "request_stop", forbidden)
                service.stop_runner("demo-quality")
            else:
                service.resume_fund("demo-quality")
    finally:
        service.close()

    assert rejected.value.status_code == 403
    assert not called


def test_saxo_web_routes_deny_before_provider_or_writer_effects(
    demo_root,
    monkeypatch,
):
    from hedge_fund.fund import FundSpec, load_spec
    from hedge_fund.paper.ledger import Ledger as RealLedger
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.web import services as service_module

    deployed_dir = demo_root / "paper" / "demo-quality"
    deployed_path = deployed_dir / "fund.yaml"
    app = create_app(
        root=demo_root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=lambda: pytest.fail("SIM route reached the data client"),
    )
    service = app.state.service
    try:
        sim_payload = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_dump(mode="python")
        sim_payload.update(
            {
                "name": "saxo-route",
                "broker": "saxo",
                "rebalance": "minute",
                "interval": 5.0,
                "window": {"start": "09:30", "end": "15:59"},
            }
        )
        sim_spec = FundSpec.model_validate(sim_payload)
        service.create_mandate(sim_spec.model_dump(mode="python"))

        deployed = yaml.safe_load(deployed_path.read_text(encoding="utf-8"))
        deployed["broker"] = "saxo"
        deployed_path.write_text(
            yaml.safe_dump(deployed, sort_keys=False),
            encoding="utf-8",
        )
        record_ledger_head(
            service.root_context,
            "demo-quality",
            admission=service._admission,
        )
        head = RealLedger(deployed_dir).latest().hash
        events_path = deployed_dir / "events.jsonl"
        before_events = events_path.read_bytes() if events_path.exists() else None
        paths = [
            (
                "/api/paper/demo-quality/approval",
                {
                    "request_id": "approval-sim-denied-1",
                    "verdict": "approve",
                    "decision_as_of": "2024-06-05",
                    "source_record_hash": "b" * 64,
                },
            ),
            ("/api/paper/demo-quality/halt", {"request_id": "halt-sim-denied-001", "reason": "blocked"}),
            ("/api/paper/demo-quality/resume", {"request_id": "resume-sim-denied-001"}),
            ("/api/paper/demo-quality/runner/stop", None),
            ("/api/paper/demo-quality/tick/preview", {"expected_head": head}),
            ("/api/paper/demo-quality/runner/preview", {"expected_head": head}),
            ("/api/paper/demo-quality/valuation", {"expected_head": head}),
            ("/api/mandates/saxo-route/deploy", {"universe": ["AAPL"]}),
        ]
        called = []

        def forbidden(*_args, **_kwargs):
            called.append(True)
            raise AssertionError("SIM route reached a writer or process adapter")

        monkeypatch.setattr(service_module, "Ledger", forbidden)
        monkeypatch.setattr(service_module, "deploy", forbidden)
        monkeypatch.setattr(service._runner_manager, "request_stop", forbidden)
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            capability = client.get(
                "/api/capabilities",
                headers={"host": "127.0.0.1"},
            ).json()
            headers = {
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": capability["mutation_token"],
            }
            results = [client.post(f"/{path.lstrip('/')}", headers=headers, json=body) if body is not None else client.post(f"/{path.lstrip('/')}", headers=headers) for path, body in paths]
    finally:
        service.close()

    assert [response.status_code for response in results] == [403] * len(paths)
    assert {(response.json()["code"], response.json()["retry_policy"]) for response in results} == {("broker-not-web-supported", "none")}
    assert called == []
    after_events = events_path.read_bytes() if events_path.exists() else None
    assert after_events == before_events
    assert not (deployed_dir / "pending-approval.json").exists()
    assert not (demo_root / "paper" / "saxo-route").exists()


def test_saxo_accept_routes_reject_previews_before_worker_or_ledger_effects(
    demo_root,
    monkeypatch,
):
    from hedge_fund.data.models import Price
    from hedge_fund.fund import load_spec
    from hedge_fund.paper.ledger import Ledger as RealLedger
    from hedge_fund.runtime.configuration import RuntimeSettings
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.web import services as service_module
    from hedge_fund.web.schemas import DeployRequest

    class OfflineData:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_prices(self, ticker, start_date, end_date, **_kwargs):
            self.calls.append((ticker, start_date, end_date))
            if start_date > end_date:
                return []
            return [
                Price(
                    open=100,
                    close=101,
                    high=102,
                    low=99,
                    volume=1000,
                    time=f"{end_date}T16:00:00-04:00",
                )
            ]

    data = OfflineData()
    app = create_app(
        root=demo_root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=lambda: data,
    )
    service = app.state.service
    service._runtime_settings = RuntimeSettings(
        data_provider="yfinance",
        llm_provider="Ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
        timeout_seconds=1,
        parameters={"max_tokens": 32},
        version=0,
    )
    name = "saxo-accept-route"
    spec = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_copy(update={"name": name})
    service.create_mandate(spec.model_dump(mode="python"))
    service.deploy_mandate(name, DeployRequest(universe=["AAPL", "MSFT"]))
    directory = demo_root / "paper" / name
    deployed_path = directory / "fund.yaml"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("SIM acceptance reached a writer or worker")

    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            capability = client.get(
                "/api/capabilities",
                headers={"host": "127.0.0.1"},
            ).json()
            headers = {
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": capability["mutation_token"],
            }
            manual_preview = client.post(
                f"/api/paper/{name}/tick/preview",
                headers=headers,
                json={"expected_head": None},
            )
            runner_preview = client.post(
                f"/api/paper/{name}/runner/preview",
                headers=headers,
                json={"expected_head": None},
            )
            assert manual_preview.status_code == 201
            assert runner_preview.status_code == 201
            calls_before_accept = len(data.calls)

            deployed = yaml.safe_load(deployed_path.read_text(encoding="utf-8"))
            deployed["broker"] = "saxo"
            deployed_path.write_text(
                yaml.safe_dump(deployed, sort_keys=False),
                encoding="utf-8",
            )
            record_ledger_head(
                service.root_context,
                name,
                admission=service._admission,
            )
            events_path = directory / "events.jsonl"
            before_events = events_path.read_bytes() if events_path.exists() else None
            head = RealLedger(directory).latest()
            assert head is None

            monkeypatch.setattr(service_module, "Ledger", forbidden)
            monkeypatch.setattr(
                service._paper_operation_jobs,
                "submit",
                forbidden,
            )
            manual = manual_preview.json()
            manual_accept = client.post(
                f"/api/paper/{name}/tick",
                headers=headers,
                json={
                    "request_id": "saxo-manual-accept",
                    "preview_id": manual["preview_id"],
                    "preview_digest": manual["preview_digest"],
                    "confirmation_token": manual["confirmation_token"],
                    "expected_head": None,
                    "due_set": manual["due_set"],
                },
            )
            runner = runner_preview.json()
            runner_accept = client.post(
                f"/api/paper/{name}/runner",
                headers=headers,
                json={
                    "request_id": "saxo-runner-accept",
                    "preview_id": runner["preview_id"],
                    "preview_digest": runner["preview_digest"],
                    "confirmation_token": runner["confirmation_token"],
                    "expected_head": None,
                    "due_set": runner["due_set"],
                    "max_sessions": runner["payload"]["max_sessions"],
                    "max_runtime_minutes": runner["payload"]["max_runtime_minutes"],
                },
            )
            accepted_operations = service._operation_store.list_operations()
    finally:
        service.close()

    assert manual_accept.status_code == 403
    assert runner_accept.status_code == 403
    assert len(data.calls) == calls_before_accept
    after_events = events_path.read_bytes() if events_path.exists() else None
    assert after_events == before_events
    assert accepted_operations == ()


def test_web_halt_enters_halt_only_lane(tmp_path, monkeypatch):
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    acquired = []
    original = service._admission.halt_lane

    @contextmanager
    def observe(identity, *, timeout):
        acquired.append((identity, timeout))
        with original(identity, timeout=timeout):
            yield

    monkeypatch.setattr(service._admission, "halt_lane", observe)
    try:
        result = service.halt_fund("demo-quality", "operator pause", "halt-lane-001")
    finally:
        service.close()

    assert result == {"name": "demo-quality", "halted": True}
    assert acquired == [("demo-quality", 0.1)]


def test_web_halt_succeeds_while_a_control_scan_is_in_flight(tmp_path):
    from threading import Event, Thread

    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    entered = Event()
    release = Event()
    failures = []

    def long_control_scan():
        try:
            with service._admission.control_lane("demo-quality"):
                entered.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release control scan")
        except BaseException as exc:
            failures.append(exc)

    holder = Thread(target=long_control_scan, name="slow-control-scan")
    holder.start()
    try:
        assert entered.wait(timeout=10), failures
        result = service.halt_fund("demo-quality", "synthetic emergency", "halt-control-inflight-001")
        assert result == {"name": "demo-quality", "halted": True}
        assert Ledger(root / "paper" / "demo-quality").halted() == "synthetic emergency"
    finally:
        release.set()
        holder.join(timeout=10)
        service.close()
    assert not holder.is_alive()
    assert failures == []


def test_web_halt_reports_applied_switch_when_audit_is_unavailable(tmp_path):
    from threading import Event, Thread

    from hedge_fund.web.demo import seed_demo
    from hedge_fund.web.services import ServiceError

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    held = Event()
    release = Event()
    failures = []

    def hold_audit():
        try:
            with service._admission.audit_lane("demo-quality"):
                held.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release audit lane")
        except BaseException as exc:
            failures.append(exc)

    holder = Thread(target=hold_audit, name="slow-audit-writer")
    holder.start()
    try:
        assert held.wait(timeout=10), failures
        with pytest.raises(ServiceError) as error:
            service.halt_fund("demo-quality", "synthetic emergency", "halt-audit-unavailable-001")
        assert error.value.status_code == 423
        assert "Halt was applied" in error.value.detail
        assert "audit" in error.value.detail
        assert Ledger(root / "paper" / "demo-quality").halted() == "synthetic emergency"
    finally:
        release.set()
        holder.join(timeout=10)
        service.close()
    assert not holder.is_alive()
    assert failures == []


def test_archive_cannot_move_a_fund_during_an_inflight_halt(tmp_path, monkeypatch):
    from threading import Event, Thread

    from hedge_fund.runtime.admission import WriterConflict
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    store = LifecycleArchiveStore(service.root_context, service._admission)
    preview = store.preview("deployment", "demo-quality")
    validated = Event()
    release = Event()
    results = []
    failures = []
    control_state = service._paper_control_state

    def pause_after_validation(name):
        state = control_state(name)
        validated.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test did not release Halt")
        return state

    def halt():
        try:
            results.append(service.halt_fund("demo-quality", "synthetic emergency", "halt-archive-race-001"))
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(service, "_paper_control_state", pause_after_validation)
    worker = Thread(target=halt, name="lifecycle-halt")
    worker.start()
    archive_error = None
    archive_result = None
    try:
        assert validated.wait(timeout=10), failures
        try:
            archive_result = store.archive(
                "deployment",
                "demo-quality",
                expected_digest=preview["digest"],
                archive_id="e" * 32,
            )
        except WriterConflict as exc:
            archive_error = exc
    finally:
        release.set()
        worker.join(timeout=10)
        service.close()
    assert not worker.is_alive()
    assert archive_error is not None, f"archive={archive_result!r}, halt={results!r}, failures={failures!r}"
    assert failures == []
    assert results == [{"name": "demo-quality", "halted": True}]
    assert Ledger(root / "paper" / "demo-quality").halted() == "synthetic emergency"


def test_web_halt_fences_an_inflight_verdict_before_it_commits(tmp_path, monkeypatch):
    from pathlib import Path
    from threading import Event, Thread

    from hedge_fund.paper import ledger as ledger_module
    from hedge_fund.paper.ledger import ApprovalHalted
    from hedge_fund.runtime.admission import paper_approval_transition
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    ledger = Ledger(root / "paper" / "demo-quality")
    latest = ledger.latest()
    assert latest is not None and latest.decision is not None
    before_commit = Event()
    release = Event()
    outcomes = []
    write_atomic = ledger_module.write_atomic

    def pause_pending_mailbox(path, text, **kwargs):
        if Path(path) == ledger.approval_path and json.loads(text).get("pending"):
            result = write_atomic(path, text, **kwargs)
            before_commit.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release verdict publisher")
            return result
        return write_atomic(path, text, **kwargs)

    def publish():
        try:
            with paper_approval_transition(service._admission, "demo-quality") as proof:
                ledger.set_approval("approve", latest.decision.as_of, latest.hash, "web", admission=proof)
            outcomes.append("approved")
        except BaseException as exc:
            outcomes.append(exc)

    monkeypatch.setattr(ledger_module, "write_atomic", pause_pending_mailbox)
    publisher = Thread(target=publish, name="inflight-verdict")
    publisher.start()
    try:
        assert before_commit.wait(timeout=10), outcomes
        assert service.halt_fund("demo-quality", "synthetic emergency", "halt-verdict-race-001")["halted"]
    finally:
        release.set()
        publisher.join(timeout=10)
        service.close()

    assert not publisher.is_alive()
    assert len(outcomes) == 1 and isinstance(outcomes[0], ApprovalHalted)
    assert ledger.halted() == "synthetic emergency"
    assert ledger.resolve_approval(latest.decision.as_of, latest.hash)[0] is None


def test_web_halt_fences_cli_approval_publication_across_processes(write_client, demo_root, tmp_path, owned_test_process):
    import time

    from hedge_fund.runtime.admission import MAX_CONTROL_WAIT_SECONDS

    client, headers = write_client
    directory = demo_root / "paper" / "demo-quality"
    ledger = Ledger(directory)
    latest = ledger.latest()
    before_sessions = ledger.sessions()
    before_records = {path.name: path.read_bytes() for path in (directory / "ledger").glob("*.json")}
    ready = tmp_path / "approval-pending"
    release = tmp_path / "approval-release"
    result = tmp_path / "approval-result"
    script = "\n".join(
        [
            "import json, sys, time",
            "from pathlib import Path",
            "import hedge_fund.paper.ledger as ledger_module",
            "from hedge_fund import run",
            f"ready, release, result = Path({str(ready)!r}), Path({str(release)!r}), Path({str(result)!r})",
            "original_write = ledger_module.write_atomic",
            "def paused_write(path, text, **kwargs):",
            "    written = original_write(path, text, **kwargs)",
            "    if Path(path).name == 'pending-approval.json' and json.loads(text).get('pending') is True:",
            "        ready.write_text('pending', encoding='utf-8')",
            "        deadline = time.monotonic() + 30",
            "        while not release.exists() and time.monotonic() < deadline: time.sleep(0.01)",
            "        if not release.exists(): raise TimeoutError('approval release missing')",
            "    return written",
            "ledger_module.write_atomic = paused_write",
            f"sys.argv = ['aihf', '--root', {str(demo_root)!r}, 'paper', 'approve', 'demo-quality', '--expected-head', {latest.hash!r}, '--request-id', 'approval-cross-process-001']",
            "try:",
            "    run.main()",
            "except SystemExit as exc:",
            "    outcome = str(exc.code)",
            "else:",
            "    outcome = 'returned'",
            "result.write_text(outcome, encoding='utf-8')",
        ]
    )
    child = owned_test_process(script)
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), f"CLI approval did not reach pending publication: {child.poll()}"
        started = time.monotonic()
        response = client.post("/api/paper/demo-quality/halt", headers=headers, json={"request_id": "halt-bounded-control-001", "reason": "synthetic emergency"})
        elapsed = time.monotonic() - started
        assert response.status_code == 200
        assert elapsed < MAX_CONTROL_WAIT_SECONDS + 5
    finally:
        release.write_text("release", encoding="utf-8")
        assert child.wait(timeout=30) == 0

    assert result.read_text(encoding="utf-8") == "1"
    assert ledger.halted() == "synthetic emergency"
    assert ledger.approval() is None
    assert ledger.resolve_approval(latest.decision.as_of, latest.hash)[0] is None
    assert ledger.sessions() == before_sessions
    assert {path.name: path.read_bytes() for path in (directory / "ledger").glob("*.json")} == before_records
    event = ledger._latest_approval_event(latest.decision.as_of, latest.hash, strict=True)
    assert event["kind"] == "expire"
    assert event["decision_hash"] == latest.hash


def test_halt_cannot_acknowledge_during_verdict_commit_before_a_publisher_crash(tmp_path, monkeypatch):
    from threading import Event, Thread

    from hedge_fund.runtime.admission import paper_approval_transition
    from hedge_fund.web.demo import seed_demo
    from hedge_fund.web.services import ServiceError

    class PublisherCrash(BaseException):
        pass

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    ledger = Ledger(root / "paper" / "demo-quality")
    latest = ledger.latest()
    assert latest is not None and latest.decision is not None
    committed = Event()
    release = Event()
    failures = []
    write_state = ledger._write_approval_publication

    def crash_after_marker(approval_id, state):
        write_state(approval_id, state)
        if state == "committed":
            committed.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release verdict publisher")
            raise PublisherCrash()

    def publish():
        try:
            with paper_approval_transition(service._admission, "demo-quality") as proof:
                ledger.set_approval("approve", latest.decision.as_of, latest.hash, "web", admission=proof)
        except PublisherCrash:
            pass
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(ledger, "_write_approval_publication", crash_after_marker)
    worker = Thread(target=publish, name="crashing-verdict")
    worker.start()
    try:
        try:
            assert committed.wait(timeout=10), failures
            with pytest.raises(ServiceError) as blocked:
                service.halt_fund("demo-quality", "synthetic emergency", "halt-publisher-crash-001")
            assert blocked.value.status_code == 409
        finally:
            release.set()
            worker.join(timeout=10)
        assert not worker.is_alive()
        assert failures == []
        assert service.halt_fund("demo-quality", "synthetic emergency", "halt-publisher-crash-001")["halted"]
        assert ledger.halted() == "synthetic emergency"
    finally:
        service.close()


def test_web_halt_does_not_wait_for_fund_work_lock(tmp_path):
    from threading import Event, Thread

    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    work_lock = service._fund_lock("demo-quality")
    completed = Event()
    result = []
    failures = []

    def halt():
        try:
            result.append(service.halt_fund("demo-quality", "operator pause", "halt-lock-independent-001"))
        except Exception as exc:
            failures.append(exc)
        finally:
            completed.set()

    work_lock.acquire()
    thread = Thread(target=halt)
    try:
        thread.start()
        # The work lock stays held until after this wait, so any finite bound proves
        # halt does not wait for it; admitted control writes need headroom under load.
        responsive = completed.wait(timeout=5)
    finally:
        work_lock.release()
        thread.join(timeout=2)
        service.close()

    assert responsive
    assert not thread.is_alive()
    assert failures == []
    assert result == [{"name": "demo-quality", "halted": True}]
    assert Ledger(root / "paper" / "demo-quality").halted() == "operator pause"


def test_capabilities_explain_deferred_runner_ownership(tmp_path):
    app = create_app(root=tmp_path)
    service = app.state.service
    try:
        result = service.capabilities(None)
    finally:
        service.close()

    assert "unavailable" in result["deferred_actions"]["runner"]
    assert "disabled" in result["deferred_actions"]["manual_run"]
    assert result["write_unavailable_reason"] == "handover-required"


@pytest.mark.parametrize(
    ("action", "filename"),
    [
        ("approve", "pending-approval.json"),
        ("approve", "control.json"),
        ("approve", "events.jsonl"),
        ("resume", "control.json"),
        ("resume", "events.jsonl"),
        ("resume", "pending-approval.json"),
    ],
)
def test_approval_and_resume_reject_symlinked_control_files(demo_root, tmp_path, action, filename):
    directory = demo_root / "paper" / "demo-quality"
    deployed = load_deployed(directory)
    state = Ledger(directory).replay(deployed.spec.capital, full=True)
    assert state.pending is not None
    request = ApprovalRequest(
        request_id="approval-symlink-1",
        verdict="approve",
        decision_as_of=state.pending.as_of,
        source_record_hash=state.prev_hash,
    )
    if filename == "pending-approval.json":
        target_contents = json.dumps(
            {
                "verdict": "reject",
                "decision_as_of": state.pending.as_of,
                "decision_hash": state.prev_hash,
                "decided_at": "2026-10-31T12:00:00+00:00",
                "by": "tui",
            }
        )
    elif filename == "control.json":
        target_contents = '{"halted": false}\n'
    else:
        target_contents = '{"time":"2026-10-31T12:00:00+00:00","kind":"audit"}\n'
    target = tmp_path / "external-control-target"
    target.write_text(target_contents, encoding="utf-8")
    target_before = target.read_bytes()
    link = directory / filename
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")

    service = DeskService(demo_root, allow_writes=True)
    try:
        with pytest.raises(ServiceError) as rejected:
            if action == "approve":
                service.approve("demo-quality", request)
            else:
                service.resume_fund("demo-quality")
    finally:
        service.close()

    assert rejected.value.status_code == 403
    assert target.read_bytes() == target_before


def test_unknown_local_policy_classification_returns_service_error(
    write_client,
    demo_root,
    monkeypatch,
):
    import hedge_fund.web.services as web_services
    from hedge_fund.runtime.configuration import RuntimeSettings
    from hedge_fund.runtime.policy import AuthorizationDenied, ProviderClass

    client, headers = write_client
    service = client.app.state.service
    service.network_enabled = True
    service._runtime_settings = RuntimeSettings(
        data_provider="yfinance",
        llm_provider="Ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
    )

    def classify(target, **_kwargs):
        if target.kind == "llm":
            raise AuthorizationDenied("LLM provider is unknown")
        return ProviderClass.FREE_DATA

    monkeypatch.setattr(web_services, "classify_provider", classify)
    latest = Ledger(demo_root / "paper" / "demo-quality").latest()
    assert latest is not None
    response = client.post(
        "/api/paper/demo-quality/tick/preview",
        headers=headers,
        json={"expected_head": latest.hash},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Provider configuration is not supported for local-paper operations.",
        "code": "readiness-denied",
        "message": "Provider configuration is not supported for local-paper operations.",
        "refresh_required": False,
        "retry_policy": "none",
        "subject_id": "demo-quality",
        "request_id": None,
        "current_head": None,
    }
