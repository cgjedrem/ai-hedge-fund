import gzip
import io
from datetime import datetime, timezone
from threading import Condition, Event, Lock, Thread

import httpx
import pytest

from hedge_fund import paths
from hedge_fund.news.catalog import load_catalog
from hedge_fund.news.filings import EdgarWorkerError, FilingRecord
from hedge_fund.news.models import RefreshLimits
from hedge_fund.news.refresh import NewsRefresher, RefreshRequest
from hedge_fund.news.store import NewsStore
from hedge_fund.news.test_catalog import catalog_bytes, source
from hedge_fund.news.test_transport import StreamingTransport
from hedge_fund.news.transport import FetchRequest, FetchResponse, InvalidResponse
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext

NOW = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)
FEED = b"<rss><channel><item><title>Results</title><link>https://one.example/story</link><pubDate>Wed, 25 Nov 2026 12:00:00 +0000</pubDate></item></channel></rss>"


class FakeTransport:
    def __init__(self, gate):
        self.gate = gate

    def fetch(self, request):
        with self.gate(request.url):
            if request.source_id == "broken":
                raise InvalidResponse("sensitive response detail")
        return FetchResponse(
            final_url=request.url,
            status_code=200,
            media_type="application/rss+xml",
            content=FEED,
            redirect_count=0,
            compressed_bytes=len(FEED),
            decompressed_bytes=len(FEED),
        )


class Clock:
    def __init__(self):
        self.monotonic = 0.0
        self.waits = []

    def time(self):
        return self.monotonic

    def wait(self, seconds):
        self.waits.append(seconds)
        self.monotonic += seconds


def test_refresh_isolates_source_failure_and_atomically_commits_success(tmp_path):
    good = source(source_id="good", url="https://one.example/feed.xml", allowed_hosts=["one.example"], scope="market", tickers=[])
    broken = source(source_id="broken", url="https://two.example/feed.xml", allowed_hosts=["two.example"], scope="market", tickers=[], sequence=200)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(good, broken))
    catalog = load_catalog(catalog_path)
    clock = Clock()
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            request = RefreshRequest(
                run_id="run-1",
                catalog=catalog,
                source_ids=("good", "broken"),
                root=root,
                dispatch=object(),
                limits=RefreshLimits(global_concurrency=1),
                wall_clock=lambda: NOW,
                monotonic_clock=clock.time,
                waiter=clock.wait,
                transport_factory=lambda source, targets, gate: FakeTransport(gate),
            )
            result = NewsRefresher().refresh(request)
            state = NewsStore(root).load()

    assert result.status == "partial"
    assert [outcome.source_id for outcome in result.outcomes] == ["broken", "good"]
    assert result.outcomes[0].reason_code == "invalid-response"
    assert result.outcomes[1].status == "healthy"
    assert "sensitive" not in result.model_dump_json()
    assert len(state.items) == 1
    assert state.health["good"].status == "healthy"
    assert state.health["broken"].status == "failed"
    assert state.revision == 1


def test_refresh_orders_outcomes_and_duplicate_dispositions_by_source_id(tmp_path):
    zeta = source(
        source_id="zeta",
        url="https://zeta.example/feed.xml",
        allowed_hosts=["zeta.example", "one.example"],
        scope="market",
        tickers=[],
        sequence=100,
    )
    alpha = source(
        source_id="alpha",
        url="https://alpha.example/feed.xml",
        allowed_hosts=["alpha.example", "one.example"],
        scope="market",
        tickers=[],
        sequence=200,
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(zeta, alpha))
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-deterministic-order",
                    catalog=load_catalog(catalog_path),
                    source_ids=("zeta", "alpha"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                    transport_factory=lambda source, targets, gate: FakeTransport(gate),
                )
            )

    assert result.status == "succeeded"
    assert [outcome.source_id for outcome in result.outcomes] == ["alpha", "zeta"]
    assert [(outcome.new_count, outcome.merged_count) for outcome in result.outcomes] == [(1, 0), (0, 1)]
    assert result.total_new_items == 1
    assert result.total_merged_items == 1


