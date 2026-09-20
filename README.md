# distval

A systematic valuation engine for US specialty distributors. Deterministic, reproducible, no spreadsheet in the loop.

## What it does

`distval` values listed specialty distributors from structured driver configs. Analyst judgement lives in version-controlled YAML files; the arithmetic lives in code and never changes per company. Every run produces a JSON snapshot with an input hash — identical inputs always produce identical outputs.

## Requirements

- Python 3.11+
- `EDGAR_IDENTITY` environment variable (your email, required by SEC fair-access policy) — only needed for ingest from SEC filings

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package with dev dependencies
pip install -e ".[dev]"
```

## Running the model

There is no CLI entry point — the model is driven from Python. The typical workflow is:

```python
from decimal import Decimal
from datetime import date

from distval.engine import value
from distval.loader import load_drivers
from distval.macro import DEFAULT_MACRO
from distval.record import write_snapshot

# Load analyst drivers from companies/fast.yaml
drivers = load_drivers("FAST")

# Run the valuation (all dollar values in millions USD)
val = value(
    drivers=drivers,
    macro=DEFAULT_MACRO,
    net_debt=Decimal("80"),          # total_debt - cash
    minority_interest=Decimal("0"),
    shares_diluted=Decimal("571"),
    price=Decimal("63.00"),          # spot price for upside calculation (optional)
    as_of=date(2024, 1, 1),
)

print(f"Value per share: ${val.value_per_share:.2f}")
print(f"Upside: {val.upside_pct:.1f}%")

# Write a snapshot to snapshots/<ticker>_<hash[:12]>.json
path = write_snapshot(val)
print(f"Snapshot written: {path}")
```

### Macro assumptions

Macro assumptions are shared across all companies and live in `distval/macro.py`. Override them at runtime:

```python
from distval.macro import MacroAssumptions

macro = MacroAssumptions(
    sustainable_risk_free_rate=0.04,   # 4% risk-free rate
    equity_risk_premium=0.05,          # 5% equity risk premium
    market_avg_multiple=15.0,          # market average NOPAT multiple
)
```

### Ingesting financials from SEC EDGAR

To pull historical financials directly from filings:

```bash
export EDGAR_IDENTITY=you@example.com
```

```python
from datetime import date
from distval.ingest import fetch_financials

history = fetch_financials("FAST", as_of=date(2024, 1, 1), years=10)
```

This returns a list of `Financials` objects, most recent first, containing only filings available as of `as_of` (no lookahead bias).

## Adding a company

1. Create `distval/companies/<ticker>.yaml` (lowercase filename, uppercase ticker field). Use `distval/companies/fast.yaml` as a reference.

2. Required fields:

```yaml
ticker: TICK
forecast_years: 5

revenue: [1000.0, 1050.0, 1100.0, 1155.0, 1213.0]  # len must equal forecast_years
gross_margin: [0.30, 0.30, 0.30, 0.30, 0.30]
opex_pct_sales: [0.20, 0.20, 0.20, 0.20, 0.20]

dio: 60.0    # days inventory outstanding
dso: 45.0    # days sales outstanding
dpo: 50.0    # days payables outstanding

maintenance_capex_pct_sales: 0.02
tax_rate: 0.25

mid_cycle_ebit: 100.0       # key output of your normalisation work
duration_score: 5            # 1–10: how durable are the competitive advantages?
stability_score: 5            # 1–10: through-cycle FCF consistency?

other_elements: {}           # optional bridge items (e.g. surplus assets)
```

3. Load and run:

```python
drivers = load_drivers("TICK")
val = value(drivers, macro, net_debt, minority_interest, shares_diluted, price, as_of)
```

## Running tests

```bash
pytest
```

The test suite includes:

- **Golden case** (`test_golden.py`) — hand-computed reference numbers that must never change
- **Property tests** (`test_engine.py`) — higher duration/stability scores increase value; debt reduces equity one-for-one; flat revenue implies zero ΔWC
- **Normalisation tests** (`test_normalise.py`) — flag detection logic
- **Schema tests** (`test_schema.py`) — validation rules on `Drivers` and `Financials`

```bash
# Run with coverage
pytest --cov=distval --cov-report=term-missing
```

## Project layout

```
distval/
  schema.py       # Pydantic contracts — Financials, Drivers, Valuation
  macro.py        # Shared macro assumptions: RFR, ERP, market multiple
  engine.py       # Pure valuation functions — no I/O, no network, no clock
  loader.py       # Load companies/<ticker>.yaml -> Drivers
  ingest.py       # SEC EDGAR -> Financials (requires EDGAR_IDENTITY)
  normalise.py    # Reported financials -> mid-cycle drivers + flags
  record.py       # Write JSON snapshot per run
  companies/      # One YAML per ticker
  tests/
snapshots/        # Written by record.py (gitignored)
```

## Design constraints

- `engine.py` performs no I/O — pure functions of their arguments, reproducible by construction
- Discount rate and market multiple live in `macro.py`, never in a company config
- Money values are `Decimal`; rates are `float` — never mixed
- Every ingest call takes an `as_of` date — point-in-time, no lookahead bias
- No terminal growth rate parameter anywhere — if you think you need one, something else is wrong
- No CAPM, no beta, no company-specific discount rate
- Normalisation flags are reported to the analyst; nothing is auto-corrected
