import threading
import time
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
from hedge_fund.data import make_data_client
from hedge_fund.fund import custom_strategy, Fund, FundSpec, load_spec
from hedge_fund.llm import load_api_models
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.pipeline.session import mandate_hash
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.operations import (
    OPERATIONS_ROOT,
    OperationStatus,
    OperationStore,
)
from hedge_fund.runtime.policy import ProviderTarget
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web import jobs as jobs_module
from hedge_fund.web.app import create_app
from hedge_fund.web.jobs import JobCancelled, OperationJobRegistry
from hedge_fund.web.schemas import (
    BacktestRequest,
    CredentialRequest,
    DeployRequest,
    ModelRequest,
    OperationAcceptRequest,
    OperationCancelRequest,
    OperationPreviewRequest,
    RuntimeSettingsRequest,
)
from hedge_fund.web.services import DeskService, ServiceError

_JOB_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def durable_job_context(tmp_path):
    root = tmp_path / "durable-jobs"
    root.mkdir()
    with RootContext.open(root) as root_context:
        enroll_fresh(root_context)
        owner_lease = RootOwnerLease.acquire(root_context)
        admission = AdmissionCoordinator(root_context, owner_lease=owner_lease)
        store = OperationStore(root_context, admission=admission)
        capture = freeze_capture(
            root=root_context,
            subject_id="alpha",
            mandate_digest="a" * 64,
            universe=("AAA",),
            broker="paper",
            settings=resolve_settings(root_context),
            credential_versions={},
            code_version="synthetic-job-code",
        )
        try:
            yield root_context, store, capture
        finally:
            owner_lease.close()


def _accepted_operation(store, capture, request_id="job-request"):
    preview = store.create_preview(
        action="backtest",
        subject_id="alpha",
        expected_head="head-1",
        due_set=(),
        capture=capture,
        operator_session="operator-1",
        payload={"mode": "synthetic"},
        now=_JOB_NOW,
        expires_at=_JOB_NOW + timedelta(minutes=1),
    )
    return store.accept_request(
        request_id=request_id,
        action=preview.action,
        subject_id=preview.subject_id,
        preview_id=preview.preview_id,
        preview_digest=preview.digest,
        confirmation_token=preview.confirmation_token,
        operator_session="operator-1",
        expected_head=preview.expected_head,
        due_set=preview.due_set,
        payload=preview.payload,
        now=_JOB_NOW,
    )


def _wait_for_operation(store, operation_id, status, timeout=5):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = store.get_operation(operation_id)
        if latest.status is status:
            return latest
        time.sleep(0.01)
    view = latest.public_view() if latest is not None else None
    raise AssertionError(f"operation did not reach {status.value}: {view}")


class ManagedFakeDataClient(FakeDataClient):
    def __init__(self, series):
        super().__init__(series)
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_args):
        self.exited = True


def _spec(name="research-sample"):
    return {
        "schema_version": 2,
        "name": name,
        "strategies": [custom_strategy(["pead"]).model_dump(mode="json")],
        "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
        "capital": 100_000,
        "rebalance": "daily",
    }


def test_backtest_call_bounds_include_llm_samples_and_local_fallback():
    from hedge_fund.web.services import _estimate_backtest_bounds

    raw = _spec()
    raw["strategies"][0]["models"] = [
        {"name": "buffett", "weight": 1.0, "params": {"samples": 2}},
        {"name": "pead", "weight": 1.0, "params": {}},
    ]
    spec = FundSpec.model_validate(raw)

    assert _estimate_backtest_bounds(
        "2024-06-03",
        "2024-06-03",
        2,
        spec,
        local_llm_fallback=False,
    ) == (6, 4)
    assert _estimate_backtest_bounds(
        "2024-06-03",
        "2024-06-03",
        2,
        spec,
        local_llm_fallback=True,
    ) == (10, 8)


def _write_headers(client):
    capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
    return {
        "host": "127.0.0.1",
        "origin": "http://127.0.0.1",
        "x-csrf-token": capabilities["mutation_token"],
    }


def _mandate_fingerprint(root, name="demo-quality"):
    return mandate_hash(load_spec(root / "mandates" / f"{name}.yaml"))


def test_builder_canonical_validation_conflicts_and_deployment(tmp_path):
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)
    created = service.create_mandate(_spec())

    assert created["name"] == "research-sample"
    deployed = service.deploy_mandate("research-sample", DeployRequest(universe=["aapl", "msft"]))
    assert deployed["universe"] == ["AAPL", "MSFT"]
    assert load_deployed(tmp_path / "paper" / "research-sample").universe == ["AAPL", "MSFT"]

    with pytest.raises(ServiceError) as conflict:
        service.create_mandate(_spec("RESEARCH-SAMPLE"))
    assert conflict.value.status_code == 409
    with pytest.raises(ServiceError) as duplicate_deploy:
        service.deploy_mandate("research-sample", DeployRequest(universe=["AAPL"]))
    assert duplicate_deploy.value.status_code == 409

    invalid = _spec("invalid-cadence")
    invalid["interval"] = 1.0
    with pytest.raises(ServiceError) as cadence:
        service.create_mandate(invalid)
    assert cadence.value.status_code == 422
    service.close()


