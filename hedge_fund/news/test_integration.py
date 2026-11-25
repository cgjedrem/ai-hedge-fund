import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

from hedge_fund.data.models import CompanyFacts
from hedge_fund.news.catalog import load_catalog
from hedge_fund.news.client import CuratedNewsDataClient
from hedge_fund.news.filings import EdgarFilingProvider, IsolatedEdgarSubmissionParser
from hedge_fund.news.models import NewsQuery, RefreshLimits
from hedge_fund.news.refresh import NewsRefresher, RefreshRequest
from hedge_fund.news.store import NewsStore
from hedge_fund.news.test_catalog import catalog_bytes, source
from hedge_fund.news.test_store import synthetic_store
from hedge_fund.news.transport import FetchResponse

NOW = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).with_name("fixtures")


class FixtureTransport:
    def __init__(self, source_id, gate):
        self.source_id = source_id
        self.gate = gate

    def fetch(self, request):
        with self.gate(request.url):
            pass
        if self.source_id == "synthetic-general":
            document = (FIXTURES / "general.xml").read_bytes()
        elif self.source_id == "synthetic-company-ir":
            document = (FIXTURES / "ir.xml").read_bytes()
        else:
            raise AssertionError(f"unexpected fixture source: {self.source_id}")
        return FetchResponse(
            final_url=request.url,
            status_code=200,
            media_type="application/rss+xml",
            content=document,
            redirect_count=0,
            compressed_bytes=len(document),
            decompressed_bytes=len(document),
        )


class LegacyClient:
    def __init__(self):
        self.news_calls = 0
        self.facts_calls = 0

    def get_news(self, *_args, **_kwargs):
        self.news_calls += 1
        raise AssertionError("legacy news retrieval must not be called")

    def get_company_facts(self, ticker):
        self.facts_calls += 1
        return CompanyFacts(ticker=ticker, name="Synthetic Example Company")


def general_source():
    value = source(
        source_id="synthetic-general",
        publisher="Synthetic Newswire",
        category="editorial",
        url="https://news.example.com/feed.xml",
        allowed_hosts=["news.example.com"],
        tickers=["ACME"],
        company_aliases=["Example Company"],
        summary_policy="feed-supplied",
        sequence=10,
    )
    value["curation"]["rights_note"] = "Synthetic CC0 test fixture; its test-only license permits summary reuse."
    return value


def ir_source():
    return source(
        source_id="synthetic-company-ir",
        url="https://ir.example.com/news.xml",
        allowed_hosts=["ir.example.com", "news.example.com"],
        tickers=["ACME"],
        sequence=5,
    )


def refresh_request(run_id, catalog, root, source_ids):
    return RefreshRequest(
        run_id=run_id,
        catalog=catalog,
        source_ids=source_ids,
        root=root,
        dispatch=object(),
        limits=RefreshLimits(global_concurrency=1),
        wall_clock=lambda: NOW,
        monotonic_clock=lambda: 0.0,
        waiter=lambda _seconds: None,
        transport_factory=lambda selected, _targets, gate: FixtureTransport(selected.source_id, gate),
    )


def test_general_and_ir_refresh_survive_100_repeats_and_reader_restarts(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(general_source(), ir_source()))
    catalog = load_catalog(catalog_path)
    source_ids = ("synthetic-general", "synthetic-company-ir")
    (tmp_path / "synthetic-desk").mkdir()

    with synthetic_store(tmp_path / "synthetic-desk") as (_store, root):
        legacy = LegacyClient()
        for index in range(100):
            result = NewsRefresher().refresh(refresh_request(f"us1-{index:03d}", catalog, root, source_ids))
            assert result.status == "succeeded"
            reader = CuratedNewsDataClient(legacy, NewsStore(root, clock=lambda: NOW))
            assert len(reader.get_news("ACME", "2026-01-07", "2026-01-06")) == 2

        restarted_store = NewsStore(root, clock=lambda: NOW)
        restarted = CuratedNewsDataClient(legacy, restarted_store)
        items = restarted.get_news("ACME", "2026-01-07", "2026-01-06", 10)
        facts = restarted.get_company_facts("ACME")
        state = restarted_store.load()

    assert state.revision == 100
    assert len(state.items) == 2
    assert len(state.recent_runs) == 100
    assert [item.title for item in items] == [
        "Example Company expands chip production",
        "Example Company expands chip production",
    ]
    assert items[0].date == "2026-01-07T14:30:00+00:00"
    assert len(items[0].attributions) == 1
    assert items[1].url == "https://news.example.com/story?id=42"
    assert items[1].category == "investor-relations"
    assert {value.source_id for value in items[1].attributions} == set(source_ids)
    assert items[1].fetched_at == NOW.isoformat()
    merged = next(item for item in state.items.values() if item.canonical_url == "https://news.example.com/story?id=42")
    assert merged.summary == "Synthetic summary with markup."
    assert "<script" not in merged.summary
    assert facts.name == "Synthetic Example Company"
    assert legacy.news_calls == 0
    assert legacy.facts_calls == 1


