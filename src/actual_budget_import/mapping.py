"""
mapping.py
----------
Resolves Actual Budget account names and categories to hledger account strings.

All mapping data comes from the config dict (loaded by config.py).
No hard-coded mappings live here — this module is pure logic.
"""

import re


def slugify(s: str) -> str:
    """Convert an arbitrary string to a safe hledger account name segment."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def payment_account(account_name: str, config: dict) -> str:
    """
    Map an Actual Budget account name to its hledger asset/liability account.
    Falls back to assets:unknown:<slugified-name> for unmapped accounts so
    that unknown accounts are visible and easy to grep for.
    """
    return config["payment_accounts"].get(
        account_name, f"assets:unknown:{slugify(account_name)}"
    )


def expense_account(category: str, payee: str, config: dict) -> str:
    """
    Resolve the hledger expense/income account for a transaction.

    Resolution order:
      1. Payee overrides  — checked in config order, first match wins
      2. Category map     — exact match on Actual Budget category name
      3. Default account  — expenses:discretionary:unclassified

    Payee overrides intentionally take precedence over categories so that
    e.g. a dining payee always routes to expenses:discretionary:dining
    regardless of what category was assigned in Actual Budget.
    """
    for entry in config.get("payee_overrides", []):
        if re.search(entry["pattern"], payee, re.IGNORECASE):
            return entry["account"]

    fallback = config["settings"].get(
        "default_account", "expenses:discretionary:unclassified"
    )
    return config.get("category_map", {}).get(category, fallback)
