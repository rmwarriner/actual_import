"""
Tests for fingerprint.py
"""

import pytest
from actual_budget_import import fingerprint


def test_simple_row_uses_amount():
    row = {
        "Account": "Spending Account", "Date": "2026-01-12",
        "Payee": "Netflix", "Notes": "Netflix Payment",
        "Amount": "-19.47", "Split_Amount": "0",
    }
    fp = fingerprint.compute(row)
    assert len(fp) == 12
    assert all(c in "0123456789abcdef" for c in fp)


def test_split_parent_uses_split_amount():
    """Split parents must hash on Split_Amount, not Amount (which is always 0)."""
    parent_a = {
        "Account": "Chase Freedom Flex", "Date": "2026-02-24",
        "Payee": "Walmart", "Notes": "(SPLIT INTO 3) WAL-MART",
        "Amount": "0", "Split_Amount": "-177.23",
    }
    parent_b = {
        "Account": "Chase Freedom Flex", "Date": "2026-02-24",
        "Payee": "Walmart", "Notes": "(SPLIT INTO 3) WAL-MART",
        "Amount": "0", "Split_Amount": "-99.99",
    }
    assert fingerprint.compute(parent_a) != fingerprint.compute(parent_b)


def test_split_parent_same_total_same_fingerprint():
    """Identical split parents produce the same fingerprint (idempotent)."""
    parent = {
        "Account": "Chase Freedom Flex", "Date": "2026-02-24",
        "Payee": "Walmart", "Notes": "(SPLIT INTO 3) WAL-MART",
        "Amount": "0", "Split_Amount": "-177.23",
    }
    assert fingerprint.compute(parent) == fingerprint.compute(parent)


def test_different_dates_differ():
    base = {
        "Account": "Spending Account", "Date": "2026-01-01",
        "Payee": "Netflix", "Notes": "Netflix Payment",
        "Amount": "-19.47", "Split_Amount": "0",
    }
    other = {**base, "Date": "2026-02-01"}
    assert fingerprint.compute(base) != fingerprint.compute(other)


def test_different_amounts_differ():
    base = {
        "Account": "Spending Account", "Date": "2026-01-12",
        "Payee": "Netflix", "Notes": "Netflix Payment",
        "Amount": "-19.47", "Split_Amount": "0",
    }
    other = {**base, "Amount": "-15.99"}
    assert fingerprint.compute(base) != fingerprint.compute(other)


def test_is_split_parent():
    assert fingerprint.is_split_parent("(SPLIT INTO 4) Walmart")
    assert fingerprint.is_split_parent("(SPLIT INTO 1) Amazon Order")
    assert not fingerprint.is_split_parent("(SPLIT 1 OF 4) Groceries")
    assert not fingerprint.is_split_parent("Netflix Payment")
    assert not fingerprint.is_split_parent("")
