"""Regression tests for TUI root admission.

Trusted paper writes require owner and fund lanes. Creation and deletion deny."""

import asyncio
import time
from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from hedge_fund import paths
from hedge_fund.backtesting.fund import FundBacktestMetrics, FundBacktestResult
from hedge_fund.backtesting.research import receipts
from hedge_fund.data.models import Price
from hedge_fund.paper import deploy, Ledger
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError, RootOwnerLease
from hedge_fund.runtime.configuration import RuntimeSettings
from hedge_fund.runtime.handover import record_ledger_head
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root
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


def _tree_snapshot(root: Path) -> dict[str, str | bytes]:
    return {path.relative_to(root).as_posix(): "dir" if path.is_dir() else path.read_bytes() for path in root.rglob("*")}


@pytest.fixture
def unenrolled_root(tmp_path, monkeypatch):
    """A bound root that was never enrolled, with the TUI dirs inside it."""
    root = tmp_path / "unenrolled"
    root.mkdir()
    with RootContext.open(root) as context, paths.bound_root(context), monkeypatch.context() as bound:
        bound.setattr(paths, "PAPER_DIR", root / "paper")
        bound.setattr(paths, "MANDATES_DIR", root / "mandates")
        bound.setattr(paths, "RESEARCH_DIR", root / "research")
        yield root


@pytest.fixture
def trusted_tui_root(tmp_path, monkeypatch):
    root_path = tmp_path / "trusted-tui-root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: {"kind": "synthetic-test-owner", "identity": "tui"},
    )
    with RootContext.open(root_path) as root, paths.bound_root(root):
        review = handover.prepare_single_writer_acknowledgement(root)
        handover.trust_single_writer(
            root,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )
        yield root_path


@pytest.fixture
def trusted_tui_paper_fund(trusted_tui_root):
    root_path = trusted_tui_root
    root = paths.root_context()
    owner = RootOwnerLease.acquire(root, timeout=0)
    admission = AdmissionCoordinator(root, owner_lease=owner)
    try:
        with admission.deployment_lock("alpha", timeout=0):
            directory = deploy("alpha", make_spec(["pead"], "alpha"), ["TEST"], root=paths.PAPER_DIR)
        ledger = Ledger(directory)
        with admission.halt_lane("alpha", timeout=0):
            ledger.halt(paper_view.APP_HALT)
        record_ledger_head(root, "alpha", admission=admission)
    finally:
        owner.close()
    return root_path, directory, ledger


def test_unenrolled_root_denies_tui_paper_writes(unenrolled_root):
    denial = funds.paper_write_denial()
    assert denial is not None
    assert "offline root enrollment" in denial
    assert "handover inspect" in denial


def test_enrolled_untrusted_root_denies_tui_paper_writes_without_creating_state(tmp_path, monkeypatch):
    root_path = tmp_path / "untrusted-tui-root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    monkeypatch.setattr(paths, "PAPER_DIR", root_path / "paper")
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: {"kind": "synthetic-test-owner", "identity": "tui"},
    )
    with RootContext.open(root_path) as root, paths.bound_root(root):
        denial = funds.paper_write_denial()

    assert denial is not None
    assert "trust-single-writer" in denial


def test_tui_denial_does_not_offer_trust_when_runtime_scope_is_unavailable(trusted_tui_root, monkeypatch):
    root_path = trusted_tui_root

    def unavailable(_root):
        raise handover.HandoverError("synthetic runtime scope unavailable")

    monkeypatch.setattr(handover, "_runtime_scope_identity", unavailable)
    before = _tree_snapshot(root_path)

    denial = funds.paper_write_denial()

    after = _tree_snapshot(root_path)
    assert denial is not None
    assert "runtime scope cannot be verified" in denial
    assert "trusted mode stays disabled" in denial
    assert "handover inspect" in denial
    assert after == before


def test_untrusted_root_denies_tui_paper_writes_without_creating_state(tmp_path, monkeypatch):
    root_path = tmp_path / "untrusted-tui-root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: {"kind": "synthetic-test-owner", "identity": "tui"},
    )
    with RootContext.open(root_path) as root, paths.bound_root(root):
        before = {path.relative_to(root_path).as_posix(): path.read_bytes() for path in root_path.rglob("*") if path.is_file()}
        denial = funds.paper_write_denial()
        after = {path.relative_to(root_path).as_posix(): path.read_bytes() for path in root_path.rglob("*") if path.is_file()}

    assert denial is not None
    assert "trust-single-writer" in denial
    assert after == before