def test_mandate_api_preserves_advanced_model_roster_and_weights_and_rejects_unknown_params(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _write_headers(client)
        catalog = client.get("/api/catalog", headers={"host": "127.0.0.1"}).json()
        library = next(strategy for strategy in catalog["strategies"] if len(strategy["models"]) > 1)

        payload = _spec("canonical-library")
        payload["strategies"] = [
            {
                "name": library["name"],
                "weight": 0.5,
                "models": library["models"],
                "blend": library["blend"],
            }
        ]
        accepted = client.post("/api/mandates", headers=headers, json={"spec": payload})

        partial = deepcopy(payload)
        partial["name"] = "partial-library"
        partial["strategies"][0]["models"] = partial["strategies"][0]["models"][:-1]
        partial_response = client.post("/api/mandates", headers=headers, json={"spec": partial})

        changed_weight = deepcopy(payload)
        changed_weight["name"] = "changed-library-weight"
        changed_weight["strategies"][0]["models"][0]["weight"] += 0.5
        weight_response = client.post("/api/mandates", headers=headers, json={"spec": changed_weight})

        changed_params = deepcopy(payload)
        changed_params["name"] = "changed-library-params"
        changed_params["strategies"][0]["models"][0]["params"]["unregistered"] = True
        params_response = client.post("/api/mandates", headers=headers, json={"spec": changed_params})

    assert accepted.status_code == 201
    assert accepted.json()["spec"]["strategies"][0]["weight"] == 0.5
    assert partial_response.status_code == 201
    assert partial_response.json()["spec"]["strategies"][0]["models"] == partial["strategies"][0]["models"]
    assert weight_response.status_code == 201
    assert weight_response.json()["spec"]["strategies"][0]["models"][0]["weight"] == changed_weight["strategies"][0]["models"][0]["weight"]
    assert params_response.status_code == 422
    assert (tmp_path / "mandates" / "partial-library.yaml").is_file()
    assert (tmp_path / "mandates" / "changed-library-weight.yaml").is_file()
    assert not (tmp_path / "mandates" / "changed-library-params.yaml").exists()
    app.state.service.close()


@pytest.mark.parametrize(
    ("names", "mode"),
    [
        (["buffett"], "long_only"),
        (["buffett", "druckenmiller"], "long_short"),
    ],
)
def test_custom_mandate_api_uses_canonical_registry_mode(tmp_path, names, mode):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _write_headers(client)
        payload = _spec(f"custom-{'-'.join(names)}")
        payload["strategies"] = [custom_strategy(names).model_dump(mode="json")]
        response = client.post("/api/mandates", headers=headers, json={"spec": payload})

    assert response.status_code == 201
    assert response.json()["spec"]["strategies"][0]["blend"]["mode"] == mode
    app.state.service.close()


def test_custom_mandate_api_preserves_dollar_neutral_override(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _write_headers(client)
        payload = _spec("custom-neutral")
        payload["strategies"] = [custom_strategy(["druckenmiller"]).model_dump(mode="json")]
        payload["strategies"][0]["blend"]["mode"] = "dollar_neutral"
        response = client.post("/api/mandates", headers=headers, json={"spec": payload})

    assert response.status_code == 201
    assert response.json()["spec"]["strategies"][0]["blend"]["mode"] == "dollar_neutral"
    assert (tmp_path / "mandates" / "custom-neutral.yaml").is_file()
    app.state.service.close()


def test_reviewed_operation_preview_accept_persists_capture_and_report(demo_root, monkeypatch):
    data_client = ManagedFakeDataClient(SERIES)
    app = create_app(
        root=demo_root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    store = app.state.service._operation_store
    assert store is not None
    apply_calls = []
    apply_if_current = store.apply_if_current

    def observe_effect(operation_id, fence, effect):
        apply_calls.append(operation_id)
        return apply_if_current(operation_id, fence, effect)

    monkeypatch.setattr(store, "apply_if_current", observe_effect)
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            headers = _write_headers(client)
            settings = client.get("/api/settings", headers={"host": "127.0.0.1"}).json()
            local_model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
            selected = client.post(
                "/api/settings/model",
                headers=headers,
                json={"model": local_model, "expected_version": settings["version"]},
            )
            assert selected.status_code == 200, selected.text
            payload = {
                "fund": "demo-quality",
                "universe": ["AAPL"],
                "start": "2024-06-03",
                "end": "2024-06-07",
                "provider": "yfinance",
                "model": local_model,
                "mandate_hash": _mandate_fingerprint(demo_root),
            }
            preview_response = client.post(
                "/api/operations/preview",
                headers=headers,
                json={
                    "action": "backtest",
                    "subject_id": "demo-quality",
                    "expected_head": payload["mandate_hash"],
                    "payload": payload,
                },
            )
            assert preview_response.status_code == 201, preview_response.text
            preview = preview_response.json()
            assert preview["capture"]["settings_version"] == 1
            assert preview["capture"]["model"] == local_model
            assert preview["estimate"]["maximum_cost_usd"] is None
            assert preview["warnings"] == ["Injected test providers only; no live provider call is authorized."]
            accepted = client.post(
                "/api/operations",
                headers=headers,
                json={
                    "request_id": "reviewed-backtest-1",
                    "action": "backtest",
                    "subject_id": "demo-quality",
                    "preview_id": preview["preview_id"],
                    "preview_digest": preview["preview_digest"],
                    "confirmation_token": preview["confirmation_token"],
                    "expected_head": payload["mandate_hash"],
                    "due_set": [],
                    "payload": payload,
                },
            )
            assert accepted.status_code == 202, accepted.text
            operation_id = accepted.json()["operation_id"]
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                current = client.get(
                    f"/api/operations/{operation_id}",
                    headers={"host": "127.0.0.1"},
                ).json()
                if current["status"] in {"completed", "failed", "interrupted"}:
                    break
                time.sleep(0.2)
            operations = client.get(
                "/api/operations",
                headers={"host": "127.0.0.1"},
            ).json()
    finally:
        app.state.service.close()

    assert current["status"] == "completed", current
    assert current["request_id"] == "reviewed-backtest-1"
    assert current["capture_id"] == preview["capture_id"]
    assert current["result"]["capture_digest"] == preview["capture_digest"]
    assert current["report_id"].endswith(".json")
    assert operations["items"][0]["operation_id"] == operation_id
    assert apply_calls == [operation_id]
    assert data_client.entered is True
    assert data_client.exited is True
    assert (demo_root / "research" / current["report_id"]).is_file()
    assert (demo_root / "runtime" / "private" / "v1" / "captures" / f"{preview['capture_id']}.json").is_file()


def test_paid_fd_web_backtest_uses_guarded_real_client_and_fake_transport(
    demo_root,
    monkeypatch,
):
    import hedge_fund.web.services as services

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
    )
    service.save_runtime_settings(
        RuntimeSettingsRequest(
            data_provider="fd",
            model=service.settings()["model"],
            endpoint=None,
            timeout_seconds=60.0,
            parameters={},
            expected_version=service.settings()["version"],
        )
    )
    secret = "synthetic-fd-key"
    service.set_credential(
        CredentialRequest(
            provider="fd",
            value=SecretStr(secret),
            expected_version=0,
        )
    )
    http_calls = []
    dispatches = []

    def handle(request):
        http_calls.append(request)
        assert request.headers.get("x-api-key") == secret
        return httpx.Response(
            200,
            json={"prices": [], "next_page_url": None},
            request=request,
        )

    production_factory = make_data_client

    def fake_transport_factory(*, provider, dispatch, api_key):
        dispatches.append(dispatch)
        return production_factory(
            provider=provider,
            dispatch=dispatch,
            api_key=api_key,
            inner_transport=httpx.MockTransport(handle),
        )

    def fake_backtest(_fund, start, end, data_client, _universe, *, on_valuation):
        assert data_client.get_prices("AAPL", start, end) == []
        on_valuation(0, 1, None)
        return object()

    def fake_save(_result, *, directory, admission):
        del admission
        path = Path(directory) / "fake-paid-backtest.json"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr(services, "make_data_client", fake_transport_factory)
    monkeypatch.setattr(services, "backtest_fund", fake_backtest)
    monkeypatch.setattr(services, "save_result", fake_save)
    payload_values = {
        "fund": "demo-quality",
        "universe": ["AAPL"],
        "start": "2024-06-03",
        "end": "2024-06-04",
        "provider": "fd",
        "model": service.settings()["model"],
        "mandate_hash": _mandate_fingerprint(demo_root),
        "authorize_paid_provider": True,
        "paid_max_calls": 1,
        "paid_max_cost_usd": "1",
        "paid_max_attempt_cost_usd": "0.25",
    }
    unconfirmed_payload = BacktestRequest(**payload_values)
    with pytest.raises(ServiceError) as tier_denied:
        service.create_operation_preview(
            OperationPreviewRequest(
                action="backtest",
                subject_id="demo-quality",
                expected_head=unconfirmed_payload.mandate_hash,
                payload=unconfirmed_payload,
            ),
            operator_session="synthetic-paid-session",
        )
    assert tier_denied.value.status_code == 403
    assert "self-service pricing confirmation" in tier_denied.value.detail
    assert http_calls == []
    assert dispatches == []
    assert service.list_operations()["items"] == []

    payload = BacktestRequest(
        **{
            **payload_values,
            "confirm_fd_self_service_pricing": True,
        }
    )
    try:
        preview = service.create_operation_preview(
            OperationPreviewRequest(
                action="backtest",
                subject_id="demo-quality",
                expected_head=payload.mandate_hash,
                payload=payload,
            ),
            operator_session="synthetic-paid-session",
        )
        accepted = service.accept_operation(
            OperationAcceptRequest(
                request_id="synthetic-paid-fd-backtest",
                action="backtest",
                subject_id="demo-quality",
                preview_id=preview["preview_id"],
                preview_digest=preview["preview_digest"],
                confirmation_token=preview["confirmation_token"],
                expected_head=preview["expected_head"],
                due_set=[],
                payload=BacktestRequest.model_validate(preview["payload"]),
            ),
            operator_session="synthetic-paid-session",
        )
        store = service._operation_store
        assert store is not None
        completed = _wait_for_operation(
            store,
            accepted["operation_id"],
            OperationStatus.COMPLETED,
            timeout=30,
        )
    finally:
        service.close()

    assert completed.result["report_id"] == "fake-paid-backtest.json"
    assert len(http_calls) == 1
    assert len(dispatches) == 1
    target = ProviderTarget(kind="data", provider="fd")
    authorization = dispatches[0]._one_shot[target.identity]
    assert authorization.calls_reserved == 1
    assert str(authorization.cost_reserved) == "0.25"
    assert secret not in str(completed.public_view())


def test_cancel_after_effect_returns_preserves_completed_result(durable_job_context):
    _root, store, capture = durable_job_context
    operation = _accepted_operation(store, capture, request_id="cancel-after-effect")
    registry = OperationJobRegistry(store)
    effect_finished = threading.Event()
    release_worker = threading.Event()
    effects = []

    def work(_progress, _cancelled, apply_if_current):
        result = apply_if_current(lambda: effects.append("report-committed") or {"report_id": "report.json"})
        effect_finished.set()
        assert release_worker.wait(timeout=5)
        return result

    try:
        registry.submit(operation, work)
        assert effect_finished.wait(timeout=5)
        cancellation = registry.cancel(
            operation.operation_id,
            request_id="cancel-after-commit",
        )
        assert cancellation.status is OperationStatus.CANCEL_REQUESTED
        release_worker.set()
        completed = _wait_for_operation(
            store,
            operation.operation_id,
            OperationStatus.COMPLETED,
        )
    finally:
        release_worker.set()
        registry.close()

    assert effects == ["report-committed"]
    assert completed.result == {"report_id": "report.json"}


def test_injected_fund_factory_does_not_bypass_local_backtest_policy(demo_root):
    from hedge_fund.runtime.configuration import RuntimeSettings

    called = False

    def forbidden_client():
        nonlocal called
        called = True
        raise AssertionError("policy denial must precede data-client construction")

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    service._runtime_settings = RuntimeSettings(
        data_provider="yfinance",
        llm_provider="TypeSafe",
        model="jev-1.13.0",
    )
    try:
        payload = BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider="yfinance",
            model="jev-1.13.0",
            mandate_hash=_mandate_fingerprint(demo_root),
            authorize_paid_provider=True,
            paid_max_calls=1,
            paid_max_cost_usd="1",
            paid_max_attempt_cost_usd="0.16",
        )
        with pytest.raises(ServiceError) as denied:
            service.create_operation_preview(
                OperationPreviewRequest(
                    action="backtest",
                    subject_id="demo-quality",
                    expected_head=payload.mandate_hash,
                    payload=payload,
                ),
                operator_session="synthetic-server-session",
            )
        assert denied.value.status_code == 403
        assert "Injected model providers" in denied.value.detail
        assert service.list_operations()["items"] == []
        assert not called
    finally:
        service.close()


def test_reviewed_operation_rejects_changed_mandate_before_data_adapter(demo_root):
    called = False

    def forbidden_client():
        nonlocal called
        called = True
        raise AssertionError("stale preview must not construct a data client")

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    try:
        local_model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
        service.set_model(ModelRequest(model=local_model, expected_version=service.settings()["version"]))
        payload = BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider="yfinance",
            model=local_model,
            mandate_hash=_mandate_fingerprint(demo_root),
        )
        preview = service.create_operation_preview(
            OperationPreviewRequest(
                action="backtest",
                subject_id="demo-quality",
                expected_head=payload.mandate_hash,
                payload=payload,
            ),
            operator_session="synthetic-server-session",
        )
        research_dir = demo_root / "research"
        research_before = {path.name for path in research_dir.iterdir()}
        path = demo_root / "mandates" / "demo-quality.yaml"
        data = load_spec(path).model_dump(mode="json")
        data["risk"]["max_position_pct"] = 0.2
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        acceptance = OperationAcceptRequest(
            request_id="stale-backtest-1",
            action="backtest",
            subject_id="demo-quality",
            preview_id=preview["preview_id"],
            preview_digest=preview["preview_digest"],
            confirmation_token=preview["confirmation_token"],
            expected_head=payload.mandate_hash,
            due_set=[],
            payload=payload,
        )
        with pytest.raises(ServiceError) as stale:
            service.accept_operation(
                acceptance,
                operator_session="synthetic-server-session",
            )
        assert stale.value.status_code == 409
        assert not called
        assert service.list_operations()["items"] == []
        assert {path.name for path in research_dir.iterdir()} == research_before
    finally:
        service.close()