def test_refresh_counts_actual_conflict_aware_merge_decisions(tmp_path):
    configured = source(source_id="conflicts", url="https://one.example/feed.xml", allowed_hosts=["one.example"], scope="market", tickers=[])
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(configured))
    content = b"<rss><channel><item><title>Results</title><link>https://one.example/first</link><guid>release-1</guid><pubDate>Wed, 25 Nov 2026 12:00:00 +0000</pubDate></item><item><title>Results</title><link>https://one.example/second</link><guid>release-2</guid><pubDate>Wed, 25 Nov 2026 12:00:00 +0000</pubDate></item></channel></rss>"

    class ConflictTransport(FakeTransport):
        def fetch(self, request):
            with self.gate(request.url):
                pass
            return FetchResponse(request.url, 200, "application/rss+xml", content, 0, len(content), len(content))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-conflict-counts",
                    catalog=load_catalog(catalog_path),
                    source_ids=("conflicts",),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                    transport_factory=lambda source, targets, gate: ConflictTransport(gate),
                )
            )
            state = NewsStore(root).load()

    assert len(state.items) == 2
    assert result.outcomes[0].accepted_count == 2
    assert (result.outcomes[0].new_count, result.outcomes[0].merged_count) == (2, 0)
    assert (result.total_new_items, result.total_merged_items) == (2, 0)
    assert state.health["conflicts"].stored_count == 2
    assert state.recent_runs[0] == result


def test_repeated_refresh_deduplicates_and_reopens_committed_state(tmp_path):
    configured = source(source_id="repeatable", url="https://one.example/feed.xml", allowed_hosts=["one.example"], scope="market", tickers=[])
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(configured))
    catalog = load_catalog(catalog_path)
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            for run_id in ("run-1", "run-2"):
                result = NewsRefresher().refresh(
                    RefreshRequest(
                        run_id=run_id,
                        catalog=catalog,
                        source_ids=(configured["source_id"],),
                        root=root,
                        dispatch=object(),
                        limits=RefreshLimits(global_concurrency=1),
                        wall_clock=lambda: NOW,
                        monotonic_clock=lambda: 0.0,
                        waiter=lambda _seconds: None,
                        transport_factory=lambda source, targets, gate: FakeTransport(gate),
                    )
                )
            reopened = NewsStore(root).load()

    assert result.status == "succeeded"
    assert result.total_new_items == 0
    assert result.total_merged_items == 1
    assert len(reopened.items) == 1
    assert reopened.revision == 2
    assert reopened.health["repeatable"].last_run_id == "run-2"


def test_redirects_share_cadence_for_the_actual_destination_host(tmp_path):
    first = source(
        source_id="first",
        url="https://first.example/feed.xml",
        allowed_hosts=["first.example", "shared.example"],
        scope="market",
        tickers=[],
    )
    second = source(
        source_id="second",
        url="https://second.example/feed.xml",
        allowed_hosts=["second.example", "shared.example"],
        scope="market",
        tickers=[],
        sequence=200,
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(first, second))
    clock = Clock()

    class RedirectTransport:
        def __init__(self, gate):
            self.gate = gate

        def fetch(self, request):
            with self.gate("https://shared.example/redirected.xml"):
                pass
            return FetchResponse(request.url, 200, "application/rss+xml", FEED, 1, len(FEED), len(FEED))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-redirect-cadence",
                    catalog=load_catalog(catalog_path),
                    source_ids=("first", "second"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(
                        global_concurrency=2,
                        minimum_host_interval_seconds=5,
                        max_requests_per_source=1,
                    ),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: RedirectTransport(gate),
                )
            )

    assert clock.waits == [5.0]


def test_host_throttle_wait_is_capped_by_the_run_deadline(tmp_path):
    definitions = [
        source(
            source_id=source_id,
            url=f"https://one.example/{source_id}.xml",
            allowed_hosts=["one.example"],
            scope="market",
            tickers=[],
            sequence=sequence,
        )
        for source_id, sequence in (("first", 100), ("second", 200))
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(*definitions))
    clock = Clock()
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-capped-host-wait",
                    catalog=load_catalog(catalog_path),
                    source_ids=("first", "second"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(
                        global_concurrency=1,
                        minimum_host_interval_seconds=3600,
                        run_deadline_seconds=5,
                        max_requests_per_source=1,
                    ),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: FakeTransport(gate),
                )
            )

    assert clock.waits == [5.0]
    assert result.outcomes[1].reason_code == "source-deadline"