def authority_source(source_id, publisher, category, host, guid):
    value = source(
        source_id=source_id,
        publisher=publisher,
        category=category,
        url=f"https://{host}/synthetic.xml",
        allowed_hosts=[host],
        scope="market",
        tickers=[],
        company_aliases=[],
        sequence=100,
    )
    value["curation"]["discovery_url"] = f"https://{host}/"
    return value, guid


class AuthorityTransport:
    def __init__(self, source_id, gate, requests):
        self.source_id = source_id
        self.gate = gate
        self.requests = requests

    def fetch(self, request):
        with self.gate(request.url):
            pass
        self.requests.append(request)
        if self.source_id == "synthetic-sec-filings":
            document = (FIXTURES / "submissions.json").read_bytes()
            media_type = "application/json"
        else:
            selected_guid = {
                "synthetic-fed": "fed-synthetic-20260108",
                "synthetic-sec-releases": "sec-synthetic-20260108",
                "synthetic-bls": "bls-synthetic-20260109",
                "synthetic-bea": "bea-synthetic-20260109",
            }[self.source_id]
            feed = ET.fromstring((FIXTURES / "macro.xml").read_bytes())
            channel = feed.find("channel")
            for item in list(channel.findall("item")):
                if item.findtext("guid") != selected_guid:
                    channel.remove(item)
            document = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
            media_type = "application/rss+xml"
        return FetchResponse(
            final_url=request.url,
            status_code=200,
            media_type=media_type,
            content=document,
            redirect_count=0,
            compressed_bytes=len(document),
            decompressed_bytes=len(document),
        )


