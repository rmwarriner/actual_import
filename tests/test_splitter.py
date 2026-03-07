"""
Tests for splitter.py
"""

import pytest
from actual_budget_import import splitter


def _make_parent(n, total="-100.00", date="2026-01-01", payee="Walmart"):
    return {
        "Account": "Chase Freedom Flex", "Date": date, "Payee": payee,
        "Notes": f"(SPLIT INTO {n}) WAL-MART", "Category": "",
        "Amount": "0", "Split_Amount": total, "Cleared": "Cleared",
    }


def _make_child(idx, total_n, amount, date="2026-01-01", payee="Walmart",
                account="Chase Freedom Flex", category="Groceries"):
    return {
        "Account": account, "Date": date, "Payee": payee,
        "Notes": f"(SPLIT {idx} OF {total_n}) item {idx}",
        "Category": category, "Amount": amount,
        "Split_Amount": "0", "Cleared": "Cleared",
    }


# ── is_split_parent / is_split_child ─────────────────────────────────────────

def test_is_split_parent():
    assert splitter.is_split_parent("(SPLIT INTO 4) Walmart")
    assert not splitter.is_split_parent("(SPLIT 1 OF 4) Groceries")
    assert not splitter.is_split_parent("Regular transaction")


def test_is_split_child():
    assert splitter.is_split_child("(SPLIT 1 OF 4) Groceries")
    assert splitter.is_split_child("(SPLIT 3 OF 3) Last item")
    assert not splitter.is_split_child("(SPLIT INTO 4) Parent")
    assert not splitter.is_split_child("Regular transaction")


# ── group — simple (non-split) rows ──────────────────────────────────────────

def test_simple_rows_pass_through():
    rows = [
        {"Account": "Spending Account", "Date": "2026-01-01", "Payee": "Netflix",
         "Notes": "Netflix Payment", "Category": "Digital Services",
         "Amount": "-19.47", "Split_Amount": "0", "Cleared": "Cleared"},
    ]
    result = splitter.group(rows)
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["Payee"] == "Netflix"


# ── group — contiguous split (same account) ───────────────────────────────────

def test_contiguous_split_grouped_correctly():
    parent = _make_parent(3, total="-177.23")
    children = [
        _make_child(1, 3, "-50.00"),
        _make_child(2, 3, "-27.23"),
        _make_child(3, 3, "-100.00"),
    ]
    result = splitter.group([parent] + children)
    assert len(result) == 1
    kind, p, ch = result[0]
    assert kind == "split"
    assert p["Notes"] == "(SPLIT INTO 3) WAL-MART"
    assert len(ch) == 3
    assert ch[0]["Notes"] == "(SPLIT 1 OF 3) item 1"
    assert ch[2]["Notes"] == "(SPLIT 3 OF 3) item 3"


def test_children_ordered_by_index():
    parent = _make_parent(3, total="-177.23")
    # Deliberately out of order
    children = [
        _make_child(3, 3, "-100.00"),
        _make_child(1, 3, "-50.00"),
        _make_child(2, 3, "-27.23"),
    ]
    result = splitter.group([parent] + children)
    _, _, ch = result[0]
    indices = [int(c["Notes"].split()[1]) for c in ch]
    assert indices == [1, 2, 3]


# ── group — cross-account split (all-accounts export case) ────────────────────

def test_cross_account_split_reunited():
    """
    Parent is on Chase Freedom Flex, children are on a different account.
    The two-pass index should reunite them regardless of file position.
    """
    unrelated = {
        "Account": "Spending Account", "Date": "2026-01-15", "Payee": "AT&T",
        "Notes": "Internet bill", "Category": "Internet",
        "Amount": "-65.55", "Split_Amount": "0", "Cleared": "Cleared",
    }
    parent = _make_parent(2, total="-75.00")
    child1 = _make_child(1, 2, "-50.00", account="Amazon Purchases (Clearing)")
    child2 = _make_child(2, 2, "-25.00", account="Amazon Purchases (Clearing)")

    # Ordering: parent, many unrelated rows, then children (as all-accounts export does)
    rows = [parent, unrelated, unrelated, unrelated, child1, child2]
    result = splitter.group(rows)

    splits  = [r for r in result if isinstance(r, tuple) and r[0] == "split"]
    simples = [r for r in result if isinstance(r, dict)]

    assert len(splits) == 1
    assert len(simples) == 3     # 3 unrelated rows
    _, p, ch = splits[0]
    assert len(ch) == 2


# ── group — orphan handling ───────────────────────────────────────────────────

def test_orphaned_parent_becomes_split_orphan():
    """A parent with no matching children becomes a split-orphan tuple."""
    parent = _make_parent(2, total="-50.00")
    # No children in the rows
    result = splitter.group([parent])
    assert len(result) == 1
    assert result[0][0] == "split-orphan"


def test_unconsumed_child_is_dropped():
    """Children that aren't matched to any parent should be silently dropped."""
    child = _make_child(1, 2, "-25.00")
    result = splitter.group([child])
    assert len(result) == 0


# ── group — disambiguation ────────────────────────────────────────────────────

def test_two_splits_same_payee_same_day_different_totals():
    """
    Two split transactions from the same payee on the same day with different
    totals should be assigned to their correct parents.
    """
    parent_a = _make_parent(2, total="-100.00", date="2026-03-01")
    parent_b = _make_parent(2, total="-50.00",  date="2026-03-01")

    children_a = [
        _make_child(1, 2, "-60.00", date="2026-03-01"),
        _make_child(2, 2, "-40.00", date="2026-03-01"),
    ]
    children_b = [
        _make_child(1, 2, "-30.00", date="2026-03-01"),
        _make_child(2, 2, "-20.00", date="2026-03-01"),
    ]

    rows = [parent_a, parent_b] + children_a + children_b
    result = splitter.group(rows)

    splits = [r for r in result if isinstance(r, tuple) and r[0] == "split"]
    assert len(splits) == 2

    totals = {abs(float(p["Split_Amount"])) for _, p, _ in splits}
    assert totals == {100.00, 50.00}

    for _, p, ch in splits:
        total = abs(float(p["Split_Amount"]))
        child_sum = abs(sum(float(c["Amount"]) for c in ch))
        assert abs(child_sum - total) < 0.02
