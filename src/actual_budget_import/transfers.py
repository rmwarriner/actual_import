"""
transfers.py
------------
Detects and groups internal account transfer pairs from Actual Budget CSV rows.

Actual Budget exports transfers as two separate rows — one on each account:

    Spending Account,    2026-02-15, Chase Freedom Flex, Payment, ,, -500.00, 0
    Chase Freedom Flex,  2026-02-15, Chase Freedom Flex, Payment, ,,  500.00, 0

Both rows represent the same physical movement of money. We want to emit a
single balanced hledger transaction:

    2026-02-15 Chase Freedom Flex Payment
        assets:checking:spending                   -500.00 USD
        liabilities:credit:chase-freedom-flex

Detection
---------
A transfer pair is identified when:
  1. Two rows share the same Date, same absolute Amount, and opposite signs
  2. Row A's Account matches a known payment account
  3. Row A's Payee matches Row B's Account (the other side of the transfer)
  4. Both accounts are in payment_accounts (i.e. both are tracked accounts)

The "primary" row is chosen as the one with the negative amount (money leaving).
The secondary row is consumed and never emitted independently.

This handles:
  - Credit card payments (Spending Account → Chase Freedom Flex)
  - Savings transfers (Spending Account → Savings Account)
  - Clearing account payments (Chase Freedom Flex → Amazon Purchases Clearing)
"""

from collections import defaultdict


def _transfer_key(row: dict) -> tuple | None:
    """
    Return a (date, abs_amount) key for a potential transfer row, or None
    if the row cannot be part of a transfer pair (no amount, or split parent).
    """
    from . import splitter
    if splitter.is_split_parent(row.get("Notes", "")):
        return None
    try:
        amount = float(row["Amount"])
    except (ValueError, TypeError):
        return None
    if amount == 0:
        return None
    return (row["Date"], f"{abs(amount):.2f}")


def group(rows: list[dict], config: dict) -> list:
    """
    Walk rows and pair up transfer legs into ("transfer", primary, secondary)
    tuples. Unpaired rows are returned as-is.

    Parameters
    ----------
    rows   : All CSV rows (after split grouping — receives plain row dicts only,
             split tuples are passed through untouched).
    config : Loaded config dict — used to identify known payment accounts.

    Returns
    -------
    List where each item is either:
      dict                               — simple/unmatched row
      ("split", ...)                     — passed through from splitter
      ("split-orphan", ...)              — passed through from splitter
      ("transfer", primary, secondary)   — matched transfer pair
    """
    known_accounts = set(config.get("payment_accounts", {}).keys())

    # Index plain rows by transfer key; split tuples pass straight through
    # candidate_index: key → list of (list_position, row)
    candidate_index: dict[tuple, list[tuple[int, dict]]] = defaultdict(list)

    for i, item in enumerate(rows):
        if isinstance(item, tuple):
            continue   # split or split-orphan — not a transfer candidate
        row = item
        if row["Account"] not in known_accounts:
            continue
        key = _transfer_key(row)
        if key is None:
            continue
        candidate_index[key].append((i, row))

    consumed: set[int] = set()
    result: list = []

    for i, item in enumerate(rows):
        if i in consumed:
            continue

        # Pass split tuples through untouched
        if isinstance(item, tuple):
            result.append(item)
            continue

        row = item

        # Only attempt transfer matching for known payment accounts
        if row["Account"] not in known_accounts:
            result.append(row)
            continue

        key = _transfer_key(row)
        if key is None:
            result.append(row)
            continue

        amount = float(row["Amount"])

        # Look for a matching counterpart:
        #   - Same key (date + abs amount)
        #   - Opposite sign
        #   - Row's Payee == counterpart's Account  (or vice versa)
        #   - Counterpart's Account is a known payment account
        candidates = candidate_index.get(key, [])
        match_pos  = None
        match_row  = None

        for ci, (cpos, crow) in enumerate(candidates):
            if cpos == i:
                continue
            if cpos in consumed:
                continue
            try:
                c_amount = float(crow["Amount"])
            except (ValueError, TypeError):
                continue
            # Opposite sign check
            if not ((amount < 0 < c_amount) or (amount > 0 > c_amount)):
                continue
            # Cross-account payee check — either direction
            if not (
                row["Payee"] == crow["Account"]
                or crow["Payee"] == row["Account"]
            ):
                continue
            # Both accounts must be known
            if crow["Account"] not in known_accounts:
                continue
            match_pos = cpos
            match_row = crow
            break

        if match_row is not None:
            consumed.add(i)
            consumed.add(match_pos)
            # Primary = the negative (outgoing) leg
            if amount < 0:
                primary, secondary = row, match_row
            else:
                primary, secondary = match_row, row
            result.append(("transfer", primary, secondary))
        else:
            result.append(row)

    return result
