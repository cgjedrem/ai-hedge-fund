from __future__ import annotations

import pytest

from hedge_fund.brokers.models import Order
from hedge_fund.brokers.saxo import SaxoBroker, SaxoClient, SaxoOrderError
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport


def _transaction(*trades):
    return 200, {"Data": [{"Trades": list(trades)}]}


def _trade(quantity, price, order_id="order-1"):
    return {"OrderId": order_id, "TradedQuantity": quantity, "Price": price}


class Tokens:
    def get_access_token(self):
        return "access"


def _broker(
    transaction,
    order_response=(200, {"OrderId": "order-1"}),
    *,
    balance=10000.0,
    check_balance=False,
    lot_size=1,
    execution_timeout_s=120,
):
    responses = [
        (200, {"ClientKey": "client"}),
        (200, {"Data": [{"AccountKey": "account", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
        (200, {"Data": [{"Identifier": 44, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ"}]}),
        (
            200,
            {
                "IsTradable": True,
                "LotSize": lot_size,
                "SupportedOrderTypes": ["Market"],
                "CurrencyCode": "USD",
                "Exchange": {"CountryCode": "US", "ExchangeId": "NASDAQ"},
            },
        ),
    ]
    if check_balance:
        responses.append((200, {"Currency": "USD", "CashBalance": balance, "CashAvailableForTrading": balance}))
    responses.extend([order_response, (404, {}), transaction])
    transport = FakeTransport(responses)
    clock = FakeClock()
    client = SaxoClient(
        tokens=Tokens(),
        transport=transport,
        clock=clock,
        execution_timeout_s=execution_timeout_s,
    )
    broker = SaxoBroker(client, ["ABC"])
    return broker, transport


@pytest.mark.parametrize(
    "quantity,fill_price,side",
    [(5, 12.5, "buy"), (2, 13.0, "sell"), (5, 12.75, "sell")],
    ids=["increase", "reduction", "full-exit"],
)
def test_fill_uses_order_correlated_execution_not_position_state(quantity, fill_price, side):
    broker, transport = _broker(
        (
            200,
            {"Data": [{"Trades": [_trade(quantity, fill_price)]}]},
        ),
        check_balance=side == "buy",
    )

    fill = broker.place_order(Order(ticker="ABC", side=side, quantity=quantity, price=14))

    assert fill.quantity == quantity
    assert fill.price == fill_price
    post = next(call for call in transport.calls if call["method"] == "POST")
    assert post["json"] == {
        "AccountKey": "account",
        "Uic": 44,
        "AssetType": "Stock",
        "Amount": quantity,
        "BuySell": "Buy" if side == "buy" else "Sell",
        "OrderType": "Market",
        "OrderDuration": {"DurationType": "DayOrder"},
        "ManualOrder": False,
    }
    assert post["headers"]["x-request-id"]


def test_http_200_errorinfo_and_partial_fill_raise():
    broker, _ = _broker(
        (200, {"Data": []}),
        order_response=(200, {"ErrorInfo": {"ErrorCode": "MarketClosed"}}),
        check_balance=True,
    )
    with pytest.raises(SaxoOrderError, match="MarketClosed"):
        broker.place_order(Order(ticker="ABC", side="buy", quantity=1, price=10))

    partial_execution = _transaction(_trade(0.5, 10))
    broker, transport = _broker(
        partial_execution,
        check_balance=True,
        execution_timeout_s=2,
    )
    transport.responses.append(partial_execution)
    with pytest.raises(SaxoOrderError, match="partially filled"):
        broker.place_order(Order(ticker="ABC", side="buy", quantity=1, price=10))


def test_insufficient_buying_power_blocks_post():
    broker, transport = _broker((200, {"Data": []}), balance=10, check_balance=True)

    with pytest.raises(SaxoOrderError, match="buying power"):
        broker.place_order(Order(ticker="ABC", side="buy", quantity=2, price=10))
    assert not any(call["method"] == "POST" for call in transport.calls)


def test_order_rounds_down_using_instrument_details_lot_size():
    broker, transport = _broker(
        _transaction(_trade(3.4, 10)),
        lot_size=0.1,
    )

    fill = broker.place_order(Order(ticker="ABC", side="sell", quantity=3.45, price=10))

    assert fill.quantity == 3.4
    post = next(call for call in transport.calls if call["method"] == "POST")
    assert post["json"]["Amount"] == 3.4


def test_lot_rounding_below_minimum_refuses_without_post():
    broker, transport = _broker(
        (200, {"Data": []}),
        lot_size=1,
    )

    with pytest.raises(SaxoOrderError, match="below the instrument lot size"):
        broker.place_order(Order(ticker="ABC", side="sell", quantity=0.5, price=10))
    assert not any(call["method"] == "POST" for call in transport.calls)


def test_conflict_never_reposts_order():
    broker, transport = _broker(
        (200, {"Data": []}),
        order_response=(409, {"ErrorInfo": {"ErrorCode": "DuplicateOrder"}}),
        check_balance=True,
    )

    with pytest.raises(SaxoOrderError):
        broker.place_order(Order(ticker="ABC", side="buy", quantity=1, price=10))
    assert sum(call["method"] == "POST" for call in transport.calls) == 1


def test_unknown_post_outcome_is_not_retried_or_exposed():
    broker, transport = _broker(
        (200, {"Data": []}),
        order_response=RuntimeError("secret response"),
    )

    with pytest.raises(SaxoOrderError, match="outcome unknown") as error:
        broker.place_order(Order(ticker="ABC", side="sell", quantity=1, price=10))

    assert "secret response" not in str(error.value)
    assert sum(call["method"] == "POST" for call in transport.calls) == 1
