from hedge_fund.brokers.models import Order
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger

_DECISION = "confirm-paper-book-matches-ledger"


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
