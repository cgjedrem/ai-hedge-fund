import pytest
from pydantic import ValidationError

from hedge_fund.fund.spec import FundSpec

MINIMAL = {
    "schema_version": 2,
    "name": "test-fund",
    "strategies": [{"name": "event", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
    "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
}

LEGACY_DEFAULT_JSON = '{"schema_version":2,"name":"test-fund","strategies":' '[{"name":"event","display_name":null,"weight":1.0,' '"models":[{"name":"pead","weight":1.0,"params":{}}],' '"blend":{"method":"conviction_weighted","gross_target":1.0,"mode":"long_short"}}],' '"risk":{"max_position_pct":0.25,"max_gross_exposure":1.0},' '"capital":100000.0,"rebalance":"weekly","benchmark":"SPY"}'


def test_broker_default_is_byte_compatible_and_saxo_requires_minute_cadence():
    assert FundSpec(**MINIMAL).model_dump_json() == LEGACY_DEFAULT_JSON
    with pytest.raises(ValidationError, match="in-market intraday cadence"):
        FundSpec(**{**MINIMAL, "broker": "saxo"})
    saxo = FundSpec(**{**MINIMAL, "broker": "saxo", "rebalance": "minute"})
    assert saxo.broker == "saxo"
    assert saxo.costs.spread_bps == 0
    assert saxo.costs.commission_per_share == 0
    assert FundSpec.model_validate(saxo.model_dump()) == saxo


def test_saxo_zero_cost_default_preserves_explicit_costs_and_paper_defaults():
    saxo = {**MINIMAL, "broker": "saxo", "rebalance": "minute"}
    explicit = FundSpec(
        **{
            **saxo,
            "costs": {"spread_bps": 2.5, "commission_per_share": 0.01},
        }
    )
    assert explicit.costs.spread_bps == 2.5
    assert explicit.costs.commission_per_share == 0.01
    explicit_paper_costs = FundSpec(
        **{
            **saxo,
            "costs": {"spread_bps": 5, "commission_per_share": 0.005},
        }
    )
    assert FundSpec.model_validate(explicit_paper_costs.model_dump()) == explicit_paper_costs
    assert "costs" in explicit_paper_costs.model_dump()

    paper = FundSpec(**MINIMAL)
    assert paper.costs.spread_bps == 5
    assert paper.costs.commission_per_share == 0.005
    assert paper.model_dump_json() == LEGACY_DEFAULT_JSON


def test_saxo_minute_window_defaults_to_regular_hours_and_rejects_close_bar():
    paper_minute = FundSpec(**{**MINIMAL, "rebalance": "minute"})
    assert paper_minute.window.start == "09:30"
    assert paper_minute.window.end == "16:00"

    saxo = FundSpec(**{**MINIMAL, "broker": "saxo", "rebalance": "minute"})
    assert saxo.window.start == "09:30"
    assert saxo.window.end == "15:59"

    with pytest.raises(ValidationError, match="regular market hours"):
        FundSpec(
            **{
                **MINIMAL,
                "broker": "saxo",
                "rebalance": "minute",
                "window": {"start": "09:30", "end": "16:00"},
            }
        )
    with pytest.raises(ValidationError, match="regular market hours"):
        FundSpec(
            **{
                **MINIMAL,
                "broker": "saxo",
                "rebalance": "minute",
                "window": {"start": "09:29", "end": "15:59"},
            }
        )
    valid = FundSpec(
        **{
            **MINIMAL,
            "broker": "saxo",
            "rebalance": "minute",
            "window": {"start": "09:30", "end": "15:59"},
        }
    )
    assert valid.window.end == "15:59"


def test_broker_literal_rejects_unknown_value():
    with pytest.raises(ValidationError, match="broker"):
        FundSpec(**{**MINIMAL, "broker": "live"})
