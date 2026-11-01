"""The saved-results index under research/."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest

from hedge_fund import paths
from hedge_fund.backtesting import research
from hedge_fund.backtesting.fund import FundBacktestMetrics, FundBacktestResult
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def research_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RESEARCH_DIR", tmp_path)
    return tmp_path


def test_research_history_is_matched_on_the_fund_field_not_the_filename_prefix(research_dir):
    """`alpha` must not pick up `alpha-2`'s backtests: names can be prefixes."""
    receipt = {"fund": "alpha-2", "start": "2025-01-01", "end": "2025-02-01", "benchmark": "SPY",
               "metrics": {"total_return_pct": .5, "annualized_return_pct": .5, "sharpe_ratio": 2,
                           "max_drawdown_pct": .1, "benchmark_return_pct": .1, "excess_return_pct": .4, "n_cycles": 5}}
    (research_dir / "alpha-2-2025-01-01-2025-02-01-x.json").write_text(json.dumps(receipt))
    assert research.receipts("alpha") == []
    assert len(research.receipts("alpha-2")) == 1
    assert research.last_score("alpha") is None


def _result() -> FundBacktestResult:
    return FundBacktestResult(
        fund="alpha",
        start="2025-01-02T09:30:00",
        end="2025-01-02T09:31:00",
        rebalance="minute",
        benchmark="SPY",
        universe=["AAPL"],
        capital=100_000,
        dates=["2025-01-02T09:30:00"],
        nav=[100_000],
        benchmark_nav=[100_000],
        metrics=FundBacktestMetrics(
            total_return_pct=0,
            annualized_return_pct=0,
            sharpe_ratio=0,
            max_drawdown_pct=0,
            benchmark_return_pct=0,
            excess_return_pct=0,
            n_cycles=0,
            n_orders=0,
        ),
        records=[],
    )


def test_save_result_requires_enrolled_root(tmp_path):
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        with paths.bound_root(context):
            with pytest.raises(research.ResearchAdmissionError):
                research.save_result(_result(), directory=tmp_path / "research")
            assert not (tmp_path / "research").exists()


def test_save_result_admission_denial_preserves_existing_bytes(tmp_path, monkeypatch):
    class FrozenDatetime:
        @staticmethod
        def now():
            return datetime(2026, 11, 1, 12, 0, 0)

        @staticmethod
        def fromisoformat(value):
            return datetime.fromisoformat(value)

    monkeypatch.setattr(research, "datetime", FrozenDatetime)
    report_name = "alpha-2025-01-02T09-30-00-2025-01-02T09-31-00-20261101-120000-000000.json"
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        context.mkdir("research")
        context.write_bytes(f"research/{report_name}", b"reviewed report")
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        owner.close()

        with paths.bound_root(context):
            with pytest.raises(research.ResearchAdmissionError):
                research.save_result(
                    _result(),
                    directory=tmp_path / "research",
                    admission=admission,
                )

        assert context.read_bytes(f"research/{report_name}") == b"reviewed report"


def test_save_result_uses_root_writer_and_safe_minute_filename(tmp_path):
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        with paths.bound_root(context):
            try:
                path = research.save_result(_result(), directory=tmp_path / "research", admission=admission)
            finally:
                owner.close()
        assert path.parent == tmp_path / "research"
        assert path.name.startswith("alpha-2025-01-02T09-30-00-2025-01-02T09-31-00-")
        assert path.suffix == ".json"
        assert research.summarize(path, 0)["fund"] == "alpha"


def test_save_result_rejects_path_like_fund_identity(tmp_path):
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        invalid = _result().model_copy(update={"fund": "../outside"})
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        with paths.bound_root(context):
            try:
                with pytest.raises(ValueError, match="identity"):
                    research.save_result(invalid, admission=admission)
            finally:
                owner.close()
        assert not (tmp_path / "research").exists()


def test_research_writer_holds_fund_lane_without_runner_lane(tmp_path, monkeypatch):
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        original_write_bytes = context.write_bytes
        observed = []

        def verify_research_lane(relative, data, **kwargs):
            if str(relative).startswith("research/"):
                observed.append(
                    (
                        admission.lane_is_held("research", "alpha"),
                        admission.lane_is_held("runner", "alpha"),
                    )
                )
            return original_write_bytes(relative, data, **kwargs)

        monkeypatch.setattr(context, "write_bytes", verify_research_lane)
        try:
            with paths.bound_root(context):
                with admission.runner_reservation("alpha", timeout=0):
                    path = research.save_result(
                        _result(),
                        directory=tmp_path / "research",
                        admission=admission,
                    )
        finally:
            owner.close()

        assert path.is_file()
        assert observed == [(True, True)]


def test_research_lanes_for_independent_funds_do_not_contend(tmp_path):
    with RootContext.open(tmp_path) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        barrier = Barrier(2)

        def hold_lane(fund):
            with admission.research_lane(fund, timeout=0):
                barrier.wait(timeout=2)
                return admission.lane_is_held("research", fund)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(hold_lane, "alpha")
                second = pool.submit(hold_lane, "beta")
                assert first.result(timeout=3)
                assert second.result(timeout=3)
        finally:
            owner.close()
