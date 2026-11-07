from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from httpcore._backends.sync import SyncBackend

from hedge_fund.runtime.dispatch import (
    _PinnedSyncBackend,
    make_one_shot_dispatch,
    ProviderDispatch,
)
from hedge_fund.runtime.endpoints import PinnedAddress, resolve_destination
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    BudgetDenied,
    OperationScope,
    ProviderTarget,
)

_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _dispatch(
    target: ProviderTarget,
    *,
    now=None,
    resolver=None,
    boundary_check=None,
    max_calls=5,
    max_cost=Decimal("1.00"),
    upper_bound_cost=Decimal("0.16"),
    approved_local_models=frozenset(),
):
    return make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="a" * 64,
        operation_id="operation-1",
        operation_digest="b" * 64,
        expires_at=_NOW + timedelta(minutes=5),
        targets=(target,),
        max_calls=max_calls,
        max_cost=max_cost,
        max_resources=10,
        upper_bound_costs={target.identity: upper_bound_cost},
        approved_local_models=approved_local_models,
        clock=now or (lambda: _NOW),
        boundary_check=boundary_check,
        resolver=resolver or (lambda _host, _port: ["8.8.8.8"]),
    )


def _client(dispatch, target, handler):
    return httpx.Client(
        transport=dispatch.httpx_transport(
            target,
            inner_transport=httpx.MockTransport(handler),
        ),
        trust_env=False,
        follow_redirects=False,
    )


def _authorization(dispatch, target):
    return dispatch._one_shot[target.identity]


def test_provider_dispatch_operation_scope_is_immutable():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target)

    assert not hasattr(dispatch, "__dict__")
    with pytest.raises(AttributeError):
        dispatch.operation_id = "other-operation"
    with pytest.raises(AttributeError):
        dispatch.scope = OperationScope.SCHEDULED
    with pytest.raises(TypeError):
        dispatch._one_shot[target.identity] = _authorization(dispatch, target)


def test_paid_retry_is_denied_before_second_transport():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with dispatch.invocation(target):
            client.get("https://api.financialdatasets.ai/prices/")
            with pytest.raises(AuthorizationDenied):
                client.get("https://api.financialdatasets.ai/prices/")

    authorization = _authorization(dispatch, target)
    assert len(calls) == 1
    assert authorization.calls_reserved == 1
    assert authorization.cost_reserved == Decimal("0.16")


def test_expiry_denies_next_invocation_before_transport():
    target = ProviderTarget(kind="data", provider="fd")
    moment = [_NOW]
    dispatch = _dispatch(target, now=lambda: moment[0])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with dispatch.invocation(target):
            client.get("https://api.financialdatasets.ai/prices/")
        moment[0] = _NOW + timedelta(minutes=6)
        with dispatch.invocation(target), pytest.raises(AuthorizationDenied):
            client.get("https://api.financialdatasets.ai/prices/")

    assert len(calls) == 1
    assert _authorization(dispatch, target).calls_reserved == 1


def test_expiry_after_dns_denies_before_inner_transport():
    target = ProviderTarget(kind="data", provider="fd")
    moment = [_NOW]

    def resolve(_host, _port):
        moment[0] = _NOW + timedelta(minutes=5)
        return ["8.8.8.8"]

    dispatch = _dispatch(target, now=lambda: moment[0], resolver=resolve)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get("https://api.financialdatasets.ai/prices/")

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 1


def test_fence_change_after_dns_denies_before_inner_transport():
    target = ProviderTarget(kind="data", provider="fd")
    fence_checks = []

    def boundary_check():
        fence_checks.append(True)
        if len(fence_checks) == 2:
            raise AuthorizationDenied("operation fence changed")

    dispatch = _dispatch(target, boundary_check=boundary_check)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied, match="operation fence changed"):
            client.get("https://api.financialdatasets.ai/prices/")

    assert fence_checks == [True, True]
    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 1


def test_private_dns_answer_denies_before_inner_transport():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target, resolver=lambda _host, _port: ["127.0.0.1"])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get("https://api.financialdatasets.ai/prices/")

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 1


