"""
formatter.py
------------
Renders Actual Budget CSV rows as hledger journal entry strings.

Three entry types:
  - Simple transaction      — one payment posting + one expense posting
  - Split transaction       — one payment posting + N expense postings
  - Orphan transaction      — fallback for unmatched split parents
"""

import re
from . import fingerprint as fp_mod
from . import mapping


_SPLIT_PARENT_PREFIX = re.compile(r"^\(SPLIT INTO \d+\)\s*")
_SPLIT_CHILD_PREFIX  = re.compile(r"^\(SPLIT\s+\d+\s+OF\s+\d+\)\s*")

_ACCT_WIDTH = 55   # column width for account name padding


def _fmt(amount: float, currency: str) -> str:
    return f"{amount:.2f} {currency}"


def _clean_child_notes(notes: str) -> str:
    return _SPLIT_CHILD_PREFIX.sub("", notes).strip()


def simple(row: dict, currency: str, config: dict) -> str:
    """
    Render a non-split transaction.

    2026-01-12 Netflix  ; Netflix Payment
        ; ab-id:abc123def456
        assets:checking:spending          -19.47 USD
        expenses:discretionary:entertainment:streaming
    """
    date    = row["Date"]
    payee   = row["Payee"]
    notes   = row["Notes"]
    amount  = float(row["Amount"])
    payment = mapping.payment_account(row["Account"], config)
    expense = mapping.expense_account(row["Category"], payee, config)
    fprint  = fp_mod.compute(row)

    return "\n".join([
        f"{date} {payee}  ; {notes}",
        f"    ; ab-id:{fprint}",
        f"    {payment:<{_ACCT_WIDTH}}  {_fmt(amount, currency)}",
        f"    {expense}",
        "",
    ])


def split(parent: dict, children: list, currency: str, config: dict) -> str:
    """
    Render a split transaction as a multi-posting hledger entry.

    The payment posting uses the parent's Split_Amount (the total charge).
    Each child becomes its own expense posting.
    The last child omits an explicit amount so hledger auto-balances,
    absorbing any floating-point rounding differences.

    2026-02-24 Walmart  ; WAL-MART ##0651
        ; ab-id:abc123def456  splits:5
        liabilities:credit:chase-freedom-flex    -271.82 USD
        expenses:planned:household-supplies      -11.84 USD  ; Dishwasher detergent
        expenses:discretionary:personal-care      -3.75 USD  ; Generic Aquaphor
        expenses:planned:household-supplies       -4.59 USD  ; Aluminum cake pan
        expenses:planned:household-supplies       -5.59 USD  ; Paper plates
        expenses:planned:groceries                           ; Groceries
    """
    date         = parent["Date"]
    payee        = parent["Payee"]
    parent_notes = _SPLIT_PARENT_PREFIX.sub("", parent["Notes"]).strip()
    total        = float(parent["Split_Amount"])
    payment      = mapping.payment_account(parent["Account"], config)
    fprint       = fp_mod.compute(parent)

    lines = [
        f"{date} {payee}  ; {parent_notes}",
        f"    ; ab-id:{fprint}  splits:{len(children)}",
        f"    {payment:<{_ACCT_WIDTH}}  {_fmt(total, currency)}",
    ]

    for i, child in enumerate(children):
        child_amount = float(child["Amount"])
        child_notes  = _clean_child_notes(child["Notes"])
        expense      = mapping.expense_account(child["Category"], child["Payee"], config)
        last         = i == len(children) - 1

        if last:
            lines.append(f"    {expense:<{_ACCT_WIDTH}}  ; {child_notes}")
        else:
            lines.append(
                f"    {expense:<{_ACCT_WIDTH}}  {_fmt(child_amount, currency)}"
                f"  ; {child_notes}"
            )

    lines.append("")
    return "\n".join(lines)


def orphan(parent: dict, partial: dict, currency: str, config: dict) -> str:
    """
    Fallback for a split parent whose children could not be matched.
    Emits a single posting to the default account with a warning comment.
    """
    date     = parent["Date"]
    payee    = parent["Payee"]
    notes    = _SPLIT_PARENT_PREFIX.sub("", parent["Notes"]).strip()
    total    = float(parent["Split_Amount"])
    payment  = mapping.payment_account(parent["Account"], config)
    fprint   = fp_mod.compute(parent)
    found    = len(partial)

    m = re.match(r"^\(SPLIT INTO (\d+)\)", parent["Notes"])
    expected = int(m.group(1)) if m else "?"

    default = config["settings"].get(
        "default_account", "expenses:discretionary:unclassified"
    )

    return "\n".join([
        f"; WARNING: split orphan — expected {expected} children, found {found}",
        f"; Imported as single posting. Re-export per-account to resolve.",
        f"{date} {payee}  ; {notes}",
        f"    ; ab-id:{fprint}  split-orphan:expected={expected},found={found}",
        f"    {payment:<{_ACCT_WIDTH}}  {_fmt(total, currency)}",
        f"    {default}",
        "",
    ])


def transfer(primary: dict, secondary: dict, currency: str, config: dict) -> str:
    """
    Render a paired transfer as a single balanced hledger transaction.

    The primary row is the outgoing leg (negative amount). The secondary
    row is the receiving leg and provides the destination account name.

    2026-02-15 Chase Freedom Flex Payment
        ; ab-id:abc123def456  transfer
        assets:checking:spending                   -500.00 USD
        liabilities:credit:chase-freedom-flex
    """
    date   = primary["Date"]
    payee  = primary["Payee"]
    notes  = primary["Notes"]
    amount = float(primary["Amount"])
    from_  = mapping.payment_account(primary["Account"], config)
    to_    = mapping.payment_account(secondary["Account"], config)
    fprint = fp_mod.compute(primary)

    return "\n".join([
        f"{date} {payee}  ; {notes}",
        f"    ; ab-id:{fprint}  transfer",
        f"    {from_:<{_ACCT_WIDTH}}  {_fmt(amount, currency)}",
        f"    {to_}",
        "",
    ])
