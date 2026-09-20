"""Load a company config from companies/<ticker>.yaml into a Drivers object."""
from decimal import Decimal
from pathlib import Path

import yaml

from distval.schema import Drivers

_COMPANIES_DIR = Path(__file__).parent / "companies"


def load_drivers(ticker: str) -> Drivers:
    path = _COMPANIES_DIR / f"{ticker.lower()}.yaml"
    raw = yaml.safe_load(path.read_text())

    # Coerce revenue list to Decimal
    raw["revenue"] = [Decimal(str(v)) for v in raw["revenue"]]

    # Coerce other_elements values to Decimal
    if "other_elements" in raw:
        raw["other_elements"] = {k: Decimal(str(v)) for k, v in raw["other_elements"].items()}

    # Coerce mid_cycle_ebit to Decimal
    raw["mid_cycle_ebit"] = Decimal(str(raw["mid_cycle_ebit"]))

    return Drivers(**raw)