def test_network_capability_is_required_before_any_data_adapter(tmp_path):
    called = False

    def forbidden():
        nonlocal called
        called = True
        raise AssertionError("disabled network must not construct a data client")

    service = DeskService(
        tmp_path,
        allow_writes=True,
        network_enabled=False,
        data_client_factory=forbidden,
    )
    try:
        payload = BacktestRequest(
            fund="missing",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider=service.settings()["data_provider"],
            model=service.settings()["model"],
            mandate_hash="0" * 64,
        )
        with pytest.raises(ServiceError) as blocked:
            service.create_operation_preview(
                OperationPreviewRequest(
                    action="backtest",
                    subject_id="missing",
                    expected_head=payload.mandate_hash,
                    payload=payload,
                ),
                operator_session="synthetic-server-session",
            )
        assert blocked.value.status_code == 403
        assert not called
        assert not (tmp_path / "research").exists()
    finally:
        service.close()


def test_backtest_preview_rejects_same_count_mandate_drift_before_client(demo_root):
    called = False

    def forbidden():
        nonlocal called
        called = True
        raise AssertionError("stale mandate must not construct a data client")

    fingerprint = _mandate_fingerprint(demo_root)
    path = demo_root / "mandates" / "demo-quality.yaml"
    data = load_spec(path).model_dump(mode="json")
    data["risk"]["max_position_pct"] = 0.2
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden,
    )
    try:
        local_model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
        service.set_model(
            ModelRequest(
                model=local_model,
                expected_version=service.settings()["version"],
            )
        )
        assert service.list_mandates()["items"][0]["agent_count"] == 1
        payload = BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider=service.settings()["data_provider"],
            model=local_model,
            mandate_hash=fingerprint,
        )
        with pytest.raises(ServiceError) as changed:
            service.create_operation_preview(
                OperationPreviewRequest(
                    action="backtest",
                    subject_id="demo-quality",
                    expected_head=fingerprint,
                    payload=payload,
                ),
                operator_session="synthetic-server-session",
            )
        assert changed.value.status_code == 409
        assert not called
        assert service.list_operations()["items"] == []
    finally:
        service.close()


