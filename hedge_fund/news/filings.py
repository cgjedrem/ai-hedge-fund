"""SEC filing metadata and its fail-closed, offline EDGAR Tools worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from threading import Thread

from pydantic import Field, ValidationError

from hedge_fund import paths
from hedge_fund.news.models import Attribution, NewsModel, SourceDefinition
from hedge_fund.news.normalize import clean_text, identity_keys, normalize_url
from hedge_fund.news.parsing import ParsedNewsEntry
from hedge_fund.news.transport import FetchRequest
from hedge_fund.runtime.root import RootContext


class FilingRecord(NewsModel):
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str = Field(min_length=1, max_length=32)
    filing_date: date
    accepted_at: datetime | None = None
    report_date: date | None = None
    items: tuple[str, ...] = Field(default=(), max_length=64)
    primary_document_description: str | None = Field(default=None, max_length=1000)
    file_number: str | None = Field(default=None, max_length=100)
    size: int = Field(ge=0, le=10_000_000_000)
    index_url: str = Field(pattern=r"^https://www\.sec\.gov/Archives/edgar/data/\d+/\d{18}/\d{10}-\d{2}-\d{6}-index\.html$")


EDGAR_WORKER_REASON_CODES = frozenset(
    {
        "record-limit-exceeded",
        "duplicate-filing-identity",
        "invalid-filing-source",
        "invalid-filing-input",
        "malformed-submissions",
        "worker-scratch-conflict",
        "malformed-worker-result",
        "entry-limit",
        "api-mismatch",
        "audit-denied",
        "worker-failed",
        "worker-timeout",
        "worker-output-limit",
        "worker-cleanup-failed",
    }
)


class EdgarWorkerError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class EdgarFilingProvider:
    def __init__(self, *, transport, parser) -> None:
        self.transport = transport
        self.parser = parser

    def get_filings(self, source: SourceDefinition, *, limit: int) -> tuple[FilingRecord, ...]:
        if source.kind != "sec-edgar" or not source.cik or not source.forms:
            raise ValueError("SEC filing source is invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("SEC filing entry limit is invalid")
        canonical_url = f"https://data.sec.gov/submissions/CIK{source.cik}.json"
        if source.url != canonical_url or set(source.allowed_hosts) != {"data.sec.gov", "www.sec.gov"}:
            raise ValueError("SEC filing source must use its reviewed canonical endpoints")
        response = self.transport.fetch(
            FetchRequest(
                source_id=source.source_id,
                url=canonical_url,
                accepted_media_types=("application/json",),
                sec_identity_required=True,
            )
        )
        records = tuple(self.parser.parse(source, response.content, limit=limit))
        if len(records) > limit:
            raise EdgarWorkerError("record-limit-exceeded")
        if len({(record.accession, record.form) for record in records}) != len(records):
            raise EdgarWorkerError("duplicate-filing-identity")
        return records


def filing_news_entries(
    records: tuple[FilingRecord, ...],
    source: SourceDefinition,
    fetched_at: datetime,
) -> tuple[ParsedNewsEntry, ...]:
    if source.kind != "sec-edgar" or source.category != "sec-filing":
        raise ValueError("filing projection requires an SEC filing source")
    entries = []
    for filing in records:
        normalized = normalize_url(filing.index_url)
        if normalized.startswith("https://www.sec.gov/") is False:
            raise ValueError("filing index URL is not official")
        title = clean_text(f"{source.publisher} — {filing.form} ({filing.filing_date.isoformat()})" + (f" — Items {', '.join(filing.items)}" if filing.items else ""))
        attribution = Attribution(
            source_id=source.source_id,
            publisher=source.publisher,
            category=source.category,
            original_id=filing.accession,
            original_url=filing.index_url,
            normalized_url=normalized,
            original_title=title,
            published_at=filing.accepted_at,
            published_on=filing.filing_date,
            publication_precision=("second" if filing.accepted_at is not None and (filing.accepted_at.second or filing.accepted_at.microsecond) else "minute" if filing.accepted_at is not None else "day"),
            first_seen_at=fetched_at,
            last_seen_at=fetched_at,
            tickers=source.tickers,
            market_scope=source.scope == "market",
            sequence=source.sequence,
        )
        associations = (*source.tickers, *(("market",) if source.scope == "market" else ()))
        entries.append(
            ParsedNewsEntry(
                attribution=attribution,
                summary=None,
                dedupe_keys=identity_keys(
                    normalized_url=normalized,
                    title=title,
                    original_id=filing.accession,
                    published_at=filing.accepted_at,
                    published_on=filing.filing_date,
                    associations=associations,
                ),
            )
        )
    return tuple(entries)


class IsolatedEdgarSubmissionParser:
    def __init__(self, *, root: RootContext, run_id: str, sec_identity: str, timeout: float | Callable[[], float] = 30) -> None:
        if not isinstance(root, RootContext) or not isinstance(run_id, str) or not run_id:
            raise ValueError("an open root and run identity are required")
        try:
            valid_timeout = callable(timeout) or 0 < timeout <= 300
        except TypeError:
            valid_timeout = False
        if not isinstance(sec_identity, str) or not sec_identity or not valid_timeout:
            raise ValueError("SEC worker configuration is invalid")
        self.root = root
        self.run_id = run_id
        self.sec_identity = sec_identity
        self.timeout = timeout
        self._resolved_timeout = timeout if not callable(timeout) else None
        self._invocation = 0

    def parse(self, source: SourceDefinition, document: bytes, *, limit: int) -> tuple[FilingRecord, ...]:
        if source.kind != "sec-edgar" or not source.cik or not source.forms:
            raise EdgarWorkerError("invalid-filing-source")
        if not isinstance(document, bytes) or len(document) > 5 * 1024 * 1024 or not 1 <= limit <= 500:
            raise EdgarWorkerError("invalid-filing-input")
        resolved_timeout = self.timeout() if callable(self.timeout) else self.timeout
        try:
            valid_timeout = 0 < resolved_timeout <= 300
        except TypeError:
            valid_timeout = False
        if not valid_timeout:
            raise EdgarWorkerError("worker-timeout")
        self._resolved_timeout = resolved_timeout
        try:
            document_text = document.decode("utf-8")
        except UnicodeError:
            raise EdgarWorkerError("malformed-submissions") from None
        self._invocation += 1
        import hashlib

        scratch_name = hashlib.sha256(f"{self.run_id}\0{source.source_id}\0{self._invocation}".encode()).hexdigest()[:32]
        scratch_relative = f"cache/news/edgar-runs/{scratch_name}"
        failure = None
        with paths._root_write_admission(self.root, scratch_relative):
            try:
                self.root.file_info(scratch_relative)
            except FileNotFoundError:
                pass
            except OSError:
                failure = EdgarWorkerError("worker-scratch-conflict")
            else:
                failure = EdgarWorkerError("worker-scratch-conflict")
            if failure is None:
                scratch = Path(self.root.mkdir(scratch_relative, parents=True))
        if failure is not None:
            raise failure
        try:
            payload = json.dumps(
                {
                    "protocol": 1,
                    "source": {"cik": source.cik, "forms": list(source.forms), "publisher": source.publisher},
                    "document": document_text,
                    "limit": limit,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            result = self._invoke(scratch, payload)
        except EdgarWorkerError as exc:
            failure = exc
        except (OSError, ValueError, RuntimeError):
            failure = EdgarWorkerError("worker-failed")
        finally:
            import shutil

            try:
                with paths._root_write_admission(self.root, scratch_relative):
                    try:
                        shutil.rmtree(scratch)
                    except FileNotFoundError:
                        pass
            except (OSError, paths.RootConfigurationError):
                failure = EdgarWorkerError("worker-cleanup-failed")
        if failure is not None:
            raise failure
        try:
            envelope = json.loads(result)
            if not isinstance(envelope, dict) or envelope.get("protocol") != 1:
                raise EdgarWorkerError("malformed-worker-result")
            if envelope.get("ok") is False:
                reason = envelope.get("reason")
                allowed = {"entry-limit", "malformed-submissions", "api-mismatch", "audit-denied", "worker-failed"}
                raise EdgarWorkerError(reason if reason in allowed else "worker-failed")
            if envelope.get("ok") is not True or not isinstance(envelope.get("records"), list):
                raise EdgarWorkerError("malformed-worker-result")
            return tuple(FilingRecord.model_validate(record) for record in envelope["records"])
        except EdgarWorkerError:
            raise
        except (UnicodeError, ValueError, TypeError, ValidationError):
            raise EdgarWorkerError("malformed-worker-result") from None

    def _invoke(self, scratch: Path, payload: bytes) -> bytes:
        worker_scratch = os.path.abspath(os.fspath(scratch))
        if os.name == "nt":
            # Native dependencies can stall while Windows resolves deep TMP/HOME
            # paths. Prefer the equivalent 8.3 name when the volume provides one;
            # the extended-length form remains the fallback, not a native-path fix.
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            result = ctypes.windll.kernel32.GetShortPathNameW(worker_scratch, buffer, len(buffer))
            if result and result < len(buffer):
                worker_scratch = buffer.value
            elif not worker_scratch.startswith("\\\\?\\"):
                worker_scratch = "\\\\?\\" + worker_scratch
        environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR"}}
        environment.update(
            {
                "HOME": worker_scratch,
                "USERPROFILE": worker_scratch,
                "TMP": worker_scratch,
                "TEMP": worker_scratch,
                "EDGAR_LOCAL_DATA_DIR": worker_scratch + os.sep + "local-data",
                "EDGAR_CACHE_DIR": worker_scratch + os.sep + "cache",
                "EDGAR_IDENTITY": self.sec_identity,
                "EDGAR_USE_LOCAL_DATA": "False",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
                "TZ": "UTC",
            }
        )
        executable = sys.executable
        site_directories: list[str] = []
        isolated_flags = ["-I", "-B", "-S"]
        if os.name == "nt":
            base_executable = getattr(sys, "_base_executable", None)
            if not isinstance(base_executable, str) or not os.path.isfile(base_executable):
                raise ValueError("direct EDGAR worker interpreter is unavailable")
            if os.path.normcase(os.path.abspath(base_executable)) != os.path.normcase(os.path.abspath(sys.executable)):
                # Avoid the virtualenv launcher: killing it does not reliably kill its
                # base-interpreter child. The worker adds these paths after its audit hook.
                executable = base_executable
        configured_paths = sysconfig.get_paths()
        for key in ("purelib", "platlib"):
            directory = configured_paths.get(key)
            if not isinstance(directory, str) or not os.path.isabs(directory) or not os.path.isdir(directory):
                raise ValueError("EDGAR worker package paths are invalid")
            if os.path.normcase(directory) not in {os.path.normcase(value) for value in site_directories}:
                site_directories.append(directory)
        command = [
            executable,
            *isolated_flags,
            str(Path(__file__).with_name("edgar_worker.py")),
            worker_scratch,
            *site_directories,
        ]
        options = {
            "env": environment,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(command, **options)
        output = bytearray()
        errors = bytearray()
        exceeded = {"stdout": False, "stderr": False}

        def send_input() -> None:
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        def receive(stream, target: bytearray, name: str, cap: int) -> None:
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    if len(target) + len(chunk) > cap:
                        exceeded[name] = True
                        target.extend(chunk[: max(0, cap - len(target))])
                    else:
                        target.extend(chunk)
            except OSError:
                pass
            finally:
                stream.close()

        writers = [Thread(target=send_input, daemon=True)]
        readers = [
            Thread(target=receive, args=(process.stdout, output, "stdout", 5 * 1024 * 1024), daemon=True),
            Thread(target=receive, args=(process.stderr, errors, "stderr", 65536), daemon=True),
        ]
        for thread in (*writers, *readers):
            thread.start()
        try:
            returncode = process.wait(timeout=self._resolved_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise EdgarWorkerError("worker-timeout") from None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for thread in (*writers, *readers):
                thread.join(timeout=1)
        if exceeded["stdout"]:
            raise EdgarWorkerError("worker-output-limit")
        if returncode != 0:
            raise EdgarWorkerError("worker-failed")
        return bytes(output)
