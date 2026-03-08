"""
__main__.py
-----------
CLI entry point for the monthly narrative report generator.

Usage:
    python -m narrative                        # previous month (default)
    python -m narrative --month 2026-03        # specific month
    python -m narrative --dry-run              # print to stdout, no file written
    python -m narrative --config path/to/narrative.yaml
    python -m narrative --no-actual            # skip Actual Budget API (hledger only)

Environment variables:
    ACTUAL_PASSWORD    Actual Budget password (overrides narrative.yaml)
    ANTHROPIC_API_KEY  Required for Claude API calls
"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from .actual_client import load_from_config
from .hledger_queries import (
    net_worth,
    income_expenses,
    expenses_by_account,
    mortgage_equity,
    monthly_comparison,
    large_transactions,
)
from .report import assemble_context, call_claude, render_report


DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "narrative.yaml"


def prev_month() -> str:
    """Return YYYY-MM string for the previous calendar month."""
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_path(p: str) -> Path:
    return Path(p).expanduser().resolve()


def run(month: str, config: dict, dry_run: bool, no_actual: bool, no_claude: bool = False) -> None:
    journal    = resolve_path(config["hledger"]["journal"])
    output_dir = resolve_path(config["report"]["output_dir"])

    print(f"Generating narrative for {month}...")

    # ── hledger queries ───────────────────────────────────────────────────────
    print("  Running hledger queries...")

    year, mon = int(month[:4]), int(month[5:])
    end_of_month = (
        f"{year + 1}-01-01" if mon == 12 else f"{year}-{mon + 1:02d}-01"
    )
    if mon == 1:
        prev_year, prev_mon = year - 1, 12
    else:
        prev_year, prev_mon = year, mon - 1
    prev_end = (
        f"{prev_year + 1}-01-01"
        if prev_mon == 12
        else f"{prev_year}-{prev_mon + 1:02d}-01"
    )
    prev_month_str = f"{prev_year}-{prev_mon:02d}"

    nw_current  = net_worth(journal, end_of_month)
    nw_previous = net_worth(journal, prev_end)
    ie          = income_expenses(journal, month)
    expenses    = expenses_by_account(journal, month)
    mortgage    = mortgage_equity(journal, month)
    comparison  = monthly_comparison(journal, month)
    large       = large_transactions(journal, month, threshold=150.0)

    hledger_data = {
        "net_worth":           nw_current,
        "net_worth_prev":      nw_previous,
        "income_expenses":     ie,
        "expenses_by_account": expenses,
        "mortgage":            mortgage,
        "comparison":          comparison,
        "large_transactions":  large,
    }

    # ── Actual Budget API ─────────────────────────────────────────────────────
    budget_data = {"groups": []}
    if not no_actual:
        print("  Fetching Actual Budget data...")
        try:
            budget_data = load_from_config(config, month)
        except Exception as e:
            print(f"  Warning: Actual Budget fetch failed: {e}")
            print("  Continuing with hledger data only.")

    # ── Assemble context ──────────────────────────────────────────────────────
    context = assemble_context(month, hledger_data, budget_data, config)

    # -- No-Claude mode: dump context JSON and exit --
    if no_claude:
        import json
        print("\n[--no-claude] Assembled context (no API call made):\n")
        print(json.dumps(context, indent=2, default=str))
        return


    # ── Call Claude ───────────────────────────────────────────────────────────
    print("  Calling Claude API...")
    narrative = call_claude(context)

    # ── Output ────────────────────────────────────────────────────────────────
    if dry_run:
        print("\n" + "=" * 72)
        print(narrative)
        print("=" * 72)
        print("\n[dry-run] No file written.")
    else:
        out_path = render_report(narrative, context, output_dir)
        print(f"  Report written to {out_path}")
        if config.get("report", {}).get("print_output"):
            print("\n" + narrative)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a monthly household financial narrative report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        default=None,
        help="Month to report on (default: previous calendar month)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(DEFAULT_CONFIG),
        help=f"Path to narrative.yaml (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report to stdout instead of writing a file",
    )
    parser.add_argument(
        "--no-actual",
        action="store_true",
        help="Skip Actual Budget API, use hledger data only",
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Skip Claude API call -- print assembled context JSON instead",
    )

    args   = parser.parse_args()
    month  = args.month or prev_month()
    config = load_config(Path(args.config))

    # Validate month format
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        print(f"Error: --month must be in YYYY-MM format, got: {month}")
        sys.exit(1)

    try:
        run(
            month=month,
            config=config,
            dry_run=args.dry_run,
            no_actual=args.no_actual,
            no_claude=args.no_claude,
        )
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
