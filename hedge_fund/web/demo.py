"""Synthetic, disk-backed demo fund."""

from __future__ import annotations

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
    data_root = Path(root).expanduser().resolve()
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
    cycle_one = _cycle(spec, first, "2024-06-04", 100_000, 100_000, 90_000, 100_500, 100.0, 105.0, buy=True)
    cycle_two = _cycle(spec, second, "2024-06-05", 100_500, 90_000, 90_000, 101_000, 105.0, 110.0)
    record_one = _record(spec, first, None, 100_000, 100_000, {}, {}, 500.0, None)
    record_two = _record(spec, second, cycle_one, 100_500, 90_000, {"AAPL": 100}, {"AAPL": 105.0}, 505.0, record_one)
    record_three = _record(spec, third, cycle_two, 101_000, 90_000, {"AAPL": 100}, {"AAPL": 110.0}, 502.5, record_two)
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
    fills = [Fill(ticker="AAPL", side="buy", quantity=100, price=reference_price)] if buy else []
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
