import pytest

from hedge_fund.runtime.endpoints import validate_provider_target, validate_request_url
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget


def test_curated_news_target_is_bound_to_one_exact_https_origin():
    target = ProviderTarget(
        kind="data",
        provider="curated-news",
        endpoint="https://www.federalreserve.gov",
    )

    validate_provider_target(target)
    assert validate_request_url(
        target,
        "https://www.federalreserve.gov/feeds/press_all.xml",
    ) == ("www.federalreserve.gov", 443, False)

    with pytest.raises(AuthorizationDenied):
        validate_request_url(target, "https://example.com/feed.xml")
    with pytest.raises(AuthorizationDenied):
        validate_request_url(target, "http://www.federalreserve.gov/feed.xml")
    with pytest.raises(AuthorizationDenied):
        validate_provider_target(ProviderTarget(kind="data", provider="curated-news"))
