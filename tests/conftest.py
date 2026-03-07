"""
conftest.py — shared pytest fixtures
"""

import pytest


@pytest.fixture
def minimal_config():
    """A minimal valid config dict for tests that don't need full mappings."""
    return {
        "payment_accounts": {
            "Chase Freedom Flex":  "liabilities:credit:chase-freedom-flex",
            "Spending Account":    "assets:checking:spending",
        },
        "category_map": {
            "Groceries":           "expenses:planned:groceries",
            "Dining & Restaurants": "expenses:discretionary:dining",
            "Digital Services":    "expenses:bills:subscriptions:digital",
            "Paycheck":            "income:employment:bnsf:paycheck",
        },
        "payee_overrides": [
            {
                "pattern": "netflix|paramount",
                "account": "expenses:discretionary:entertainment:streaming",
            },
            {
                "pattern": "jason.s deli|raising cane",
                "account": "expenses:discretionary:dining",
            },
        ],
        "skip_payees":       ["Chase Freedom Flex", "Savings Account"],
        "clearing_accounts": ["Amazon Purchases (Clearing)"],
        "settings": {
            "currency":        "USD",
            "default_account": "expenses:discretionary:unclassified",
        },
    }


@pytest.fixture
def simple_row():
    """A basic non-split CSV row."""
    return {
        "Account":       "Spending Account",
        "Date":          "2026-01-12",
        "Payee":         "Netflix",
        "Notes":         "Netflix Payment",
        "Category_Group": "Other Spending",
        "Category":      "Entertainment & Gaming",
        "Amount":        "-19.47",
        "Split_Amount":  "0",
        "Cleared":       "Cleared",
    }


@pytest.fixture
def split_parent_row():
    return {
        "Account":       "Chase Freedom Flex",
        "Date":          "2026-02-24",
        "Payee":         "Walmart",
        "Notes":         "(SPLIT INTO 3) WAL-MART ##0651",
        "Category_Group": "",
        "Category":      "",
        "Amount":        "0",
        "Split_Amount":  "-177.23",
        "Cleared":       "Reconciled",
    }


@pytest.fixture
def split_children_rows():
    return [
        {
            "Account":       "Chase Freedom Flex",
            "Date":          "2026-02-24",
            "Payee":         "Walmart",
            "Notes":         "(SPLIT 1 OF 3) Household supplies",
            "Category_Group": "Planned Spending",
            "Category":      "Groceries",
            "Amount":        "-50.00",
            "Split_Amount":  "0",
            "Cleared":       "Reconciled",
        },
        {
            "Account":       "Chase Freedom Flex",
            "Date":          "2026-02-24",
            "Payee":         "Walmart",
            "Notes":         "(SPLIT 2 OF 3) Personal care",
            "Category_Group": "Planned Spending",
            "Category":      "Groceries",
            "Amount":        "-27.23",
            "Split_Amount":  "0",
            "Cleared":       "Reconciled",
        },
        {
            "Account":       "Chase Freedom Flex",
            "Date":          "2026-02-24",
            "Payee":         "Walmart",
            "Notes":         "(SPLIT 3 OF 3) Groceries",
            "Category_Group": "Planned Spending",
            "Category":      "Groceries",
            "Amount":        "-100.00",
            "Split_Amount":  "0",
            "Cleared":       "Reconciled",
        },
    ]
