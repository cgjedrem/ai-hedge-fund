"""Regression tests for TUI writes under root admission.

The TUI holds no paper lanes and no admitted delete primitive, so every
paper write and mandate deletion is denied with a message instead of
crashing on an admission error; backtest receipts are saved under the same
owner lease plus research lane that `aihf backtest` takes."""

import asyncio
from pathlib import Path

import pytest
import yaml

from hedge_fund import paths
from hedge_fund.backtesting.fund import FundBacktestMetrics, FundBacktestResult
from hedge_fund.backtesting.research import receipts
from hedge_fund.paper import deploy, Ledger
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    RootOwnerLease,
)
from hedge_fund.runtime.handover import enroll_fresh, record_ledger_head
from hedge_fund.runtime.root import RootContext
from hedge_fund.tui import backtest, builder, funds, paper, paper_view
from hedge_fund.tui.app import HedgeFundApp
from hedge_fund.tui.fixtures import make_spec


def _notices(monkeypatch, screen) -> list[str]:
    notices: list[str] = []
    monkeypatch.setattr(screen, "notify", lambda message, **_kwargs: notices.append(message))
    return notices


def _result(fund: str = "alpha") -> FundBacktestResult:
    return FundBacktestResult(
        fund=fund,
        start="2025-01-02",
        end="2025-01-03",
        rebalance="daily",
        benchmark="SPY",
        universe=["AAPL"],
        capital=100_000,
        dates=["2025-01-02"],
        nav=[100_000],
        benchmark_nav=[100_000],
        metrics=FundBacktestMetrics(total_return_pct=0, annualized_return_pct=0, sharpe_ratio=0, max_drawdown_pct=0, benchmark_return_pct=0, excess_return_pct=0, n_cycles=0, n_orders=0),
        records=[],
    )


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and "runtime/" not in p.relative_to(root).as_posix()}


@pytest.fixture
def unenrolled_root(tmp_path, monkeypatch):
    """A bound root that was never enrolled, with the TUI dirs inside it."""
    root = tmp_path / "unenrolled"
    root.mkdir()
    with RootContext.open(root) as context, paths.bound_root(context), monkeypatch.context() as bound:
        bound.setattr(paths, "MANDATES_DIR", root / "mandates")
        bound.setattr(paths, "RESEARCH_DIR", root / "research")
        yield root


def test_unenrolled_root_denies_tui_paper_writes(unenrolled_root):
    assert funds.paper_write_denial() == "TUI paper writes require root admission the TUI does not hold; use the explicit-root CLI or web desk."


def test_enrolled_root_denies_tui_paper_writes():
    assert funds.paper_write_denial() == "TUI paper writes are disabled on enrolled roots; use the web desk."


def test_backtest_builder_save_on_unenrolled_root_reports_denial_without_crashing(unenrolled_root, monkeypatch):
    spec = make_spec(["pead"], "alpha")

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="backtest"))
            screen = app.screen
            notices = _notices(monkeypatch, screen)
            screen._state.update(name="alpha", strategies=list(spec.strategies), capital=spec.capital, rebalance="weekly")
            screen._finish_build()
            await pilot.pause()
            assert app.screen is screen
            assert notices == ["The mandate was not saved: root storage admission is unavailable. Use the web desk."]
            assert screen._built is None

    asyncio.run(scenario())
    assert not (unenrolled_root / "mandates" / "alpha.yaml").exists()


def test_paper_resume_uses_tui_actor_for_simple_halt(monkeypatch):
    """Synthetic standalone Resume records the TUI audit actor."""
    directory = deploy("alpha", make_spec(["pead"], "alpha"), ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    ledger.halt(paper_view.APP_HALT)
    monkeypatch.setattr(paper, "paper_write_denial", lambda: None)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            notices = _notices(monkeypatch, screen)
            await pilot.press("r")
            await pilot.pause()
            assert app.screen is screen
            assert notices == ["alpha resumed"]

    asyncio.run(scenario())
    events = ledger.events()
    assert ledger.halted() is None
    assert [event["kind"] for event in events] == ["halt", "resume", "resume_effect_intent", "resume_completed"]
    assert events[1]["by"] == "tui"


def test_paper_resume_cannot_bypass_enrolled_root_admission(monkeypatch, tmp_path):
    """A bypassed TUI guard cannot write an enrolled root without a lane."""
    root = tmp_path / "enrolled"
    root.mkdir()
    with RootContext.open(root) as context, paths.bound_root(context):
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", make_spec(["pead"], "alpha"), ["TEST"], root=paths.PAPER_DIR)
            ledger = Ledger(directory)
            with admission.halt_lane("alpha", timeout=0):
                ledger.halt(paper_view.APP_HALT)
            record_ledger_head(context, "alpha", admission=admission)
            before_events = ledger.events()
            before_control = ledger.control_path.read_bytes()
            monkeypatch.setattr(paper, "paper_write_denial", lambda: None)

            async def scenario():
                app = HedgeFundApp()
                async with app.run_test(size=(140, 50)) as pilot:
                    await app.push_screen(paper.PaperScreen())
                    screen = app.screen
                    notices = _notices(monkeypatch, screen)
                    await pilot.press("r")
                    await pilot.pause()
                    assert app.screen is screen
                    assert len(notices) == 1 and notices[0].startswith("alpha stays halted: ")

            asyncio.run(scenario())
            assert ledger.halted() == paper_view.APP_HALT
            assert ledger.events() == before_events
            assert ledger.control_path.read_bytes() == before_control
        finally:
            owner.close()


def test_mandate_library_delete_is_denied_and_keeps_every_file(monkeypatch):
    spec = make_spec(["buffett"], "alpha")
    mandate = paths.MANDATES_DIR / "alpha.yaml"
    mandate.write_text(yaml.safe_dump(spec.model_dump()))
    receipt = paths.RESEARCH_DIR / "alpha-backtest-2025-01-01.json"
    receipt.write_text("{}")
    before = _files(paths.root_context().path)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(funds.FundSelectScreen())
            screen = app.screen
            notices = _notices(monkeypatch, screen)
            await pilot.press("d")
            await pilot.pause()
            assert app.screen is screen  # no confirmation modal
            screen._finish_delete("all")  # a stale confirm callback is denied too
            assert notices == [funds.mandate_delete_denial()] * 2

    asyncio.run(scenario())
    assert mandate.exists() and receipt.exists()
    assert _files(paths.root_context().path) == before


def test_backtest_receipt_is_saved_under_research_admission():
    path = backtest._save_admitted(_result())
    assert path.parent == paths.root_context().path / "research"
    assert path in receipts("alpha")


def test_backtest_receipt_save_fails_closed_on_an_unenrolled_root(unenrolled_root):
    with pytest.raises(AdmissionError):
        backtest._save_admitted(_result())
    assert not (unenrolled_root / "research").exists()