def test_queued_source_deadline_starts_when_that_source_starts(tmp_path):
    first = source(
        source_id="first",
        url="https://one.example/first.xml",
        allowed_hosts=["one.example"],
        scope="market",
        tickers=[],
    )
    second = source(
        source_id="second",
        url="https://one.example/second.xml",
        allowed_hosts=["one.example"],
        scope="market",
        tickers=[],
        sequence=200,
        limits={"source_deadline_seconds": 5},
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(first, second))
    clock = Clock()

    class QueuedTransport(FakeTransport):
        def fetch(self, request):
            with self.gate(request.url):
                if request.source_id == "first":
                    clock.wait(10)
            return FetchResponse(request.url, 200, "application/rss+xml", FEED, 0, len(FEED), len(FEED))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-source-deadline",
                    catalog=load_catalog(catalog_path),
                    source_ids=("first", "second"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(
                        global_concurrency=1,
                        source_deadline_seconds=30,
                        max_requests_per_source=1,
                    ),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: QueuedTransport(gate),
                )
            )

    assert clock.waits == [10]
    assert [outcome.status for outcome in result.outcomes] == ["healthy", "healthy"]
    assert result.outcomes[1].request_count == 1


def test_no_source_transport_is_constructed_after_the_run_deadline(tmp_path):
    first = source(
        source_id="first",
        url="https://one.example/first.xml",
        allowed_hosts=["one.example"],
        scope="market",
        tickers=[],
    )
    second = source(
        source_id="second",
        url="https://two.example/second.xml",
        allowed_hosts=["two.example"],
        scope="market",
        tickers=[],
        sequence=200,
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(first, second))
    clock = Clock()
    constructed = []

    class AdvancingTransport(FakeTransport):
        def fetch(self, request):
            with self.gate(request.url):
                clock.wait(10)
            return FetchResponse(request.url, 200, "application/rss+xml", FEED, 0, len(FEED), len(FEED))

    def factory(source, targets, gate):
        constructed.append(source.source_id)
        return AdvancingTransport(gate)

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-no-late-start",
                    catalog=load_catalog(catalog_path),
                    source_ids=("first", "second"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(
                        global_concurrency=1,
                        run_deadline_seconds=5,
                        max_requests_per_source=1,
                    ),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=factory,
                )
            )

    assert constructed == ["first"]
    assert result.outcomes[1].status == "failed"
    assert result.outcomes[1].reason_code == "source-deadline"
    assert result.outcomes[1].request_count == 0


def test_response_arriving_after_run_deadline_persists_only_failed_health(tmp_path):
    definition = source(
        source_id="slow",
        url="https://one.example/feed.xml",
        allowed_hosts=["one.example"],
        scope="market",
        tickers=[],
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))
    clock = Clock()

    class SlowTransport(FakeTransport):
        def fetch(self, request):
            with self.gate(request.url):
                clock.wait(10)
            return FetchResponse(request.url, 200, "application/rss+xml", FEED, 0, len(FEED), len(FEED))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-late-response",
                    catalog=load_catalog(catalog_path),
                    source_ids=("slow",),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(run_deadline_seconds=5, max_requests_per_source=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: SlowTransport(gate),
                )
            )
            state = NewsStore(root).load()

    assert result.status == "failed"
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "source-deadline"
    assert result.outcomes[0].accepted_count == 0
    assert state.revision == 1
    assert state.items == {}
    assert [run.run_id for run in state.recent_runs] == ["run-late-response"]
    assert state.health["slow"].status == "failed"
    assert state.health["slow"].reason_code == "source-deadline"
    assert state.health["slow"].last_attempt_at == NOW
    assert state.health["slow"].last_success_at is None


