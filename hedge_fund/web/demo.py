"""Synthetic, disk-backed demo fund."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from hedge_fund.backtesting.fund import FundBacktestResult, performance_metrics
from hedge_fund.backtesting.research import save_result
from hedge_fund.brokers.models import Fill, Order
from hedge_fund.fund import FundSpec, save_spec
from hedge_fund.models import Signal
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.models import CycleRecord, DecisionRecord, StrategyRecord
from hedge_fund.pipeline.session import mandate_hash, SessionRecord


def seed_demo(root: str | Path) -> Path:
    """Write deterministic fixtures under an explicit empty root."""
    data_root = _demo_root(root)
    data_root.mkdir(parents=True, exist_ok=True)
    if any(data_root.iterdir()):
        raise ValueError("demo root must be empty")

    spec = FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": "demo-quality",
            "strategies": [
                {
                    "name": "earnings-drift",
                    "display_name": "Earnings Drift",
                    "models": [{"name": "pead"}],
                    "blend": {"mode": "long_short"},
                }
            ],
            "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
            "costs": {"spread_bps": 4.5, "commission_per_share": 0.005},
            "capital": 100_000,
            "rebalance": "daily",
            "benchmark": "SPY",
            "approval_required": True,
        }
    )
    save_spec(spec, data_root / "mandates")
    paper_dir = deploy("demo-quality", spec, ["AAPL", "MSFT"], root=data_root / "paper")
    ledger = Ledger(paper_dir)

    first = _decision(spec, "2024-06-03", 100.0, 0.8)
    second = _decision(spec, "2024-06-04", 105.0, 0.4)
    third = _decision(spec, "2024-06-05", 110.0, -0.2)
    cycle_one = _cycle(spec, first, "2024-06-04", 100_000, 100_000, 89_995, 100_495, 100.0, 105.0, buy=True)
    cycle_two = _cycle(spec, second, "2024-06-05", 100_495, 89_995, 89_995, 100_995, 105.0, 110.0)
    record_one = _record(spec, first, None, 100_000, 100_000, {}, {}, 500.0, None)
    record_two = _record(spec, second, cycle_one, 100_495, 89_995, {"AAPL": 100}, {"AAPL": 105.0}, 505.0, record_one)
    record_three = _record(spec, third, cycle_two, 100_995, 89_995, {"AAPL": 100}, {"AAPL": 110.0}, 502.5, record_two)
    records = [record_one, record_two, record_three]
    for record in records:
        ledger.append(record)

    dates = [record.session for record in records]
    nav = [record.nav for record in records]
    benchmark_nav = [spec.capital * record.benchmark_close / records[0].benchmark_close for record in records]
    result = FundBacktestResult(
        fund=spec.name,
        start=dates[0],
        end=dates[-1],
        rebalance=spec.rebalance,
        benchmark=spec.benchmark,
        universe=["AAPL", "MSFT"],
        capital=spec.capital,
        dates=dates,
        nav=nav,
        benchmark_nav=benchmark_nav,
        metrics=performance_metrics(spec.capital, dates, nav, benchmark_nav, [cycle_one, cycle_two]),
        records=records,
    )
    save_result(result, directory=data_root / "research")
    return data_root


def _demo_root(root: str | Path) -> Path:
    candidate = Path(root)
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1":
        return candidate.expanduser().resolve()

    test_root_value = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    test_root = Path(test_root_value)
    if not test_root_value or not test_root.is_absolute():
        raise RuntimeError("test demo requires an absolute test root")
    if not candidate.is_absolute():
        raise ValueError("test demo root must be absolute")

    test_root = Path(os.path.abspath(os.fspath(test_root)))
    data_root = Path(os.path.abspath(os.fspath(candidate)))
    try:
        relative = data_root.relative_to(test_root)
    except ValueError:
        raise ValueError(
            "demo root must stay inside test-owned root",
        ) from None

    current = test_root
    if is_reparse_point(current):
        raise ValueError("test root cannot contain reparse points")
    for part in relative.parts:
        current = current / part
        if is_reparse_point(current):
            raise ValueError("demo root cannot contain reparse points")

    resolved_test_root = test_root.resolve(strict=True)
    resolved_data_root = data_root.resolve(strict=False)
    if not resolved_data_root.is_relative_to(resolved_test_root):
        raise ValueError(
            "demo root must stay inside test-owned root",
        )
    return resolved_data_root


def is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _strategy(spec: FundSpec, session: str, conviction: float) -> StrategyRecord:
    strategy = spec.strategies[0]
    signal = Signal(
        model_name="pead",
        ticker="AAPL",
        date=session,
        value=conviction,
        reasoning="Synthetic demo view; not a live forecast.",
        components={"demo_conviction": conviction},
    )
    return StrategyRecord(
        name=strategy.name,
        slice=1.0,
        signals=[signal],
        convictions={"AAPL": conviction},
        weights={"AAPL": 0.1 if conviction > 0 else -0.1},
        final_contribution={"AAPL": 0.1 if conviction > 0 else -0.1},
    )


def _decision(spec: FundSpec, session: str, price: float, conviction: float) -> DecisionRecord:
    strategy = _strategy(spec, session, conviction)
    weight = 0.1 if conviction > 0 else -0.1
    return DecisionRecord(
        fund=spec.name,
        as_of=session,
        spec=spec,
        universe=["AAPL", "MSFT"],
        marks={"AAPL": price, "MSFT": 50.0, "SPY": 500.0},
        skipped=[],
        strategies=[strategy],
        target_weights={"AAPL": weight},
        clamps=[],
        final_weights={"AAPL": weight},
    )


def _cycle(
    spec: FundSpec,
    decision: DecisionRecord,
    execution: str,
    equity_before: float,
    cash_before: float,
    cash: float,
    nav: float,
    reference_price: float,
    mark: float,
    *,
    buy: bool = False,
) -> CycleRecord:
    orders = [Order(ticker="AAPL", side="buy", quantity=100, price=reference_price)] if buy else []
    fills = [Fill(ticker="AAPL", side="buy", quantity=100, price=spec.costs.fill_price("buy", reference_price))] if buy else []
    return CycleRecord(
        fund=spec.name,
        as_of=decision.as_of,
        spec=spec,
        universe=["AAPL", "MSFT"],
        marks={"AAPL": reference_price, "SPY": 500.0},
        skipped=[],
        strategies=decision.strategies,
        target_weights=decision.target_weights,
        clamps=[],
        final_weights=decision.final_weights,
        equity_before=equity_before,
        cash_before=cash_before,
        orders=orders,
        fills=fills,
        positions={"AAPL": 100},
        cash=cash,
        nav=nav,
        original_assessment=decision,
        execution_as_of=execution,
        execution_policy="next_close",
    )


def _record(
    spec: FundSpec,
    decision: DecisionRecord,
    executed: CycleRecord | None,
    nav: float,
    cash: float,
    positions: dict[str, float],
    marks: dict[str, float],
    benchmark_close: float,
    previous: SessionRecord | None,
) -> SessionRecord:
    record = SessionRecord(
        fund=spec.name,
        session=decision.as_of,
        universe=["AAPL", "MSFT"],
        nav=nav,
        cash=cash,
        positions=positions,
        marks=marks,
        benchmark=spec.benchmark,
        benchmark_close=benchmark_close,
        rebalance=True,
        executed=executed,
        decision=decision,
        prev_hash=previous.hash if previous is not None else None,
        code_version="synthetic-demo",
        mandate_hash=mandate_hash(spec),
    )
    record.hash = record.compute_hash()
    return record
