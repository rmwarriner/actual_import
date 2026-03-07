"""
Tests for formatter.py
"""

import pytest
from actual_budget_import import formatter


def test_simple_transaction_structure(minimal_config, simple_row):
    output = formatter.simple(simple_row, "USD", minimal_config)
    lines = output.strip().splitlines()

    # First line: date + payee + notes comment
    assert lines[0].startswith("2026-01-12 Netflix")
    assert "; Netflix Payment" in lines[0]

    # Second line: ab-id fingerprint
    assert lines[1].strip().startswith("; ab-id:")
    assert len(lines[1].strip().split(":")[1]) == 12

    # Third line: payment account with amount
    assert "assets:checking:spending" in lines[2]
    assert "-19.47 USD" in lines[2]

    # Fourth line: expense account (payee override should fire for Netflix)
    assert "expenses:discretionary:entertainment:streaming" in lines[3]


def test_simple_transaction_uses_payee_override(minimal_config, simple_row):
    """Netflix should route via payee override, not category map."""
    output = formatter.simple(simple_row, "USD", minimal_config)
    assert "expenses:discretionary:entertainment:streaming" in output
    assert "expenses:bills:subscriptions:digital" not in output


def test_split_transaction_structure(minimal_config, split_parent_row, split_children_rows):
    output = formatter.split(split_parent_row, split_children_rows, "USD", minimal_config)
    lines = output.strip().splitlines()

    # Header line
    assert "2026-02-24 Walmart" in lines[0]

    # ab-id line with splits count
    assert "ab-id:" in lines[1]
    assert "splits:3" in lines[1]

    # Payment posting uses Split_Amount
    assert "liabilities:credit:chase-freedom-flex" in lines[2]
    assert "-177.23 USD" in lines[2]

    # Three child postings
    assert len(lines) == 6   # header + ab-id + payment + 3 children

    # Last child has no explicit amount (auto-balance)
    last_child = lines[-1]
    assert ";" in last_child   # has a notes comment
    # Should not have an amount on the last line
    assert "USD" not in last_child


def test_split_last_child_omits_amount(minimal_config, split_parent_row, split_children_rows):
    output = formatter.split(split_parent_row, split_children_rows, "USD", minimal_config)
    lines = [l for l in output.strip().splitlines() if l.strip()]
    last_posting = lines[-1]
    assert "USD" not in last_posting


def test_orphan_transaction_has_warning(minimal_config, split_parent_row):
    output = formatter.orphan(split_parent_row, {}, "USD", minimal_config)
    assert "; WARNING: split orphan" in output
    assert "split-orphan:" in output


def test_orphan_routes_to_default_account(minimal_config, split_parent_row):
    output = formatter.orphan(split_parent_row, {}, "USD", minimal_config)
    assert "expenses:discretionary:unclassified" in output


def test_currency_symbol_respected(minimal_config, simple_row):
    output = formatter.simple(simple_row, "GBP", minimal_config)
    assert "GBP" in output
    assert "USD" not in output