def test_parse_finishing_after_run_deadline_persists_only_failed_health(tmp_path, monkeypatch):
    from hedge_fund.news import refresh as refresh_module

    definition = source(
        source_id="slow-parse",
        url="https://one.example/feed.xml",
        allowed_hosts=["one.example"],
        scope="market",
        tickers=[],
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))
    clock = Clock()
    real_parse = refresh_module.parse_feed

    def slow_parse(*args, **kwargs):
        document = real_parse(*args, **kwargs)
        clock.wait(10)
        return document

    monkeypatch.setattr(refresh_module, "parse_feed", slow_parse)
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-late-parse",
                    catalog=load_catalog(catalog_path),
                    source_ids=("slow-parse",),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(run_deadline_seconds=5, max_requests_per_source=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: FakeTransport(gate),
                )
            )
            state = NewsStore(root).load()

    assert result.status == "failed"
    assert result.outcomes[0].reason_code == "source-deadline"
    assert result.outcomes[0].accepted_count == 0
    assert result.outcomes[0].rejected_count == 0
    assert state.items == {}
    assert state.health["slow-parse"].status == "failed"
    assert state.health["slow-parse"].reason_code == "source-deadline"
    assert state.health["slow-parse"].last_success_at is None


def test_run_expiry_preserves_earlier_success_and_later_failed_health(tmp_path):
    definitions = [
        source(
            source_id="good",
            url="https://one.example/good.xml",
            allowed_hosts=["one.example"],
            scope="market",
            tickers=[],
        ),
        source(
            source_id="slow",
            url="https://two.example/slow.xml",
            allowed_hosts=["two.example"],
            scope="market",
            tickers=[],
            sequence=200,
        ),
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(*definitions))
    clock = Clock()

    class MixedTransport(FakeTransport):
        def fetch(self, request):
            with self.gate(request.url):
                if request.source_id == "slow":
                    clock.wait(10)
            return FetchResponse(request.url, 200, "application/rss+xml", FEED, 0, len(FEED), len(FEED))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-mixed-deadline",
                    catalog=load_catalog(catalog_path),
                    source_ids=("good", "slow"),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1, run_deadline_seconds=5, max_requests_per_source=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda source, targets, gate: MixedTransport(gate),
                )
            )
            state = NewsStore(root).load()

    assert result.status == "partial"
    assert [outcome.status for outcome in result.outcomes] == ["healthy", "failed"]
    assert result.outcomes[1].reason_code == "source-deadline"
    assert result.total_new_items == 1
    assert len(state.items) == 1
    assert next(iter(state.items.values())).attributions[0].source_id == "good"
    assert state.health["good"].last_success_at == NOW
    assert state.health["slow"].status == "failed"
    assert state.health["slow"].last_success_at is None


def test_fifty_source_refresh_never_exceeds_four_active_workers(tmp_path):
    definitions = [
        source(
            source_id=f"source-{index:02d}",
            url=f"https://source-{index:02d}.example/feed.xml",
            allowed_hosts=[f"source-{index:02d}.example"],
            scope="market",
            tickers=[],
            sequence=index,
        )
        for index in range(50)
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(*definitions))
    catalog = load_catalog(catalog_path)
    clock = Clock()
    condition = Condition()
    release = Event()
    started = []
    active = 0
    maximum_active = 0
    active_lock = Lock()

    class BlockingTransport:
        def __init__(self, gate):
            self.gate = gate

        def fetch(self, request):
            nonlocal active, maximum_active
            with self.gate(request.url):
                with active_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                with condition:
                    started.append(request.source_id)
                    condition.notify_all()
                release.wait(2)
                with active_lock:
                    active -= 1
            content = (f"<rss><channel><item><title>{request.source_id}</title>" f"<link>{request.url}story</link></item></channel></rss>").encode()
            return FetchResponse(request.url, 200, "application/rss+xml", content, 0, len(content), len(content))

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    failures = []
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            request = RefreshRequest(
                run_id="run-50",
                catalog=catalog,
                source_ids=tuple(item.source_id for item in catalog.sources),
                root=root,
                dispatch=object(),
                limits=RefreshLimits(max_requests_per_source=1),
                wall_clock=lambda: NOW,
                monotonic_clock=clock.time,
                waiter=clock.wait,
                transport_factory=lambda source, targets, gate: BlockingTransport(gate),
            )

            def execute():
                try:
                    NewsRefresher().refresh(request)
                except Exception as exc:
                    failures.append(exc)

            worker = Thread(target=execute)
            worker.start()
            with condition:
                condition.wait_for(lambda: len(started) >= 4, timeout=2)
                observed_first_wave = len(started)
            release.set()
            worker.join(30)

    assert not worker.is_alive()
    assert failures == []
    assert observed_first_wave == 4
    assert maximum_active == 4
    assert len(started) == 50


