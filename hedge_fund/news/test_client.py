from datetime import timedelta

import pytest

from hedge_fund.data.cached import CachedDataClient
from hedge_fund.data.models import CompanyFacts, CompanyNews
from hedge_fund.data.protocol import DataClientError
from hedge_fund.features.news import build_news_context
from hedge_fund.news.client import CuratedNewsDataClient
from hedge_fund.news.store import NewsStore
from hedge_fund.news.test_store import definition, entry, NOW, run, synthetic_store


class LegacyClient:
    def __init__(self):
        self.news_calls = 0
        self.facts_calls = 0

    def get_news(self, *_args, **_kwargs):
        self.news_calls += 1
        raise AssertionError("legacy news must not be called")

    def get_company_facts(self, ticker):
        self.facts_calls += 1
        return CompanyFacts(ticker=ticker, name="Example")


def test_curated_adapter_bypasses_legacy_news_and_delegates_other_methods(tmp_path):
    with synthetic_store(tmp_path) as (_store, root):
        configured = definition()
        store = NewsStore(root, clock=lambda: NOW)
        store.commit(
            expected_revision=0,
            run=run(),
            entries=(entry(configured),),
            sources=(configured,),
        )
        legacy = LegacyClient()
        cached = CachedDataClient(legacy, cache_dir=root.resolve("cache/data"))
        client = CuratedNewsDataClient(cached, store)

        items = client.get_news("example", "2026-11-25", "2026-11-25", 10)
        facts = client.get_company_facts("EXAMPLE")

        assert legacy.news_calls == 0
        assert legacy.facts_calls == 1
        assert facts.name == "Example"
        assert len(items) == 1
        item = items[0]
        assert item.ticker == "EXAMPLE"
        assert item.title == "Results"
        assert item.source == configured.publisher
        assert item.news_id.startswith("news_")
        assert item.date == "2026-11-25T17:34:56+00:00"
        assert item.fetched_at == NOW.isoformat()
        assert item.category == "investor-relations"
        assert item.source_state == "healthy:current"
        assert len(item.attributions) == 1
        assert item.attributions[0].source_id == configured.source_id
        assert item.attributions[0].original_url == item.url


def test_curated_adapter_rejects_invalid_queries_before_reading():
    client = CuratedNewsDataClient(LegacyClient(), object())

    for arguments in (
        ("example", "not-a-date", None, 10),
        ("example", "2026-11-24", "2026-11-25", 10),
        ("example", "2026-11-25", None, 0),
        ("example", "2026-11-25", None, 1001),
    ):
        with pytest.raises(DataClientError, match="query is invalid"):
            client.get_news(*arguments)

    legacy = CompanyNews(ticker="EXAMPLE", title="Old", source="Fixture", date=None, url=None)
    assert legacy.news_id is None
    assert legacy.attributions == []


def test_metadata_only_refresh_does_not_change_analyst_news_hash(tmp_path):
    with synthetic_store(tmp_path) as (_store, root):
        configured = definition()
        store = NewsStore(root, clock=lambda: NOW)
        store.commit(expected_revision=0, run=run(), entries=(entry(configured),), sources=(configured,))
        client = CuratedNewsDataClient(LegacyClient(), store)
        first = build_news_context("EXAMPLE", "2026-11-25", client)
        first_fetched_at = client.get_news("EXAMPLE", "2026-11-25")[0].fetched_at

        later = NOW + timedelta(days=1)
        refreshed = entry(configured).model_copy(update={"attribution": entry(configured).attribution.model_copy(update={"last_seen_at": later})})
        store.commit(
            expected_revision=1,
            run=run(run_id="run-2", started_at=later, new_count=0),
            entries=(refreshed,),
            sources=(configured,),
        )
        second = build_news_context("EXAMPLE", "2026-11-25", client)

        assert client.get_news("EXAMPLE", "2026-11-25")[0].fetched_at != first_fetched_at
        assert second.render() == first.render()
        assert second.content_hash == first.content_hash
