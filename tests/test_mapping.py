"""
Tests for mapping.py
"""

import pytest
from actual_budget_import import mapping


def test_known_payment_account(minimal_config):
    assert mapping.payment_account("Spending Account", minimal_config) == \
        "assets:checking:spending"


def test_unknown_payment_account_slugified(minimal_config):
    result = mapping.payment_account("My New Credit Card", minimal_config)
    assert result == "assets:unknown:my-new-credit-card"


def test_category_map_lookup(minimal_config):
    assert mapping.expense_account("Groceries", "H-E-B", minimal_config) == \
        "expenses:planned:groceries"


def test_payee_override_beats_category(minimal_config):
    """Netflix payee override should win even if category says something else."""
    result = mapping.expense_account("Digital Services", "Netflix", minimal_config)
    assert result == "expenses:discretionary:entertainment:streaming"


def test_payee_override_case_insensitive(minimal_config):
    result = mapping.expense_account("", "NETFLIX", minimal_config)
    assert result == "expenses:discretionary:entertainment:streaming"


def test_payee_override_partial_match(minimal_config):
    result = mapping.expense_account("", "Jason's Deli", minimal_config)
    assert result == "expenses:discretionary:dining"


def test_unknown_category_falls_back_to_default(minimal_config):
    result = mapping.expense_account("Some New Category", "Unknown Payee", minimal_config)
    assert result == "expenses:discretionary:unclassified"


def test_payee_override_first_match_wins(minimal_config):
    """When multiple overrides could match, first one in list wins."""
    # "raising cane" matches the second override pattern
    result = mapping.expense_account("", "Raising Cane's", minimal_config)
    assert result == "expenses:discretionary:dining"


def test_slugify():
    assert mapping.slugify("My New Account!") == "my-new-account"
    assert mapping.slugify("Chase Sapphire Preferred") == "chase-sapphire-preferred"
    assert mapping.slugify("AT&T") == "at-t"
