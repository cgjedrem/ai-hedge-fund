"""Market-cap breakpoints tests — canned CSV, no network."""

import io
import os
import time
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from hedge_fund.features.breakpoints import (
    fetch_breakpoints_csv,
    load_breakpoints,
    MEBreakpoints,
)
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.policy import AuthorizationDenied, BudgetDenied, ProviderTarget


def _row(month: str, start: int) -> str:
    """20 thresholds in $ millions: start, 2*start, ..., 20*start."""
    values = ", ".join(f"{start * i:.2f}" for i in range(1, 21))
    return f"{month}, 1100, {values}"


SAMPLE = "\n".join([
    "This file contains every 5th market-cap percentile (divided by 1000000).",
    "",
    _row("202405", 100),
    _row("202406", 110),
    _row("202407", 120),
    "",
    "Copyright footer line",
])

_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _dispatch(*, boundary_check=None, max_calls=1):
    target = ProviderTarget(kind="data", provider="ken-french-breakpoints")
    dispatch = make_one_shot_dispatch(
        root_id="breakpoints-test-root",
        subject_id="breakpoints-test",
        capture_digest="a" * 64,
        operation_id="breakpoints-operation",
        operation_digest="b" * 64,
        expires_at=_NOW + timedelta(minutes=5),
        targets=(target,),
        max_calls=max_calls,
        max_cost=Decimal("0"),
        max_resources=max_calls,
        upper_bound_costs={target.identity: Decimal("0")},
        clock=lambda: _NOW,
        boundary_check=boundary_check,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )
    return target, dispatch


def _archive():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ME_Breakpoints.csv", SAMPLE)
    return output.getvalue()


def _transport(calls, content=None):
    payload = _archive() if content is None else content

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=payload, request=request)

    return httpx.MockTransport(respond)


def test_parse_skips_prose_and_keeps_every_month():
    table = MEBreakpoints.parse(SAMPLE)
    assert table.latest_month == "202407"
    month, thresholds = table.row_for("2024-08-15")
    assert month == "202407"
    assert thresholds[0] == pytest.approx(120.0) and thresholds[-1] == pytest.approx(2400.0)


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        MEBreakpoints.parse("no rows here")


def test_row_is_the_latest_month_strictly_before_the_filing_month():
    """Month M's breakpoints use end-of-M prices — not knowable inside M."""
    table = MEBreakpoints.parse(SAMPLE)
    assert table.row_for("2024-07-15")[0] == "202406"
    assert table.row_for("2024-07-01")[0] == "202406"
    assert table.row_for("2024-12-31")[0] == "202407"  # gap: fall back to latest published
    assert table.row_for("2024-05-20") is None  # nothing published before May


def test_size_percentile_counts_thresholds_met():
    table = MEBreakpoints.parse(SAMPLE)
    # Filed in July -> June row: thresholds 110M, 220M, ..., 2200M.
    assert table.size_percentile(1_500_000_000, "2024-07-15") == 65   # >= 13 of them
    assert table.size_percentile(110_000_000, "2024-07-15") == 5      # exactly the 5th
    assert table.size_percentile(50_000_000, "2024-07-15") == 0       # below the 5th
    assert table.size_percentile(2_200_000_000, "2024-07-15") == 95   # meets all 20, capped
    assert table.size_percentile(3_000_000_000_000, "2024-07-15") == 95
    assert table.size_percentile(None, "2024-07-15") is None
    assert table.size_percentile(0.0, "2024-07-15") is None
    assert table.size_percentile(1_500_000_000, "2024-05-20") is None  # no row


def test_load_fetches_once_then_reads_the_cache(tmp_path, monkeypatch):
    calls = []

    def fetch(**_kwargs):
        calls.append(1)
        return SAMPLE

    monkeypatch.setattr(
        "hedge_fund.features.breakpoints.fetch_breakpoints_csv",
        fetch,
    )
    path = tmp_path / "breakpoints" / "ME_Breakpoints.csv"
    first = load_breakpoints(path)
    second = load_breakpoints(path)
    assert calls == [1]
    assert path.exists()
    assert first.latest_month == second.latest_month == "202407"


def test_breakpoint_download_requires_dispatch_before_transport():
    calls = []
    with pytest.raises(AuthorizationDenied):
        fetch_breakpoints_csv(inner_transport=_transport(calls))
    assert calls == []


def test_breakpoint_fetch_reserves_before_transport_and_exhausts_budget(tmp_path):
    target, dispatch = _dispatch()
    calls = []
    transport = _transport(calls)

    first = fetch_breakpoints_csv(dispatch=dispatch, inner_transport=transport)
    assert MEBreakpoints.parse(first).latest_month == "202407"
    assert len(calls) == 1
    assert dispatch._one_shot[target.identity].calls_reserved == 1

    with pytest.raises(BudgetDenied):
        fetch_breakpoints_csv(dispatch=dispatch, inner_transport=transport)
    assert len(calls) == 1
    assert dispatch._one_shot[target.identity].calls_reserved == 1


def test_breakpoint_cache_uses_guarded_fetch_once(tmp_path):
    target, dispatch = _dispatch()
    calls = []
    path = tmp_path / "breakpoints" / "ME_Breakpoints.csv"

    first = load_breakpoints(
        path,
        dispatch=dispatch,
        inner_transport=_transport(calls),
    )
    second = load_breakpoints(
        path,
        dispatch=dispatch,
        inner_transport=_transport(calls),
    )

    assert first.latest_month == second.latest_month == "202407"
    assert len(calls) == 1
    assert dispatch._one_shot[target.identity].calls_reserved == 1


def test_authorization_denial_does_not_fall_back_to_stale_cache(tmp_path):
    path = tmp_path / "ME_Breakpoints.csv"
    path.write_text(SAMPLE)
    stale = time.time() - 40 * 86400
    os.utime(path, (stale, stale))
    calls = []
    transport = _transport(calls)
    _, dispatch = _dispatch(boundary_check=lambda: (_ for _ in ()).throw(AuthorizationDenied("operation expired")))

    with pytest.raises(AuthorizationDenied, match="operation expired"):
        load_breakpoints(path, dispatch=dispatch, inner_transport=transport)
    assert calls == []


def test_load_refreshes_a_stale_cache(tmp_path, monkeypatch):
    path = tmp_path / "ME_Breakpoints.csv"
    path.write_text(SAMPLE)
    old = time.time() - 40 * 86400
    os.utime(path, (old, old))

    newer = SAMPLE.replace("Copyright", _row("202408", 130) + "\nCopyright")
    monkeypatch.setattr(
        "hedge_fund.features.breakpoints.fetch_breakpoints_csv",
        lambda **_kwargs: newer,
    )
    table = load_breakpoints(path)
    assert table.latest_month == "202408"
    assert "202408" in path.read_text()


def test_load_keeps_a_stale_cache_when_the_fetch_fails(tmp_path, monkeypatch):
    path = tmp_path / "ME_Breakpoints.csv"
    path.write_text(SAMPLE)
    old = time.time() - 40 * 86400
    os.utime(path, (old, old))

    def fetch(**_kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(
        "hedge_fund.features.breakpoints.fetch_breakpoints_csv",
        fetch,
    )
    assert load_breakpoints(path).latest_month == "202407"


def test_load_raises_with_no_cache_and_fetch_failure(tmp_path, monkeypatch):
    def fetch(**_kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(
        "hedge_fund.features.breakpoints.fetch_breakpoints_csv",
        fetch,
    )
    with pytest.raises(ConnectionError):
        load_breakpoints(tmp_path / "missing.csv")
