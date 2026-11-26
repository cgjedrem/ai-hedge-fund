"""Strict loading of the packaged, reviewed news catalog."""

from __future__ import annotations

import ipaddress
import json
import re
from importlib.resources.abc import Traversable
from urllib.parse import urlsplit

from pydantic import ValidationError

from hedge_fund.news.models import CuratedCatalog, SourceDefinition


class CatalogValidationError(ValueError):
    """The complete catalog is invalid; no partial plan is available."""


def load_catalog(resource: Traversable) -> CuratedCatalog:
    """Load one supplied resource without resolving URLs or ambient paths."""
    try:
        payload = json.loads(
            resource.read_bytes().decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        catalog = CuratedCatalog.model_validate(payload)
        _validate_sources(catalog.sources)
        return catalog
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise CatalogValidationError("curated news catalog is invalid") from exc


def _canonical_public_hostname(value: str) -> bool:
    if not value or len(value) > 253 or value != value.lower():
        return False
    try:
        value.encode("ascii")
        ipaddress.ip_address(value)
    except UnicodeError:
        return False
    except ValueError:
        pass
    else:
        return False
    return all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split("."))


def _excluded_publisher(host: str) -> bool:
    return host == "yahoo.com" or host.endswith(".yahoo.com")


def _validate_sources(sources: tuple[SourceDefinition, ...]) -> None:
    ids: set[str] = set()
    bindings: set[tuple[str, ...]] = set()
    for source in sources:
        parsed = urlsplit(source.url)
        host = parsed.hostname
        if source.source_id in ids or parsed.scheme != "https" or parsed.port not in (None, 443) or host is None or host != host.lower() or host not in source.allowed_hosts or parsed.fragment or parsed.username or parsed.password or any(not _canonical_public_hostname(allowed) or _excluded_publisher(allowed) for allowed in source.allowed_hosts):
            raise ValueError("invalid source identity or origin")
        if (source.scope == "company") != bool(source.tickers):
            raise ValueError("company scope and tickers disagree")
        if source.category == "editorial" and (source.scope != "company" or len(source.tickers) != 1 or not source.company_aliases):
            raise ValueError("editorial sources require one ticker and reviewed aliases")
        if source.kind == "feed":
            if source.cik is not None or source.forms:
                raise ValueError("only SEC sources accept EDGAR bindings")
        else:
            if not source.cik or not source.cik.isdigit() or len(source.cik) != 10 or source.category != "sec-filing" or not source.forms or set(source.allowed_hosts) != {"data.sec.gov", "www.sec.gov"} or parsed.path != f"/submissions/CIK{source.cik}.json":
                raise ValueError("invalid EDGAR binding")
        evidence = source.curation
        if evidence.basis == "registry-reviewed" and not (evidence.registry_opml_path and evidence.registry_xml_url):
            raise ValueError("registry provenance requires exact evidence")
        if evidence.basis == "independently-verified" and (evidence.registry_opml_path or evidence.registry_xml_url):
            raise ValueError("independent source has registry provenance")
        if evidence.approved_by.strip().lower() in {"todo", "tbd", "unknown", ""}:
            raise ValueError("curation approval is missing")
        if source.summary_policy == "feed-supplied" and "license" not in evidence.rights_note.lower():
            raise ValueError("summary reuse has no rights evidence")
        binding = (source.kind, source.url, *source.tickers, source.cik or "", *source.forms)
        if source.enabled and source.scope == "company" and binding in bindings:
            raise ValueError("duplicate source binding")
        ids.add(source.source_id)
        if source.enabled:
            bindings.add(binding)
