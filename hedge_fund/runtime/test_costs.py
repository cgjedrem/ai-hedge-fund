import json
from decimal import Decimal

import pytest

from hedge_fund.runtime.costs import (
    cost_model_description,
    cost_model_identity,
    COST_MODEL_VERSION,
    has_verified_cost_model,
    minimum_attempt_cost,
    request_cost_upper_bound,
)
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget


def test_financial_datasets_bound_uses_maximum_published_self_service_rate():
    target = ProviderTarget(kind="data", provider="fd")

    assert has_verified_cost_model(target)
    assert cost_model_identity(target) == "fd-self-service-max-8x-v1"
    assert minimum_attempt_cost(target) == Decimal("0.16")
    assert request_cost_upper_bound(
        target,
        url="https://api.financialdatasets.ai/financial-metrics/?ticker=AAPL",
        method="GET",
        body=b"",
    ) == Decimal("0.16")


def test_typesafe_cost_uses_documented_context_ceiling_and_input_rate():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")
    body = '{"model":"jev-1.13.0","state":"é"}'.encode("utf-8")

    assert has_verified_cost_model(target)
    assert cost_model_identity(target) == "typesafe-jev-1.13.0-64k-context-v1"
    assert minimum_attempt_cost(target) == Decimal("0.002688")
    assert request_cost_upper_bound(
        target,
        url="https://api.typesafe.ai/v1/systemone",
        method="POST",
        body=body,
    ) == Decimal("0.002688")


def test_typesafe_model_mismatch_has_no_cost_bound():
    target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")

    assert (
        request_cost_upper_bound(
            target,
            url="https://api.typesafe.ai/v1/systemone",
            method="POST",
            body=b'{"model":"jev-9.99.0"}',
        )
        is None
    )


def test_ollama_cloud_has_no_verified_cost_model_without_operator_pricing():
    target = ProviderTarget(kind="llm", provider="ollama", model="kimi-k3:cloud")

    assert not has_verified_cost_model(target)
    assert cost_model_identity(target) is None
    assert minimum_attempt_cost(target) is None
    assert (
        request_cost_upper_bound(
            target,
            url="http://127.0.0.1:11434/api/chat",
            method="POST",
            body=b'{"model":"kimi-k3:cloud"}',
        )
        is None
    )


def test_kimi_k3_1_pro_ollama_cost_model_uses_operator_rates_and_context_bound():
    target = ProviderTarget(kind="llm", provider="ollama", model="kimi-k3.1-pro:cloud")
    default_request = json.dumps(
        {
            "model": target.model,
            "messages": [],
            "options": {"num_ctx": 8192, "num_predict": 4096},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    maximum_request = json.dumps(
        {
            "model": target.model,
            "messages": [],
            "options": {"num_ctx": 1_000_000, "num_predict": 131_072},
        },
        separators=(",", ":"),
    ).encode("utf-8")

    assert has_verified_cost_model(target)
    assert cost_model_identity(target) == "ollama-kimi-k3.1-pro-1m-context-v1"
    assert minimum_attempt_cost(target) == Decimal("3.31072")
    assert "$2.00/1M input ($0.20 cached), $10.00/1M output" in cost_model_description(target)
    assert request_cost_upper_bound(
        target,
        url="http://127.0.0.1:11434/api/chat",
        method="POST",
        body=default_request,
    ) == Decimal("2.04096")
    assert request_cost_upper_bound(
        target,
        url="http://127.0.0.1:11434/api/chat",
        method="POST",
        body=maximum_request,
    ) == Decimal("3.31072")
    assert not has_verified_cost_model(ProviderTarget(kind="llm", provider="ollama", model="kimi-k3:cloud"))


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "http://127.0.0.1",
        "http://127.0.0.1/",
        "http://127.0.0.1:11434",
        "http://127.0.0.1:11434/",
    ],
    ids=["default", "host-only", "host-slash", "port", "port-slash"],
)
def test_kimi_cost_model_normalizes_approved_loopback_endpoints(endpoint):
    from hedge_fund.runtime.endpoints import validate_provider_target

    target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="kimi-k3.1-pro:cloud",
        endpoint=endpoint,
    )

    validate_provider_target(target, per_operation_authorization_supplied=True)

    assert has_verified_cost_model(target)
    assert cost_model_identity(target) == "ollama-kimi-k3.1-pro-1m-context-v1"
    assert minimum_attempt_cost(target) == Decimal("3.31072")


def test_kimi_cost_model_rejects_non_loopback_endpoint():
    from hedge_fund.runtime.endpoints import validate_provider_target

    target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="kimi-k3.1-pro:cloud",
        endpoint="http://127.0.0.2:11434",
    )

    assert not has_verified_cost_model(target)
    assert cost_model_identity(target) is None
    with pytest.raises(AuthorizationDenied, match="Ollama endpoint"):
        validate_provider_target(target, per_operation_authorization_supplied=True)


@pytest.mark.parametrize(
    ("target", "url", "method", "body"),
    [
        (
            ProviderTarget(kind="llm", provider="openai", model="gpt-6-sol"),
            "https://api.openai.com/v1/chat/completions",
            "POST",
            b"{}",
        ),
        (
            ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0"),
            "https://api.typesafe.ai/v1/models",
            "GET",
            b"",
        ),
        (
            ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0"),
            "http://api.typesafe.ai/v1/systemone",
            "POST",
            b"{}",
        ),
        (
            ProviderTarget(kind="data", provider="fd"),
            "https://api.financialdatasets.ai/prices/",
            "DELETE",
            b"",
        ),
    ],
)
def test_unknown_request_cost_fails_closed(target, url, method, body):
    assert (
        request_cost_upper_bound(
            target,
            url=url,
            method=method,
            body=body,
        )
        is None
    )


def test_typesafe_custom_endpoint_and_oversized_request_have_no_bound():
    target = ProviderTarget(
        kind="llm",
        provider="typesafe",
        model="jev-1.13.0",
        endpoint="https://api.typesafe.ai",
    )
    default_target = ProviderTarget(kind="llm", provider="typesafe", model="jev-1.13.0")

    assert not has_verified_cost_model(target)
    assert cost_model_identity(target) is None
    assert (
        request_cost_upper_bound(
            default_target,
            url="https://api.typesafe.ai/v1/systemone",
            method="POST",
            body=b"x" * (1024 * 1024 + 1),
        )
        is None
    )
    assert COST_MODEL_VERSION == "2026-11-01-v2"
