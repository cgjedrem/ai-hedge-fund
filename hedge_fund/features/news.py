"""Recent headlines for a daily session — the block a daily fund's
analysts read under the fundamentals.

The fundamentals snapshot is filed data and moves a few times a year; a
daily fund asked at every close needs the week: what has been written.
`NewsContext` gathers the headlines a data client serves for one
(ticker, session) and renders them so that the same set of headlines
renders *identically* on any later date: absolute day labels, newest
last, and the session's own date never appears. An unchanged news week
means an unchanged prompt, which means the prompt cache answers and no
model is called. A new headline changes the block, and only then is the
analyst asked again.

Everything is point-in-time by construction: only items dated on or
before the session are kept, so a headline that landed after the close
is next session's news. A provider with no news history (yfinance serves
only ~100 recent items) simply returns nothing for a past session — a
backtest sees no news rather than future news.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from hedge_fund.data.protocol import DataClient
from hedge_fund.features.intraday import Headline, _aware  # shared timestamp policy

_WINDOW_DAYS = 7   # headlines older than this are not asked for
_LIMIT = 8         # the newest this many are shown


@dataclass(frozen=True)
class NewsContext:
    ticker: str
    as_of: str                       # the session; never rendered
    headlines: list[Headline]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.render().encode()).hexdigest()[:16]

    def render(self) -> str:
        """The block. Day labels are absolute, so the same headlines render
        the same text on any later session — the cache-exactness contract."""
        if not self.headlines:
            return f"Recent headlines: none in the last {_WINDOW_DAYS} days"
        lines = [f"Recent headlines (last {_WINDOW_DAYS} days, newest last):"]
        for h in self.headlines:
            lines.append(f"  {h.when.strftime('%b %d')}  {h.source}: {h.title}")
        return "\n".join(lines)


def build_news_context(
    ticker: str, as_of: str, data_client: DataClient,
    *, days: int = _WINDOW_DAYS, limit: int = _LIMIT,
) -> NewsContext:
    """Gather recent headlines for one ticker as of a daily session.

    The window is the *days* ending at the session; the data client filters
    to it, and undated items are dropped (they cannot be proven inside the
    window). Data-layer errors propagate.
    """
    day = as_of[:10]
    start = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    items = data_client.get_news(ticker, end_date=day, start_date=start, limit=limit)
    headlines = [
        Headline(when=_aware(item.date), source=item.source, title=item.title.strip())
        for item in items
        if item.date is not None and item.date[:10] <= day
    ]
    headlines.sort(key=lambda h: (h.when, h.title))
    return NewsContext(ticker=ticker, as_of=as_of, headlines=headlines)