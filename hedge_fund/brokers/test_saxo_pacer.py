from hedge_fund.brokers.saxo import Pacer
from hedge_fund.brokers.test_saxo_doubles import FakeClock


def test_order_calls_are_spaced_and_reads_are_unpaced():
    clock = FakeClock()
    pacer = Pacer(clock=clock)

    pacer.wait_for("orders")
    pacer.wait_for("orders")
    pacer.wait_for("positions")

    assert clock.sleeps == [1.0]
    assert clock.value == 1.0
    assert pacer.last_call_at["orders"] == 1.0
