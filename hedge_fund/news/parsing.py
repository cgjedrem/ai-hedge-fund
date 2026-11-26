"""Offline parsing of bounded response bytes; feedparser never receives URLs."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlsplit

import feedparser
from pydantic import Field

from .models import Attribution, NewsModel, SourceDefinition
from .normalize import clean_text, identity_keys, normalize_url, parse_publication_time


class FeedParseError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _reviewed_editorial_match(source: SourceDefinition, title: str, summary: object) -> bool:
    if source.scope != "company" or len(source.tickers) != 1 or not source.company_aliases:
        return False
    text = clean_text(f"{title} {summary or ''}", max_length=20000).casefold()
    for alias in source.company_aliases:
        normalized = clean_text(alias, max_length=500).casefold()
        if normalized and re.search(rf"(?<![\w]){re.escape(normalized)}(?![\w])", text):
            return True
    return False


class ParsedNewsEntry(NewsModel):
    attribution: Attribution
    summary: str | None = None
    dedupe_keys: tuple[str, ...]


class ParsedFeed(NewsModel):
    entries: tuple[ParsedNewsEntry, ...]
    rejected_count: int = Field(ge=0)


def parse_feed(response_bytes: bytes, source: SourceDefinition, fetched_at: datetime, *, max_entries: int = 500) -> ParsedFeed:
    if not isinstance(response_bytes, bytes) or len(response_bytes) > 5 * 1024 * 1024:
        raise FeedParseError("response-too-large")
    try:
        document = feedparser.parse(BytesIO(response_bytes))
    except Exception as exc:
        raise FeedParseError("malformed-feed") from exc
    if document.bozo or not document.get("version", "").startswith(("rss", "atom")):
        raise FeedParseError("malformed-feed")
    if len(document.entries) > max_entries:
        raise FeedParseError("entry-limit")
    entries: list[ParsedNewsEntry] = []
    rejected = 0
    for raw in document.entries:
        try:
            title = clean_text(raw.get("title"))
            original_url = raw.get("link")
            if not title or not original_url:
                raise ValueError("missing title or link")
            if source.category == "editorial" and not _reviewed_editorial_match(source, title, raw.get("summary")):
                raise ValueError("editorial entry has no reviewed company association")
            normalized = normalize_url(original_url)
            if urlsplit(normalized).hostname not in source.allowed_hosts:
                raise ValueError("unapproved article host")
            published_at = published_on = None
            precision = "unknown"
            for timestamp in (
                raw.get("published"),
                raw.get("updated"),
                raw.get("published_parsed"),
                raw.get("updated_parsed"),
            ):
                published_at, published_on, precision = parse_publication_time(timestamp)
                if precision != "unknown":
                    break
            if published_at and published_at > fetched_at + timedelta(minutes=5):
                raise ValueError("future publication")
            original_id = clean_text(raw.get("id") or raw.get("guid"), 512) or None
            associations = (*source.tickers, *(("market",) if source.scope == "market" else ()))
            attribution = Attribution(
                source_id=source.source_id,
                publisher=source.publisher,
                category=source.category,
                original_id=original_id,
                original_url=normalized,
                normalized_url=normalized,
                original_title=title,
                published_at=published_at,
                published_on=published_on,
                publication_precision=precision,
                first_seen_at=fetched_at,
                last_seen_at=fetched_at,
                tickers=source.tickers,
                market_scope=source.scope == "market",
                sequence=source.sequence,
            )
            entries.append(
                ParsedNewsEntry(
                    attribution=attribution,
                    summary=clean_text(raw.get("summary"), 10000) if source.summary_policy == "feed-supplied" else None,
                    dedupe_keys=identity_keys(
                        normalized_url=normalized,
                        title=title,
                        original_id=original_id,
                        published_at=published_at,
                        published_on=published_on,
                        associations=associations,
                    ),
                )
            )
        except (TypeError, ValueError):
            rejected += 1
    return ParsedFeed(entries=tuple(entries), rejected_count=rejected)
