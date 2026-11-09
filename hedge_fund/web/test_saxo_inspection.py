from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hedge_fund.brokers.test_saxo_doubles import FakeClock
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    INSPECTION_CAPABILITY_DESTINATIONS,
    RuntimeCredentialLeaseStore,
)
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.app import create_app
from hedge_fund.web.saxo_inspection import (
    SaxoInspectionCoordinator,
    SaxoInspectionError,
)
from hedge_fund.web.schemas import (
    SaxoInspectionAuthorizeRequest,
    SaxoInspectionDiscoveryResponse,
    SaxoInspectionRequest,
    SaxoInspectionResultResponse,
    SaxoInspectionStatusResponse,
)

ROOT_ID = "c" * 64
INSTANCE_ID = "inspection-boot"
TOKEN = "synthetic-inspection-token"


def test_http_request_models_are_strict_and_reject_secret_or_endpoint_fields():
    valid = {"authorize_network": True, "expected_generation": 1}
    assert SaxoInspectionAuthorizeRequest.model_validate(valid).authorize_network is True
    with pytest.raises(ValidationError):
        SaxoInspectionAuthorizeRequest.model_validate({**valid, "token": TOKEN})
    with pytest.raises(ValidationError):
        SaxoInspectionAuthorizeRequest.model_validate({"authorize_network": 1, "expected_generation": 1})
    with pytest.raises(ValidationError):
        SaxoInspectionRequest.model_validate({**valid, "selection_id": "a" * 32, "account_key": "injected"})


def test_http_response_models_allow_only_safe_typed_projection():
    status = {
        "environment": "SIM",
        "read_only": True,
        "capability": {
            "enabled": True,
            "state": "available",
            "generation": 1,
            "expires_at": "2026-10-31T12:00:00Z",
            "actions": {"discover": True, "inspect": True, "revoke": True},
        },
    }
    discovery = {
        "environment": "SIM",
        "read_only": True,
        "generation": 1,
        "selection_required": True,
        "choices": [{"selection_id": "a" * 32, "label": "SIM account 1", "currency": "USD"}],
    }
    result = {
        "environment": "SIM",
        "read_only": True,
        "generation": 1,
        "account": {
            "label": "SIM account 1",
            "currency": "USD",
            "cash_balance": 10.0,
            "positions": [{"uic": 7, "amount": 1.0}],
        },
        "fund_connected": False,
        "trading_enabled": False,
    }

    assert SaxoInspectionStatusResponse.model_validate(status)
    assert SaxoInspectionDiscoveryResponse.model_validate(discovery)
    assert SaxoInspectionResultResponse.model_validate(result)
    with pytest.raises(ValidationError):
        SaxoInspectionResultResponse.model_validate({**result, "token": TOKEN})


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.block_first = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.block_first and len(self.calls) == 1:
            self.started.set()
            self.release.wait(timeout=2)
        return self.responses.pop(0)


def _setup(responses, *, network_enabled=True, transport=None, clock=None):
    clock = clock or FakeClock()
    store = RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS,
        clock=clock.utcnow,
    )
    store.publish_capability(
        "saxo-demo-token",
        TOKEN,
        expected_generation=0,
        delivery_id="delivery",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination="saxo-sim-readonly",
        expires_at="2026-10-31T12:00:00Z",
    )
    fake = transport or FakeTransport(responses)
    coordinator = SaxoInspectionCoordinator(
        store,
        enabled=True,
        network_enabled=lambda: network_enabled,
        authority_check=lambda: None,
        clock=clock,
        transport_factory=lambda: fake,
    )
    return store, coordinator, fake


