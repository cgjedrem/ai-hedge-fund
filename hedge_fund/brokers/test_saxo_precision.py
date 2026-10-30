from types import SimpleNamespace

import pytest

from hedge_fund.brokers.models import Order
from hedge_fund.brokers.saxo import _tradable_quantity, SaxoBroker
from hedge_fund.brokers.test_saxo_doubles import FakeClock


def test_quantity_rounds_down_to_lot_size():
    assert _tradable_quantity(3.47, 0.1) == 3.4


def test_fraction_below_lot_is_not_rounded_up():
    assert _tradable_quantity(0.5, 1) == 0


def test_saxo_filters_lot_dust_before_order_submission():
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {"ABC": (0.0, 42, "Stock", {"LotSize": 1})}
    broker.client = SimpleNamespace(clock=FakeClock())
    dust = Order(ticker="ABC", side="sell", quantity=0.0001, price=100)
    fractional_drift = Order(ticker="ABC", side="sell", quantity=3.83, price=100)

    filtered = broker.filter_orders([dust, fractional_drift])

    assert len(filtered) == 1
    assert filtered[0] == fractional_drift.model_copy(update={"quantity": 3})
    assert filtered[0] is not fractional_drift


@pytest.mark.parametrize("details", [{}, {"LotSize": None}])
def test_missing_or_null_lot_size_uses_one_share_fallback(details):
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {"ABC": (0.0, 42, "Stock", details)}
    broker.client = SimpleNamespace(clock=FakeClock())
    order = Order(ticker="ABC", side="buy", quantity=3.83, price=100)

    filtered = broker.filter_orders([order])

    assert len(filtered) == 1
    assert filtered[0].quantity == 3