def test_reviewed_backtest_executes_captured_mandate_after_template_edit(demo_root, monkeypatch):
    data_client = ManagedFakeDataClient(SERIES)
    observed_specs = []
    selected_model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: observed_specs.append(spec)
        or Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    service.set_model(
        ModelRequest(
            model=selected_model,
            expected_version=service.settings()["version"],
        )
    )
    worker = service._operation_jobs
    store = service._operation_store
    assert worker is not None
    assert store is not None
    original_submit = worker.submit
    pending_work = []
    monkeypatch.setattr(
        worker,
        "submit",
        lambda operation, work: pending_work.append((operation, work)) or operation,
    )

    try:
        payload = BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-07",
            provider="yfinance",
            model=selected_model,
            mandate_hash=_mandate_fingerprint(demo_root),
        )
        preview = service.create_operation_preview(
            OperationPreviewRequest(
                action="backtest",
                subject_id="demo-quality",
                expected_head=payload.mandate_hash,
                payload=payload,
            ),
            operator_session="synthetic-server-session",
        )
        accepted = service.accept_operation(
            OperationAcceptRequest(
                request_id="captured-mandate-backtest",
                action="backtest",
                subject_id="demo-quality",
                preview_id=preview["preview_id"],
                preview_digest=preview["preview_digest"],
                confirmation_token=preview["confirmation_token"],
                expected_head=preview["expected_head"],
                due_set=[],
                payload=payload,
            ),
            operator_session="synthetic-server-session",
        )
        assert accepted["status"] == "accepted"
        assert len(pending_work) == 1

        mandate_path = demo_root / "mandates" / "demo-quality.yaml"
        changed = load_spec(mandate_path).model_dump(mode="json")
        changed["risk"]["max_position_pct"] = 0.2
        mandate_path.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")

        original_submit(*pending_work[0])
        future = worker._submitted[accepted["operation_id"]]
        assert future is not None
        future.result(timeout=30)
        result = store.get_operation(accepted["operation_id"])
        assert result.status is OperationStatus.COMPLETED, result.public_view()
        assert len(observed_specs) == 1
        assert observed_specs[0].risk.max_position_pct == pytest.approx(0.25)
        assert data_client.entered is True
        assert data_client.exited is True
    finally:
        service.close()


