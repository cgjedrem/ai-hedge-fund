import hashlib
import io
import json
import subprocess
import sysconfig
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hedge_fund import paths
from hedge_fund.news.filings import (
    EdgarFilingProvider,
    EdgarWorkerError,
    filing_news_entries,
    FilingRecord,
    IsolatedEdgarSubmissionParser,
)
from hedge_fund.news.models import SourceDefinition
from hedge_fund.news.test_catalog import source
from hedge_fund.news.transport import FetchResponse
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


def sec_source(**overrides):
    values = dict(
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
    values.update(overrides)
    return SourceDefinition.model_validate(source(**values))


def submissions_document(*, acceptance="2026-11-25T16:30:15-05:00"):
    recent = {
        "accessionNumber": ["0000320193-26-000123", "0000320193-26-000124", "0000320193-26-000125"],
        "filingDate": ["2026-11-25", "2026-11-25", "2026-11-24"],
        "reportDate": ["2026-11-24", "2026-09-30", "2026-11-24"],
        "acceptanceDateTime": [acceptance, "2026-11-25T12:00:00-05:00", "2026-11-24T10:00:00"],
        "act": ["34", "34", "34"],
        "form": ["8-K", "10-Q", "8-K"],
        "fileNumber": ["001-36743", "001-36743", "001-36743"],
        "items": ["2.02,9.01", "", "7.01"],
        "size": [12345, 23456, 34567],
        "isXBRL": [0, 1, 0],
        "isInlineXBRL": [0, 1, 0],
        "primaryDocument": ["a8k.htm", "a10q.htm", "another-a8k.htm"],
        "primaryDocDescription": ["Current report", "Quarterly report", "Legacy item labels"],
    }
    return json.dumps({"cik": 320193, "name": "Apple Inc.", "filings": {"recent": recent, "files": [{"name": "must-not-be-fetched.json"}]}}).encode()


def test_isolated_worker_parses_only_configured_filing_metadata(tmp_path):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        records = IsolatedEdgarSubmissionParser(
            root=root,
            run_id="offline-parser-test",
            sec_identity="Synthetic News Tests contact@tests.invalid",
            timeout=300,
        ).parse(sec_source(), submissions_document(), limit=10)

    assert len(records) == 2
    precise, ambiguous = records
    assert precise.accession == "0000320193-26-000123"
    assert precise.form == "8-K"
    assert precise.filing_date.isoformat() == "2026-11-25"
    assert precise.accepted_at == datetime(2026, 11, 25, 21, 30, 15, tzinfo=timezone.utc)
    assert precise.report_date.isoformat() == "2026-11-24"
    assert precise.items == ("2.02", "9.01")
    assert precise.primary_document_description == "Current report"
    assert precise.file_number == "001-36743"
    assert precise.size == 12345
    assert precise.index_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.html"
    assert ambiguous.accession == "0000320193-26-000125"
    assert ambiguous.accepted_at is None
    assert ambiguous.items == ("7.01",)
    assert ambiguous.index_url.endswith("/0000320193-26-000125-index.html")
    assert all(record.form == "8-K" for record in records)


def test_isolated_worker_rejects_entry_overflow_before_edgar_import(tmp_path):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        parser = IsolatedEdgarSubmissionParser(
            root=root,
            run_id="offline-parser-limits",
            sec_identity="Synthetic News Tests contact@tests.invalid",
            timeout=5,
        )
        with pytest.raises(EdgarWorkerError, match="entry-limit"):
            parser.parse(sec_source(forms=["8-K", "10-Q"]), submissions_document(), limit=1)


class StubProcess:
    def __init__(self, *, stdout=b"", stderr=b"", timeout=False):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.timeout = timeout
        self.returncode = None
        self.killed = False

    def wait(self, timeout=None):
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("edgar-worker", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def poll(self):
        return self.returncode


def isolated_parser(root, **overrides):
    values = dict(
        root=root,
        run_id="offline-parser-boundary",
        sec_identity="Synthetic News Tests secret-contact@tests.invalid",
        timeout=5,
    )
    values.update(overrides)
    return IsolatedEdgarSubmissionParser(**values)


def assert_parser_scratch_empty(root):
    scratch_root = root.path / "cache" / "news" / "edgar-runs"
    assert not scratch_root.exists() or list(scratch_root.iterdir()) == []


def test_existing_worker_scratch_conflict_is_not_masked_by_write_admission(tmp_path):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    selected = sec_source()
    scratch_name = hashlib.sha256(f"offline-parser-conflict\0{selected.source_id}\0{1}".encode()).hexdigest()[:32]
    scratch_relative = f"cache/news/edgar-runs/{scratch_name}"
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        root.mkdir(scratch_relative, parents=True)
        parser = IsolatedEdgarSubmissionParser(
            root=root,
            run_id="offline-parser-conflict",
            sec_identity="Synthetic News Tests contact@tests.invalid",
            timeout=5,
        )

        with pytest.raises(EdgarWorkerError) as failure:
            parser.parse(selected, submissions_document(), limit=10)

        assert failure.value.reason_code == "worker-scratch-conflict"
        assert root.path.joinpath(*scratch_relative.split("/")).is_dir()


def test_worker_process_runs_outside_root_writer_admission(tmp_path, monkeypatch):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    real_admission = paths._root_write_admission
    active = 0
    observed = []

    @contextmanager
    def recording_admission(root, relative_path):
        nonlocal active
        with real_admission(root, relative_path):
            active += 1
            try:
                yield
            finally:
                active -= 1

    class RecordingParser(IsolatedEdgarSubmissionParser):
        def _invoke(self, scratch, payload):
            observed.append(active)
            return b'{"protocol":1,"ok":true,"records":[]}'

    monkeypatch.setattr(paths, "_root_write_admission", recording_admission)
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        parser = RecordingParser(
            root=root,
            run_id="offline-parser-lock-scope",
            sec_identity="Synthetic News Tests contact@tests.invalid",
            timeout=5,
        )

        assert parser.parse(sec_source(), submissions_document(), limit=10) == ()
        assert observed == [0]
        assert_parser_scratch_empty(root)


def test_malformed_worker_output_is_sanitized_and_parser_scratch_is_removed(tmp_path):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    class MalformedParser(IsolatedEdgarSubmissionParser):
        def _invoke(self, scratch, payload):
            return b'{"protocol":1,"ok":true,"records":"secret-contact@tests.invalid"}'

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        parser = MalformedParser(
            root=root,
            run_id="offline-parser-boundary",
            sec_identity="Synthetic News Tests secret-contact@tests.invalid",
            timeout=5,
        )

        with pytest.raises(EdgarWorkerError) as failure:
            parser.parse(sec_source(), submissions_document(), limit=10)

        assert failure.value.reason_code == "malformed-worker-result"
        assert str(failure.value) == "malformed-worker-result"
        assert "secret-contact" not in str(failure.value)
        assert str(root_path) not in str(failure.value)
        assert_parser_scratch_empty(root)


def test_worker_cleanup_failure_is_fail_visible(tmp_path, monkeypatch):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()

    class CleanupParser(IsolatedEdgarSubmissionParser):
        def _invoke(self, scratch, payload):
            return b'{"protocol":1,"ok":true,"records":[]}'

    def fail_cleanup(*_args, **_kwargs):
        raise OSError("simulated cleanup failure")

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        monkeypatch.setattr("shutil.rmtree", fail_cleanup)
        parser = isolated_parser(root)

        with pytest.raises(EdgarWorkerError) as failure:
            parser.parse(sec_source(), submissions_document(), limit=10)

        assert failure.value.reason_code == "worker-cleanup-failed"
        assert str(failure.value) == "worker-cleanup-failed"


def test_worker_timeout_kills_the_process_and_removes_parser_scratch(tmp_path, monkeypatch):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    process = StubProcess(timeout=True)
    commands = []

    def record_popen(command, **kwargs):
        commands.append(command)
        return process

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        monkeypatch.setattr("hedge_fund.news.filings.subprocess.Popen", record_popen)
        parser = isolated_parser(root)

        with pytest.raises(EdgarWorkerError) as failure:
            parser.parse(sec_source(), submissions_document(), limit=10)

        assert failure.value.reason_code == "worker-timeout"
        assert process.killed
        assert process.returncode == -9
        assert "-S" in commands[0]
        assert commands[0].count(str(Path(sysconfig.get_paths()["purelib"]))) == 1
        assert_parser_scratch_empty(root)


def test_worker_output_limit_is_sanitized_and_removes_parser_scratch(tmp_path, monkeypatch):
    root_path = tmp_path / "synthetic-desk"
    root_path.mkdir()
    process = StubProcess(stdout=b"x" * (5 * 1024 * 1024 + 1))
    monkeypatch.setattr("hedge_fund.news.filings.subprocess.Popen", lambda *args, **kwargs: process)

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        parser = isolated_parser(root)

        with pytest.raises(EdgarWorkerError) as failure:
            parser.parse(sec_source(), submissions_document(), limit=10)

        assert failure.value.reason_code == "worker-output-limit"
        assert_parser_scratch_empty(root)


def test_filing_provider_uses_only_guarded_canonical_submissions_retrieval():
    class Transport:
        def __init__(self):
            self.requests = []

        def fetch(self, request):
            self.requests.append(request)
            return FetchResponse(
                final_url=request.url,
                status_code=200,
                media_type="application/json",
                content=submissions_document(),
                redirect_count=0,
                compressed_bytes=100,
                decompressed_bytes=100,
            )

    class Parser:
        def __init__(self):
            self.calls = []

        def parse(self, selected, document, *, limit):
            self.calls.append((selected, document, limit))
            return ()

    transport = Transport()
    parser = Parser()
    result = EdgarFilingProvider(transport=transport, parser=parser).get_filings(sec_source(forms=["8-K"]), limit=5)

    assert result == ()
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.url == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert request.accepted_media_types == ("application/json",)
    assert request.sec_identity_required is True
    assert parser.calls[0][2] == 5


def test_filing_projection_retains_accession_metadata_without_article_content():
    filing = FilingRecord(
        accession="0000320193-26-000123",
        form="8-K",
        filing_date=datetime(2026, 11, 25).date(),
        accepted_at=datetime(2026, 11, 25, 21, 30, 15, tzinfo=timezone.utc),
        report_date=datetime(2026, 11, 24).date(),
        items=("2.02", "9.01"),
        primary_document_description="Current report",
        file_number="001-36743",
        size=12345,
        index_url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.html",
    )
    fetched_at = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)

    entries = filing_news_entries((filing,), sec_source(), fetched_at)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.summary is None
    assert entry.attribution.original_id == filing.accession
    assert entry.attribution.original_url == filing.index_url
    assert entry.attribution.published_at == filing.accepted_at
    assert entry.attribution.published_on == filing.filing_date
    assert entry.attribution.publication_precision == "second"
    assert "sec:000032019326000123" in entry.dedupe_keys
    assert entry.attribution.original_title.startswith("Apple Inc. / SEC EDGAR — 8-K (2026-11-25)")
    assert "Items 2.02, 9.01" in entry.attribution.original_title
