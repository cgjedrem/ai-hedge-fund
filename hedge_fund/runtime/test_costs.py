from decimal import Decimal

import pytest

from hedge_fund.runtime.costs import (
    cost_model_identity,
    COST_MODEL_VERSION,
    has_verified_cost_model,
    minimum_attempt_cost,
    request_cost_upper_bound,
)
from hedge_fund.runtime.policy import ProviderTarget


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
