"""Versioned, atomically committed local news state."""

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from hedge_fund import paths
from hedge_fund.data.protocol import DataClientError
from hedge_fund.news.models import (
    Attribution,
    NewsItem,
    NewsPage,
    NewsQuery,
    NewsState,
    RefreshRun,
    SourceDefinition,
    SourceHealth,
    SourceHealthView,
)
from hedge_fund.news.parsing import ParsedNewsEntry
from hedge_fund.runtime.root import RootContext


class NewsRevisionConflict(DataClientError):
    """The caller read a different revision from the one being replaced."""


class NewsStore:
    def __init__(self, root: RootContext, *, clock: Callable[[], datetime] | None = None):
        self.root = root
        self.path = Path(root.resolve("cache/news/state.json"))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def query(self, query: NewsQuery) -> NewsPage:
        state = self.load()
        selected = []
        for item in state.items.values():
            if query.ticker is not None and query.ticker not in item.tickers and not (query.include_market and item.market_scope):
                continue
            if query.categories and item.category not in query.categories:
                continue
            if query.source_ids and not any(value.source_id in query.source_ids for value in item.attributions):
                continue
            published = self._publication_sort_key(item)
            if published is None and not query.include_undated:
                continue
            if published is not None:
                published_on = published.date()
                if query.start_date is not None and published_on < query.start_date:
                    continue
                if query.end_date is not None and published_on > query.end_date:
                    continue
            selected.append(item)
        selected.sort(key=lambda item: (item.canonical_url, item.news_id))
        selected.sort(
            key=lambda item: self._publication_sort_key(item) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        relevant_sources = []
        for source_id, source in state.sources.items():
            if query.source_ids and source_id not in query.source_ids:
                continue
            if query.categories and source.category not in query.categories:
                continue
            if query.ticker is not None and query.ticker not in source.tickers and not (query.include_market and source.scope == "market"):
                continue
            relevant_sources.append(source_id)
        return NewsPage(items=tuple(selected[: query.limit]), health=self._health_views(state, relevant_sources))

    def health(self, source_ids: tuple[str, ...] = ()) -> tuple[SourceHealthView, ...]:
        return self._health_views(self.load(), source_ids)

    def _health_views(self, state: NewsState, source_ids) -> tuple[SourceHealthView, ...]:
        selected = set(source_ids)
        views = []
        for source_id in sorted(selected or state.health.keys()):
            if source_id not in state.health:
                continue
            value = state.health[source_id]
            if value.last_success_at is None:
                freshness = "unknown"
            else:
                age = max(0.0, (self.clock() - value.last_success_at).total_seconds())
                freshness = "current" if age <= value.freshness_seconds else "stale"
            views.append(
                SourceHealthView(
                    **value.model_dump(),
                    freshness=freshness,
                    is_stale=True if freshness == "stale" else False if freshness == "current" else None,
                )
            )
        return tuple(views)

    @staticmethod
    def _publication_sort_key(item: NewsItem) -> datetime | None:
        if item.published_at is not None:
            return item.published_at
        if item.published_on is not None:
            return datetime.combine(item.published_on, datetime.min.time(), tzinfo=timezone.utc)
        return None

    def load(self) -> NewsState:
        try:
            path = self.root.resolve("cache/news/state.json")
            if not path.exists():
                return NewsState()
            return NewsState.model_validate_json(self.root.read_bytes("cache/news/state.json"))
        except DataClientError:
            raise
        except (OSError, ValueError, ValidationError) as exc:
            raise DataClientError("The curated news state is invalid; no records were returned.") from exc

    def commit(
        self,
        *,
        expected_revision: int,
        run: RefreshRun,
        entries: tuple[ParsedNewsEntry, ...],
        sources: tuple[SourceDefinition, ...],
    ) -> NewsState:
        with paths._root_write_admission(self.root, "cache/news/state.json"):
            previous = self.load()
            if any(item.run_id == run.run_id for item in previous.recent_runs):
                return previous
            if previous.revision != expected_revision:
                raise NewsRevisionConflict("The curated news state changed; refresh the snapshot before retrying.")

            definitions = {**previous.sources, **{item.source_id: item for item in sources}}
            items = dict(previous.items)
            aliases = dict(previous.aliases)
            merge_conflicts = 0
            for parsed in sorted(entries, key=lambda item: (item.attribution.source_id, item.attribution.original_id or "", item.attribution.normalized_url or "", item.dedupe_keys)):
                merge_conflicts += self._merge(items, aliases, parsed)
            health = dict(previous.health)
            for source_id, definition in definitions.items():
                old = health.get(source_id)
                outcome = next((item for item in run.outcomes if item.source_id == source_id), None)
                if outcome is None:
                    health[source_id] = old or SourceHealth(source_id=source_id, enabled=definition.enabled, status="never-run" if definition.enabled else "disabled", freshness_seconds=definition.freshness_seconds)
                    continue
                if old is not None and old.last_attempt_at is not None and outcome.started_at < old.last_attempt_at:
                    continue
                success = outcome.status in {"healthy", "healthy-empty", "degraded"}
                failures = 0 if success else (old.consecutive_failures + 1 if old is not None else 1)
                publications = [item.attribution.published_at for item in entries if item.attribution.source_id == source_id and item.attribution.published_at is not None]
                if old is not None and old.last_publication_at is not None:
                    publications.append(old.last_publication_at)
                publication = max(publications, default=None)
                health[source_id] = SourceHealth(
                    source_id=source_id,
                    enabled=definition.enabled,
                    status=outcome.status if definition.enabled else "disabled",
                    last_attempt_at=outcome.started_at,
                    last_success_at=outcome.finished_at if success else (old.last_success_at if old is not None else None),
                    last_publication_at=publication,
                    last_run_id=run.run_id,
                    accepted_count=outcome.accepted_count,
                    rejected_count=outcome.rejected_count,
                    stored_count=outcome.new_count,
                    consecutive_failures=failures,
                    reason_code=outcome.reason_code,
                    freshness_seconds=definition.freshness_seconds,
                )
            state = NewsState(
                revision=previous.revision + 1,
                catalog_digest=run.catalog_digest,
                items=items,
                aliases=aliases,
                sources=definitions,
                health=health,
                recent_runs=tuple(sorted((run, *previous.recent_runs), key=lambda item: (item.started_at, item.run_id)))[-100:],
                merge_conflict_count=min(1000000, previous.merge_conflict_count + merge_conflicts),
            )
            payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            relative = "cache/news/state.json"
            temporary = f"cache/news/.state.json.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            self.root.mkdir("cache/news", parents=True)
            try:
                self.root.write_bytes(temporary, payload, mode=0o600)
                self.root.replace_file(temporary, relative)
            except BaseException:
                try:
                    self.root.unlink_file(temporary)
                except FileNotFoundError:
                    pass
                raise
            return state

    def _merge(self, items: dict[str, NewsItem], aliases: dict[str, str], parsed: ParsedNewsEntry) -> int:
        keys = set(parsed.dedupe_keys)
        strong_keys = {key for key in keys if not key.startswith("title:")}
        title_keys = keys - strong_keys
        incoming_sec = {key for key in strong_keys if key.startswith("sec:")}
        merge_conflicts = 0
        matching = {aliases[key] for key in strong_keys if aliases.get(key) in items}
        matching.update(item_id for item_id, item in items.items() if strong_keys.intersection(item.dedupe_keys))
        if title_keys:
            for item_id, item in items.items():
                if not title_keys.intersection(item.dedupe_keys):
                    continue
                existing_sec = {key for key in item.dedupe_keys if key.startswith("sec:")}
                if incoming_sec and existing_sec and incoming_sec.isdisjoint(existing_sec):
                    merge_conflicts += 1
                    continue
                incoming_native = parsed.attribution.original_id
                existing_native = {value.original_id for value in item.attributions if value.source_id == parsed.attribution.source_id and value.original_id}
                if incoming_native and existing_native and incoming_native not in existing_native:
                    merge_conflicts += 1
                    continue
                matching.add(item_id)
        news_id = min(matching) if matching else "news_" + hashlib.sha256(parsed.dedupe_keys[0].encode("utf-8")).hexdigest()
        clusters = [items[item_id] for item_id in sorted(matching)]
        attribution = parsed.attribution
        attributions = {(value.source_id, value.original_id, value.normalized_url): value for cluster in clusters for value in cluster.attributions}
        attribution_key = (attribution.source_id, attribution.original_id, attribution.normalized_url)
        old = attributions.get(attribution_key)
        if old is not None:
            attribution = attribution.model_copy(
                update={
                    "first_seen_at": min(old.first_seen_at, attribution.first_seen_at),
                    "last_seen_at": max(old.last_seen_at, attribution.last_seen_at),
                }
            )
        attributions[attribution_key] = attribution

        def precedence(value: Attribution) -> tuple:
            accession = (value.original_id or "").replace("-", "")
            official_filing = value.category == "sec-filing" and accession.isdigit() and len(accession) == 18
            return (
                not official_filing,
                value.sequence,
                value.published_at is None,
                value.published_at or value.first_seen_at,
                value.normalized_url or "",
                value.source_id,
                value.original_id or "",
                value.original_title,
            )

        all_attributions = tuple(sorted(attributions.values(), key=precedence))
        canonical = all_attributions[0]
        all_keys = keys.union(*(set(cluster.dedupe_keys) for cluster in clusters))
        summary = parsed.summary
        if summary is None:
            summary = next((cluster.summary for cluster in clusters if cluster.summary is not None), None)
        item = NewsItem(
            news_id=news_id,
            title=canonical.original_title,
            summary=summary,
            canonical_url=canonical.normalized_url or canonical.original_url or "",
            category=canonical.category,
            tickers=tuple(sorted({ticker for value in all_attributions for ticker in value.tickers})),
            market_scope=any(value.market_scope for value in all_attributions),
            published_at=canonical.published_at,
            published_on=canonical.published_on,
            publication_precision=canonical.publication_precision,
            first_fetched_at=min([attribution.first_seen_at, *(cluster.first_fetched_at for cluster in clusters)]),
            last_fetched_at=max([attribution.last_seen_at, *(cluster.last_fetched_at for cluster in clusters)]),
            attributions=all_attributions,
            dedupe_keys=tuple(sorted(all_keys)),
        )
        for absorbed in matching:
            items.pop(absorbed, None)
        items[news_id] = item
        for key, target in tuple(aliases.items()):
            if target in matching:
                aliases[key] = news_id
        for absorbed in matching:
            aliases[absorbed] = news_id
        for key in item.dedupe_keys:
            aliases[key] = news_id
        aliases[news_id] = news_id
        return merge_conflicts