def test_sec_filings_and_macro_releases_survive_restart_and_repeat_refresh(tmp_path):
    filing = source(
        source_id="synthetic-sec-filings",
        kind="sec-edgar",
        publisher="Synthetic Example Company / SEC EDGAR",
        category="sec-filing",
        url="https://data.sec.gov/submissions/CIK1234567890.json",
        allowed_hosts=["data.sec.gov", "www.sec.gov"],
        tickers=["ACME"],
        cik="1234567890",
        forms=["8-K", "10-Q"],
        limits={"max_entries": 10},
        sequence=1,
    )
    definitions = [
        filing,
        authority_source("synthetic-fed", "Federal Reserve", "macro", "www.federalreserve.gov", "fed-synthetic-20260108")[0],
        authority_source("synthetic-sec-releases", "U.S. Securities and Exchange Commission", "regulatory", "www.sec.gov", "sec-synthetic-20260108")[0],
        authority_source("synthetic-bls", "U.S. Bureau of Labor Statistics", "macro", "www.bls.gov", "bls-synthetic-20260109")[0],
        authority_source("synthetic-bea", "U.S. Bureau of Economic Analysis", "macro", "www.bea.gov", "bea-synthetic-20260109")[0],
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_bytes(*definitions))
    catalog = load_catalog(catalog_path)
    source_ids = tuple(value["source_id"] for value in definitions)
    requests = []
    parser_calls = []

    class RecordingParser:
        def __init__(self, delegate):
            self.delegate = delegate

        def parse(self, selected, document, *, limit):
            parser_calls.append((selected, document, limit))
            return self.delegate.parse(selected, document, limit=limit)

    def transport_factory(selected, _targets, gate):
        return AuthorityTransport(selected.source_id, gate, requests)

    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with synthetic_store(root_path) as (_store, root):
        for run_id in ("us2-first", "us2-repeat"):

            def filing_provider_factory(selected, transport):
                return EdgarFilingProvider(
                    transport=transport,
                    parser=RecordingParser(
                        IsolatedEdgarSubmissionParser(
                            root=root,
                            run_id=run_id,
                            sec_identity="Synthetic News Tests contact@tests.invalid",
                            timeout=300,
                        )
                    ),
                )

            result = NewsRefresher().refresh(
                RefreshRequest(
                    run_id=run_id,
                    catalog=catalog,
                    source_ids=source_ids,
                    root=root,
                    dispatch=object(),
                    limits=RefreshLimits(global_concurrency=1),
                    wall_clock=lambda: NOW,
                    monotonic_clock=lambda: 0.0,
                    waiter=lambda _seconds: None,
                    transport_factory=transport_factory,
                    filing_provider_factory=filing_provider_factory,
                )
            )
            assert result.status == "succeeded", [(o.source_id, o.status, o.reason_code) for o in result.outcomes]

        restarted_store = NewsStore(root, clock=lambda: NOW)
        legacy = LegacyClient()
        reader = CuratedNewsDataClient(legacy, restarted_store)
        items = reader.get_news("ACME", "2026-01-10", "2026-01-07", 20)
        state = restarted_store.load()
        filings_only = restarted_store.query(NewsQuery(ticker="ACME", include_market=False, categories=("sec-filing",), limit=20)).items

    assert len(items) == 6
    assert len(state.items) == 6
    assert state.revision == 2
    assert result.total_new_items == 0
    assert result.total_merged_items == 6
    assert [item.title for item in items] == [
        "Synthetic Example Company / SEC EDGAR — 8-K (2026-01-09) — Items 2.02, 9.01",
        "BLS publishes synthetic employment situation",
        "BEA publishes synthetic GDP estimate",
        "Federal Reserve issues synthetic policy statement",
        "SEC issues synthetic regulatory release",
        "Synthetic Example Company / SEC EDGAR — 10-Q (2026-01-07)",
    ]
    eight_k, bls, bea, fed, sec, ten_q = items
    assert eight_k.category == "sec-filing"
    assert eight_k.date == "2026-01-09T15:45:10+00:00"
    assert eight_k.attributions[0].original_id == "1234567890-26-000001"
    assert eight_k.url == "https://www.sec.gov/Archives/edgar/data/1234567890/123456789026000001/1234567890-26-000001-index.html"
    assert ten_q.date == "2026-01-07"
    assert ten_q.attributions[0].original_id == "1234567890-26-000002"
    assert [value.category for value in (bls, bea, fed)] == ["macro", "macro", "macro"]
    assert sec.category == "regulatory"
    assert all(value.fetched_at == NOW.isoformat() for value in items)
    assert len(filings_only) == 2
    ambiguous = next(value for value in filings_only if value.attributions[0].original_id == "1234567890-26-000002")
    assert ambiguous.published_at is None
    assert ambiguous.published_on == date(2026, 1, 7)
    assert ambiguous.publication_precision == "day"
    assert len(parser_calls) == 2
    assert all(call[0].source_id == "synthetic-sec-filings" for call in parser_calls)
    assert all(call[1] == (FIXTURES / "submissions.json").read_bytes() for call in parser_calls)
    assert all(call[2] == 10 for call in parser_calls)
    sec_requests = [request for request in requests if request.source_id == "synthetic-sec-filings"]
    assert len(sec_requests) == 2
    assert all(request.url == "https://data.sec.gov/submissions/CIK1234567890.json" for request in sec_requests)
    assert all(request.sec_identity_required for request in sec_requests)
    assert not any("filings.files" in request.url or "submissions-001" in request.url for request in requests)
    assert legacy.news_calls == 0
