from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator


class Financials(BaseModel):
    """As-reported, from filings. Never edited by hand."""

    ticker: str
    fiscal_year: int
    filed_date: date
    revenue: Decimal
    gross_profit: Decimal
    operating_income: Decimal
    d_and_a: Decimal
    capex: Decimal
    inventory: Decimal
    receivables: Decimal
    payables: Decimal
    net_ppe: Decimal
    total_debt: Decimal
    cash: Decimal
    minority_interest: Decimal
    shares_diluted: Decimal
    lifo_reserve: Decimal | None = None


class Drivers(BaseModel):
    """Analyst judgement. Lives in companies/<ticker>.yaml."""

    ticker: str
    forecast_years: int

    revenue: list[Decimal]
    gross_margin: list[float]
    opex_pct_sales: list[float]

    dio: float
    dso: float
    dpo: float

    maintenance_capex_pct_sales: float
    tax_rate: float

    mid_cycle_ebit: Decimal
    duration_score: int
    stability_score: int

    other_elements: dict[str, Decimal] = {}

    @model_validator(mode="after")
    def _list_lengths(self) -> "Drivers":
        n = self.forecast_years
        if len(self.revenue) != n:
            raise ValueError(f"revenue must have {n} entries, got {len(self.revenue)}")
        if len(self.gross_margin) != n:
            raise ValueError(f"gross_margin must have {n} entries")
        if len(self.opex_pct_sales) != n:
            raise ValueError(f"opex_pct_sales must have {n} entries")
        return self

    @field_validator("duration_score", "stability_score")
    @classmethod
    def _score_range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("score must be between 1 and 10")
        return v

    @field_validator("tax_rate")
    @classmethod
    def _tax_rate_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("tax_rate must be between 0 and 1")
        return v


class Valuation(BaseModel):
    ticker: str
    as_of: date
    input_hash: str
    fcf_path: list[Decimal]
    discount_rate: float
    terminal_multiple: float
    terminal_value: Decimal
    enterprise_value: Decimal
    other_elements_total: Decimal
    net_debt: Decimal
    minority_interest: Decimal
    equity_value: Decimal
    value_per_share: Decimal
    price: Decimal | None
    upside_pct: float | None
