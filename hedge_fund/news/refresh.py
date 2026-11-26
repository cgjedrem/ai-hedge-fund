"""Finite, injectable coordination for explicitly selected news sources."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Protocol
from urllib.parse import urlsplit

from hedge_fund.data.protocol import DataClientError
from hedge_fund.news.filings import (
    EDGAR_WORKER_REASON_CODES,
    EdgarFilingProvider,
    EdgarWorkerError,
    filing_news_entries,
    FilingRecord,
    IsolatedEdgarSubmissionParser,
)
from hedge_fund.news.models import (
    CuratedCatalog,
    RefreshLimits,
    RefreshRun,
    SourceDefinition,
    SourceOutcome,
)
from hedge_fund.news.parsing import FeedParseError, parse_feed, ParsedNewsEntry
from hedge_fund.news.store import NewsStore
from hedge_fund.news.transport import (
    DestinationDenied,
    FetchRequest,
    FetchResponse,
    GuardedNewsTransport,
    InvalidResponse,
    RequestTimeout,
    ResponseLimitExceeded,
)
from hedge_fund.runtime.dispatch import ProviderDispatch
from hedge_fund.runtime.policy import AuthorizationDenied, BudgetDenied, ProviderTarget
from hedge_fund.runtime.root import RootContext

RequestGate = Callable[[str], AbstractContextManager[None]]


class FeedTransport(Protocol):
    def fetch(self, request: FetchRequest) -> FetchResponse:
        ...


TransportFactory = Callable[[SourceDefinition, tuple[ProviderTarget, ...], RequestGate], FeedTransport]


class FilingProvider(Protocol):
    def get_filings(self, source: SourceDefinition, *, limit: int) -> tuple[FilingRecord, ...]:
        ...


FilingProviderFactory = Callable[[SourceDefinition, FeedTransport], FilingProvider]


def _effective_limits(limits: RefreshLimits, source: SourceDefinition) -> RefreshLimits:
    overrides = source.limits
    if overrides is None:
        return limits
    return limits.model_copy(
        update={
            "max_requests_per_source": min(limits.max_requests_per_source, overrides.max_requests or limits.max_requests_per_source),
            "max_redirects": min(limits.max_redirects, overrides.max_redirects if overrides.max_redirects is not None else limits.max_redirects),
            "max_compressed_bytes": min(limits.max_compressed_bytes, overrides.max_compressed_bytes or limits.max_compressed_bytes),
            "max_decompressed_bytes": min(limits.max_decompressed_bytes, overrides.max_decompressed_bytes or limits.max_decompressed_bytes),
            "max_entries": min(limits.max_entries, overrides.max_entries or limits.max_entries),
            "source_deadline_seconds": min(limits.source_deadline_seconds, overrides.source_deadline_seconds or limits.source_deadline_seconds),
            "minimum_host_interval_seconds": max(limits.minimum_host_interval_seconds, overrides.minimum_host_interval_seconds or limits.minimum_host_interval_seconds),
        }
    )


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    run_id: str
    catalog: CuratedCatalog
    source_ids: tuple[str, ...]
    root: RootContext
    dispatch: ProviderDispatch
    limits: RefreshLimits
    wall_clock: Callable[[], datetime]
    monotonic_clock: Callable[[], float]
    waiter: Callable[[float], None]
    transport_factory: TransportFactory | None = None
    filing_provider_factory: FilingProviderFactory | None = None
    sec_identity: str | None = field(default=None, repr=False)


class RefreshDeadlineExceeded(RuntimeError):
    pass


class _DeadlineCheckpoint:
    def __init__(self, controller: _RequestController, source: SourceDefinition, source_started: float) -> None:
        self.controller = controller
        self.source = source
        self.source_started = source_started

    def __call__(self) -> None:
        self.controller.check_deadline(self.source, self.source_started)

    def remaining_seconds(self) -> float:
        source_limit = self.source.limits.source_deadline_seconds if self.source.limits and self.source.limits.source_deadline_seconds is not None else self.controller.request.limits.source_deadline_seconds
        deadline = min(
            self.source_started + min(self.controller.request.limits.source_deadline_seconds, source_limit),
            self.controller.started + self.controller.request.limits.run_deadline_seconds,
        )
        return max(0.0, deadline - self.controller.request.monotonic_clock())


class _RequestController:
    def __init__(self, request: RefreshRequest, started: float) -> None:
        self.request = request
        self.started = started
        self.lock = Lock()
        self.host_locks: dict[str, Lock] = {}
        self.next_host_start: dict[str, float] = {}
        self.total_requests = 0

    def check_deadline(self, source: SourceDefinition, source_started: float) -> None:
        source_deadline = source_started + min(
            self.request.limits.source_deadline_seconds,
            source.limits.source_deadline_seconds if source.limits and source.limits.source_deadline_seconds is not None else self.request.limits.source_deadline_seconds,
        )
        run_deadline = self.started + self.request.limits.run_deadline_seconds
        if self.request.monotonic_clock() >= min(source_deadline, run_deadline):
            raise RefreshDeadlineExceeded("source deadline")

    @contextmanager
    def gate(
        self,
        source: SourceDefinition,
        source_state: dict[str, int],
        url: str,
        source_started: float,
    ) -> Iterator[Callable[[], None]]:
        with self.lock:
            self.check_deadline(source, source_started)
            source_limit = min(
                self.request.limits.max_requests_per_source,
                source.limits.max_requests if source.limits and source.limits.max_requests is not None else self.request.limits.max_requests_per_source,
            )
            if source_state["requests"] >= source_limit or self.total_requests >= self.request.limits.max_requests_per_run:
                raise BudgetDenied("news request bound would be exceeded")
            source_state["requests"] += 1
            self.total_requests += 1
            host = (urlsplit(url).hostname or "").casefold()
            host_lock = self.host_locks.setdefault(host, Lock())
        with host_lock:
            now = self.request.monotonic_clock()
            wait = max(0.0, self.next_host_start.get(host, 0.0) - now)
            source_deadline = source_started + min(
                self.request.limits.source_deadline_seconds,
                source.limits.source_deadline_seconds if source.limits and source.limits.source_deadline_seconds is not None else self.request.limits.source_deadline_seconds,
            )
            remaining = max(0.0, min(source_deadline, self.started + self.request.limits.run_deadline_seconds) - now)
            if wait:
                self.request.waiter(min(wait, remaining))
            self.check_deadline(source, source_started)
            self.next_host_start[host] = self.request.monotonic_clock() + max(
                self.request.limits.minimum_host_interval_seconds,
                source.limits.minimum_host_interval_seconds if source.limits and source.limits.minimum_host_interval_seconds is not None else self.request.limits.minimum_host_interval_seconds,
            )
            yield _DeadlineCheckpoint(self, source, source_started)


class NewsRefresher:
    def refresh(self, request: RefreshRequest) -> RefreshRun:
        selected = self._selected(request)
        started_at = request.wall_clock()
        if not selected:
            return RefreshRun(
                run_id=request.run_id,
                catalog_digest=request.catalog.digest,
                source_ids=(),
                started_at=started_at,
                ended_at=request.wall_clock(),
                limits=request.limits,
                status="no-op",
            )
        store = NewsStore(request.root)
        previous = store.load()
        controller = _RequestController(request, request.monotonic_clock())
        entries: list[ParsedNewsEntry] = []
        with ThreadPoolExecutor(max_workers=min(request.limits.global_concurrency, len(selected)), thread_name_prefix="curated-news") as pool:
            results = list(pool.map(lambda source: self._refresh_source(request, controller, source, previous), selected))
        outcomes = [result[0] for result in results]
        for _outcome, parsed in results:
            entries.extend(parsed)
        entries.sort(
            key=lambda item: (
                item.attribution.source_id,
                item.attribution.original_id or "",
                item.attribution.normalized_url or "",
                item.dedupe_keys,
            )
        )
        outcomes = sorted(outcomes, key=lambda outcome: outcome.source_id)
        ended_at = request.wall_clock()
        successful = [item for item in outcomes if item.status != "failed"]
        status = "succeeded" if len(successful) == len(outcomes) and all(item.status != "degraded" for item in outcomes) else "partial" if successful else "failed"
        run = RefreshRun(
            run_id=request.run_id,
            catalog_digest=request.catalog.digest,
            source_ids=tuple(item.source_id for item in selected),
            started_at=started_at,
            ended_at=ended_at,
            limits=request.limits,
            status=status,
            outcomes=tuple(outcomes),
            total_requests=sum(item.request_count for item in outcomes),
            total_new_items=sum(item.new_count for item in outcomes),
            total_merged_items=sum(item.merged_count for item in outcomes),
        )
        state = store.commit(expected_revision=previous.revision, run=run, entries=tuple(entries), sources=selected)
        return next(committed for committed in state.recent_runs if committed.run_id == request.run_id)

    def _selected(self, request: RefreshRequest) -> tuple[SourceDefinition, ...]:
        by_id = {source.source_id: source for source in request.catalog.sources}
        if len(request.source_ids) > request.limits.max_sources or len(set(request.source_ids)) != len(request.source_ids):
            raise ValueError("news source selection is invalid")
        selected = []
        for source_id in request.source_ids:
            source = by_id.get(source_id)
            if source is None or not source.enabled:
                raise ValueError("news source selection is invalid")
            selected.append(source)
        selected.sort(key=lambda item: (item.sequence, item.source_id))
        required = sum(
            min(
                request.limits.max_requests_per_source,
                source.limits.max_requests if source.limits and source.limits.max_requests is not None else request.limits.max_requests_per_source,
            )
            for source in selected
        )
        if required > request.limits.max_requests_per_run:
            raise ValueError("news request reservations exceed the run bound")
        return tuple(selected)

    def _refresh_source(
        self,
        request: RefreshRequest,
        controller: _RequestController,
        source: SourceDefinition,
        previous,
    ) -> tuple[SourceOutcome, tuple[ParsedNewsEntry, ...]]:
        started_at = request.wall_clock()
        source_started = request.monotonic_clock()
        source_state = {"requests": 0}

        def gate(url):
            return controller.gate(source, source_state, url, source_started)

        targets = tuple(ProviderTarget(kind="data", provider="curated-news", endpoint=f"https://{host}") for host in source.allowed_hosts)
        limits = _effective_limits(request.limits, source)
        factory = request.transport_factory or (
            lambda selected, approved_targets, request_gate: GuardedNewsTransport(
                request.dispatch,
                targets=approved_targets,
                limits=limits,
                sec_identity=request.sec_identity,
                request_gate=request_gate,
            )
        )
        parsed: tuple[ParsedNewsEntry, ...] = ()
        response: FetchResponse | None = None
        status = "failed"
        reason = None
        accepted = rejected = 0
        try:
            if request.monotonic_clock() >= controller.started + request.limits.run_deadline_seconds:
                raise RefreshDeadlineExceeded("run deadline")
            transport = factory(source, targets, gate)
            if source.kind == "feed":
                response = transport.fetch(
                    FetchRequest(
                        source_id=source.source_id,
                        url=source.url,
                        accepted_media_types=("application/rss+xml", "application/atom+xml", "application/xml", "text/xml"),
                        sec_identity_required=False,
                    )
                )
                controller.check_deadline(source, source_started)
                document = parse_feed(response.content, source, started_at, max_entries=limits.max_entries)
                controller.check_deadline(source, source_started)
                parsed = document.entries
                accepted = len(parsed)
                rejected = document.rejected_count
            else:
                if request.filing_provider_factory is not None:
                    provider = request.filing_provider_factory(source, transport)
                else:
                    deadline = _DeadlineCheckpoint(controller, source, source_started)

                    def worker_timeout() -> float:
                        remaining = deadline.remaining_seconds()
                        if remaining <= 0:
                            raise RefreshDeadlineExceeded("source deadline")
                        return min(30.0, remaining)

                    provider = EdgarFilingProvider(
                        transport=transport,
                        parser=IsolatedEdgarSubmissionParser(
                            root=request.root,
                            run_id=request.run_id,
                            sec_identity=request.sec_identity or "",
                            timeout=worker_timeout,
                        ),
                    )
                records = provider.get_filings(source, limit=limits.max_entries)
                controller.check_deadline(source, source_started)
                parsed = filing_news_entries(records, source, started_at)
                accepted = len(parsed)
                rejected = 0
            status = "degraded" if accepted and rejected else "failed" if rejected else "healthy-empty" if not accepted else "healthy"
            if status == "failed":
                reason = "all-entries-rejected"
        except FeedParseError as exc:
            reason = exc.reason_code
        except DestinationDenied:
            reason = "destination-denied"
        except RequestTimeout:
            reason = "request-timeout"
        except ResponseLimitExceeded:
            reason = "response-limit"
        except InvalidResponse:
            reason = "invalid-response"
        except RefreshDeadlineExceeded:
            reason = "source-deadline"
        except EdgarWorkerError as exc:
            reason = exc.reason_code if exc.reason_code in EDGAR_WORKER_REASON_CODES else "source-failed"
        except (AuthorizationDenied, BudgetDenied):
            reason = "authorization-denied"
        except DataClientError:
            raise
        except Exception:
            reason = "source-failed"
        outcome = SourceOutcome(
            source_id=source.source_id,
            status=status,
            started_at=started_at,
            finished_at=request.wall_clock(),
            request_count=source_state["requests"],
            redirect_count=response.redirect_count if response else 0,
            compressed_bytes=response.compressed_bytes if response else 0,
            decompressed_bytes=response.decompressed_bytes if response else 0,
            entry_count=accepted + rejected,
            accepted_count=accepted,
            rejected_count=rejected,
            reason_code=reason,
        )
        return outcome, parsed
