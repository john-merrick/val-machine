"""
Convert reported financial history into mid-cycle drivers and surface flags.
Separate from engine.py — the most likely module to change as normalisation rules evolve.

No auto-adjustment of flags. Flags are reported; a human decides.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import statistics

from distval.schema import Financials


# ---------------------------------------------------------------------------
# Distributor flags
# ---------------------------------------------------------------------------

@dataclass
class NormalisationFlags:
    """Red flags surfaced to the analyst for distributor businesses."""

    capex_exceeds_da: bool = False
    working_capital_outpacing_revenue: bool = False
    elevated_gross_margin: bool = False
    rising_leverage_falling_roic: bool = False
    inventory_outpacing_revenue: bool = False
    organic_growth_unclear: bool = False

    def any_set(self) -> bool:
        return any(vars(self).values())


# ---------------------------------------------------------------------------
# Industrial/manufacturing flags
# ---------------------------------------------------------------------------

@dataclass
class IndustrialNormalisationFlags:
    """Red flags surfaced to the analyst for industrial/manufacturing businesses."""

    capex_to_revenue_elevated: bool = False
    backlog_declining_vs_guide: bool = False
    asset_turnover_deteriorating: bool = False
    acquisition_contribution_unquantified: bool = False

    def any_set(self) -> bool:
        return any(vars(self).values())


# ---------------------------------------------------------------------------
# SaaS/software flags
# ---------------------------------------------------------------------------

@dataclass
class SaaSNormalisationFlags:
    """Red flags surfaced to the analyst for SaaS/software businesses."""

    nrr_declining: bool = False
    s_and_m_accelerating_vs_arr_growth: bool = False
    gross_margin_compressing_at_scale: bool = False
    cohort_data_absent: bool = False

    def any_set(self) -> bool:
        return any(vars(self).values())


# ---------------------------------------------------------------------------
# Distributor normalisation functions (unchanged from v0.1)
# ---------------------------------------------------------------------------

def mean_gross_margin(history: list[Financials]) -> float:
    """Average gross margin over the full history (minimum 10 years required)."""
    if len(history) < 10:
        raise ValueError(f"Need at least 10 years of history for mid-cycle derivation, got {len(history)}")
    margins = [float(f.gross_profit / f.revenue) for f in history]
    return statistics.mean(margins)


def mean_opex_pct(history: list[Financials]) -> float:
    """Average opex (gross_profit − operating_income) as % of revenue over full history."""
    if len(history) < 10:
        raise ValueError(f"Need at least 10 years of history for mid-cycle derivation, got {len(history)}")
    pcts = [float((f.gross_profit - f.operating_income) / f.revenue) for f in history]
    return statistics.mean(pcts)


def avg_wc_days(history: list[Financials]) -> tuple[float, float, float]:
    """Average DIO, DSO, DPO (days of revenue) over history."""
    if not history:
        raise ValueError("History must not be empty")
    dios = [float(f.inventory / f.revenue * 365) for f in history]
    dsos = [float(f.receivables / f.revenue * 365) for f in history]
    dpos = [float(f.payables / f.revenue * 365) for f in history]
    return statistics.mean(dios), statistics.mean(dsos), statistics.mean(dpos)


def detect_flags(history: list[Financials]) -> NormalisationFlags:
    """Scan history and return any normalisation flags that need analyst review."""
    flags = NormalisationFlags()

    sorted_h = sorted(history, key=lambda f: f.fiscal_year)

    if len(sorted_h) >= 3:
        capex_above_da_streak = 0
        for f in sorted_h:
            if f.capex > f.d_and_a:
                capex_above_da_streak += 1
            else:
                capex_above_da_streak = 0
        if capex_above_da_streak >= 3:
            flags.capex_exceeds_da = True

    if len(sorted_h) >= 2:
        for i in range(1, len(sorted_h)):
            prev, cur = sorted_h[i - 1], sorted_h[i]
            if prev.revenue == 0 or prev.inventory == 0:
                continue
            rev_growth = float((cur.revenue - prev.revenue) / prev.revenue)
            inv_growth = float((cur.inventory - prev.inventory) / prev.inventory)
            if inv_growth - rev_growth > 0.10:
                flags.inventory_outpacing_revenue = True
                break

    if len(sorted_h) >= 10:
        margins = [float(f.gross_profit / f.revenue) for f in sorted_h]
        mean = statistics.mean(margins)
        stdev = statistics.stdev(margins)
        current = float(sorted_h[-1].gross_profit / sorted_h[-1].revenue)
        if stdev > 0 and (current - mean) / stdev > 1.5:
            flags.elevated_gross_margin = True

    return flags