def _discovery_responses():
    return [
        (200, {"ClientKey": "sim-client"}),
        (
            200,
            {
                "Data": [
                    {"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                    {"AccountKey": "account-2", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                ]
            },
        ),
    ]


def test_discovery_requires_actor_consent_and_network_before_transport():
    _store, coordinator, transport = _setup(_discovery_responses())
    with pytest.raises(SaxoInspectionError, match="Explicit network consent"):
        coordinator.discover("actor-a", authorize_network=False, expected_generation=1)
    assert transport.calls == []

    _store, offline, transport = _setup(_discovery_responses(), network_enabled=False)
    with pytest.raises(SaxoInspectionError, match="Network capability is disabled"):
        offline.discover("actor-a", authorize_network=True, expected_generation=1)
    assert transport.calls == []


def test_discovery_returns_only_opaque_actor_scoped_choices_and_status_never_exposes_runtime_ids():
    store, coordinator, transport = _setup(_discovery_responses())
    observer_status = coordinator.status(operator=False)
    assert observer_status["state"] == "unavailable"
    assert observer_status["generation"] == 0
    assert ROOT_ID not in repr(observer_status)
    assert INSTANCE_ID not in repr(observer_status)
    status = coordinator.status(operator=True)
    assert status["generation"] == 1
    assert ROOT_ID not in repr(status)
    assert INSTANCE_ID not in repr(status)

    response = coordinator.discover("actor-a", authorize_network=True, expected_generation=1)

    assert response["environment"] == "SIM"
    assert response["read_only"] is True
    assert all(TOKEN not in repr(choice) for choice in response["choices"])
    assert all("account_key" not in choice for choice in response["choices"])
    assert [choice["currency"] for choice in response["choices"]] == ["USD", "USD"]
    assert all(call[0] == "GET" for call in transport.calls)
    assert all(call[2]["allow_redirects"] is False for call in transport.calls)
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "available"


def test_inspection_revalidates_choice_and_returns_only_typed_summary_without_fund_effects():
    responses = _discovery_responses() + [
        (200, {"ClientKey": "sim-client"}),
        (200, {"Data": [{"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
        (200, {"Currency": "USD", "CashBalance": 1250}),
        (200, {"Data": [{"PositionBase": {"Uic": 7, "Amount": 2}}]}),
    ]
    _store, coordinator, transport = _setup(responses)
    discovery = coordinator.discover("actor-a", authorize_network=True, expected_generation=1)
    selection_id = discovery["choices"][0]["selection_id"]

    result = coordinator.inspect(
        "actor-a",
        authorize_network=True,
        expected_generation=1,
        selection_id=selection_id,
    )

    assert result["environment"] == "SIM"
    assert result["read_only"] is True
    assert result["fund_connected"] is False
    assert result["trading_enabled"] is False
    assert result["account"]["cash_balance"] == 1250
    assert result["account"]["positions"] == [{"uic": 7, "amount": 2}]
    assert all(call[0] == "GET" for call in transport.calls)
    assert len(transport.calls) == 6
    assert TOKEN not in repr(result)


def test_selection_cannot_be_used_by_another_actor_or_replayed():
    _store, coordinator, transport = _setup(_discovery_responses())
    discovery = coordinator.discover("actor-a", authorize_network=True, expected_generation=1)
    selection_id = discovery["choices"][0]["selection_id"]

    with pytest.raises(SaxoInspectionError, match="Choose an account again"):
        coordinator.inspect(
            "actor-b",
            authorize_network=True,
            expected_generation=1,
            selection_id=selection_id,
        )
    assert len(transport.calls) == 2
    with pytest.raises(SaxoInspectionError, match="Choose an account again"):
        coordinator.inspect(
            "actor-a",
            authorize_network=True,
            expected_generation=1,
            selection_id=selection_id,
        )


def test_generation_rotation_between_status_and_capture_never_substitutes_latest_lease():
    store, coordinator, transport = _setup(_discovery_responses())
    capture = store.capture_capability

    def rotate_then_capture(*args, **kwargs):
        store.publish_capability(
            "saxo-demo-token",
            "synthetic-token-B",
            expected_generation=1,
            delivery_id="delivery-B",
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination="saxo-sim-readonly",
            expires_at="2026-10-31T12:00:00Z",
        )
        return capture(*args, **kwargs)

    store.capture_capability = rotate_then_capture
    with pytest.raises(SaxoInspectionError) as error:
        coordinator.discover("actor-a", authorize_network=True, expected_generation=1)

    assert error.value.reason == "stale-generation"
    assert transport.calls == []
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["generation"] == 2


def test_rejected_broker_credential_is_invalidated_without_retry_or_refresh():
    store, coordinator, transport = _setup([(403, {"error": TOKEN})])
    with pytest.raises(SaxoInspectionError, match="rejected the credential"):
        coordinator.discover("actor-a", authorize_network=True, expected_generation=1)

    assert len(transport.calls) == 1
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "requires-auth"


def test_cancel_during_inflight_read_prevents_choice_publication_and_releases_capture():
    transport = FakeTransport(_discovery_responses())
    transport.block_first = True
    store, coordinator, _ = _setup([], transport=transport)
    results = []
    failures = []

    def run_discovery():
        try:
            results.append(coordinator.discover("actor-a", authorize_network=True, expected_generation=1))
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=run_discovery)
    thread.start()
    assert transport.started.wait(timeout=1)
    assert coordinator.cancel("actor-a") == {"cancelled": True}
    transport.release.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert results == []
    assert len(failures) == 1 and isinstance(failures[0], SaxoInspectionError)
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "available"
    handle = store.current_capability_handle("saxo-demo-token", destination="saxo-sim-readonly")
    with pytest.raises(ExternalCredentialError, match="credential handle is unavailable"):
        store.assert_capability_dispatch_allowed(handle, destination="saxo-sim-readonly")


def test_request_count_timeout_and_mid_action_expiry_fail_without_partial_choices(monkeypatch):
    from hedge_fund.brokers import saxo

    store, coordinator, transport = _setup(_discovery_responses())
    monkeypatch.setattr(saxo, "_MAX_INSPECTION_REQUESTS", 1)
    with pytest.raises(SaxoInspectionError) as limit:
        coordinator.discover("actor-a", authorize_network=True, expected_generation=1)
    assert limit.value.reason == "inspection-limit"
    assert len(transport.calls) == 1

    clock = FakeClock()
    store, coordinator, transport = _setup(_discovery_responses(), clock=clock)

    class ExpiringTransport(FakeTransport):
        def request(self, method, url, **kwargs):
            result = super().request(method, url, **kwargs)
            clock._utc_now += timedelta(days=2)
            return result

    expiring = ExpiringTransport(_discovery_responses())
    coordinator.transport_factory = lambda: expiring
    with pytest.raises(SaxoInspectionError) as expired:
        coordinator.discover("actor-a", authorize_network=True, expected_generation=1)
    assert expired.value.reason == "requires-auth"
    assert len(expiring.calls) == 1


def test_total_action_deadline_is_enforced_after_a_slow_response():
    clock = FakeClock()
    store, coordinator, _transport = _setup(_discovery_responses(), clock=clock)

    class SlowTransport(FakeTransport):
        def request(self, method, url, **kwargs):
            response = super().request(method, url, **kwargs)
            clock.value += 31
            return response

    slow = SlowTransport(_discovery_responses())
    coordinator.transport_factory = lambda: slow
    with pytest.raises(SaxoInspectionError) as error:
        coordinator.discover("actor-a", authorize_network=True, expected_generation=1)
    assert error.value.reason == "inspection-timeout"
    assert error.value.status_code == 504
    assert len(slow.calls) == 1


@pytest.mark.parametrize("bound", ["_MAX_INSPECTION_PAGES", "_MAX_INSPECTION_ROWS", "_MAX_INSPECTION_PAGE_ROWS"])
def test_http_collection_bounds_never_publish_partial_choices(inspection_http, monkeypatch, bound):
    from hedge_fund.brokers import saxo

    app, client, headers, store, transport = inspection_http
    monkeypatch.setattr(saxo, bound, 1)
    row = {"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}
    transport.responses[1] = (200, {"Data": [row, {**row, "AccountKey": "account-2"}]})
    if bound == "_MAX_INSPECTION_PAGES":
        transport.responses[1] = (200, {"Data": [row], "__next": "/sim/openapi/port/v1/accounts/me?%24top=100&%24skip=1"})
        transport.responses.append((200, {"Data": [{**row, "AccountKey": "account-2"}]}))
    result = _http_discover(client, headers)
    assert result.status_code == 429, result.text
    assert not app.state.service._saxo_inspection._choices
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


@pytest.mark.parametrize(
    "rows",
    [
        [{"AccountKey": "same", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}] * 2,
        [{"AccountKey": "missing-fields", "Currency": "USD"}],
        [{"AccountKey": "account-1", "Currency": TOKEN, "Active": True, "LegalAssetTypes": ["Stock"]}],
    ],
)
def test_http_malformed_ambiguous_or_secret_reflecting_accounts_fail_closed(inspection_http, rows):
    app, client, headers, store, transport = inspection_http
    transport.responses[1] = (200, {"Data": rows})
    result = _http_discover(client, headers)
    assert result.status_code == 422, result.text
    assert TOKEN not in result.text
    assert not app.state.service._saxo_inspection._choices


@pytest.fixture
def inspection_http(tmp_path):
    enroll_synthetic_root(tmp_path)

    def forbidden_effect(*args, **kwargs):
        raise AssertionError("Inspection must not build a fund or application data client")

    app = create_app(root=tmp_path, allow_writes=True, network_enabled=True, fund_factory=forbidden_effect, data_client_factory=forbidden_effect)
    service = app.state.service
    store, coordinator, transport = _setup(_discovery_responses())
    coordinator.authority_check = service._admit_external_credential_delivery
    coordinator.network_enabled = lambda: service.network_enabled
    service._saxo_inspection = coordinator
    service._external_credential_store = store
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        capabilities = client.get("/api/capabilities").json()
        assert capabilities["writes"] is True
        headers = {"origin": "http://127.0.0.1", "x-csrf-token": capabilities["mutation_token"]}
        yield app, client, headers, store, transport


def _http_discover(client, headers, **changes):
    return client.post("/api/saxo/sim/accounts", headers=headers, json={"authorize_network": True, "expected_generation": 1, **changes})


@pytest.mark.parametrize("denial", ["session", "origin", "missing-origin", "csrf", "peer", "consent", "network", "owner", "root", "permission", "generation", "secret-field"])
def test_http_denies_before_any_broker_dispatch(inspection_http, monkeypatch, denial):
    app, client, headers, store, transport = inspection_http
    service = app.state.service
    body = {}
    if denial == "session":
        client.cookies.clear()
    elif denial == "origin":
        headers["origin"] = "https://attacker.invalid"
    elif denial == "missing-origin":
        headers.pop("origin")
    elif denial == "csrf":
        headers["x-csrf-token"] = "invalid"
    elif denial == "peer":
        client = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.1", 50000))
    elif denial == "consent":
        body["authorize_network"] = False
    elif denial == "network":
        service.network_enabled = False
    elif denial == "owner":
        service._owner_lease.close()
    elif denial == "root":
        service.root_context.close()
    elif denial == "permission":
        monkeypatch.setattr(service.root_context, "verify_private_storage", lambda: False)
    elif denial == "generation":
        body["expected_generation"] = 2
    elif denial == "secret-field":
        body["token"] = TOKEN

    response = _http_discover(client, headers, **body)

    assert response.status_code in {400, 403, 409, 422, 503}, response.text
    assert transport.calls == []
    assert TOKEN not in response.text
    handle = store.current_capability_handle("saxo-demo-token", destination="saxo-sim-readonly")
    with pytest.raises(ExternalCredentialError):
        store.assert_capability_dispatch_allowed(handle, destination="saxo-sim-readonly")


def test_http_discovery_explicit_selection_and_typed_inspection_are_disk_quiet(inspection_http):
    app, client, headers, store, transport = inspection_http
    root = app.state.service.root_context.path
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    status = client.get("/api/saxo/sim/status")
    assert status.status_code == 200 and status.json()["capability"]["state"] == "available"
    response = _http_discover(client, headers)
    assert response.status_code == 200, response.text
    assert response.json()["selection_required"] is True
    selection = response.json()["choices"][0]["selection_id"]
    transport.responses.extend(
        [
            (200, {"ClientKey": "sim-client"}),
            (200, {"Data": [{"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 1250}),
            (200, {"Data": [{"PositionBase": {"Uic": 7, "Amount": 2}}]}),
        ]
    )
    result = client.post("/api/saxo/sim/inspect", headers=headers, json={"authorize_network": True, "expected_generation": 1, "selection_id": selection})
    assert result.status_code == 200, result.text
    assert result.json()["account"]["cash_balance"] == 1250
    assert result.json()["fund_connected"] is False
    assert result.json()["trading_enabled"] is False
    assert TOKEN not in result.text and "account-1" not in result.text
    assert len(transport.calls) == 6 and all(call[0] == "GET" for call in transport.calls)
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("loss", ["revoke", "owner", "root", "permission", "cancel", "rotation", "rejection"])
def test_http_inflight_fences_publication_and_releases_generation(inspection_http, monkeypatch, loss):
    app, client, headers, store, transport = inspection_http
    service = app.state.service
    transport.block_first = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_http_discover, client, headers)
        try:
            assert transport.started.wait(timeout=5)
            if loss == "revoke":
                response = client.delete("/api/credentials/runtime/saxo-demo-token?expected_generation=1", headers=headers)
                assert response.status_code == 200, response.text
            elif loss == "cancel":
                response = client.post("/api/saxo/sim/cancel", headers=headers, json={})
                assert response.status_code == 200 and response.json()["cancelled"] is True
            elif loss == "owner":
                service._owner_lease.close()
            elif loss == "root":
                service.root_context.close()
            elif loss == "permission":
                monkeypatch.setattr(service.root_context, "verify_private_storage", lambda: False)
            else:
                store.publish_capability("saxo-demo-token", "synthetic-token-B", expected_generation=1, delivery_id="delivery-B", root_id=ROOT_ID, instance_id=INSTANCE_ID, destination="saxo-sim-readonly", expires_at="2026-10-31T12:00:00Z")
                if loss == "rejection":
                    transport.responses[0] = (401, {"error": TOKEN})
        finally:
            transport.release.set()
        response = future.result(timeout=5)
    if loss == "rotation":
        assert response.status_code == 200, response.text
        assert response.json()["generation"] == 1
        assert all(call[2]["headers"]["Authorization"] == f"Bearer {TOKEN}" for call in transport.calls)
    else:
        assert response.status_code != 200, response.text
        assert "choices" not in response.json()
        assert len(transport.calls) == 1
    assert TOKEN not in response.text
    assert not service._saxo_inspection._choices or loss == "rotation"
    assert all(lease.captures == 0 for lease in store._capability_leases.values())
    if loss in {"rotation", "rejection"}:
        assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["generation"] == 2
        assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "available"


def test_http_selection_is_session_bound_and_revoke_uses_generation_cas(inspection_http):
    app, client, headers, store, transport = inspection_http
    discovery = _http_discover(client, headers).json()
    selection = discovery["choices"][0]["selection_id"]
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as other:
        other_headers = {**headers, "x-csrf-token": other.get("/api/capabilities").json()["mutation_token"]}
        denied = other.post("/api/saxo/sim/inspect", headers=other_headers, json={"authorize_network": True, "expected_generation": 1, "selection_id": selection})
        assert denied.status_code == 409, denied.text
        assert len(transport.calls) == 2
        stale = other.delete("/api/credentials/runtime/saxo-demo-token?expected_generation=0", headers=other_headers)
        assert stale.status_code == 409
        assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "available"


@pytest.mark.parametrize("status", [401, 403])
def test_http_rejection_invalidates_only_inspection_without_retry_or_body_reflection(inspection_http, status):
    app, client, headers, store, transport = inspection_http
    transport.responses[0] = (status, {"error": TOKEN})
    result = _http_discover(client, headers)
    assert result.status_code == 503
    assert TOKEN not in result.text
    assert len(transport.calls) == 1
    assert client.get("/api/saxo/sim/status").json()["capability"]["state"] == "requires-auth"
    assert not app.state.service._saxo_inspection._choices


@pytest.mark.parametrize("failure", ["request-count", "body", "timeout", "expiry"])
def test_http_request_resource_and_clock_limits_return_no_partial_data(inspection_http, monkeypatch, failure):
    from hedge_fund.brokers import saxo

    app, client, headers, store, transport = inspection_http
    clock = app.state.service._saxo_inspection.clock
    original = transport.request

    def bounded_response(*args, **kwargs):
        response = original(*args, **kwargs)
        if failure == "timeout":
            clock.value += 31
        elif failure == "expiry":
            clock._utc_now += timedelta(days=2)
        return response

    transport.request = bounded_response
    if failure == "request-count":
        monkeypatch.setattr(saxo, "_MAX_INSPECTION_REQUESTS", 1)
    elif failure == "body":
        monkeypatch.setattr(saxo, "_MAX_INSPECTION_BODY_BYTES", 1)
    result = _http_discover(client, headers)
    assert result.status_code == {"request-count": 429, "body": 429, "timeout": 504, "expiry": 503}[failure], result.text
    assert len(transport.calls) == 1
    assert not app.state.service._saxo_inspection._choices
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


def test_http_busy_and_foreign_cancel_do_not_interrupt_owner_action(inspection_http):
    app, client, headers, store, transport = inspection_http
    transport.block_first = True
    other = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001))
    other.get("/api/capabilities")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_http_discover, client, headers)
        try:
            assert transport.started.wait(timeout=5)
            busy = _http_discover(other, headers)
            assert busy.status_code == 409
            cancel = other.post("/api/saxo/sim/cancel", headers=headers, json={})
            assert cancel.json() == {"cancelled": False}
        finally:
            transport.release.set()
        assert future.result(timeout=5).status_code == 200
    assert len(transport.calls) == 2
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


def test_http_revoke_after_final_inspection_get_prevents_summary_publication(inspection_http):
    app, client, headers, store, transport = inspection_http
    discovery = _http_discover(client, headers).json()
    transport.responses.extend(
        [
            (200, {"ClientKey": "sim-client"}),
            (200, {"Data": [{"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 1250}),
            (200, {"Data": []}),
        ]
    )
    original = transport.request
    started, release = threading.Event(), threading.Event()

    def final_read(method, url, **kwargs):
        response = original(method, url, **kwargs)
        if url.endswith("/positions"):
            started.set()
            assert release.wait(timeout=5)
        return response

    transport.request = final_read
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/api/saxo/sim/inspect", headers=headers, json={"authorize_network": True, "expected_generation": 1, "selection_id": discovery["choices"][0]["selection_id"]})
        try:
            assert started.wait(timeout=5)
            revoked = client.delete("/api/credentials/runtime/saxo-demo-token?expected_generation=1", headers=headers)
            assert revoked.status_code == 200
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.status_code != 200
    assert "cash_balance" not in result.text and "account" not in result.json()
    assert not app.state.service._saxo_inspection._choices
    assert not store._capability_leases


@pytest.mark.parametrize("action", ["discover", "inspect"])
@pytest.mark.parametrize("loss", ["revoke", "cancel", "owner", "root", "permission", "expiry", "rejection"])
def test_http_loss_during_result_redaction_prevents_publication(inspection_http, monkeypatch, action, loss):
    app, client, headers, store, transport = inspection_http
    service = app.state.service
    coordinator = service._saxo_inspection
    selection = None
    if action == "inspect":
        selection = _http_discover(client, headers).json()["choices"][0]["selection_id"]
        transport.responses.extend(
            [
                (200, {"ClientKey": "sim-client"}),
                (200, {"Data": [{"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
                (200, {"Currency": "USD", "CashBalance": 1250}),
                (200, {"Data": [{"PositionBase": {"Uic": 7, "Amount": 2}}]}),
            ]
        )
    started, release = threading.Event(), threading.Event()
    original = coordinator._reject_secret_reflection

    def blocked_redaction(value, secret):
        original(value, secret)
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(coordinator, "_reject_secret_reflection", blocked_redaction)
    with ThreadPoolExecutor(max_workers=1) as pool:
        if action == "inspect":
            future = pool.submit(client.post, "/api/saxo/sim/inspect", headers=headers, json={"authorize_network": True, "expected_generation": 1, "selection_id": selection})
        else:
            future = pool.submit(_http_discover, client, headers)
        try:
            assert started.wait(timeout=5)
            if loss == "revoke":
                revoked = client.delete("/api/credentials/runtime/saxo-demo-token?expected_generation=1", headers=headers)
                assert revoked.status_code == 200, revoked.text
            elif loss == "cancel":
                cancelled = client.post("/api/saxo/sim/cancel", headers=headers, json={})
                assert cancelled.status_code == 200 and cancelled.json()["cancelled"] is True
            elif loss == "owner":
                service._owner_lease.close()
            elif loss == "root":
                service.root_context.close()
            elif loss == "permission":
                monkeypatch.setattr(service.root_context, "verify_private_storage", lambda: False)
            elif loss == "expiry":
                coordinator.clock._utc_now += timedelta(days=2)
            else:
                handle = store.current_capability_handle("saxo-demo-token", destination="saxo-sim-readonly")
                store.invalidate_capability(handle)
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.status_code != 200, result.text
    assert "cash_balance" not in result.text and "positions" not in result.text
    assert "account" not in result.json() and "choices" not in result.json()
    assert TOKEN not in result.text
    assert len(transport.calls) == (6 if action == "inspect" else 2)
    assert not coordinator._choices
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


@pytest.mark.parametrize("loss", ["revoke", "cancel"])
def test_http_publication_commit_precedes_transport_handoff(inspection_http, monkeypatch, loss):
    app, client, headers, store, transport = inspection_http
    coordinator = app.state.service._saxo_inspection
    selection = _http_discover(client, headers).json()["choices"][0]["selection_id"]
    transport.responses.extend(
        [
            (200, {"ClientKey": "sim-client"}),
            (200, {"Data": [{"AccountKey": "account-1", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 1250}),
            (200, {"Data": []}),
        ]
    )
    committed, release = threading.Event(), threading.Event()
    original = coordinator._end

    def blocked_cleanup(actor, handle):
        committed.set()
        assert release.wait(timeout=5)
        original(actor, handle)

    monkeypatch.setattr(coordinator, "_end", blocked_cleanup)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, "/api/saxo/sim/inspect", headers=headers, json={"authorize_network": True, "expected_generation": 1, "selection_id": selection})
        try:
            assert committed.wait(timeout=5)
            if loss == "revoke":
                revoked = client.delete("/api/credentials/runtime/saxo-demo-token?expected_generation=1", headers=headers)
                assert revoked.status_code == 200
            else:
                cancelled = client.post("/api/saxo/sim/cancel", headers=headers, json={})
                assert cancelled.status_code == 200 and cancelled.json()["cancelled"] is False
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.status_code == 200, result.text
    assert result.json()["account"]["cash_balance"] == 1250
    assert not coordinator._choices
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


def test_http_cancel_cannot_split_lease_validation_and_publication(inspection_http, monkeypatch):
    app, client, headers, store, _transport = inspection_http
    coordinator = app.state.service._saxo_inspection
    committing, release, cancelling = threading.Event(), threading.Event(), threading.Event()
    original = store.commit_capability_publication

    def blocked_commit(handle, commit, **kwargs):
        def finish():
            committing.set()
            assert release.wait(timeout=5)
            return commit()

        return original(handle, finish, **kwargs)

    def cancel():
        cancelling.set()
        return client.post("/api/saxo/sim/cancel", headers=headers, json={})

    monkeypatch.setattr(store, "commit_capability_publication", blocked_commit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(_http_discover, client, headers)
        try:
            assert committing.wait(timeout=5)
            acquired = coordinator._lock.acquire(blocking=False)
            if acquired:
                coordinator._lock.release()
            assert not acquired, "Actor cancellation must share the publication critical section"
            cancelled = pool.submit(cancel)
            assert cancelling.wait(timeout=5)
            assert not cancelled.done()
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200
        response = cancelled.result(timeout=5)
    assert response.status_code == 200 and response.json()["cancelled"] is False
    assert all(lease.captures == 0 for lease in store._capability_leases.values())


def test_http_inspection_capability_cannot_become_model_data_or_durable_credential(inspection_http):
    app, client, headers, store, transport = inspection_http
    settings = client.get("/api/settings").json()
    assert "saxo" not in repr(settings["providers"]).lower()
    assert "saxo" not in repr(settings["data_providers"]).lower()
    assert "saxo" not in repr(settings["models"]).lower()
    model = client.post("/api/settings/model", headers=headers, json={"model": "saxo-demo-token", "expected_version": settings["version"]})
    assert model.status_code == 400
    data = client.put("/api/settings", headers=headers, json={"data_provider": "saxo-demo-token", "model": settings["model"], "timeout_seconds": 30.0, "expected_version": settings["version"]})
    assert data.status_code == 400
    durable = client.post("/api/settings/credentials", headers=headers, json={"provider": "saxo-demo-token", "value": "synthetic-not-an-application-secret", "expected_version": 0})
    assert durable.status_code == 400
    assert client.get("/api/settings").json() == settings
    assert transport.calls == []


def test_http_restart_rejects_old_session_and_selection_and_requires_fresh_delivery(inspection_http):
    app, client, headers, old_store, transport = inspection_http
    discovery = _http_discover(client, headers).json()
    old_cookies = dict(client.cookies)
    root = app.state.service.root_context.path
    app.state.service.close()
    restarted = create_app(root=root, allow_writes=True, network_enabled=True)
    service = restarted.state.service
    fresh_store = RuntimeCredentialLeaseStore(root_id=ROOT_ID, instance_id="fresh-boot", allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS, clock=FakeClock().utcnow)
    service._external_credential_store = fresh_store
    service._saxo_inspection = SaxoInspectionCoordinator(fresh_store, enabled=True, network_enabled=lambda: service.network_enabled, authority_check=service._admit_external_credential_delivery, clock=FakeClock(), transport_factory=lambda: transport)
    with TestClient(restarted, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as new_client:
        new_client.cookies.update(old_cookies)
        stale = _http_discover(new_client, headers)
        assert stale.status_code == 403
        fresh_headers = {**headers, "x-csrf-token": new_client.get("/api/capabilities").json()["mutation_token"]}
        assert new_client.get("/api/saxo/sim/status").json()["capability"]["state"] == "requires-auth"
        request = {"authorize_network": True, "expected_generation": 1, "selection_id": discovery["choices"][0]["selection_id"]}
        assert new_client.post("/api/saxo/sim/inspect", headers=fresh_headers, json=request).status_code == 503
        fresh_store.publish_capability("saxo-demo-token", "synthetic-new-boot-token", expected_generation=0, delivery_id="fresh-delivery", root_id=ROOT_ID, instance_id="fresh-boot", destination="saxo-sim-readonly", expires_at="2026-10-31T12:00:00Z")
        stale_selection = new_client.post("/api/saxo/sim/inspect", headers=fresh_headers, json=request)
        assert stale_selection.status_code == 409
        assert len(transport.calls) == 2
