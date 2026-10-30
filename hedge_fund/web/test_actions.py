from fastapi.testclient import TestClient

from hedge_fund.paper.ledger import Ledger
from hedge_fund.web.app import create_app


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


def test_protected_name_guard_runs_before_fund_adapter(tmp_path, monkeypatch):
    app = create_app(root=tmp_path, allow_writes=True)
    service = app.state.service
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected fund adapter must not run")

    monkeypatch.setattr(service, "_paper_state", forbidden)
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


def test_capabilities_explain_deferred_runner_ownership():
    app = create_app(root="unused-read-only-root")
    result = app.state.service.capabilities(None)

    assert "ownership" in result["deferred_actions"]["runner"]
    assert "disabled" in result["deferred_actions"]["manual_run"]
    app.state.service.close()
