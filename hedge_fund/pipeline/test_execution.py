"""build_orders tests — pure diffing math."""

from hedge_fund.brokers.models import Position
from hedge_fund.pipeline.execution import build_orders


def _positions(**shares):
    return {t: Position(ticker=t, shares=s) for t, s in shares.items()}


def test_truncated_sizing_never_overshoots():
    orders = build_orders({"AAPL": 0.25}, {}, {"AAPL": 300.0}, equity=10_000.0)
    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].quantity == 8.3333  # 2500 / 300 = 8.3333... -> 8.3333
    assert orders[0].quantity * 300.0 <= 2_500.0  # never overshoots the allocation


def test_delta_against_existing_position():
    orders = build_orders(
        {"AAPL": 0.25}, _positions(AAPL=5), {"AAPL": 250.0}, equity=10_000.0,
    )
    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].quantity == 5  # target 10, held 5


def test_held_name_missing_from_targets_is_closed():
    orders = build_orders({}, _positions(AAPL=7), {"AAPL": 100.0}, equity=10_000.0)
    assert len(orders) == 1
    assert orders[0].side == "sell"
    assert orders[0].quantity == 7


def test_subshare_delta_emits_nothing():
    orders = build_orders({"AAPL": 0.0000001}, {}, {"AAPL": 100.0}, equity=10_000.0)
    assert orders == []  # 0.00001 shares: below the 4dp sizing precision


def test_fractional_target_emits_a_fractional_order():
    orders = build_orders({"AAPL": 0.005}, {}, {"AAPL": 100.0}, equity=10_000.0)
    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].quantity == 0.5  # 50 dollars / 100 = 0.5 shares


def test_high_priced_name_buys_a_fraction_instead_of_nothing():
    # The watchtower bug: 0.244 * 3000 / 928.76 = 0.78813... used to floor to
    # 0 shares and silently emit no order.
    orders = build_orders({"AAPL": 0.244}, {}, {"AAPL": 928.76}, equity=3_000.0)
    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].quantity == 0.7881
    assert orders[0].quantity * 928.76 <= 732.0  # never overshoots the allocation


def test_sells_before_buys_alphabetical():
    orders = build_orders(
        {"AAPL": 0.2, "MSFT": 0.0, "NVDA": 0.2, "AMZN": 0.0},
        _positions(MSFT=10, NVDA=1, AMZN=5),
        {"AAPL": 100.0, "MSFT": 100.0, "NVDA": 100.0, "AMZN": 100.0},
        equity=10_000.0,
    )
    assert [(o.ticker, o.side) for o in orders] == [
        ("AMZN", "sell"), ("MSFT", "sell"),
        ("AAPL", "buy"), ("NVDA", "buy"),
    ]


def test_short_target_sells_past_zero():
    orders = build_orders({"AAPL": -0.2}, {}, {"AAPL": 100.0}, equity=10_000.0)
    assert len(orders) == 1
    assert orders[0].side == "sell"
    assert orders[0].quantity == 20


def test_min_order_gate_off_by_default():
    # no threshold -> a $30 order still trades (pre-gate behavior preserved)
    orders = build_orders({"AAPL": 0.003}, {}, {"AAPL": 100.0}, equity=10_000.0)
    assert len(orders) == 1


def test_min_order_gate_skips_orders_below_the_threshold():
    # 0.003 * 10_000 = $30 < 1% of equity ($100) -> skipped
    orders = build_orders({"AAPL": 0.003}, {}, {"AAPL": 100.0}, equity=10_000.0, min_order_pct=1.0)
    assert orders == []


def test_min_order_gate_passes_meaningful_orders():
    orders = build_orders({"AAPL": 0.25}, {}, {"AAPL": 100.0}, equity=10_000.0, min_order_pct=1.0)
    assert len(orders) == 1
    assert orders[0].side == "buy"


def test_min_order_gate_trades_at_the_threshold():
    # exactly 1% of equity -> trades; the gate is strict less-than
    orders = build_orders({"AAPL": 0.01}, {}, {"AAPL": 100.0}, equity=10_000.0, min_order_pct=1.0)
    assert len(orders) == 1


def test_min_order_gate_skips_dust_exits_too():
    # closing a $30 dust position is skipped as well — paying a per-order
    # minimum to move dust is the waste the gate exists to stop; the dust
    # stays in the book and exits only if it grows past the threshold
    orders = build_orders({}, _positions(AAPL=0.3), {"AAPL": 100.0}, equity=10_000.0, min_order_pct=1.0)
    assert orders == []