def test_reviewed_backtest_cancellation_closes_fake_client_and_freezes_model(demo_root, monkeypatch):
    import hedge_fund.web.services as services

    data_client = ManagedFakeDataClient(SERIES)
    entered = threading.Event()
    release = threading.Event()
    selected_model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    service.set_model(
        ModelRequest(
            model=selected_model,
            expected_version=service.settings()["version"],
        )
    )
    captured_settings_version = service.settings()["version"]

    def paused_backtest(_fund, _start, _end, _client, _universe, *, on_valuation):
        on_valuation(0, 2, None)
        entered.set()
        release.wait()
        on_valuation(1, 2, None)

    monkeypatch.setattr(services, "backtest_fund", paused_backtest)
    payload = BacktestRequest(
        fund="demo-quality",
        universe=["AAPL"],
        start="2024-06-03",
        end="2024-06-04",
        provider=service.settings()["data_provider"],
        model=selected_model,
        mandate_hash=_mandate_fingerprint(demo_root),
    )
    preview = service.create_operation_preview(
        OperationPreviewRequest(
            action="backtest",
            subject_id="demo-quality",
            expected_head=payload.mandate_hash,
            payload=payload,
        ),
        operator_session="synthetic-server-session",
    )
    operation = service.accept_operation(
        OperationAcceptRequest(
            request_id="cancel-reviewed-backtest",
            action="backtest",
            subject_id="demo-quality",
            preview_id=preview["preview_id"],
            preview_digest=preview["preview_digest"],
            confirmation_token=preview["confirmation_token"],
            expected_head=preview["expected_head"],
            due_set=preview["due_set"],
            payload=payload,
        ),
        operator_session="synthetic-server-session",
    )
    try:
        assert operation["model"] == selected_model
        assert entered.wait(timeout=5)
        changed_model = next(item["id"] for item in service.settings()["models"] if item["id"] != selected_model)
        service.set_model(
            ModelRequest(
                model=changed_model,
                expected_version=service.settings()["version"],
            )
        )
        captured = service._captures[operation["capture_id"]]
        effective_settings = service.settings()
        assert effective_settings["model"] == changed_model
        assert captured.model == selected_model
        assert captured.settings_version == captured_settings_version
        assert effective_settings["active_captures"] == [
            {
                "capture_id": operation["capture_id"],
                "subject_id": "demo-quality",
                "status": "running",
                "capture_details_available": True,
                "settings_version": captured_settings_version,
                "data_provider": "yfinance",
                "llm_provider": "Ollama",
                "model": selected_model,
                "endpoint": None,
                "restart_needed": True,
            }
        ]
        service.cancel_operation(
            operation["operation_id"],
            OperationCancelRequest(request_id="cancel-reviewed-backtest-1"),
        )
        release.set()
        deadline = time.monotonic() + 5
        current = service.get_operation(operation["operation_id"])
        while current["status"] in {"accepted", "running", "cancel-requested"} and time.monotonic() < deadline:
            time.sleep(0.02)
            current = service.get_operation(operation["operation_id"])
    finally:
        release.set()
        service.close()

    assert current["status"] == "cancelled"
    assert current["report_id"] is None
    assert data_client.entered is True
    assert data_client.exited is True
    assert not (demo_root / "research" / "cancelled.json").exists()