def test_sec_filing_refresh_uses_injected_provider_and_persists_metadata(tmp_path):
    definition = source(
        source_id="apple-sec-edgar",
        kind="sec-edgar",
        publisher="Apple Inc. / SEC EDGAR",
        category="sec-filing",
        url="https://data.sec.gov/submissions/CIK0000320193.json",
        allowed_hosts=["data.sec.gov", "www.sec.gov"],
        scope="company",
        tickers=["AAPL"],
        cik="0000320193",
        forms=["8-K"],
        limits={"max_entries": 2, "source_deadline_seconds": 7},
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))
    filing = FilingRecord(
        accession="0000320193-26-000123",
        form="8-K",
        filing_date=NOW.date(),
        accepted_at=NOW,
        report_date=NOW.date(),
        items=("2.02", "9.01"),
        primary_document_description="Current report",
        file_number="001-36743",
        size=12345,
        index_url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.html",
    )
    observed_limits = []

    class Provider:
        def __init__(self, transport):
            self.transport = transport

        def get_filings(self, selected, *, limit):
            observed_limits.append(limit)
            self.transport.fetch(
                FetchRequest(
                    source_id=selected.source_id,
                    url=selected.url,
                    accepted_media_types=("application/json",),
                    sec_identity_required=True,
                )
            )
            return (filing,)

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-sec-filing",
                    catalog=load_catalog(catalog_path),
                    source_ids=(definition["source_id"],),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1, max_requests_per_source=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                    transport_factory=lambda source, targets, gate: FakeTransport(gate),
                    filing_provider_factory=lambda source, transport: Provider(transport),
                )
            )
            state = NewsStore(root).load()

    assert observed_limits == [2]
    assert result.status == "succeeded"
    assert result.total_requests == 1
    assert result.total_new_items == 1
    assert result.outcomes[0].entry_count == 1
    assert len(state.items) == 1
    item = next(iter(state.items.values()))
    assert item.category == "sec-filing"
    assert item.tickers == ("AAPL",)
    assert item.summary is None
    assert "sec:000032019326000123" in item.dedupe_keys


def test_sec_worker_timeout_uses_the_deadline_remaining_after_download(tmp_path, monkeypatch):
    definition = source(
        source_id="apple-sec-edgar",
        kind="sec-edgar",
        publisher="Apple Inc. / SEC EDGAR",
        category="sec-filing",
        url="https://data.sec.gov/submissions/CIK0000320193.json",
        allowed_hosts=["data.sec.gov", "www.sec.gov"],
        scope="company",
        tickers=["AAPL"],
        cik="0000320193",
        forms=["8-K"],
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))
    clock = Clock()
    wait_timeouts = []

    class Transport:
        def fetch(self, request):
            clock.monotonic = 20.0
            return FetchResponse(
                final_url=request.url,
                status_code=200,
                media_type="application/json",
                content=b'{"filings":{"recent":{}}}',
                redirect_count=0,
            )

    class Process:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b'{"protocol":1,"ok":true,"records":[]}')
            self.stderr = io.BytesIO()
            self.returncode = 0

        def wait(self, timeout=None):
            if timeout is not None:
                wait_timeouts.append(timeout)
            return 0

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = 0

    process = Process()
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        monkeypatch.setattr("hedge_fund.news.filings.subprocess.Popen", lambda *_args, **_kwargs: process)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-sec-remaining-deadline",
                    catalog=load_catalog(catalog_path),
                    source_ids=(definition["source_id"],),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1, source_deadline_seconds=30, max_requests_per_source=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=clock.time,
                    waiter=clock.wait,
                    transport_factory=lambda _source, _targets, _gate: Transport(),
                    sec_identity="Synthetic News Tests contact@tests.invalid",
                )
            )

    assert result.status == "succeeded"
    assert wait_timeouts == [10.0]


