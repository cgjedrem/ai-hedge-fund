"""DataClient compatibility over explicitly refreshed local news state."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError

from hedge_fund.data.models import CompanyNews, NewsAttribution
from hedge_fund.data.protocol import DataClient, DataClientError
from hedge_fund.news.models import NewsQuery
from hedge_fund.news.store import NewsStore


class CuratedNewsDataClient:
    def __init__(self, client: DataClient, store: NewsStore):
        self.client = client
        self.store = store

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def get_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
    ) -> list[CompanyNews]:
        try:
            query = NewsQuery(
                ticker=ticker.upper(),
                start_date=date.fromisoformat(start_date) if start_date is not None else None,
                end_date=date.fromisoformat(end_date),
                limit=limit,
            )
        except (ValidationError, ValueError) as exc:
            raise DataClientError("The curated news query is invalid.") from exc
        page = self.store.query(query)
        health = {value.source_id: value for value in page.health}
        results = []
        for item in page.items:
            canonical = item.attributions[0]
            state = health.get(canonical.source_id)
            published = item.published_at.isoformat() if item.published_at is not None else (item.published_on.isoformat() if item.published_on is not None else None)
            results.append(
                CompanyNews(
                    ticker=query.ticker,
                    title=item.title,
                    source=canonical.publisher,
                    date=published,
                    url=item.canonical_url or None,
                    news_id=item.news_id,
                    fetched_at=item.last_fetched_at.isoformat(),
                    category=item.category,
                    attributions=[
                        NewsAttribution(
                            source_id=value.source_id,
                            publisher=value.publisher,
                            original_id=value.original_id,
                            original_url=value.original_url,
                            published_at=value.published_at.isoformat() if value.published_at is not None else (value.published_on.isoformat() if value.published_on is not None else None),
                            fetched_at=value.last_seen_at.isoformat(),
                        )
                        for value in item.attributions
                    ],
                    source_state=f"{state.status}:{state.freshness}" if state is not None else None,
                )
            )
        return results