def test_trusted_tui_resume_is_admitted_and_request_bound(trusted_tui_paper_fund, monkeypatch):
    _root_path, _directory, ledger = trusted_tui_paper_fund
    assert funds.paper_write_denial() is None

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen(select="alpha"))
            screen = app.screen
            notices = _notices(monkeypatch, screen)
            screen.action_resume()
            await pilot.pause()
            assert notices == ["alpha resumed"]

    asyncio.run(scenario())
    assert ledger.halted() is None
    resume = next(event for event in ledger.events() if event["kind"] == "resume")
    assert resume["by"] == "tui"
    assert resume["request_action"] == "resume"
    assert resume["request_id"]


def test_tui_run_records_one_captured_quant_session(trusted_tui_root, monkeypatch):
    from importlib import import_module

    root = paths.root_context()
    owner = RootOwnerLease.acquire(root, timeout=0)
    admission = AdmissionCoordinator(root, owner_lease=owner)
    try:
        with admission.deployment_lock("alpha", timeout=0):
            directory = deploy("alpha", make_spec(["pead"], "alpha"), ["TEST"], root=paths.PAPER_DIR)
        record_ledger_head(root, "alpha", admission=admission)
    finally:
        owner.close()

    class FakeDataClient:
        def get_prices(self, ticker, start_date, end_date, **_kwargs):
            return [Price(open=100, close=100, high=100, low=100, volume=1000, time=f"{day}T16:00:00Z") for day in ("2025-01-20", "2025-01-21") if start_date <= day <= end_date]

        def get_earnings_history(self, _ticker, limit=8):
            assert limit == 8
            return []

    fake_data = FakeDataClient()
    monkeypatch.setattr(paper, "make_data_client", lambda *_args, **_kwargs: nullcontext(fake_data))
    monkeypatch.setattr(paper, "CachedDataClient", lambda client, **_kwargs: client)
    monkeypatch.setattr(
        paper,
        "resolve_settings",
        lambda *_args, **_kwargs: RuntimeSettings(
            data_provider="yfinance",
            llm_provider="Ollama",
            model="gemma3:4b",
        ),
    )
    monkeypatch.setattr(paper, "next_session", lambda *_args, **_kwargs: "2025-01-21")
    tick_module = import_module("hedge_fund.paper.tick")
    monkeypatch.setattr(tick_module, "next_session", lambda *_args, **_kwargs: "2025-01-21")
    plan = paper._resolve_tui_run_plan(directory)
    assert plan.action == "run"
    assert plan.due == "2025-01-21"

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            screen = paper.RunSessionScreen(directory, plan=plan)
            await app.push_screen(screen)
            for _ in range(400):
                await pilot.pause(0.05)
                if screen._phase in {"done", "failed"}:
                    break
            assert screen._phase == "done"

    asyncio.run(scenario())
    ledger = Ledger(directory)
    assert ledger.latest() is not None
    assert ledger.latest().session == "2025-01-21"
    event = next(event for event in ledger.events() if event.get("kind") == "tick")
    assert event["request_id"] == plan.request_id
    assert event["operation_id"] == plan.operation_id
    assert event["capture_id"] == plan.capture.capture_id
    assert event["capture_digest"] == plan.capture.digest


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


def test_paper_resume_uses_tui_actor_for_simple_halt(trusted_tui_paper_fund, monkeypatch):
    """Synthetic trusted-root Resume records the TUI audit actor."""
    _root_path, _directory, ledger = trusted_tui_paper_fund

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


def test_paper_resume_denies_a_concurrent_participating_writer(monkeypatch, tmp_path, owned_test_process):
    """TUI resume denies while another process holds the fund control lane."""
    root = tmp_path / "enrolled"
    root.mkdir()
    enroll_synthetic_root(root)
    monkeypatch.setattr(paths, "PAPER_DIR", root / "paper")
    with RootContext.open(root) as context, paths.bound_root(context):
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

            ready = tmp_path / "writer-ready"
            release = tmp_path / "writer-release"
            script = (
                "import time\n"
                "from pathlib import Path\n"
                "from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease\n"
                "from hedge_fund.runtime.root import RootContext\n"
                f"root_path = Path({str(root)!r})\n"
                f"ready = Path({str(ready)!r})\n"
                f"release = Path({str(release)!r})\n"
                "with RootContext.open(root_path) as root:\n"
                "    owner = RootOwnerLease.acquire(root, timeout=0)\n"
                "    try:\n"
                "        admission = AdmissionCoordinator(root, owner_lease=owner)\n"
                "        with admission.control_lane('alpha', timeout=0):\n"
                "            ready.write_text('held', encoding='utf-8')\n"
                "            deadline = time.monotonic() + 15\n"
                "            while not release.exists() and time.monotonic() < deadline:\n"
                "                time.sleep(0.01)\n"
                "    finally:\n"
                "        owner.close()\n"
            )
            process = owned_test_process(script)
            deadline = time.monotonic() + 10
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists()

            try:

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
            finally:
                release.write_text("release", encoding="utf-8")
            assert process.wait(timeout=10) == 0
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