@pytest.mark.parametrize(
    ("worker_reason", "expected_reason"),
    [
        ("worker-timeout", "worker-timeout"),
        ("secret-contact@tests.invalid C:\\private\\desk", "source-failed"),
    ],
)
def test_sec_worker_failure_preserves_only_allowlisted_reason_codes(tmp_path, worker_reason, expected_reason):
    definition = source(
        source_id="apple-sec-edgar",
        kind="sec-edgar",
        publisher="Apple Inc. / SEC EDGAR",
        category="sec-filing",
        url="https://data.sec.gov/submissions/CIK0000320193.json",
        allowed_hosts=["data.sec.gov", "www.sec.gov"],
        scope="company",
        tickers=["AAPL"],
        cik="0000320193",
        forms=["8-K"],
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))

    class Provider:
        def get_filings(self, selected, *, limit):
            raise EdgarWorkerError(worker_reason)

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-sec-worker-timeout",
                    catalog=load_catalog(catalog_path),
                    source_ids=(definition["source_id"],),
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                    transport_factory=lambda source, targets, gate: FakeTransport(gate),
                    filing_provider_factory=lambda source, transport: Provider(),
                )
            )
            state = NewsStore(root).load()

    assert result.status == "failed"
    assert result.outcomes[0].reason_code == expected_reason
    assert state.health["apple-sec-edgar"].reason_code == expected_reason
    assert state.items == {}
    if expected_reason == "source-failed":
        assert worker_reason not in str(result)
        assert worker_reason not in str(state.health["apple-sec-edgar"])


def refresh_with_default_transport(tmp_path, definition, handler):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(definition))

    class Dispatch:
        def httpx_transport(self, target, allow_manual_redirects=False):
            return StreamingTransport(handler)

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id="run-source-transport-limits",
                    catalog=load_catalog(catalog_path),
                    source_ids=(definition["source_id"],),
                    root=root,
                    dispatch=Dispatch(),
                    limits=RefreshLimits(global_concurrency=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                )
            )
    return result


def test_refresh_enforces_a_stricter_source_redirect_limit(tmp_path):
    definition = source(
        url="https://ir.example.com/start.xml",
        limits={"max_redirects": 0},
    )
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/start.xml":
            return httpx.Response(302, headers={"Location": "/final.xml"})
        return httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            content=b"<rss><channel /></rss>",
        )

    result = refresh_with_default_transport(tmp_path, definition, handler)

    assert result.status == "failed"
    assert result.outcomes[0].reason_code == "invalid-response"
    assert result.outcomes[0].request_count == 1
    assert requested == ["https://ir.example.com/start.xml"]


@pytest.mark.parametrize(
    ("limits", "headers", "body", "reason"),
    [
        (
            {"max_compressed_bytes": 4},
            {"Content-Type": "application/rss+xml"},
            b"<rss><channel /></rss>",
            "response-limit",
        ),
        (
            {"max_decompressed_bytes": 8},
            {"Content-Type": "application/rss+xml", "Content-Encoding": "gzip"},
            gzip.compress(b"<rss><channel /></rss>"),
            "response-limit",
        ),
    ],
)
def test_refresh_enforces_stricter_source_byte_limits(tmp_path, limits, headers, body, reason):
    definition = source(limits=limits)
    result = refresh_with_default_transport(
        tmp_path,
        definition,
        lambda _request: httpx.Response(200, headers=headers, content=body),
    )

    assert result.status == "failed"
    assert result.outcomes[0].reason_code == reason
    assert result.outcomes[0].request_count == 1
    assert result.outcomes[0].accepted_count == 0


@pytest.mark.parametrize(
    "document",
    [
        b'<rss version="2.0"><channel><title>Empty</title></channel></rss>',
        b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>',
    ],
)
def test_refresh_accepts_a_valid_empty_feed_as_healthy(tmp_path, document):
    result = refresh_with_default_transport(
        tmp_path,
        source(),
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            content=document,
        ),
    )

    assert result.status == "succeeded"
    assert result.outcomes[0].status == "healthy-empty"
    assert result.outcomes[0].entry_count == 0
    assert result.outcomes[0].accepted_count == 0
    assert result.outcomes[0].reason_code is None
    with RootContext.open(tmp_path / "synthetic-desk") as root:
        state = NewsStore(root).load()
    assert state.items == {}
    assert state.health[source()["source_id"]].last_success_at == NOW
