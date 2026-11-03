import json

import pytest
import yaml
from fastapi.testclient import TestClient

from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import ApprovalRequest
from hedge_fund.web.services import DeskService, ServiceError


def test_approval_is_bound_to_the_displayed_timestamp_and_source_hash(write_client, demo_root):
    client, headers = write_client
    before = Ledger(demo_root / "paper" / "demo-quality").sessions()
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
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


def test_stale_and_expired_approvals_fail_without_rebinding(write_client, demo_root):
    client, headers = write_client
    detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
    pending = detail["pending"]
    stale = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()

    ledger = Ledger(demo_root / "paper" / "demo-quality")
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
            "verdict": "reject",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert expired.status_code == 409
    assert not ledger.approval()


def test_approval_is_rejected_when_gate_is_disabled(write_client, demo_root):
    client, headers = write_client
    fund_path = demo_root / "paper" / "demo-quality" / "fund.yaml"
    deployed = yaml.safe_load(fund_path.read_text(encoding="utf-8"))
    deployed["spec"].pop("approval_required", None)
    fund_path.write_text(yaml.safe_dump(deployed, sort_keys=False), encoding="utf-8")
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This fund does not require approval."
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()


def test_approval_is_rejected_for_halted_fund(write_client, demo_root):
    client, headers = write_client
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    pending = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()["pending"]
    ledger.halt("test pause")

    response = client.post(
        "/api/paper/demo-quality/approval",
        headers=headers,
        json={
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Halted funds cannot accept a verdict."
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
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Paper state is invalid (LedgerError)."
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()


def test_halt_and_resume_reuse_the_existing_ledger_control(tmp_path):
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    with TestClient(create_app(root=root, allow_writes=True, demo=True)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"reason": "operator pause"})
        current = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers)

    ledger = Ledger(root / "paper" / "demo-quality")
    assert halted.status_code == 200
    assert current["halted"] == "operator pause"
    assert resumed.status_code == 200
    assert ledger.halted() is None
    assert [event["kind"] for event in ledger.events()][-2:] == ["halt", "resume"]


def test_halt_works_for_corrupt_ledger_but_resume_still_requires_valid_replay(demo_root):
    path = demo_root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["cash"] = 1
    path.write_text(json.dumps(record), encoding="utf-8")
    with TestClient(create_app(root=demo_root, allow_writes=True, demo=True)) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"reason": "ledger review"})
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers)

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    assert halted.status_code == 200
    assert ledger.halted() == "ledger review"
    assert resumed.status_code == 409
    assert ledger.halted() == "ledger review"


def test_protected_name_guard_runs_before_fund_adapter(tmp_path, monkeypatch):
    app = create_app(root=tmp_path, allow_writes=True)
    service = app.state.service
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected fund adapter must not run")

    monkeypatch.setattr(service, "_paper_control_state", forbidden)
    with TestClient(app) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        response = client.post(
            "/api/paper/WATCHTOWER/halt",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": token,
            },
            json={"reason": "not allowed"},
        )

    assert response.status_code == 403
    assert not called
    assert not (tmp_path / "paper").exists()


def test_protected_windows_aliases_are_rejected_before_control_writes(tmp_path, monkeypatch):
    root = tmp_path / "temporary-root"
    fund_dir = root / "paper" / "watchtower"
    fund_dir.mkdir(parents=True)
    control = fund_dir / "control.json"
    events = fund_dir / "events.jsonl"
    control.write_text('{"halted": false}\n', encoding="utf-8")
    events.write_text("", encoding="utf-8")
    before_control = control.read_bytes()
    before_events = events.read_bytes()
    app = create_app(root=root, allow_writes=True)
    service = app.state.service
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected path must not reach a paper adapter")

    monkeypatch.setattr(service, "_paper_control_state", forbidden)
    with TestClient(app) as client:
        token = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        canonical = client.post("/api/paper/watchtower/halt", headers=headers, json={"reason": "blocked"})
        trailing_dot = client.post("/api/paper/watchtower./halt", headers=headers, json={"reason": "blocked"})
        trailing_space = client.post("/api/paper/watchtower%20/halt", headers=headers, json={"reason": "blocked"})

    assert canonical.status_code == 403
    assert trailing_dot.status_code == 422
    assert trailing_space.status_code == 422
    assert not called
    assert control.read_bytes() == before_control
    assert events.read_bytes() == before_events
    assert not (fund_dir / "pending-approval.json").exists()


def test_capabilities_explain_deferred_runner_ownership():
    app = create_app(root="unused-read-only-root")
    result = app.state.service.capabilities(None)

    assert "ownership" in result["deferred_actions"]["runner"]
    assert "disabled" in result["deferred_actions"]["manual_run"]
    app.state.service.close()


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
