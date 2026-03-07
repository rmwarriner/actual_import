"""
fingerprint.py
--------------
Stable fingerprints for Actual Budget CSV rows.

The fingerprint is used as a deduplication key: if a transaction's fingerprint
already exists in the journal, it is skipped on re-import.

Design notes
------------
- Simple rows:      hash Account|Date|Payee|Amount|Notes
- Split parents:    hash Account|Date|Payee|Split_Amount|Notes
  (Amount is always "0" on parent rows; Split_Amount holds the real total.
   Using Amount would produce identical hashes for two different-valued split
   parents on the same account/date/payee, making them indistinguishable.)
- Output is a 12-character hex string (48 bits) — collision probability is
  negligible for household-scale data (~10k transactions/year).
"""

import hashlib
import re


_SPLIT_PARENT_RE = re.compile(r"^\(SPLIT INTO \d+\)")


def is_split_parent(notes: str) -> bool:
    return bool(_SPLIT_PARENT_RE.match(notes))


def compute(row: dict) -> str:
    """Return a 12-char hex fingerprint for a CSV row dict."""
    amount_field = (
        row.get("Split_Amount", "0")
        if is_split_parent(row.get("Notes", ""))
        else row.get("Amount", "0")
    )
    key = (
        f"{row['Account']}|{row['Date']}|{row['Payee']}"
        f"|{amount_field}|{row['Notes']}"
    )
    return hashlib.sha1(key.encode()).hexdigest()[:12]