@pytest.mark.parametrize(
    "answers",
    [
        ["8.8.8.8", "127.0.0.1"],
        ["169.254.169.254"],
        ["::ffff:8.8.8.8"],
        ["::1"],
    ],
)
def test_destination_rejects_non_global_or_mapped_dns_answers(answers):
    with pytest.raises(AuthorizationDenied):
        resolve_destination(
            "api.openai.com",
            443,
            local=False,
            resolver=lambda _host, _port: answers,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.financialdatasets.ai/prices/",
        "https://evil.example/prices/",
        "https://user:pass@api.financialdatasets.ai/prices/",
        "https://api.financialdatasets.ai/prices/?api_key=secret",
        "https://api.financialdatasets.ai/prices/?access_token=secret",
        "https://api.financialdatasets.ai/prices/?access_key=secret",
        "https://api.financialdatasets.ai/prices/?AWSAccessKeyId=secret",
        "https://api.financialdatasets.ai/prices/?X-Amz-Credential=secret",
        "https://api.financialdatasets.ai/prices/?X-Amz-Signature=secret",
        "https://api.financialdatasets.ai/prices/?X-Amz-Security-Token=secret",
        "https://api.financialdatasets.ai/prices/?client_secret=secret",
    ],
)
def test_destination_mismatch_denies_before_inner_transport(url):
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get(url)

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_host_header_mismatch_denies_before_inner_transport():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get(
                "https://api.financialdatasets.ai/prices/",
                headers={"Host": "evil.example"},
            )

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_redirect_is_not_followed():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example/"},
            request=request,
        )

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get("https://api.financialdatasets.ai/prices/")

    assert len(calls) == 1


def test_unknown_paid_cost_denies_before_fake_transport():
    target = ProviderTarget(kind="llm", provider="openai", model="gpt-6-sol")
    dispatch = _dispatch(target)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied, match="cost is unknown"):
            client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-6-sol"},
            )

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_paid_cost_bound_must_cover_verified_provider_maximum():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(target, upper_bound_cost=Decimal("0.15"))
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(BudgetDenied, match="exceeds authorization"):
            client.get("https://api.financialdatasets.ai/prices/")

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_typesafe_worst_case_is_reserved_before_fake_transport():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")
    dispatch = _dispatch(
        target,
        max_cost=Decimal("0.002688"),
        upper_bound_cost=Decimal("0.002688"),
    )
    authorization = _authorization(dispatch, target)
    calls = []

    def respond(request):
        assert authorization.calls_reserved == 1
        assert authorization.cost_reserved == Decimal("0.002688")
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        response = client.post(
            "https://api.typesafe.ai/v1/systemone",
            json={"model": "jev-1.13.0", "state": "é"},
        )

    assert response.status_code == 200
    assert len(calls) == 1
    assert authorization.cost_reserved == Decimal("0.002688")


def test_typesafe_model_mismatch_denies_before_reservation_and_transport():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")
    dispatch = _dispatch(
        target,
        max_cost=Decimal("0.002688"),
        upper_bound_cost=Decimal("0.002688"),
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied, match="cost is unknown"):
            client.post(
                "https://api.typesafe.ai/v1/systemone",
                json={"model": "jev-9.99.0", "state": "short"},
            )

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_typesafe_cap_below_context_worst_case_denies_before_transport():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")
    dispatch = _dispatch(
        target,
        max_cost=Decimal("0.01"),
        upper_bound_cost=Decimal("0.002687"),
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(BudgetDenied, match="exceeds authorization"):
            client.post(
                "https://api.typesafe.ai/v1/systemone",
                json={"model": "jev-1.13.0", "state": "short"},
            )

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_typesafe_oversized_request_denies_before_reservation_and_transport():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")
    dispatch = _dispatch(target, upper_bound_cost=Decimal("1"))
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied, match="cost is unknown"):
            client.post(
                "https://api.typesafe.ai/v1/systemone",
                content=b"x" * (1024 * 1024 + 1),
            )

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_local_ollama_uses_literal_loopback_and_zero_cost():
    target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
    )
    dispatch = _dispatch(
        target,
        resolver=lambda _host, _port: pytest.fail("local endpoints do not resolve"),
        upper_bound_cost=Decimal("0"),
        max_cost=Decimal("0"),
        approved_local_models={"gemma3:4b"},
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"message": "ok"}, request=request)

    with _client(dispatch, target, respond) as client:
        response = client.post("http://127.0.0.1:11434/api/chat", json={})

    assert response.status_code == 200
    assert len(calls) == 1
    assert _authorization(dispatch, target).cost_reserved == Decimal("0")


