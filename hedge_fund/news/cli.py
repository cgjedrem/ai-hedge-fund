"""Manual bounded refresh and strictly local news health commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from importlib.resources import files
from urllib.parse import urlsplit

from hedge_fund.data.protocol import DataClientError
from hedge_fund.news.catalog import CatalogValidationError, load_catalog
from hedge_fund.news.models import (
    RefreshLimits,
    RefreshRun,
    SourceHealth,
    SourceHealthView,
)
from hedge_fund.news.refresh import NewsRefresher, RefreshRequest
from hedge_fund.news.store import NewsStore
from hedge_fund.news.transport import validate_sec_identity
from hedge_fund.runtime.capture import root_identity_id
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget
from hedge_fund.runtime.root import RootContext, RootPathError


def execute(args: argparse.Namespace, parser: argparse.ArgumentParser, root: RootContext) -> None:
    try:
        catalog = load_catalog(files("hedge_fund.news").joinpath("catalog.json"))
    except CatalogValidationError:
        parser.error("curated news catalog is invalid")
    if args.news_action == "status":
        _status(args, parser, root, catalog)
        return
    _refresh(args, parser, root, catalog)


def _is_sec_host(host: str) -> bool:
    normalized = host.casefold()
    return normalized == "sec.gov" or normalized.endswith(".sec.gov")


def _selected_sources(args, catalog, *, explicit_requires_enabled: bool, allow_unknown: bool = False):
    by_id = {source.source_id: source for source in catalog.sources}
    explicit = list(args.source or ())
    if len(explicit) != len(set(explicit)):
        raise ValueError("duplicate news source selector")
    selected = []
    if explicit:
        for source_id in explicit:
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", source_id) is None:
                raise ValueError("malformed news source selector")
            source = by_id.get(source_id)
            if source is None:
                if allow_unknown:
                    continue
                raise ValueError("unknown news source")
            if explicit_requires_enabled and not source.enabled:
                raise ValueError("disabled news source")
            selected.append(source)
    elif args.news_action == "status":
        selected = list(catalog.sources)
    else:
        selected = [source for source in catalog.sources if source.enabled]
    tickers = {value.upper() for value in (getattr(args, "ticker", None) or ())}
    if tickers:
        matches = [source for source in catalog.sources if source.enabled and tickers.intersection(source.tickers)]
        selected = list({source.source_id: source for source in (*selected, *matches)}.values()) if explicit else matches
    return tuple(sorted(selected, key=lambda source: (source.sequence, source.source_id)))


def _status(args, parser, root: RootContext, catalog) -> None:
    try:
        selected = _selected_sources(args, catalog, explicit_requires_enabled=False, allow_unknown=True)
        known_ids = {source.source_id for source in catalog.sources}
        absent_source_ids = sorted(set(args.source or ()) - known_ids)
        health = {item.source_id: item for item in NewsStore(root).health(tuple(source.source_id for source in selected))}
    except ValueError:
        parser.error("news source selection is invalid")
    except (DataClientError, RootPathError):
        print("curated news state is unreadable", file=sys.stderr)
        raise SystemExit(1) from None
    views = []
    for source in selected:
        view = health.get(source.source_id)
        if view is None:
            view = SourceHealthView(
                **SourceHealth(
                    source_id=source.source_id,
                    enabled=source.enabled,
                    status="never-run" if source.enabled else "disabled",
                    freshness_seconds=source.freshness_seconds,
                ).model_dump()
            )
        if not source.enabled:
            view = view.model_copy(update={"enabled": False, "status": "disabled"})
        views.append(view)
    payload = {
        "status": "ok",
        "sources": [item.model_dump(mode="json") for item in views],
        "absent_source_ids": absent_source_ids,
    }
    rows = [(item.source_id, item.status, item.freshness, item.reason_code or "-") for item in views]
    rows.extend((source_id, "absent", "-", "-") for source_id in absent_source_ids)
    _output(args, payload, rows)


def _refresh(args, parser, root: RootContext, catalog) -> None:
    if not args.enable_network:
        parser.error("news refresh requires explicit --enable-network consent")
    if args.model:
        parser.error("news refresh does not accept an analyst model override")
    try:
        selected = _selected_sources(args, catalog, explicit_requires_enabled=True)
        limits = RefreshLimits()
    except ValueError:
        parser.error("news source selection or request bounds are invalid")
    try:
        if not selected:
            now = datetime.now(UTC)
            run = RefreshRun(
                run_id=uuid.uuid4().hex,
                catalog_digest=catalog.digest,
                source_ids=(),
                started_at=now,
                ended_at=now,
                limits=limits,
                status="no-op",
            )
            _output_run(args, run)
            return
        sec_identity = os.environ.get("HEDGE_FUND_NEWS_SEC_IDENTITY")
        requires_sec_identity = any(source.kind == "sec-edgar" or _is_sec_host(urlsplit(source.url).hostname or "") or any(_is_sec_host(host) for host in source.allowed_hosts) for source in selected)
        if requires_sec_identity:
            try:
                sec_identity = validate_sec_identity(sec_identity)
            except AuthorizationDenied:
                parser.error("SEC news sources require a descriptive HEDGE_FUND_NEWS_SEC_IDENTITY")
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=limits.run_deadline_seconds)
        operation_id = uuid.uuid4().hex
        targets = tuple(ProviderTarget(kind="data", provider="curated-news", endpoint=f"https://{host}") for host in sorted({host for source in selected for host in source.allowed_hosts}))
        operation = {
            "catalog_digest": catalog.digest,
            "expires_at": expires_at.isoformat(),
            "limits": limits.model_dump(mode="json"),
            "sources": [{"source_id": source.source_id, "url": source.url, "allowed_hosts": source.allowed_hosts} for source in selected],
        }
        operation_digest = hashlib.sha256(json.dumps(operation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        dispatch = make_one_shot_dispatch(
            root_id=root_identity_id(root),
            subject_id="curated-news-operator",
            capture_digest=catalog.digest,
            operation_id=operation_id,
            operation_digest=operation_digest,
            expires_at=expires_at,
            targets=targets,
            max_calls=limits.max_requests_per_run,
            max_cost=Decimal("0"),
            max_resources=limits.max_requests_per_run,
            upper_bound_costs={target.identity: Decimal("0") for target in targets},
        )
        run = NewsRefresher().refresh(
            RefreshRequest(
                run_id=operation_id,
                catalog=catalog,
                source_ids=tuple(source.source_id for source in selected),
                root=root,
                dispatch=dispatch,
                limits=limits,
                wall_clock=lambda: datetime.now(UTC),
                monotonic_clock=time.monotonic,
                waiter=time.sleep,
                sec_identity=sec_identity,
            )
        )
    except AuthorizationDenied:
        parser.error("news provider authorization is invalid")
    except DataClientError:
        print("curated news state could not be committed", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, OSError, RootPathError):
        print("curated news refresh failed", file=sys.stderr)
        raise SystemExit(1) from None
    _output_run(args, run)
    if run.status != "succeeded":
        raise SystemExit(1)


def _output_run(args, run: RefreshRun) -> None:
    payload = run.model_dump(mode="json")
    rows = [(item.source_id, item.status, str(item.accepted_count), item.reason_code or "-") for item in run.outcomes]
    _output(args, payload, rows or [(run.run_id, run.status, str(run.total_requests), "-")])


def _output(args, payload, rows) -> None:
    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    for row in rows:
        print("\t".join(row))