def test_reviewed_backtest_pause_requires_explicit_release(demo_root, monkeypatch):
    event_type = threading.Event
    wait_called = event_type()
    wait_timeouts = []
    event_count = 0
    set_model = DeskService.set_model

    def make_event():
        nonlocal event_count
        event_count += 1
        event = event_type()
        if event_count == 2:
            wait = event.wait

            def expire_timed_wait(timeout=None):
                wait_timeouts.append(timeout)
                wait_called.set()
                if timeout is not None:
                    return False
                return wait()

            event.wait = expire_timed_wait
        return event

    def save_after_pause(self, request):
        worker = self._operation_jobs
        if worker is not None and worker._active:
            assert wait_called.wait(timeout=5)
            if wait_timeouts[-1] is not None:
                future = next(iter(worker._submitted.values()))
                assert future is not None
                future.result(timeout=5)
        return set_model(self, request)

    monkeypatch.setattr(threading, "Event", make_event)
    monkeypatch.setattr(DeskService, "set_model", save_after_pause)
    test_reviewed_backtest_cancellation_closes_fake_client_and_freezes_model(demo_root, monkeypatch)
    assert wait_timeouts == [None]


def test_legacy_backtest_and_job_routes_cannot_start_work(demo_root):
    called = False

    def forbidden_client():
        nonlocal called
        called = True
        raise AssertionError("removed route must not construct a data client")

    app = create_app(
        root=demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden_client,
    )
    research_before = {path.name for path in (demo_root / "research").iterdir()}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _write_headers(client)
        settings = client.get("/api/settings", headers={"host": "127.0.0.1"}).json()
        legacy_payload = {
            "fund": "demo-quality",
            "universe": ["AAPL"],
            "start": "2024-06-03",
            "end": "2024-06-04",
            "provider": settings["data_provider"],
            "model": settings["model"],
            "mandate_hash": _mandate_fingerprint(demo_root),
        }
        start = client.post("/api/backtests", headers=headers, json=legacy_payload)
        jobs = client.get("/api/jobs", headers={"host": "127.0.0.1"})
        detail = client.get(
            f"/api/jobs/{'a' * 32}",
            headers={"host": "127.0.0.1"},
        )
        cancel = client.post(
            f"/api/jobs/{'a' * 32}/cancel",
            headers=headers,
            json={"request_id": "legacy-cancel"},
        )

    assert [start.status_code, jobs.status_code, detail.status_code, cancel.status_code] == [
        405,
        404,
        404,
        405,
    ]
    assert not called
    assert {path.name for path in (demo_root / "research").iterdir()} == research_before


