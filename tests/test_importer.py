"""
tests/test_importer.py
----------------------
Integration-level tests for importer.run().
These tests use real CSV data (constructed inline) and verify the full pipeline.
"""

import csv
import io
import pytest
from pathlib import Path
from unittest.mock import patch

from actual_budget_import import importer


def _csv_string(rows: list[dict]) -> str:
    fields = ["Account", "Date", "Payee", "Notes", "Category_Group",
              "Category", "Amount", "Split_Amount", "Cleared"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        full = {f: row.get(f, "") for f in fields}
        writer.writerow(full)
    return buf.getvalue()


def _write_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "export.csv"
    p.write_text(_csv_string(rows))
    return p


# ── simple transaction import ─────────────────────────────────────────────────

def test_simple_transaction_written(tmp_path, minimal_config):
    csv_path = _write_csv(tmp_path, [{
        "Account": "Spending Account", "Date": "2026-01-12",
        "Payee": "Netflix", "Notes": "Netflix Payment",
        "Category": "Digital Services", "Amount": "-19.47", "Split_Amount": "0",
    }])
    text, stats = importer.run(csv_path, minimal_config)
    assert stats["written"] == 1
    assert stats["skipped"] == 0
    assert "Netflix" in text
    assert "ab-id:" in text


def test_skip_payee_is_skipped(tmp_path, minimal_config):
    csv_path = _write_csv(tmp_path, [{
        "Account": "Chase Freedom Flex", "Date": "2026-01-12",
        "Payee": "Chase Freedom Flex",  # internal transfer
        "Notes": "Payment", "Category": "", "Amount": "500.00", "Split_Amount": "0",
    }])
    _, stats = importer.run(csv_path, minimal_config)
    assert stats["skipped"] == 1
    assert stats["written"] == 0


def test_starting_balance_skipped(tmp_path, minimal_config):
    csv_path = _write_csv(tmp_path, [{
        "Account": "Spending Account", "Date": "2026-01-01",
        "Payee": "Starting Balance", "Notes": "Starting Balance",
        "Category": "Starting Balances", "Amount": "5000.00", "Split_Amount": "0",
    }])
    _, stats = importer.run(csv_path, minimal_config)
    assert stats["skipped"] == 1


# ── deduplication ─────────────────────────────────────────────────────────────

def test_dedup_suppresses_seen_transaction(tmp_path, minimal_config):
    rows = [{
        "Account": "Spending Account", "Date": "2026-01-12",
        "Payee": "Netflix", "Notes": "Netflix Payment",
        "Category": "Digital Services", "Amount": "-19.47", "Split_Amount": "0",
    }]
    csv_path = _write_csv(tmp_path, rows)

    # First import
    text1, stats1 = importer.run(csv_path, minimal_config, seen_ids=set())
    assert stats1["written"] == 1

    # Extract the fingerprint from the output
    import re
    fp_match = re.search(r"ab-id:([a-f0-9]{12})", text1)
    assert fp_match
    seen = {fp_match.group(1)}

    # Second import with seen set — should be suppressed
    text2, stats2 = importer.run(csv_path, minimal_config, seen_ids=seen)
    assert stats2["written"] == 0
    assert stats2["dupes"] == 1


def test_dedup_only_suppresses_matching_transaction(tmp_path, minimal_config):
    rows = [
        {"Account": "Spending Account", "Date": "2026-01-12",
         "Payee": "Netflix", "Notes": "Netflix Payment",
         "Category": "Digital Services", "Amount": "-19.47", "Split_Amount": "0"},
        {"Account": "Spending Account", "Date": "2026-01-15",
         "Payee": "AT&T", "Notes": "Internet bill",
         "Category": "Digital Services", "Amount": "-65.55", "Split_Amount": "0"},
    ]
    csv_path = _write_csv(tmp_path, rows)

    # Fake only the Netflix fingerprint as already seen
    from actual_budget_import import fingerprint as fp_mod
    netflix_fp = fp_mod.compute(rows[0])

    _, stats = importer.run(csv_path, minimal_config, seen_ids={netflix_fp})
    assert stats["written"] == 1    # AT&T written
    assert stats["dupes"] == 1      # Netflix suppressed


# ── split transaction import ──────────────────────────────────────────────────

def test_split_transaction_reconstructed(tmp_path, minimal_config):
    rows = [
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT INTO 2) WAL-MART", "Category": "",
         "Amount": "0", "Split_Amount": "-75.00"},
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT 1 OF 2) Groceries", "Category": "Groceries",
         "Amount": "-50.00", "Split_Amount": "0"},
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT 2 OF 2) Personal Care", "Category": "Groceries",
         "Amount": "-25.00", "Split_Amount": "0"},
    ]
    csv_path = _write_csv(tmp_path, rows)
    text, stats = importer.run(csv_path, minimal_config)
    assert stats["written"] == 1
    assert "splits:2" in text
    assert "-75.00 USD" in text


def test_split_cross_account_reunited(tmp_path, minimal_config):
    """Parent on Chase, children on clearing account — should still reconstruct."""
    rows = [
        {"Account": "Chase Freedom Flex", "Date": "2026-03-04", "Payee": "Amazon",
         "Notes": "(SPLIT INTO 2) Order #123", "Category": "",
         "Amount": "0", "Split_Amount": "-60.43"},
        # Unrelated transaction in between
        {"Account": "Spending Account", "Date": "2026-03-04", "Payee": "AT&T",
         "Notes": "Internet", "Category": "Digital Services",
         "Amount": "-65.55", "Split_Amount": "0"},
        # Children on different account
        {"Account": "Amazon Purchases (Clearing)", "Date": "2026-03-04", "Payee": "Amazon",
         "Notes": "(SPLIT 1 OF 2) USB Cable", "Category": "Digital Services",
         "Amount": "-32.46", "Split_Amount": "0"},
        {"Account": "Amazon Purchases (Clearing)", "Date": "2026-03-04", "Payee": "Amazon",
         "Notes": "(SPLIT 2 OF 2) HDMI Cable", "Category": "Digital Services",
         "Amount": "-27.97", "Split_Amount": "0"},
    ]
    csv_path = _write_csv(tmp_path, rows)
    text, stats = importer.run(csv_path, minimal_config)
    assert stats["written"] == 2    # split + AT&T
    assert "splits:2" in text


# ── no_splits flag ────────────────────────────────────────────────────────────

def test_no_splits_flag_degrades_to_simple(tmp_path, minimal_config):
    rows = [
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT INTO 2) WAL-MART", "Category": "",
         "Amount": "0", "Split_Amount": "-75.00"},
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT 1 OF 2) Groceries", "Category": "Groceries",
         "Amount": "-50.00", "Split_Amount": "0"},
        {"Account": "Chase Freedom Flex", "Date": "2026-02-24", "Payee": "Walmart",
         "Notes": "(SPLIT 2 OF 2) Supplies", "Category": "Groceries",
         "Amount": "-25.00", "Split_Amount": "0"},
    ]
    csv_path = _write_csv(tmp_path, rows)
    text, stats = importer.run(csv_path, minimal_config, no_splits=True)
    assert stats["written"] == 1
    assert "splits:" not in text
    assert "-75.00 USD" in text
