"""Property tests for the engine."""
from decimal import Decimal
from datetime import date

import pytest

from distval.engine import value
from distval.macro import MacroAssumptions
from distval.schema import Drivers


MACRO = MacroAssumptions()

_BASE_DRIVERS = dict(
    ticker="PROP",
    forecast_years=5,
    revenue=[Decimal("1000")] * 5,
    gross_margin=[0.30] * 5,
    opex_pct_sales=[0.20] * 5,
    dio=60.0,
    dso=45.0,
    dpo=50.0,
    maintenance_capex_pct_sales=0.02,
    tax_rate=0.25,
    mid_cycle_ebit=Decimal("100"),
    duration_score=5,
    stability_score=5,
)


_AS_OF = date(2024, 1, 1)


def _val(**driver_overrides):
    d = {**_BASE_DRIVERS, **driver_overrides}
    drivers = Drivers(**d)
    return value(
        drivers=drivers,
        macro=MACRO,
        net_debt=Decimal("200"),
        minority_interest=Decimal("0"),
        shares_diluted=Decimal("100"),
        price=None,
        as_of=_AS_OF,
    )


def test_higher_duration_score_increases_value():
    low = _val(duration_score=3, stability_score=5)
    high = _val(duration_score=8, stability_score=5)
    assert high.equity_value > low.equity_value


def test_higher_stability_score_increases_value():
    low = _val(duration_score=5, stability_score=3)
    high = _val(duration_score=5, stability_score=8)
    assert high.equity_value > low.equity_value


def test_net_debt_decreases_equity_one_for_one():
    base = value(Drivers(**_BASE_DRIVERS), MACRO, Decimal("200"), Decimal("0"), Decimal("100"), None, _AS_OF)
    more_debt = value(Drivers(**_BASE_DRIVERS), MACRO, Decimal("300"), Decimal("0"), Decimal("100"), None, _AS_OF)
    diff = base.equity_value - more_debt.equity_value
    assert float(diff) == pytest.approx(100.0, abs=0.01)


def test_zero_revenue_growth_implies_zero_delta_wc():
    val = _val()
    # With flat revenue, every FCF year should be identical
    for fcf in val.fcf_path:
        assert float(fcf) == pytest.approx(float(val.fcf_path[0]), abs=0.001)