def test_operation_job_registry_persists_progress_and_result(durable_job_context):
    root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(store, clock=lambda: _JOB_NOW)
    operation = _accepted_operation(store, capture)
    entered = threading.Event()
    release = threading.Event()

    def work(progress, cancelled, _apply_if_current):
        assert not cancelled()
        progress(20)
        entered.set()
        release.wait()
        assert not cancelled()
        progress(75)
        return {"sessions": 1}

    try:
        submitted = registry.submit(operation, work)
        assert submitted.operation_id == operation.operation_id
        assert entered.wait(timeout=5)
        running = _wait_for_operation(store, operation.operation_id, OperationStatus.RUNNING)
        assert running.progress == 20
        release.set()
        completed = _wait_for_operation(store, operation.operation_id, OperationStatus.COMPLETED)
        assert completed.progress == 100
        assert completed.result == {"sessions": 1}
        assert root_context.read_bytes(f"{OPERATIONS_ROOT}/results/{operation.operation_id}.json")
    finally:
        release.set()
        registry.close()


@pytest.mark.parametrize("phase", ["claim", "work", "complete"])
def test_operation_worker_failures_log_safe_cause_without_payload(durable_job_context, monkeypatch, caplog, phase):
    _root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(store, clock=lambda: _JOB_NOW)
    operation = _accepted_operation(store, capture)
    secret = "synthetic-private-config-prompt-credential"

    def fail(*_args, **_kwargs):
        try:
            raise OSError(5, secret)
        except OSError as cause:
            raise RuntimeError(secret) from cause

    def work(_progress, _cancelled, _apply):
        if phase == "work":
            fail()
        return {"sessions": 1}

    if phase == "claim":
        monkeypatch.setattr(store, "claim_worker", fail)
    elif phase == "complete":
        monkeypatch.setattr(store, "complete", fail)
    caplog.set_level("ERROR", logger="hedge_fund.web.jobs")
    try:
        registry.submit(operation, work)
        future = registry._submitted[operation.operation_id]
        assert future is not None
        future.result(timeout=5)
        current = store.get_operation(operation.operation_id)
        expected = OperationStatus.INTERRUPTED if phase == "claim" else OperationStatus.FAILED
        assert current.status is expected
        assert "type=RuntimeError" in caplog.text
        assert "cause_type=OSError errno=5 winerror=None" in caplog.text
        assert f"phase={phase}" in caplog.text
        assert secret not in caplog.text
        assert str(_root_context.path) not in caplog.text
        assert all(record.exc_info is None and record.stack_info is None for record in caplog.records)
        assert secret not in str(current.public_view())
    finally:
        registry.close()


@pytest.mark.parametrize(("phase", "expected"), [("claim", OperationStatus.INTERRUPTED), ("work", OperationStatus.FAILED), ("complete", OperationStatus.FAILED)])
def test_diagnostic_failure_does_not_skip_durable_worker_failure(
    durable_job_context,
    monkeypatch,
    phase,
    expected,
):
    _root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(store, clock=lambda: _JOB_NOW)
    operation = _accepted_operation(store, capture)

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic worker failure")

    def fail_diagnostic(*_args, **_kwargs):
        raise RuntimeError("synthetic diagnostic failure")

    def work(_progress, _cancelled, _apply):
        if phase == "work":
            fail()
        return {"sessions": 1}

    if phase == "claim":
        monkeypatch.setattr(store, "claim_worker", fail)
    elif phase == "complete":
        monkeypatch.setattr(store, "complete", fail)
    monkeypatch.setattr(jobs_module, "_log_failure", fail_diagnostic)
    try:
        registry.submit(operation, work)
        future = registry._submitted[operation.operation_id]
        assert future is not None
        with pytest.raises(RuntimeError, match="synthetic diagnostic failure"):
            future.result(timeout=5)
        assert store.get_operation(operation.operation_id).status is expected
    finally:
        registry.close()


