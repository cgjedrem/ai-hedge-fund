"""Immutable catalog and durable news contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NewsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegistryProvenance(NewsModel):
    name: Literal["plenaryapp/awesome-rss-feeds"]
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: Literal["CC0-1.0"]
    repository_url: Literal["https://github.com/plenaryapp/awesome-rss-feeds"]
    reviewed_on: date


class SourceLimits(NewsModel):
    max_requests: int | None = Field(default=None, ge=1, le=20)
    max_redirects: int | None = Field(default=None, ge=0, le=3)
    max_compressed_bytes: int | None = Field(default=None, ge=1, le=2 * 1024 * 1024)
    max_decompressed_bytes: int | None = Field(default=None, ge=1, le=5 * 1024 * 1024)
    max_entries: int | None = Field(default=None, ge=1, le=500)
    source_deadline_seconds: int | None = Field(default=None, ge=1, le=30)
    minimum_host_interval_seconds: float | None = Field(default=None, ge=1, le=3600)


class CurationEvidence(NewsModel):
    basis: Literal["registry-reviewed", "independently-verified"]
    registry_opml_path: str | None = Field(default=None, max_length=500)
    registry_xml_url: str | None = Field(default=None, max_length=2048)
    discovery_url: str = Field(min_length=1, max_length=2048)
    verified_on: date
    purpose: str = Field(min_length=10, max_length=500)
    rights_note: str = Field(min_length=10, max_length=1000)
    approved_by: str = Field(min_length=1, max_length=120)


class SourceDefinition(NewsModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    kind: Literal["feed", "sec-edgar"]
    publisher: str = Field(min_length=1, max_length=160)
    category: Literal["editorial", "investor-relations", "sec-filing", "regulatory", "macro"]
    url: str = Field(min_length=1, max_length=2048)
    enabled: bool
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=16)
    scope: Literal["company", "market"]
    tickers: tuple[str, ...] = Field(default=(), max_length=32)
    cik: str | None = None
    forms: tuple[str, ...] = Field(default=(), max_length=16)
    company_aliases: tuple[str, ...] = Field(default=(), max_length=64)
    freshness_seconds: int = Field(ge=60, le=31536000)
    limits: SourceLimits | None = None
    curation: CurationEvidence
    summary_policy: Literal["none", "feed-supplied"]
    sequence: int = Field(ge=0, le=1000000)


class CuratedCatalog(NewsModel):
    schema_version: Literal[1]
    catalog_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    registry: RegistryProvenance
    sources: tuple[SourceDefinition, ...] = Field(max_length=1000)

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


PublicationPrecision = Literal["second", "minute", "day", "unknown"]
Freshness = Literal["current", "stale", "unknown"]


class Attribution(NewsModel):
    source_id: str = Field(min_length=1, max_length=80)
    publisher: str = Field(min_length=1, max_length=160)
    category: Literal["editorial", "investor-relations", "sec-filing", "regulatory", "macro"]
    original_id: str | None = Field(default=None, max_length=512)
    original_url: str | None = Field(default=None, max_length=2048)
    normalized_url: str | None = Field(default=None, max_length=2048)
    original_title: str = Field(min_length=1, max_length=1000)
    published_at: datetime | None = None
    published_on: date | None = None
    publication_precision: PublicationPrecision = "unknown"
    first_seen_at: datetime
    last_seen_at: datetime
    tickers: tuple[str, ...] = Field(default=(), max_length=32)
    market_scope: bool = False
    sequence: int = Field(ge=0, le=1000000)


class NewsItem(NewsModel):
    news_id: str = Field(pattern=r"^news_[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=1000)
    summary: str | None = Field(default=None, max_length=10000)
    canonical_url: str = Field(min_length=1, max_length=2048)
    category: Literal["editorial", "investor-relations", "sec-filing", "regulatory", "macro"]
    tickers: tuple[str, ...] = Field(default=(), max_length=64)
    market_scope: bool = False
    published_at: datetime | None = None
    published_on: date | None = None
    publication_precision: PublicationPrecision = "unknown"
    first_fetched_at: datetime
    last_fetched_at: datetime
    attributions: tuple[Attribution, ...] = Field(min_length=1)
    dedupe_keys: tuple[str, ...] = Field(default=(), max_length=128)


class SourceHealth(NewsModel):
    source_id: str = Field(min_length=1, max_length=80)
    enabled: bool
    status: Literal["disabled", "never-run", "healthy", "healthy-empty", "degraded", "failed"] = "never-run"
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_publication_at: datetime | None = None
    last_run_id: str | None = None
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    stored_count: int = Field(default=0, ge=0)
    consecutive_failures: int = Field(default=0, ge=0)
    reason_code: str | None = Field(default=None, max_length=80)
    freshness_seconds: int = Field(ge=60, le=31536000)


class SourceOutcome(NewsModel):
    source_id: str = Field(min_length=1, max_length=80)
    status: Literal["healthy", "healthy-empty", "degraded", "failed"]
    started_at: datetime
    finished_at: datetime
    request_count: int = Field(default=0, ge=0)
    redirect_count: int = Field(default=0, ge=0)
    compressed_bytes: int = Field(default=0, ge=0)
    decompressed_bytes: int = Field(default=0, ge=0)
    entry_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    new_count: int = Field(default=0, ge=0)
    merged_count: int = Field(default=0, ge=0)
    reason_code: str | None = Field(default=None, max_length=80)


class RefreshLimits(NewsModel):
    max_sources: int = Field(default=100, ge=1, le=100)
    global_concurrency: int = Field(default=4, ge=1, le=4)
    per_host_concurrency: int = Field(default=1, ge=1, le=1)
    minimum_host_interval_seconds: float = Field(default=1.0, ge=1, le=3600)
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=5)
    read_timeout_seconds: float = Field(default=15.0, gt=0, le=15)
    source_deadline_seconds: float = Field(default=30.0, gt=0, le=30)
    run_deadline_seconds: float = Field(default=120.0, gt=0, le=120)
    max_redirects: int = Field(default=3, ge=0, le=3)
    max_requests_per_source: int = Field(default=20, ge=1, le=20)
    max_requests_per_run: int = Field(default=500, ge=1, le=500)
    max_compressed_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=2 * 1024 * 1024)
    max_decompressed_bytes: int = Field(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024)
    max_entries: int = Field(default=500, ge=1, le=500)


class RefreshRun(NewsModel):
    run_id: str = Field(min_length=1, max_length=128)
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ids: tuple[str, ...]
    started_at: datetime
    ended_at: datetime | None = None
    limits: RefreshLimits
    status: Literal["running", "succeeded", "partial", "failed", "no-op"]
    outcomes: tuple[SourceOutcome, ...] = ()
    total_requests: int = Field(default=0, ge=0)
    total_new_items: int = Field(default=0, ge=0)
    total_merged_items: int = Field(default=0, ge=0)


class NewsState(NewsModel):
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    catalog_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    items: dict[str, NewsItem] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)
    sources: dict[str, SourceDefinition] = Field(default_factory=dict)
    health: dict[str, SourceHealth] = Field(default_factory=dict)
    recent_runs: tuple[RefreshRun, ...] = Field(default=(), max_length=100)
    merge_conflict_count: int = Field(default=0, ge=0, le=1000000)

    @model_validator(mode="after")
    def validate_references(self):
        for key, target in self.aliases.items():
            if target not in self.items or (key in self.items and key != target):
                raise ValueError("news aliases must resolve directly to a retained item")
        for key, item in self.items.items():
            if key != item.news_id:
                raise ValueError("news item key does not match its stable identity")
        for key, source in self.sources.items():
            if key != source.source_id:
                raise ValueError("source key does not match its identity")
        for key, health in self.health.items():
            if key != health.source_id:
                raise ValueError("health key does not match its source identity")
        run_ids = [run.run_id for run in self.recent_runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("recent run identities must be unique")
        if list(self.recent_runs) != sorted(self.recent_runs, key=lambda run: (run.started_at, run.run_id)):
            raise ValueError("recent runs must have deterministic chronological order")
        return self


class SourceHealthView(SourceHealth):
    freshness: Literal["current", "stale", "unknown"] = "unknown"
    is_stale: bool | None = None


class NewsQuery(NewsModel):
    ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9.-]+$")
    include_market: bool = True
    start_date: date | None = None
    end_date: date | None = None
    categories: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    include_undated: bool = True
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("start date must not follow end date")
        return self


class NewsPage(NewsModel):
    items: tuple[NewsItem, ...] = ()
    health: tuple[SourceHealthView, ...] = ()
