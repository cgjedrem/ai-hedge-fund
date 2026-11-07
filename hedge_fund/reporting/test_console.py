"""Fixed-output tests for reports usable without the terminal interface."""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from rich.text import Text

from hedge_fund.brokers.models import format_shares
from hedge_fund.pipeline import SessionRecord
from hedge_fund.reporting.console import analyst_table, cost_line, session_headline, strategy_table
from hedge_fund.scorecard import AnalystScore, Scorecard, StrategyScore


def _render(renderable) -> str:
    output = io.StringIO()
    Console(file=output, width=160, color_system=None).print(renderable, soft_wrap=True)
    return output.getvalue()


def _card(*, analysts=(), strategies=(), fund_pnl=0.0, trading_cost=0.0) -> Scorecard:
    return Scorecard(
        fund="alpha",
        first_session="2025-01-06",
        last_session="2025-03-03",
        horizon="weekly",
        analysts=list(analysts),
        strategies=list(strategies),
        fund_pnl=fund_pnl,
        trading_cost=trading_cost,
    )


def test_cost_line_uses_traded_notional_bps():
    assert cost_line(312.0, 375_000.0) == "costs $312 · 8.3 bps of $375,000 traded"
    assert cost_line(0.0, 0.0) == "no trades"
    assert cost_line(-0.49, 12_500.0) == "costs $-0 · -0.4 bps of $12,500 traded"


@pytest.mark.parametrize(("cost", "notional"), [(True, 1), (float("nan"), 1), (1, float("inf"))])
def test_cost_line_rejects_non_numeric_or_non_finite_values(cost, notional):
    with pytest.raises(ValueError, match="finite numbers"):
        cost_line(cost, notional)


def test_analyst_scorecard_preserves_counts_rates_and_row_order():
    card = _card(
        analysts=[
            AnalystScore(
                name="pead",
                n_views=4,
                n_directional=0,
                n_abstained=4,
                hit_rate=None,
                slugging=None,
                ic_mean=-0.042,
                ic_std=0.11,
                ic_t_stat=-2.3,
                n_dates=3,
            ),
            AnalystScore(
                name="buffett",
                n_views=40,
                n_directional=32,
                n_abstained=3,
                hit_rate=0.5625,
                slugging=1.8,
                ic_mean=0.042,
                ic_std=0.11,
                ic_t_stat=1.2,
                n_dates=10,
            ),
        ]
    )
    table = analyst_table(card)
    headers = [column.header.plain if isinstance(column.header, Text) else column.header for column in table.columns]
    text = _render(table)

    assert headers == ["analyst", "views", "abstained", "hit rate", "slugging", "IC", "IC t", "dates"]
    assert "judged over one weekly period" in text
    assert text.index("PEAD") < text.index("Buffett")
    assert "56% of 32" in text and "1.80×" in text
    assert "-0.042" in text and "+0.042" in text
    assert "-2.3" in text and "+1.2" in text


def test_strategy_scorecard_reports_signed_precision_and_unattributed_gap():
    card = _card(
        strategies=[
            StrategyScore(
                name="fundamental-ls",
                n_periods=8,
                pnl=2450.0,
                return_pct=0.0245,
                win_rate=0.625,
                share_of_pnl=1.2,
                max_drawdown_pct=0.013,
            ),
            StrategyScore(
                name="carry",
                n_periods=2,
                pnl=-1234.56,
                return_pct=-0.0245,
                win_rate=0.25,
                share_of_pnl=-0.6,
                max_drawdown_pct=0.02,
            ),
        ],
        fund_pnl=2040.0,
        trading_cost=300.0,
    )
    table = strategy_table(card)
    headers = [column.header.plain if isinstance(column.header, Text) else column.header for column in table.columns]
    text = _render(table)

    assert headers == ["strategy", "periods", "P&L", "return", "win rate", "max DD", "share"]
    assert text.index("fundamental-ls") < text.index("carry")
    assert "+2,450" in text and "-1,235" in text
    assert "+2.45%" in text and "-2.45%" in text
    assert "62% of 8" in text
    assert "fund P&L +2,040" in text
    assert "unattributed +825" in text
    assert "trading costs -300" in text


def test_empty_scorecard_explains_missing_gradeable_data():
    card = _card()
    assert "nothing to grade yet" in _render(analyst_table(card))
    assert "nothing to attribute yet" in _render(strategy_table(card))
    assert "no decisions yet" in _render(analyst_table(card.model_copy(update={"horizon": None})))


def test_fixed_code_version_report_fixture_keeps_serialization_and_fact_order():
    record = SessionRecord(
        fund="alpha",
        session="2025-01-21",
        universe=["TEST"],
        nav=10_000.0,
        cash=9_763.27,
        positions={"TEST": 0.7891},
        marks={"TEST": 300.0},
        benchmark="SPY",
        benchmark_close=500.0,
        rebalance=False,
        code_version="spec005-fixture-v1",
        mandate_hash="fixed-mandate",
    )
    expected_json = '{"schema_version":2,"fund":"alpha","session":"2025-01-21","universe":["TEST"],' '"nav":10000.0,"cash":9763.27,"positions":{"TEST":0.7891},"marks":{"TEST":300.0},' '"benchmark":"SPY","benchmark_close":500.0,"rebalance":false,"executed":null,' '"decision":null,"prev_hash":null,"code_version":"spec005-fixture-v1",' '"mandate_hash":"fixed-mandate","llm_model":null,"snapshot_times":null}'

    assert record.model_dump_json(exclude={"hash"}) == expected_json
    assert _render(session_headline("alpha", record)) == "alpha  ·  session 2025-01-21  ·  valuation only\n"


def test_signed_fractional_share_format_keeps_precision():
    assert format_shares(0.7891, signed=True) == "+0.7891"
    assert format_shares(-0.7891, signed=True) == "-0.7891"


def test_console_helpers_import_without_tui_or_textual(owned_test_process):
    process = owned_test_process("import sys; import hedge_fund.reporting.console; " "assert not any(name == 'hedge_fund.tui' or name.startswith('hedge_fund.tui.') " "or name == 'textual' or name.startswith('textual.') for name in sys.modules)")
    assert process.wait(timeout=10) == 0
