"""Read-only session report parity against canonical synthetic ledger records."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from hedge_fund.paper.ledger import Ledger
from hedge_fund.risk.limits import ClampEvent
from hedge_fund.web.app import create_app
from hedge_fund.web.demo import seed_demo

LOOPBACK = {"host": "127.0.0.1"}


def seed_clamped_report(root):
    """Preseed report-only facts; no provider, runner or trading operation runs."""
    directory = seed_demo(root)
    ledger = Ledger(directory / "paper" / "demo-quality")
    previous_hash = None
    for session in ledger.sessions():
        record = ledger.read(session)
        record.code_version = "report-parity-synthetic-v1"
        if session == "2024-06-04":
            record.decision.target_weights = {"AAPL": 0.4, "MSFT": -0.125}
            record.decision.final_weights = {"AAPL": 0.25, "MSFT": -0.125}
            record.decision.clamps = [
                ClampEvent(limit="max_position_pct", ticker="AAPL", before=0.4, after=0.25),
            ]
            record.decision.risk_scale_factor = None
            record.decision.strategies[0].signals[0].reasoning = "<img src=x onerror=alert('report-fixture')>"
        record.prev_hash = previous_hash
        record.hash = record.compute_hash()
        previous_hash = record.hash
        (ledger.directory / "ledger" / f"{session}.json").write_bytes(record.model_dump_json(indent=2).encode("utf-8"))
    return directory


def tree_digest(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}


def test_session_report_preserves_proposed_clamps_and_recorded_risk(tmp_path):
    root = seed_clamped_report(tmp_path / "reports")
    before = tree_digest(root)

    with TestClient(create_app(root=root), client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/paper/demo-quality/sessions/2024-06-04", headers=LOOPBACK)
        capabilities = client.get("/api/capabilities", headers=LOOPBACK).json()

    assert response.status_code == 200
    proposed = response.json()["proposed"]
    assert proposed["clamps"] == [
        {"limit": "max_position_pct", "ticker": "AAPL", "before": 0.4, "after": 0.25},
    ]
    assert proposed["risk"] == {"max_position_pct": 0.25, "max_gross_exposure": 1.0}
    assert proposed["risk_scale_factor"] is None
    assert proposed["target_weights"] == {"AAPL": 0.4, "MSFT": -0.125}
    assert proposed["final_weights"] == {"AAPL": 0.25, "MSFT": -0.125}
    assert response.json()["executed"]["clamps"] == []
    assert capabilities["writes"] is False
    assert capabilities["network"] is False
    assert capabilities["mutation_token"] is None
    assert tree_digest(root) == before


def test_canonical_download_is_bound_to_the_displayed_record_hash(tmp_path):
    root = seed_clamped_report(tmp_path / "reports")
    before = tree_digest(root)

    with TestClient(create_app(root=root), client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={"expected_hash": "0" * 64},
            headers=LOOPBACK,
        )

    assert response.status_code == 409
    assert response.json()["code"] == "stale-preview"
    assert response.json()["refresh_required"] is True
    assert response.json()["message"] == "Session report changed; reload the report before downloading."
    assert "content-disposition" not in response.headers
    assert "decision" not in response.json()
    assert tree_digest(root) == before


def test_canonical_download_refuses_a_corrupt_earlier_record(tmp_path):
    root = seed_clamped_report(tmp_path / "reports")
    earlier = root / "paper" / "demo-quality" / "ledger" / "2024-06-03.json"
    payload = json.loads(earlier.read_bytes())
    payload["cash"] = 1
    earlier.write_bytes(json.dumps(payload).encode("utf-8"))
    target = root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json"
    before = tree_digest(root)

    with TestClient(create_app(root=root), client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={"expected_hash": json.loads(target.read_bytes())["hash"]},
            headers=LOOPBACK,
        )

    assert response.status_code == 423
    assert response.json()["code"] == "replay-corrupt"
    assert "content-disposition" not in response.headers
    assert "decision" not in response.json()
    assert tree_digest(root) == before


def test_canonical_download_serializes_the_record_captured_by_verified_replay(tmp_path, monkeypatch):
    root = seed_clamped_report(tmp_path / "reports")
    persisted = (root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json").read_bytes()
    original_read = Ledger.read
    reads = 0

    def change_on_reread(ledger, session):
        nonlocal reads
        record = original_read(ledger, session)
        if session == "2024-06-04":
            reads += 1
            if reads > 1:
                return record.model_copy(update={"nav": -1})
        return record

    app = create_app(root=root)
    monkeypatch.setattr(Ledger, "read", change_on_reread)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={"expected_hash": json.loads(persisted)["hash"]},
            headers=LOOPBACK,
        )

    assert response.status_code == 200
    assert reads == 1
    assert response.content == persisted


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "desk.invalid"},
        {"host": "127.0.0.1", "origin": "https://desk.invalid"},
    ],
)
def test_canonical_download_retains_loopback_host_and_origin_guards(tmp_path, headers):
    root = seed_clamped_report(tmp_path / "reports")
    before = tree_digest(root)
    with TestClient(create_app(root=root), client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={"expected_hash": "0" * 64},
            headers=headers,
        )

    assert response.status_code == 403
    assert "content-disposition" not in response.headers
    assert tree_digest(root) == before


@pytest.mark.parametrize("expected_hash", [None, "bad", "a" * 65, "A" * 64])
def test_canonical_download_rejects_invalid_hash_before_reading(tmp_path, monkeypatch, expected_hash):
    root = seed_clamped_report(tmp_path / "reports")
    app = create_app(root=root)
    before = tree_digest(root)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid download must not read a report")

    monkeypatch.setattr(app.state.service, "session_report_download", forbidden)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={} if expected_hash is None else {"expected_hash": expected_hash},
            headers=LOOPBACK,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid-request"
    assert "content-disposition" not in response.headers
    assert tree_digest(root) == before


def test_canonical_download_preserves_verified_record_bytes_without_writes(tmp_path):
    root = seed_clamped_report(tmp_path / "reports")
    persisted = (root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json").read_bytes()
    expected_hash = json.loads(persisted)["hash"]
    before = tree_digest(root)

    with TestClient(create_app(root=root), client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04/download",
            params={"expected_hash": expected_hash},
            headers=LOOPBACK,
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == 'attachment; filename="demo-quality-2024-06-04.json"'
    assert response.content == persisted
    payload = response.json()
    assert payload["schema_version"] == 2
    assert payload["hash"] == expected_hash
    assert payload["decision"]["final_weights"]["MSFT"] == -0.125
    assert payload["code_version"] == "report-parity-synthetic-v1"
    assert "proposed" not in payload
    assert "trading_cost" not in payload["executed"]
    assert tree_digest(root) == before