def test_halt_or_fence_check_denies_before_reservation_and_transport():
    target = ProviderTarget(kind="data", provider="fd")
    dispatch = _dispatch(
        target,
        boundary_check=lambda: (_ for _ in ()).throw(AuthorizationDenied("operation fence changed")),
    )
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with _client(dispatch, target, respond) as client:
        with pytest.raises(AuthorizationDenied):
            client.get("https://api.financialdatasets.ai/prices/")

    assert calls == []
    assert _authorization(dispatch, target).calls_reserved == 0


def test_dispatch_requires_network_authority():
    target = ProviderTarget(kind="data", provider="yfinance")

    with pytest.raises(AuthorizationDenied):
        ProviderDispatch(
            scope=OperationScope.MANUAL_ONE_SHOT,
            root_id="synthetic-root",
            subject_id="research-1",
            capture_digest="a" * 64,
            operation_id="operation-1",
            operation_digest="b" * 64,
            targets=(target,),
            network_authorized=False,
        )


@pytest.mark.parametrize(
    "max_calls,max_cost,max_resources,per_target",
    [
        (
            1,
            Decimal("0.32"),
            2,
            (1, Decimal("0.16"), 1, 1, Decimal("0.16"), 1),
        ),
        (
            2,
            Decimal("0.16"),
            2,
            (1, Decimal("0.16"), 1, 1, Decimal("0.16"), 1),
        ),
        (
            2,
            Decimal("0.32"),
            2,
            (1, Decimal("0.16"), 2, 1, Decimal("0.16"), 2),
        ),
    ],
)
def test_per_target_bounds_cannot_exceed_aggregate_authorization(
    max_calls,
    max_cost,
    max_resources,
    per_target,
):
    fd_target = ProviderTarget(kind="data", provider="fd")
    llm_target = ProviderTarget(
        kind="llm",
        provider="typesafe",
        model="jev-1.13.0",
    )
    targets = (fd_target, llm_target)
    fd_bounds = (per_target[0], per_target[1], per_target[2])
    llm_bounds = (per_target[3], per_target[4], per_target[5])

    with pytest.raises(AuthorizationDenied, match="aggregate"):
        make_one_shot_dispatch(
            root_id="synthetic-root",
            subject_id="research-1",
            capture_digest="a" * 64,
            operation_id="aggregate-budget",
            operation_digest="b" * 64,
            expires_at=_NOW + timedelta(minutes=5),
            targets=targets,
            max_calls=max_calls,
            max_cost=max_cost,
            max_resources=max_resources,
            upper_bound_costs={
                fd_target.identity: Decimal("0.16"),
                llm_target.identity: Decimal("0.16"),
            },
            per_target_bounds={
                fd_target.identity: fd_bounds,
                llm_target.identity: llm_bounds,
            },
            clock=lambda: _NOW,
            resolver=lambda _host, _port: ["8.8.8.8"],
        )


def test_pinned_backend_connects_to_validated_ip(monkeypatch):
    backend = _PinnedSyncBackend()
    pin = PinnedAddress(
        host="api.openai.com",
        port=443,
        address="8.8.8.8",
        local=False,
    )
    connected = []

    def connect_tcp(_self, host, port, **kwargs):
        connected.append((host, port))
        return object()

    monkeypatch.setattr(SyncBackend, "connect_tcp", connect_tcp)
    token = backend.pin(pin)
    try:
        backend.connect_tcp("api.openai.com", 443)
    finally:
        backend.unpin(token)

    assert connected == [("8.8.8.8", 443)]
