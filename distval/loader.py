"""Load a company config from companies/<ticker>.yaml into a Drivers object."""
from decimal import Decimal
from pathlib import Path

import yaml

from distval.schema import Drivers

_COMPANIES_DIR = Path(__file__).parent / "companies"


def load_drivers(ticker: str) -> Drivers:
    if not ticker.replace("-", "").isalnum():
        raise ValueError(f"Invalid ticker {ticker!r}: must be alphanumeric")
    safe = ticker.strip().upper()
    path = _COMPANIES_DIR / f"{safe.lower()}.yaml"
    # Guard against path traversal — confirm resolution stays inside companies/
    if not path.resolve().is_relative_to(_COMPANIES_DIR.resolve()):
        raise ValueError(f"Ticker {ticker!r} resolves outside companies directory")
    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise FileNotFoundError(
            f"No company config found for ticker {ticker!r}. Expected: {path}"
        ) from None
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed YAML for {ticker!r} at {path}: {exc}") from exc

    # Coerce revenue list to Decimal
    raw["revenue"] = [Decimal(str(v)) for v in raw["revenue"]]

    # Coerce other_elements values to Decimal
    if "other_elements" in raw:
        raw["other_elements"] = {k: Decimal(str(v)) for k, v in raw["other_elements"].items()}

    # Coerce mid_cycle_ebit to Decimal
    raw["mid_cycle_ebit"] = Decimal(str(raw["mid_cycle_ebit"]))

    return Drivers(**raw)
