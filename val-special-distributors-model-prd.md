# PRD — `distval`

**A systematic valuation engine for US specialty distributors.**

Version 0.1 · Batch one of a wider portfolio-management system.

---

## 1. Purpose

Build a Python package that values listed specialty distributors from a
structured set of drivers, deterministically and reproducibly, with no
spreadsheet in the loop.

The engine replaces the Excel model. Judgement stays with the analyst and lives
in version-controlled config files; the arithmetic lives in code and never
changes per company.

This is batch one. The schema and engine must generalise to other industries
later, but **do not build for that now** — build for distributors and keep the
seams clean.

### Success criteria

1. Ten distributors valued end to end from committed config files.
2. Any valuation reproducible from its input hash alone.
3. A hand-computed golden case that a refactor cannot silently break.
4. Every run recorded as a timestamped snapshot with upside vs price.

---

## 2. Scope

### In scope

- Fundamentals ingest from SEC filings via `edgartools`
- Normalisation of reported financials to mid-cycle earnings
- Ungeared enterprise valuation, then bridge to equity value
- Per-company driver config in YAML
- Forecast snapshot recording

### Out of scope (v0.1)

- Portfolio optimisation, position sizing, regime modelling
- Any machine learning
- Price data beyond a single spot price for upside calculation
- Any UI, dashboard, or web layer
- Non-US filers, banks, insurers
- Backtesting infrastructure

Explicitly: **do not add a Streamlit app.** Output is a Python object and a
JSON snapshot.

---

## 3. Universe

Ten US specialty distributors, ordered by modelling difficulty. Build in this
order.

| # | Ticker | Company | Why this position |
|---|--------|---------|-------------------|
| 1 | FAST | Fastenal | Single segment, minimal M&A noise, best disclosure |
| 2 | POOL | Pool Corp | Clean single-vertical, housing-linked |
| 3 | GWW | W.W. Grainger | Two segments, clean |
| 4 | MSM | MSC Industrial | Single segment |
| 5 | AIT | Applied Industrial | Two segments |
| 6 | SITE | SiteOne Landscape | Acquisitive, housing-linked |
| 7 | WSO | Watsco | **Carrier JVs — material minority interests** |
| 8 | BECN | Beacon Roofing | Acquisitive, storm-demand distortion |
| 9 | WCC | Wesco | Large acquisition (Anixter), hardest organic split |
| 10 | DXPE | DXP Enterprises | Small cap, oil & gas exposure |

Verify each files a 10-K (not 40-F or 20-F) before adding it.

---

## 4. Architecture

```
distval/
  __init__.py
  schema.py       # pydantic contracts — Financials, Drivers, Valuation
  macro.py        # shared assumptions: RFR, ERP, market multiple
  ingest.py       # edgartools -> Financials
  normalise.py    # reported -> mid-cycle drivers
  engine.py       # pure functions, zero I/O
  record.py       # snapshot writer
  companies/      # one YAML per ticker
  tests/
    test_golden.py
    test_engine.py
    test_normalise.py
```

### Hard architectural rules

1. **`engine.py` performs no I/O.** No file reads, no network, no clock. Pure
   functions of their arguments. This is non-negotiable — it is what makes the
   engine testable and the valuations reproducible.
2. **Discount rate and market multiple live in `macro.py`, never in a company
   config.** Every company moves together when the macro deck moves.
3. **Money is `Decimal`, rates are `float`.** No mixing.
4. **Every ingest call takes an `as_of` date.** Point-in-time by construction;
   never silently pull restated figures.

---

## 5. Data contracts

```python
# schema.py

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

    revenue: list[Decimal]            # len == forecast_years
    gross_margin: list[float]
    opex_pct_sales: list[float]

    # working capital — the capital base in this industry
    dio: float                        # days inventory outstanding
    dso: float                        # days sales outstanding
    dpo: float                        # days payables outstanding

    maintenance_capex_pct_sales: float
    tax_rate: float

    mid_cycle_ebit: Decimal           # THE key output of normalisation
    duration_score: int               # 1-10
    stability_score: int              # 1-10

    other_elements: dict[str, Decimal] = {}   # +ve or -ve, e.g. surplus land


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
```

