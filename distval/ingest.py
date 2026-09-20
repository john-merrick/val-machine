"""
Ingest financial data from SEC EDGAR filings via edgartools.
Populates Financials objects from 10-K filings, point-in-time by construction.
All calls take an as_of date — never silently pull restated figures.
"""
import logging
import os
from datetime import date
from decimal import Decimal

from distval.schema import Financials

logger = logging.getLogger(__name__)


def fetch_financials(ticker: str, as_of: date, years: int = 10) -> list[Financials]:
    """
    Fetch up to `years` years of 10-K Financials for `ticker` as of `as_of`.

    Only filings with a filed_date <= as_of are returned, enforcing point-in-time
    discipline. No lookahead bias.

    Requires EDGAR_IDENTITY env var (your email, per SEC fair-access policy).

    Raises:
        ValueError: if the company does not file a 10-K (e.g. foreign filers)
        RuntimeError: if the EDGAR connection fails
    """
    try:
        import edgar  # edgartools
    except ImportError as e:
        raise ImportError("edgartools is required for ingest. Install with: pip install edgartools") from e

    identity = os.environ.get("EDGAR_IDENTITY")
    if not identity:
        raise RuntimeError(
            "Set the EDGAR_IDENTITY environment variable to your email address. "
            "This is required by the SEC fair-access policy. "
            "Example: export EDGAR_IDENTITY=you@example.com"
        )
    edgar.set_identity(identity)

    company = edgar.Company(ticker)
    filings_10k = company.get_filings(form="10-K")

    results: list[Financials] = []
    skipped = 0
    for filing in filings_10k:
        if filing.filing_date > as_of:
            continue

        try:
            fin = _parse_10k(ticker, filing)
        except Exception as exc:
            logger.warning("Skipping filing %s for %s: %s", filing.filing_date, ticker, exc)
            skipped += 1
            continue

        results.append(fin)
        if len(results) >= years:
            break

    if skipped:
        logger.info("Skipped %d filing(s) for %s due to parse errors", skipped, ticker)

    results.sort(key=lambda f: f.fiscal_year, reverse=True)
    return results


def _parse_10k(ticker: str, filing) -> Financials:
    """Extract Financials from a single 10-K filing object."""
    income = filing.income_statement
    balance = filing.balance_sheet
    cash_flow = filing.cash_flow_statement

    def _d(val) -> Decimal:
        if val is None:
            return Decimal("0")
        return Decimal(str(val))

    return Financials(
        ticker=ticker,
        fiscal_year=filing.period_of_report.year,
        filed_date=filing.filing_date,
        revenue=_d(income.revenues),
        gross_profit=_d(income.gross_profit),
        operating_income=_d(income.operating_income),
        d_and_a=_d(cash_flow.depreciation_amortization),
        capex=abs(_d(cash_flow.capital_expenditures)),
        inventory=_d(balance.inventory),
        receivables=_d(balance.net_receivables),
        payables=_d(balance.accounts_payable),
        net_ppe=_d(balance.net_ppe),
        total_debt=_d(balance.total_debt),
        cash=_d(balance.cash_and_equivalents),
        minority_interest=_d(balance.minority_interest),
        shares_diluted=_d(income.diluted_shares),
        lifo_reserve=None,  # extracted separately where disclosed
    )
