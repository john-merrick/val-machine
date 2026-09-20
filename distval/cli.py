"""CLI entry point — run a DCF valuation for a ticker."""
import argparse
import sys
from datetime import date, datetime
from decimal import Decimal

from distval.engine import value
from distval.loader import load_drivers
from distval.macro import DEFAULT_MACRO
from distval.record import write_snapshot
from distval.schema import Valuation


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date {s!r}: expected YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="distval",
        description="Run a DCF valuation for a ticker with a companies/<ticker>.yaml config.",
    )
    p.add_argument("ticker", help="Company ticker — must match companies/<ticker>.yaml")
    p.add_argument(
        "--net-debt",
        type=Decimal,
        required=True,
        metavar="M",
        help="Net debt in millions (total_debt − cash)",
    )
    p.add_argument(
        "--shares-diluted",
        type=Decimal,
        required=True,
        metavar="M",
        help="Diluted shares outstanding in millions",
    )
    p.add_argument(
        "--minority-interest",
        type=Decimal,
        default=Decimal("0"),
        metavar="M",
        help="Minority interest in millions (default: 0)",
    )
    p.add_argument(
        "--price",
        type=Decimal,
        default=None,
        metavar="USD",
        help="Current share price for upside calculation (optional)",
    )
    p.add_argument(
        "--as-of",
        type=_parse_date,
        default=None,
        metavar="DATE",
        help="Valuation date YYYY-MM-DD (default: today)",
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="Write a snapshot JSON to ./snapshots/",
    )
    return p


def _print_valuation(val: Valuation) -> None:
    w = 52
    print(f"\n{'=' * w}")
    print(f"  {val.ticker}  |  as of {val.as_of}")
    print(f"{'=' * w}")
    fcf_str = "  ".join(f"{float(f):,.0f}" for f in val.fcf_path)
    print(f"  Discount rate:        {val.discount_rate:.1%}")
    print(f"  Terminal multiple:    {val.terminal_multiple:.2f}x")
    print(f"  FCF path ($M):        [{fcf_str}]")
    print(f"  Terminal value:       ${float(val.terminal_value):>13,.1f}M")
    print(f"  Enterprise value:     ${float(val.enterprise_value):>13,.1f}M")
    print(f"  Net debt:             ${float(val.net_debt):>13,.1f}M")
    print(f"  Minority interest:    ${float(val.minority_interest):>13,.1f}M")
    print(f"  Equity value:         ${float(val.equity_value):>13,.1f}M")
    print(f"  Value per share:      ${float(val.value_per_share):>13.2f}")
    if val.price is not None:
        print(f"  Current price:        ${float(val.price):>13.2f}")
        sign = "+" if val.upside_pct and val.upside_pct > 0 else ""
        print(f"  Upside:               {sign}{val.upside_pct:.1f}%")
    print(f"{'=' * w}")
    print(f"  input hash:  {val.input_hash[:12]}")
    print(f"{'=' * w}\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today()

    try:
        drivers = load_drivers(args.ticker)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    val = value(
        drivers=drivers,
        macro=DEFAULT_MACRO,
        net_debt=args.net_debt,
        minority_interest=args.minority_interest,
        shares_diluted=args.shares_diluted,
        price=args.price,
        as_of=as_of,
    )

    _print_valuation(val)

    if args.save:
        path = write_snapshot(val)
        print(f"snapshot written → {path}")

    return 0
