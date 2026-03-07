"""
Tests for dedup.py
"""

import pytest
from pathlib import Path
from actual_budget_import import dedup


def test_load_seen_ids_empty_dir(tmp_path):
    seen = dedup.load_seen_ids(tmp_path)
    assert seen == set()


def test_load_seen_ids_finds_fingerprints(tmp_path):
    journal = tmp_path / "2026.journal"
    journal.write_text(
        "2026-01-12 Netflix  ; Netflix Payment\n"
        "    ; ab-id:abc123def456\n"
        "    assets:checking:spending  -19.47 USD\n"
        "    expenses:discretionary:entertainment:streaming\n"
        "\n"
        "2026-01-15 Walmart  ; Groceries\n"
        "    ; ab-id:111222333444\n"
        "    liabilities:credit:chase-freedom-flex  -89.05 USD\n"
        "    expenses:planned:groceries\n"
    )
    seen = dedup.load_seen_ids(tmp_path)
    assert "abc123def456" in seen
    assert "111222333444" in seen
    assert len(seen) == 2


def test_load_seen_ids_multiple_files(tmp_path):
    (tmp_path / "jan.journal").write_text(
        "    ; ab-id:aaaaaaaaaaaa\n"
    )
    (tmp_path / "feb.journal").write_text(
        "    ; ab-id:bbbbbbbbbbbb\n"
    )
    seen = dedup.load_seen_ids(tmp_path)
    assert "aaaaaaaaaaaa" in seen
    assert "bbbbbbbbbbbb" in seen


def test_load_seen_ids_recursive(tmp_path):
    subdir = tmp_path / "2025"
    subdir.mkdir()
    (subdir / "2025.journal").write_text("    ; ab-id:cccccccccccc\n")
    (tmp_path / "2026.journal").write_text("    ; ab-id:dddddddddddd\n")

    seen = dedup.load_seen_ids(tmp_path)
    assert "cccccccccccc" in seen
    assert "dddddddddddd" in seen


def test_load_seen_ids_ignores_non_journal_files(tmp_path):
    (tmp_path / "notes.txt").write_text("    ; ab-id:eeeeeeeeeeee\n")
    (tmp_path / "2026.journal").write_text("    ; ab-id:ffffffffffff\n")
    seen = dedup.load_seen_ids(tmp_path)
    assert "eeeeeeeeeeee" not in seen
    assert "ffffffffffff" in seen


def test_collect_journal_files_follows_includes(tmp_path):
    subdir = tmp_path / "2026"
    subdir.mkdir()
    included = subdir / "2026.journal"
    included.write_text("    ; ab-id:123456789abc\n")

    main = tmp_path / "main.journal"
    main.write_text(f"include 2026/2026.journal\n")

    files = dedup.collect_journal_files(tmp_path)
    resolved = [f.resolve() for f in files]
    assert included.resolve() in resolved
    assert main.resolve() in resolved
