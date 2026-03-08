"""
actual_client.py
----------------
Client for Actual Budget using the actualpy library.
"""

import os
from datetime import date
from pathlib import Path


def _require_actualpy():
    try:
        from actual import Actual
        return Actual
    except ImportError:
        raise ImportError(
            "actualpy is required. Run: pip install actualpy"
        )


def get_budget_month(url: str, password: str, budget_file: str,
                     month: str, cache_dir: Path) -> dict:
    """
    Connect to Actual Budget and return budget vs actual data for the month.

    For each category we capture:
      - budgeted: new dollars allocated this month
      - spent:    dollars spent this month (summed from transactions)
      - balance:  envelope balance after carryover and spending
                  (positive = money remaining, negative = overspent)

    Using balance instead of just budgeted catches situations where an
    envelope was funded in a prior month and spent in the current month --
    those show $0 budgeted but a positive pre-spend balance, which is
    planned spending, not a surprise.
    """
    Actual = _require_actualpy()
    cache_dir.mkdir(parents=True, exist_ok=True)

    year  = int(month[:4])
    mon   = int(month[5:])
    month_date = date(year, mon, 1)

    with Actual(
        base_url=url,
        password=password,
        file=budget_file,
        data_dir=str(cache_dir),
    ) as actual:
        from actual.queries import get_budgets, get_categories, get_transactions

        # Budget amounts per category
        raw_budgets = get_budgets(actual.session, month_date)
        budget_lookup = {}
        for b in raw_budgets:
            cat_id = b.category_id
            if cat_id:
                budgeted      = float(b.amount or 0) / 100
                # balance = envelope balance after carryover, before spending
                # In ZeroBudgets this is the running balance field
                envelope_bal  = float(getattr(b, 'balance', None) or 0) / 100
                budget_lookup[cat_id] = {
                    "budgeted":     budgeted,
                    "envelope_bal": envelope_bal,
                }

        # Spent amounts from transactions
        if mon == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, mon + 1, 1)

        transactions = get_transactions(
            actual.session,
            start_date=month_date,
            end_date=end_date,
        )
        spent_lookup = {}
        for t in transactions:
            cat_id = getattr(t, 'category_id', None)
            if not cat_id:
                continue
            amt = float(getattr(t, 'amount', 0) or 0) / 100
            spent_lookup[cat_id] = spent_lookup.get(cat_id, 0.0) + amt

        # Categories with group assignments
        categories = get_categories(actual.session)
        groups_map = {}
        for cat in categories:
            if getattr(cat, 'hidden', False) or getattr(cat, 'tombstone', False):
                continue
            group_name = cat.group.name if cat.group else "Uncategorized"
            if group_name not in groups_map:
                groups_map[group_name] = []

            bdata        = budget_lookup.get(cat.id, {})
            budgeted     = bdata.get("budgeted", 0.0)
            envelope_bal = bdata.get("envelope_bal", 0.0)
            spent        = abs(spent_lookup.get(cat.id, 0.0))

            # Pre-spend balance: envelope balance before this month's spending
            # If the envelope carried funds from prior months, this will be
            # higher than just the current month's budgeted amount.
            pre_spend_balance = envelope_bal + spent

            groups_map[group_name].append({
                "name":              cat.name,
                "budgeted":          budgeted,          # new $ added this month
                "spent":             spent,             # $ spent this month
                "balance":           envelope_bal,      # remaining after spending
                "pre_spend_balance": pre_spend_balance, # available before spending
                "funded_from_prior": pre_spend_balance > budgeted,  # carryover flag
            })

        groups = [
            {"name": name, "categories": cats}
            for name, cats in groups_map.items()
            if any(c["budgeted"] or c["spent"] for c in cats)
        ]
        return {"groups": groups}


def load_from_config(config: dict, month: str) -> dict:
    actual_cfg = config["actual"]
    password   = os.environ.get("ACTUAL_PASSWORD") or actual_cfg.get("password", "")
    if not password:
        raise ValueError(
            "Actual Budget password not set.\n"
            "Set ACTUAL_PASSWORD environment variable or add to narrative.yaml."
        )
    cache_dir = Path("~/.cache/actual-budget").expanduser()
    return get_budget_month(
        url=actual_cfg["url"],
        password=password,
        budget_file=actual_cfg["budget_file"],
        month=month,
        cache_dir=cache_dir,
    )
