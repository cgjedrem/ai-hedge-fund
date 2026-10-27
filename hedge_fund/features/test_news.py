"""NewsContext — the week's headlines under a daily fund's fundamentals.

The contract under test: point-in-time (only items dated on or before the
session), newest last, undated items dropped, and cache-exactness — the
same headline set renders identically on any later session, so a quiet
news week is a prompt-cache hit and costs no model calls.
"""

import pytest

from hedge_fund.data.models import CompanyNews
from hedge_fund.features.news import NewsContext, build_news_context


class MockNewsClient:
    def __init__(self, items):
        self._items = items
        self.calls = []

    def get_news(self, ticker, end_date, start_date=None, limit=100):
        self.calls.append({"ticker": ticker, "end_date": end_date,
                           "start_date": start_date, "limit": limit})
        return self._items


def _item(title, when, source="Reuters"):
    return CompanyNews(ticker="TEST", title=title, source=source, date=when, url="https://x")


def test_window_is_the_seven_days_ending_at_the_session():
    client = MockNewsClient([])
    build_news_context("TEST", "2025-01-15", client)
    assert client.calls[0]["start_date"] == "2025-01-08"
    assert client.calls[0]["end_date"] == "2025-01-15"


def test_headlines_render_newest_last_with_absolute_days():
    client = MockNewsClient([
        _item("Later news", "2025-01-14T18:00:00Z"),
        _item("Earlier news", "2025-01-10T15:00:00Z"),
    ])
    text = build_news_context("TEST", "2025-01-15", client).render()
    assert text.index("Earlier news") < text.index("Later news")
    assert "Jan 10" in text and "Jan 14" in text
    assert "2025-01-15" not in text  # the session itself never appears


def test_undated_items_are_dropped():
    client = MockNewsClient([
        _item("Dated", "2025-01-12T15:00:00Z"),
        CompanyNews(ticker="TEST", title="Undated", source="X", date=None, url="u"),
    ])
    context = build_news_context("TEST", "2025-01-15", client)
    assert [h.title for h in context.headlines] == ["Dated"]


def test_empty_window_renders_the_none_line():
    text = build_news_context("TEST", "2025-01-15", MockNewsClient([])).render()
    assert text == "Recent headlines: none in the last 7 days"


def test_same_headlines_render_identically_on_a_later_session():
    """Cache-exactness: the block keys the prompt, so an unchanged news
    week must render the same text (and hash) days later."""
    items = [
        _item("One", "2025-01-10T15:00:00Z"),
        _item("Two", "2025-01-13T09:00:00Z", source="Bloomberg"),
    ]
    early = build_news_context("TEST", "2025-01-15", MockNewsClient(items))
    late = build_news_context("TEST", "2025-01-20", MockNewsClient(items))
    assert early.render() == late.render()
    assert early.content_hash == late.content_hash


def test_a_new_headline_changes_the_hash():
    early = build_news_context("TEST", "2025-01-15", MockNewsClient(
        [_item("One", "2025-01-10T15:00:00Z")]))
    late = build_news_context("TEST", "2025-01-15", MockNewsClient([
        _item("One", "2025-01-10T15:00:00Z"),
        _item("Two", "2025-01-14T09:00:00Z"),
    ]))
    assert early.content_hash != late.content_hash


def test_items_after_the_session_are_excluded():
    """Point-in-time: the data client filters to the window, but a stray
    future-dated item must not survive either."""
    client = MockNewsClient([
        _item("Before", "2025-01-12T15:00:00Z"),
        _item("After", "2025-01-16T15:00:00Z"),
    ])
    context = build_news_context("TEST", "2025-01-15", client)
    assert [h.title for h in context.headlines] == ["Before"]


def test_context_is_frozen():
    context = build_news_context("TEST", "2025-01-15", MockNewsClient([]))
    with pytest.raises(Exception):
        context.ticker = "OTHER"