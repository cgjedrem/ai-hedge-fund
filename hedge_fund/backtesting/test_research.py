"""The saved-results index under research/."""

import json

import pytest

from hedge_fund import paths
from hedge_fund.backtesting import research
from hedge_fund.backtesting.fund import FundBacktestMetrics, FundBacktestResult
from hedge_fund.runtime.handover import enroll_fresh, HandoverError
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
    context = RootContext.open(tmp_path)
    try:
        context.prepare_private_storage()
        with paths.bound_root(context):
            with pytest.raises(HandoverError):
                research.save_result(_result(), directory=tmp_path / "research")
            assert not (tmp_path / "research").exists()
    finally:
        context.close()


def test_save_result_uses_root_writer_and_safe_minute_filename(tmp_path):
    context = RootContext.open(tmp_path)
    try:
        enroll_fresh(context)
        with paths.bound_root(context):
            path = research.save_result(_result(), directory=tmp_path / "research")
            assert path.parent == tmp_path / "research"
            assert path.name.startswith("alpha-2025-01-02T09-30-00-2025-01-02T09-31-00-")
            assert path.suffix == ".json"
            assert research.summarize(path, 0)["fund"] == "alpha"
    finally:
        context.close()


def test_save_result_rejects_path_like_fund_identity(tmp_path):
    context = RootContext.open(tmp_path)
    try:
        enroll_fresh(context)
        invalid = _result().model_copy(update={"fund": "../outside"})
        with paths.bound_root(context):
            with pytest.raises(ValueError, match="identity"):
                research.save_result(invalid)
            assert not (tmp_path / "research").exists()
    finally:
        context.close()
