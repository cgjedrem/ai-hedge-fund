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
            "verdict": "reject",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert expired.status_code == 409
    assert not ledger.approval()


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
            "verdict": "approve",
            "decision_as_of": pending["decision_as_of"],
            "source_record_hash": pending["source_record_hash"],
        },
    )

    assert response.status_code == 423
    assert response.json()["detail"] == "Paper state is invalid (LedgerError)."
    assert not (demo_root / "paper" / "demo-quality" / "pending-approval.json").exists()


def test_halt_reuses_ledger_control_and_resume_requires_reconciliation(tmp_path):
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
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"reason": "operator pause"})
        current = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers)

    ledger = Ledger(root / "paper" / "demo-quality")
    assert halted.status_code == 200
    assert current["halted"] == "operator pause"
    assert resumed.status_code == 423
    assert resumed.json()["code"] == "reconciliation-required"
    assert resumed.json()["retry_policy"] == "inspect-status"
    assert "reconciliation receipt" in resumed.json()["detail"]
    assert ledger.halted() == "operator pause"
    assert [event["kind"] for event in ledger.events()][-1:] == ["halt"]


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
        halted = client.post("/api/paper/demo-quality/halt", headers=headers, json={"reason": "ledger review"})
        resumed = client.post("/api/paper/demo-quality/resume", headers=headers)

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
            json={"reason": "control recovery"},
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
            json={"reason": "not allowed"},
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
        canonical = client.post("/api/paper/watchtower/halt", headers=headers, json={"reason": "blocked"})
        trailing_dot = client.post("/api/paper/watchtower./halt", headers=headers, json={"reason": "blocked"})
        trailing_space = client.post("/api/paper/watchtower%20/halt", headers=headers, json={"reason": "blocked"})

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
                service.halt_fund("demo-quality", "must not write")
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
                    "verdict": "approve",
                    "decision_as_of": "2024-06-05",
                    "source_record_hash": "b" * 64,
                },
            ),
            ("/api/paper/demo-quality/halt", {"reason": "blocked"}),
            ("/api/paper/demo-quality/resume", None),
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


def test_web_halt_enters_shared_control_lane(tmp_path, monkeypatch):
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "writes")
    service = DeskService(root, allow_writes=True)
    acquired = []
    original = service._admission.control_lane

    @contextmanager
    def observe(identity, *, timeout):
        acquired.append((identity, timeout))
        with original(identity, timeout=timeout):
            yield

    monkeypatch.setattr(service._admission, "control_lane", observe)
    try:
        result = service.halt_fund("demo-quality", "operator pause")
    finally:
        service.close()

    assert result == {"name": "demo-quality", "halted": True}
    assert acquired == [("demo-quality", 0.1)]


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
            result.append(service.halt_fund("demo-quality", "operator pause"))
        except Exception as exc:
            failures.append(exc)
        finally:
            completed.set()

    work_lock.acquire()
    thread = Thread(target=halt)
    try:
        thread.start()
        responsive = completed.wait(timeout=1)
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
