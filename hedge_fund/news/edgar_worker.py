"""Isolated offline EDGAR Tools parser. Execute only through filings.py."""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class WorkerFailure(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuditDenied(WorkerFailure):
    def __init__(self) -> None:
        super().__init__("audit-denied")


def _inside(scratch: str, value: object) -> bool:
    try:
        candidate = os.path.realpath(os.fspath(value))
        return os.path.commonpath((scratch, candidate)) == scratch
    except (TypeError, ValueError, OSError):
        return False


def _install_audit_hook(scratch_directory: str, *, allow_native_imports: bool = False):
    scratch = os.path.realpath(scratch_directory)
    if os.name == "nt":
        scratch = scratch.casefold()
    native_imports_allowed = allow_native_imports

    def finish_native_imports() -> None:
        nonlocal native_imports_allowed
        native_imports_allowed = False

    def contained(value: object) -> bool:
        try:
            candidate = os.path.realpath(os.fspath(value))
            if os.name == "nt":
                candidate = candidate.casefold()
            return os.path.commonpath((scratch, candidate)) == scratch
        except (TypeError, ValueError, OSError):
            return False

    def writing_open(args: tuple[Any, ...]) -> bool:
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
            return True
        return isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event in {"ctypes.dlopen", "ctypes.dlsym"}:
            if native_imports_allowed:
                return
            raise AuditDenied()
        if (event.startswith("socket.") and event != "socket.gethostname") or event in {
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.execv",
            "os.execve",
            "os.spawn",
            "os.spawnv",
            "os.spawnve",
            "os.posix_spawn",
            "os.startfile",
            "os.chown",
            "os.fork",
            "os.forkpty",
            "os.symlink",
        }:
            raise AuditDenied()
        if event == "os.link" and (len(args) < 2 or not contained(args[0]) or not contained(args[1])):
            raise AuditDenied()
        if event == "open" and args and writing_open(args) and not contained(args[0]) and args[0] != os.devnull:
            raise AuditDenied()
        if event in {"os.mkdir", "os.remove", "os.unlink", "os.rmdir", "os.truncate", "os.chmod", "os.utime"} and args and not contained(args[0]):
            raise AuditDenied()
        if event in {"os.rename", "os.replace"} and (not args or not contained(args[0]) or len(args) < 2 or not contained(args[1])):
            raise AuditDenied()

    sys.addaudithook(audit)
    return finish_native_imports


def _date(value: object, *, required: bool = False) -> str | None:
    if value in (None, "", "NaT"):
        if required:
            raise WorkerFailure("malformed-submissions")
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        raise WorkerFailure("malformed-submissions") from None


def _accepted_at(value: object) -> str | None:
    if value in (None, "", "NaT"):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _labels(value: object) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    labels = []
    for item in values:
        cleaned = " ".join(str(item).replace("Item", "").split()).strip(" ,")[:32]
        if cleaned:
            labels.append(cleaned)
    return labels[:64]


def _parse(request: dict[str, Any], finish_native_imports) -> list[dict[str, Any]]:
    if request.get("protocol") != 1 or not isinstance(request.get("source"), dict) or not isinstance(request.get("document"), str):
        raise WorkerFailure("malformed-submissions")
    limit = request.get("limit")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise WorkerFailure("malformed-submissions")
    selected = request["source"]
    cik = selected.get("cik")
    forms = selected.get("forms")
    if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit() or not isinstance(forms, list) or not forms or not all(isinstance(form, str) and form for form in forms):
        raise WorkerFailure("malformed-submissions")
    try:
        document = json.loads(request["document"])
        recent = document["filings"]["recent"]
        if not isinstance(recent, dict):
            raise TypeError
    except (ValueError, TypeError, KeyError):
        raise WorkerFailure("malformed-submissions") from None

    raw_forms = recent.get("form") or []
    if not isinstance(raw_forms, list):
        raise WorkerFailure("malformed-submissions")
    matching = sum(form in set(forms) for form in raw_forms)
    if matching > limit:
        raise WorkerFailure("entry-limit")
    raw_accessions = recent.get("accessionNumber") or []
    raw_acceptance = recent.get("acceptanceDateTime") or []
    if not isinstance(raw_accessions, list) or not isinstance(raw_acceptance, list) or len(raw_accessions) != len(raw_forms) or len(raw_acceptance) != len(raw_forms):
        raise WorkerFailure("malformed-submissions")
    acceptance_by_accession = dict(zip(raw_accessions, raw_acceptance, strict=True))

    try:
        try:
            if os.name == "nt":
                import platform

                # truststore asks for this constant during import; on Windows the stdlib
                # otherwise shells out to `cmd /c ver`, which the worker must not permit.
                platform.system = lambda: "Windows"

            from pyrate_limiter import SingleBucketFactory

            # EDGAR creates an unused HTTP manager at import. Its limiter otherwise starts
            # a background asyncio thread that requires loopback sockets on Windows.
            SingleBucketFactory.schedule_leak = lambda self, bucket: None

            from edgar.entity.data import (
                create_company_filings,
                extract_company_filings_table,
            )

            extract_company_filings_table(copy.deepcopy(recent))
            filings = create_company_filings(
                {"recent": copy.deepcopy(recent)},
                cik=int(cik),
                company_name=str(document.get("name") or selected.get("publisher") or "SEC registrant"),
            )
        finally:
            finish_native_imports()
    except WorkerFailure:
        raise
    except Exception:
        raise WorkerFailure("api-mismatch") from None

    records = []
    try:
        for index in range(len(filings)):
            filing = filings[index]
            form = str(filing.form)
            if form not in forms:
                continue
            accession = str(filing.accession_no)
            compact = accession.replace("-", "")
            if len(compact) != 18 or not compact.isdigit():
                raise WorkerFailure("malformed-submissions")
            description = str(filing.primary_doc_description or "")[:1000] or None
            file_number = str(filing.file_number or "")[:100] or None
            records.append(
                {
                    "accession": accession,
                    "form": form,
                    "filing_date": _date(filing.filing_date, required=True),
                    "accepted_at": _accepted_at(acceptance_by_accession.get(accession)),
                    "report_date": _date(filing.report_date),
                    "items": _labels(filing.items),
                    "primary_document_description": description,
                    "file_number": file_number,
                    "size": int(filing.size or 0),
                    "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/{accession}-index.html",
                }
            )
    except WorkerFailure:
        raise
    except Exception:
        raise WorkerFailure("api-mismatch") from None
    if len(records) != matching:
        raise WorkerFailure("api-mismatch")
    return records


def main() -> None:
    if len(sys.argv) < 2 or not os.path.isdir(sys.argv[1]):
        sys.stdout.write('{"ok":false,"protocol":1,"reason":"worker-failed"}')
        return
    scratch = os.path.realpath(sys.argv[1])
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(Path(scratch) / "local-data")
    os.environ["EDGAR_CACHE_DIR"] = str(Path(scratch) / "cache")
    os.environ["EDGAR_USE_LOCAL_DATA"] = "False"
    try:
        for directory in sys.argv[2:]:
            if not os.path.isabs(directory) or not os.path.isdir(directory):
                raise WorkerFailure("worker-failed")
            sys.path.append(directory)
        finish_native_imports = _install_audit_hook(scratch, allow_native_imports=True)
        payload = sys.stdin.buffer.read(6 * 1024 * 1024 + 1)
        if len(payload) > 6 * 1024 * 1024:
            raise WorkerFailure("malformed-submissions")
        records = _parse(json.loads(payload), finish_native_imports)
        response = {"protocol": 1, "ok": True, "records": records}
    except WorkerFailure as exc:
        response = {"protocol": 1, "ok": False, "reason": exc.reason}
    except Exception:
        response = {"protocol": 1, "ok": False, "reason": "worker-failed"}
    sys.stdout.write(json.dumps(response, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