Note `Drivers` contains no discount rate and no terminal growth rate. This is
deliberate. Terminal growth is not a free variable and must not be exposed as
one.

---

## 6. Engine specification

### 6.1 Invested capital

Working capital is the capital base for a distributor. Net PP&E is small;
growth is funded through inventory. Free cash flow is dominated by the working
capital delta, not by capex.

```python
def invested_capital(revenue, dio, dso, dpo, net_ppe) -> Decimal:
    inventory   = revenue * Decimal(dio) / 365
    receivables = revenue * Decimal(dso) / 365
    payables    = revenue * Decimal(dpo) / 365
    return inventory + receivables - payables + net_ppe
```

### 6.2 Free cash flow

For each forecast year `t`:

```
gross_profit_t = revenue_t * gross_margin_t
ebit_t         = gross_profit_t - (revenue_t * opex_pct_sales_t)
nopat_t        = ebit_t * (1 - tax_rate)
capex_t        = revenue_t * maintenance_capex_pct_sales
delta_wc_t     = invested_capital_t - invested_capital_{t-1}
fcf_t          = nopat_t + d_and_a_t - capex_t - delta_wc_t
```

Assume `d_and_a_t == capex_t` unless the config overrides it. These are
capex-light businesses; if the two diverge materially, that is a red flag to
surface, not a number to smooth.

### 6.3 Discount rate — building block

```python
def discount_rate(macro) -> float:
    return macro.sustainable_risk_free_rate + macro.equity_risk_premium
```

No CAPM. No company beta. Applied consistently across the explicit forecast
period. Sourced from `macro.py`, identical for every company in the universe.

### 6.4 Terminal multiple — the ±40% band

Everything in the terminal value is standardised except duration and
stability. Those two, and only those two, move the multiple.

```python
def terminal_multiple(market_avg_multiple, duration_score, stability_score):
    combined = (duration_score + stability_score) / 2      # 1..10
    adjustment = 0.40 * (combined - 5.5) / 4.5             # -0.40..+0.40
    return market_avg_multiple * (1 + adjustment)
```

Terminal value is `mid_cycle_nopat * terminal_multiple`, discounted at the
same rate over `forecast_years`.

**There must be no terminal growth rate parameter anywhere in the codebase.**
If a future requirement seems to need one, that is a signal something else is
wrong.

### 6.5 Equity bridge

```
enterprise_value = PV(fcf_path) + PV(terminal_value)
equity_value     = enterprise_value
                 + sum(other_elements)
                 - net_debt
                 - minority_interest
value_per_share  = equity_value / shares_diluted
```

Minority interest matters for Watsco specifically — the Carrier joint ventures
are material and must come out below the enterprise line.

---

## 7. Golden test — build this before anything else

Hand-computed. Any refactor that moves these numbers has broken something.

**Inputs**

| Parameter | Value |
|---|---|
| Revenue (flat, 5 years) | 1,000.00 |
| Gross margin | 30% |
| Opex % sales | 20% |
| Tax rate | 25% |
| D&A = capex | 2% of sales |
| Working capital days | dio 60, dso 45, dpo 50 |
| Risk-free rate | 4% |
| Equity risk premium | 5% |
| Market average multiple | 15.0x NOPAT |
| Duration score | 6 |
| Stability score | 5 |
| Net debt | 200.00 |
| Minority interest | 0 |
| Shares | 100 |

**Expected outputs**

| Output | Value |
|---|---|
| EBIT (each year) | 100.00 |
| NOPAT (each year) | 75.00 |
| ΔWC (revenue flat) | 0.00 |
| FCF (each year) | 75.00 |
| Discount rate | 9.0% |
| Combined score | 5.5 → neutral |
| Terminal multiple | 15.00x |
| PV of 5-year FCF | 291.72 |
| Terminal value | 1,125.00 |
| PV of terminal value | 731.18 |
| Enterprise value | 1,022.90 |
| Equity value | 822.90 |
| Value per share | 8.2290 |

