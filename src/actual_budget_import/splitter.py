"""
splitter.py
-----------
Groups Actual Budget split transactions across account boundaries.

Actual Budget exports splits as:
  Parent row:  Notes="(SPLIT INTO 4) WM SUPERCENTER"  Amount=0  Split_Amount=-177.23
  Child rows:  Notes="(SPLIT 1 OF 4) Groceries"       Amount=-72.11
               Notes="(SPLIT 2 OF 4) Kitchen stuff"   Amount=-54.00
               ...

The all-accounts CSV export can place parent and child rows in different
account sections, separated by many unrelated rows. The naive approach of
scanning forward from each parent fails in this case.

This module uses a two-pass strategy:
  Pass 1 — index all child rows globally by (date, payee, total_n)
  Pass 2 — walk rows; each parent looks up its children in the index

Returns a list of items, each one of:
  dict                           — simple (non-split) row
  ("split", parent, [children])  — fully matched split group
  ("split-orphan", parent, {})   — parent with missing/partial children
"""

import re
from collections import defaultdict


_PARENT_RE = re.compile(r"^\(SPLIT INTO (\d+)\)")
_CHILD_RE  = re.compile(r"^\(SPLIT (\d+) OF (\d+)\)")


def is_split_parent(notes: str) -> bool:
    return bool(_PARENT_RE.match(notes))


def is_split_child(notes: str) -> bool:
    return bool(_CHILD_RE.match(notes))


def _parent_total_n(notes: str) -> int:
    m = _PARENT_RE.match(notes)
    return int(m.group(1)) if m else 0


def _child_indices(notes: str) -> tuple[int | None, int | None]:
    """Return (child_index, total_n) from '(SPLIT 2 OF 4) ...'"""
    m = _CHILD_RE.match(notes)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def group(rows: list[dict]) -> list:
    """
    Group split parents with their children and return a flat list of items.
    Each item is either a plain row dict or a ("split"/"split-orphan", ...) tuple.
    """

    # ── Pass 1: index all child rows ─────────────────────────────────────────
    # children_index[(date, payee, total_n)] = list of child-groups
    # Each child-group is {child_index: (row_position, row_dict)}
    children_index: dict[tuple, list[dict]] = defaultdict(list)
    consumed: set[int] = set()

    for i, row in enumerate(rows):
        if not is_split_child(row["Notes"]):
            continue
        idx, total_n = _child_indices(row["Notes"])
        if idx is None:
            continue
        key = (row["Date"], row["Payee"], total_n)

        placed = False
        for grp in children_index[key]:
            if idx not in grp:
                grp[idx] = (i, row)
                placed = True
                break
        if not placed:
            children_index[key].append({idx: (i, row)})

    # ── Pass 2: walk rows and assemble output ─────────────────────────────────
    result: list = []

    for i, row in enumerate(rows):
        if i in consumed:
            continue

        if is_split_parent(row["Notes"]):
            total_n      = _parent_total_n(row["Notes"])
            key          = (row["Date"], row["Payee"], total_n)
            parent_total = abs(float(row.get("Split_Amount") or 0))
            candidates   = children_index.get(key, [])

            best, best_idx = _pick_best_group(candidates, total_n, parent_total)

            if best and len(best) == total_n:
                # Full match — consume child rows and emit grouped tuple
                for _, (ri, _) in best.items():
                    consumed.add(ri)
                if best_idx is not None:
                    candidates.pop(best_idx)
                children_ordered = [r for _, (_, r) in sorted(best.items())]
                result.append(("split", row, children_ordered))
            else:
                result.append(("split-orphan", row, best or {}))

        elif is_split_child(row["Notes"]):
            # Not consumed by a parent — its parent was on a skipped/clearing
            # account whose Split_Amount already represents the total.
            consumed.add(i)

        else:
            result.append(row)

    return result


def _pick_best_group(
    candidates: list[dict],
    total_n: int,
    parent_total: float,
) -> tuple[dict | None, int | None]:
    """
    Choose the best-matching child group from candidates.

    With one candidate, return it directly.
    With multiple (same date/payee/count — e.g. two Walmart trips of
    identical size on the same day), prefer the group whose child amounts
    sum closest to parent_total.
    """
    if not candidates:
        return None, None
    if len(candidates) == 1:
        return candidates[0], 0

    for gi, grp in enumerate(candidates):
        child_sum = abs(sum(float(r["Amount"]) for _, r in grp.values()))
        if abs(child_sum - parent_total) < 0.02:   # 2-cent float tolerance
            return grp, gi

    return candidates[0], 0   # best-effort fallback
