"""TradingCosts — the half-spread and the commission, by hand."""

import pytest
from pydantic import ValidationError

from hedge_fund.brokers.costs import TradingCosts


def test_defaults_are_a_liquid_large_cap_at_retail_rates():
    costs = TradingCosts()
    assert costs.spread_bps == 5.0
    assert costs.commission_per_share == 0.005


def test_buy_pays_the_half_spread_and_sell_receives_it():
    costs = TradingCosts(spread_bps=5, commission_per_share=0.005)
    assert costs.fill_price("buy", 100.0) == pytest.approx(100.05)
    assert costs.fill_price("sell", 100.0) == pytest.approx(99.95)
    assert costs.commission(100, 100.0) == pytest.approx(0.50)


def test_zero_on_both_is_a_free_fill():
    costs = TradingCosts(spread_bps=0, commission_per_share=0)
    assert costs.fill_price("buy", 100.0) == 100.0
    assert costs.fill_price("sell", 100.0) == 100.0
    assert costs.commission(1_000, 100.0) == 0.0


def test_notional_commission_scales_with_the_order_value():
    costs = TradingCosts(spread_bps=0, commission_per_share=0, commission_bps=8)
    assert costs.commission(100, 100.0) == pytest.approx(8.00)
    assert costs.commission(10, 50.0) == pytest.approx(0.40)


def test_minimum_floors_small_orders():
    costs = TradingCosts(spread_bps=0, commission_per_share=0, commission_bps=8, min_commission_per_order=15)
    assert costs.commission(10, 50.0) == 15.0
    assert costs.commission(1_000, 100.0) == pytest.approx(80.0)


def test_minimum_applies_even_to_a_free_cost_model():
    costs = TradingCosts(spread_bps=0, commission_per_share=0, min_commission_per_order=15)
    assert costs.commission(1, 100.0) == 15.0


@pytest.mark.parametrize(
    "bad",
    [
        {"spread_bps": -1},
        {"commission_per_share": -0.01},
        {"commission_bps": -1},
        {"min_commission_per_order": -1},
        {"impact": 0.1},
    ],
)
def test_negative_or_unknown_fields_are_rejected(bad):
    with pytest.raises(ValidationError):
        TradingCosts(**bad)