Assert to two decimal places on all money values.

---

## 8. Normalisation rules

`normalise.py` converts reported history into `mid_cycle_ebit` and the driver
set. This is the module that will be rewritten most; keep it fully separate
from the engine.

### 8.1 Gross margin is mean-reverting

Distributors earn a price/cost spread. When input costs rise quickly, price is
pushed through ahead of cost flowing out of inventory and margins inflate —
then give it back. **2021–2022 gross margins are not mid-cycle for any name in
this universe.**

Rule: average gross margin over a full cycle (minimum 10 years, spanning at
least one contraction). Never use a trailing three-year average.

### 8.2 LIFO reserve

Several names use LIFO. Extract the LIFO reserve from the filing and record it
on `Financials`. It breaks cross-company comparability and distorts mid-cycle
earnings during inflationary periods if ignored.

### 8.3 Organic versus acquired growth

Wesco, Beacon and SiteOne are serial acquirers. Reported revenue growth
conflates organic and bought growth, and roll-up accounting is where value
destruction hides.

Rule: strip acquisition contribution from the growth series used to set
forward revenue. Where companies disclose organic growth, use the disclosure;
where they do not, flag the company as requiring manual review rather than
guessing.

### 8.4 Flags to surface (do not auto-adjust)

The normaliser reports these; a human decides what to do.

- Capex persistently above D&A over 3+ years
- Working capital growing faster than revenue over 3+ years
- Gross margin more than 1.5 standard deviations above its own 10-year mean
- Rising leverage alongside falling ROIC
- Inventory growth exceeding revenue growth by >10pp in any year

---

## 9. Build phases

Each phase has an acceptance criterion. Do not begin the next until it passes.

### Phase 0 — Skeleton
Repo, package layout, dependencies, pre-commit, pytest.
**Done when:** `pytest` runs green on an empty suite.

### Phase 1 — Schema
`schema.py` complete, with validation (list lengths match `forecast_years`,
scores in 1–10, rates in plausible bounds).
**Done when:** invalid configs raise on load.

### Phase 2 — Engine + golden test
`engine.py` and `macro.py`, driven by hardcoded dicts. No ingest yet.
**Done when:** the Section 7 golden case passes to two decimal places.

### Phase 3 — Fastenal by hand
Key FAST's figures manually from the 10-K into `companies/fast.yaml`. Run the
engine. Compare to market price and write a short note explaining the gap.
**Done when:** the value is the right order of magnitude and the gap is
explainable.

### Phase 4 — Normalisation
`normalise.py` per Section 8, with the flag set.
**Done when:** it reproduces the hand-derived FAST mid-cycle EBIT within 5%.

### Phase 5 — Ingest
`edgartools` wired to populate `Financials`, with `as_of` honoured.
**Done when:** ingested FAST figures match the hand-keyed ones exactly.

### Phase 6 — Recording
`record.py` writes a JSON snapshot per run: input hash, drivers, full
`Valuation`, spot price, upside.
**Done when:** two runs with identical inputs produce identical hashes.

### Phase 7 — Remaining nine
Build in the Section 3 order.
**Done when:** ten configs committed and all ten value end to end.

---

## 10. Testing requirements

- Golden case (Section 7) — must never be edited to accommodate a change
- Property test: increasing duration or stability score never decreases value
- Property test: increasing net debt decreases equity value one-for-one
- Property test: zero revenue growth implies zero ΔWC
- Regression: snapshot every ticker's value; flag any run that moves >2%
  without a config change
- No network access in any test

---

## 11. Non-goals and guardrails

- **No terminal growth rate parameter.** Anywhere.
- **No CAPM, no beta, no company-specific discount rate.**
- **No machine learning in this package.** Later, and elsewhere.
- **No auto-adjustment of flagged anomalies.** Flags go to a human.
- **No moving terminal assumptions to close a gap to market price.** If the
  output disagrees with the market, that is the output.

---