def test_operation_job_cancellation_stops_at_boundary_without_result(durable_job_context):
    _root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(store, clock=lambda: _JOB_NOW)
    operation = _accepted_operation(store, capture)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def work(progress, cancelled, _apply_if_current):
        calls.append("started")
        progress(25)
        entered.set()
        release.wait()
        if cancelled():
            raise JobCancelled()
        return {"must_not_persist": True}

    try:
        registry.submit(operation, work)
        assert entered.wait(timeout=5)
        cancel_requested = registry.cancel(
            operation.operation_id,
            request_id="cancel-job-1",
            now=_JOB_NOW,
        )
        assert cancel_requested.status is OperationStatus.CANCEL_REQUESTED
        release.set()
        cancelled = _wait_for_operation(store, operation.operation_id, OperationStatus.CANCELLED)
        assert cancelled.result is None
        assert calls == ["started"]
    finally:
        release.set()
        registry.close()


def test_cancelled_queued_future_releases_operation_capacity(durable_job_context, monkeypatch):
    _root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(
        store,
        max_active=1,
        clock=lambda: _JOB_NOW,
    )
    first = _accepted_operation(store, capture, request_id="queued-first")
    second = _accepted_operation(store, capture, request_id="queued-second")
    futures = []

    def queued_submit(*_args, **_kwargs):
        future = Future()
        futures.append(future)
        return future

    monkeypatch.setattr(registry._executor, "submit", queued_submit)

    try:
        registry.submit(first, lambda _progress, _cancelled, _effect: {"unexpected": True})
        cancelled = registry.cancel(
            first.operation_id,
            request_id="cancel-queued-first",
            now=_JOB_NOW,
        )
        assert cancelled.status is OperationStatus.CANCELLED

        submitted = registry.submit(
            second,
            lambda _progress, _cancelled, _effect: {"unexpected": True},
        )
        assert submitted.operation_id == second.operation_id
        assert len(futures) == 2
    finally:
        registry.close()


def test_close_waits_for_worker_boundary_before_interruption(durable_job_context, monkeypatch):
    _root_context, store, capture = durable_job_context
    registry = OperationJobRegistry(store, clock=lambda: _JOB_NOW)
    operation = _accepted_operation(store, capture)
    entered = threading.Event()
    request_cancel_entered = threading.Event()
    release_request_cancel = threading.Event()
    request_cancel_persisted = threading.Event()
    probe_worker = threading.Event()
    release_worker = threading.Event()
    worker_checked = threading.Event()
    shutdown_done = threading.Event()
    restarts = []
    cancel_results = []
    acknowledgements = []
    interruptions = []
    original_request_cancel = store.request_cancel
    original_acknowledge = store.acknowledge_cancel
    original_interrupt = store.interrupt

    def delay_request_cancel(*args, **kwargs):
        request_cancel_entered.set()
        if not release_request_cancel.wait(timeout=5):
            raise TimeoutError("shutdown cancellation barrier timed out")
        result = original_request_cancel(*args, **kwargs)
        request_cancel_persisted.set()
        return result

    def observe(method, results):
        def call(*args, **kwargs):
            try:
                result = method(*args, **kwargs)
            except Exception as exc:
                results.append(f"{type(exc).__name__}:{exc}")
                raise
            results.append(result.status.value)
            return result

        return call

    monkeypatch.setattr(store, "request_cancel", delay_request_cancel)
    monkeypatch.setattr(store, "acknowledge_cancel", observe(original_acknowledge, acknowledgements))
    monkeypatch.setattr(store, "interrupt", observe(original_interrupt, interruptions))

    def work(_progress, cancelled, _apply_if_current):
        entered.set()
        if not probe_worker.wait(timeout=5):
            raise TimeoutError("worker probe barrier timed out")
        cancel_results.append(cancelled())
        worker_checked.set()
        if cancel_results[-1]:
            raise JobCancelled()
        if not release_worker.wait(timeout=5):
            raise TimeoutError("worker release barrier timed out")
        if cancelled():
            raise JobCancelled()
        return {"unexpected": True}

    registry.submit(operation, work)
    assert entered.wait(timeout=5)

    def close_registry():
        registry.close()
        shutdown_done.set()

    shutdown = threading.Thread(target=close_registry)
    shutdown.start()
    try:
        assert request_cancel_entered.wait(timeout=5)
        assert not shutdown_done.wait(timeout=0.05)
        probe_worker.set()
        assert worker_checked.wait(timeout=5)
        assert cancel_results == [False]
        release_request_cancel.set()
        assert request_cancel_persisted.wait(timeout=5)
        release_worker.set()
    finally:
        release_request_cancel.set()
        release_worker.set()
        shutdown.join(timeout=10)

    assert shutdown_done.is_set()
    assert not shutdown.is_alive()

    observed = store.get_operation(operation.operation_id)

    assert observed.status is OperationStatus.CANCELLED, f"checked={cancel_results!r}, ack={acknowledgements!r}, interrupt={interruptions!r}"
    assert acknowledgements == ["cancelled"]
    assert interruptions == []
    assert restarts == []
