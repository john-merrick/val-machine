"""
Pure valuation functions. No I/O, no network, no clock.
All inputs come in; all outputs come out. Reproducible by construction.
"""
from decimal import Decimal, getcontext
from datetime import date
import hashlib
import json

from distval.macro import MacroAssumptions
from distval.schema import Drivers, Valuation

getcontext().prec = 28


def discount_rate(macro: MacroAssumptions) -> float:
    return macro.sustainable_risk_free_rate + macro.equity_risk_premium


def terminal_multiple(market_avg_multiple: float, duration_score: int, stability_score: int) -> float:
    combined = (duration_score + stability_score) / 2
    adjustment = 0.40 * (combined - 5.5) / 4.5
    return market_avg_multiple * (1 + adjustment)


def invested_capital(
    revenue: Decimal,
    dio: float,
    dso: float,
    dpo: float,
    net_ppe: Decimal,
) -> Decimal:
    inventory = revenue * Decimal(dio) / 365
    receivables = revenue * Decimal(dso) / 365
    payables = revenue * Decimal(dpo) / 365
    return inventory + receivables - payables + net_ppe


def _pv_of_annuity(cash_flows: list[Decimal], rate: float) -> Decimal:
    r = Decimal(str(rate))
    total = Decimal("0")
    for t, cf in enumerate(cash_flows, start=1):
        total += cf / (1 + r) ** t
    return total


def _build_fcf_path(drivers: Drivers) -> list[Decimal]:
    fcf_path: list[Decimal] = []

    # IC at t=0: base year — use d.revenue[0] as the baseline (flat prior period)
    # ΔWC at t=1 is IC[1] - IC[0]. For a cold start we use revenue[0] as t=0 proxy.
    prev_ic = invested_capital(
        drivers.revenue[0], drivers.dio, drivers.dso, drivers.dpo, Decimal("0")
    )

    for t in range(drivers.forecast_years):
        rev = drivers.revenue[t]
        gm = Decimal(str(drivers.gross_margin[t]))
        opex = Decimal(str(drivers.opex_pct_sales[t]))
        tax = Decimal(str(drivers.tax_rate))
        capex_pct = Decimal(str(drivers.maintenance_capex_pct_sales))

        gross_profit = rev * gm
        ebit = gross_profit - rev * opex
        nopat = ebit * (1 - tax)
        capex = rev * capex_pct
        d_and_a = capex  # assume D&A == capex unless overridden

        cur_ic = invested_capital(rev, drivers.dio, drivers.dso, drivers.dpo, Decimal("0"))
        delta_wc = cur_ic - prev_ic
        prev_ic = cur_ic

        fcf = nopat + d_and_a - capex - delta_wc
        fcf_path.append(fcf)

    return fcf_path


def _input_hash(drivers: Drivers, macro: MacroAssumptions, net_debt: Decimal, minority_interest: Decimal, shares_diluted: Decimal) -> str:
    payload = json.dumps(
        {
            "drivers": drivers.model_dump(mode="json"),
            "macro": {"rfr": macro.sustainable_risk_free_rate, "erp": macro.equity_risk_premium, "mkt": macro.market_avg_multiple},
            "net_debt": str(net_debt),
            "minority_interest": str(minority_interest),
            "shares_diluted": str(shares_diluted),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def value(
    drivers: Drivers,
    macro: MacroAssumptions,
    net_debt: Decimal,
    minority_interest: Decimal,
    shares_diluted: Decimal,
    price: Decimal | None,
    as_of: date,
) -> Valuation:
    if shares_diluted <= 0:
        raise ValueError("shares_diluted must be positive")

    dr = discount_rate(macro)
    tm = terminal_multiple(macro.market_avg_multiple, drivers.duration_score, drivers.stability_score)

    fcf_path = _build_fcf_path(drivers)

    pv_fcf = _pv_of_annuity(fcf_path, dr)

    mid_cycle_nopat = drivers.mid_cycle_ebit * (1 - Decimal(str(drivers.tax_rate)))
    tv = mid_cycle_nopat * Decimal(str(tm))
    n = drivers.forecast_years
    pv_tv = tv / (1 + Decimal(str(dr))) ** n

    ev = pv_fcf + pv_tv

    other_total = sum(drivers.other_elements.values(), Decimal("0"))
    equity = ev + other_total - net_debt - minority_interest
    vps = equity / shares_diluted

    upside: float | None = None
    if price is not None and price > 0:
        upside = float((vps - price) / price * 100)

    ih = _input_hash(drivers, macro, net_debt, minority_interest, shares_diluted)

    return Valuation(
        ticker=drivers.ticker,
        as_of=as_of,
        input_hash=ih,
        fcf_path=fcf_path,
        discount_rate=dr,
        terminal_multiple=tm,
        terminal_value=tv,
        enterprise_value=ev,
        other_elements_total=other_total,
        net_debt=net_debt,
        minority_interest=minority_interest,
        equity_value=equity,
        value_per_share=vps,
        price=price,
        upside_pct=upside,
    )
