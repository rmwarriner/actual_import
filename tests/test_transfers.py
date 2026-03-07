"""
Tests for transfers.py
"""

import pytest
from actual_budget_import import transfers


def _row(account, date, payee, amount, notes="", category=""):
    return {
        "Account":   account, "Date": date, "Payee": payee,
        "Notes":     notes,   "Category": category,
        "Amount":    str(amount), "Split_Amount": "0", "Cleared": "Cleared",
    }


@pytest.fixture
def transfer_config():
    return {
        "payment_accounts": {
            "Spending Account":             "assets:checking:spending",
            "Chase Freedom Flex":           "liabilities:credit:chase-freedom-flex",
            "Chase Sapphire Preferred":     "liabilities:credit:chase-sapphire-preferred",
            "Savings Account":              "assets:savings:main",
            "Amazon Purchases (Clearing)":  "assets:clearing:amazon",
        },
        "skip_payees":       [],
        "clearing_accounts": ["Amazon Purchases (Clearing)"],
        "settings": {"currency": "USD", "default_account": "expenses:discretionary:unclassified"},
    }


# ── basic credit card payment ─────────────────────────────────────────────────

def test_credit_card_payment_paired(transfer_config):
    rows = [
        _row("Spending Account",   "2026-02-15", "Chase Freedom Flex", -500.00, "Payment"),
        _row("Chase Freedom Flex", "2026-02-15", "Spending Account",    500.00, "Payment"),
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    kind, primary, secondary = result[0]
    assert kind == "transfer"
    assert primary["Account"] == "Spending Account"
    assert secondary["Account"] == "Chase Freedom Flex"


def test_primary_is_always_negative_leg(transfer_config):
    """Primary should be the outgoing (negative) leg regardless of row order."""
    rows = [
        _row("Chase Freedom Flex", "2026-02-15", "Spending Account",    500.00, "Payment"),
        _row("Spending Account",   "2026-02-15", "Chase Freedom Flex", -500.00, "Payment"),
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    _, primary, _ = result[0]
    assert float(primary["Amount"]) < 0


# ── savings transfer ──────────────────────────────────────────────────────────

def test_savings_transfer_paired(transfer_config):
    rows = [
        _row("Spending Account", "2026-01-21", "Savings Account", -200.00, "Transfer to savings"),
        _row("Savings Account",  "2026-01-21", "Spending Account",  200.00, "Transfer from checking"),
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    kind, primary, secondary = result[0]
    assert kind == "transfer"
    assert primary["Account"] == "Spending Account"
    assert secondary["Account"] == "Savings Account"


# ── clearing account payment ──────────────────────────────────────────────────

def test_clearing_account_payment_paired(transfer_config):
    """Chase paying Amazon clearing account should be a transfer."""
    rows = [
        _row("Chase Freedom Flex",          "2026-03-04", "Amazon Purchases (Clearing)", -76.66, "Payment on Order"),
        _row("Amazon Purchases (Clearing)", "2026-03-04", "Chase Freedom Flex",           76.66, "Payment on Order"),
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    kind, primary, secondary = result[0]
    assert kind == "transfer"
    assert primary["Account"] == "Chase Freedom Flex"
    assert secondary["Account"] == "Amazon Purchases (Clearing)"


# ── non-transfer rows pass through ────────────────────────────────────────────

def test_regular_expense_not_paired(transfer_config):
    rows = [
        _row("Chase Freedom Flex", "2026-01-12", "Netflix", -19.47, "Netflix Payment", "Digital Services"),
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["Payee"] == "Netflix"


def test_unmatched_transfer_leg_passes_through(transfer_config):
    """A row that looks like a transfer leg but has no counterpart passes through."""
    rows = [
        _row("Spending Account", "2026-02-15", "Chase Freedom Flex", -500.00, "Payment"),
        # No counterpart row
    ]
    result = transfers.group(rows, transfer_config)
    assert len(result) == 1
    assert isinstance(result[0], dict)


# ── multiple transfers same day ───────────────────────────────────────────────

def test_multiple_transfers_same_day(transfer_config):
    rows = [
        _row("Spending Account",   "2026-02-15", "Chase Freedom Flex",       -500.00, "Chase payment"),
        _row("Chase Freedom Flex", "2026-02-15", "Spending Account",           500.00, "Chase payment"),
        _row("Spending Account",   "2026-02-15", "Chase Sapphire Preferred", -300.00, "Sapphire payment"),
        _row("Chase Sapphire Preferred", "2026-02-15", "Spending Account",     300.00, "Sapphire payment"),
    ]
    result = transfers.group(rows, transfer_config)
    transfers_found = [r for r in result if isinstance(r, tuple) and r[0] == "transfer"]
    assert len(transfers_found) == 2


def test_same_amount_different_payees_not_cross_matched(transfer_config):
    """Two transfers of identical amounts on the same day don't get cross-matched."""
    rows = [
        _row("Spending Account",         "2026-02-15", "Chase Freedom Flex",       -500.00, "Chase"),
        _row("Chase Freedom Flex",       "2026-02-15", "Spending Account",           500.00, "Chase"),
        _row("Spending Account",         "2026-02-15", "Chase Sapphire Preferred", -500.00, "Sapphire"),
        _row("Chase Sapphire Preferred", "2026-02-15", "Spending Account",           500.00, "Sapphire"),
    ]
    result = transfers.group(rows, transfer_config)
    transfers_found = [r for r in result if isinstance(r, tuple) and r[0] == "transfer"]
    assert len(transfers_found) == 2
    accounts = {(p["Account"], s["Account"]) for _, p, s in transfers_found}
    assert ("Spending Account", "Chase Freedom Flex") in accounts
    assert ("Spending Account", "Chase Sapphire Preferred") in accounts


# ── split tuples pass through untouched ──────────────────────────────────────

def test_split_tuples_pass_through(transfer_config):
    split_item = ("split", {"Account": "Chase Freedom Flex"}, [])
    orphan_item = ("split-orphan", {"Account": "Chase Freedom Flex"}, {})
    regular = _row("Spending Account", "2026-01-01", "Netflix", -19.47, "", "Digital Services")
    result = transfers.group([split_item, orphan_item, regular], transfer_config)
    assert result[0] is split_item
    assert result[1] is orphan_item
    assert result[2] is regular
