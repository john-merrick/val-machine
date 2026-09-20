from dataclasses import dataclass


@dataclass(frozen=True)
class MacroAssumptions:
    sustainable_risk_free_rate: float = 0.04
    equity_risk_premium: float = 0.05
    market_avg_multiple: float = 15.0


DEFAULT_MACRO = MacroAssumptions()
