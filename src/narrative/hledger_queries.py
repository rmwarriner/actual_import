"""
hledger_queries.py
------------------
Runs hledger CLI commands and parses the output into structured data.
"""

import subprocess
import re
from pathlib import Path


class HledgerError(Exception):
    pass


def _run(journal: Path, *args: str) -> str:
    cmd = ["hledger", "-f", str(journal)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HledgerError(
            f"hledger command failed:\n  {' '.join(cmd)}\n{result.stderr}"
        )
    return result.stdout


def _period(month: str) -> tuple:
    year, mon = int(month[:4]), int(month[5:])
    begin = f"{year}-{mon:02d}-01"
    end = f"{year + 1}-01-01" if mon == 12 else f"{year}-{mon + 1:02d}-01"
    return begin, end


def _prev_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _parse_amount(s: str) -> float:
    s = re.sub(r'[A-Z]{3}', '', s).replace(',', '').strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_bal_output(output: str) -> dict:
    """
    Parse hledger bal --flat output into {account: amount}.
    With --flat, each line is: '  AMOUNT  account:name'
    """
    result = {}
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) <= set('-= '):
            continue
        # Split on 2+ spaces
        parts = re.split(r'\s{2,}', stripped, maxsplit=1)
        if len(parts) != 2:
            continue
        left, right = parts[0].strip(), parts[1].strip()
        # Determine which side is the amount and which is the account
        # Account names contain ':' or are known root names
        if ':' in right or right in ('assets', 'liabilities', 'expenses', 'income', 'equity'):
            amt_str, acct = left, right
        elif ':' in left or left in ('assets', 'liabilities', 'expenses', 'income', 'equity'):
            acct, amt_str = left, right
        else:
            # Assume left is amount, right is account
            amt_str, acct = left, right
        try:
            result[acct] = _parse_amount(amt_str)
        except Exception:
            continue
    return result


def net_worth(journal: Path, as_of: str) -> dict:
    out = _run(journal, "bal", "assets", "liabilities",
               "-e", as_of, "--no-total", "--flat")
    accounts = _parse_bal_output(out)
    assets      = sum(v for k, v in accounts.items() if k.startswith("assets"))
    liabilities = sum(v for k, v in accounts.items() if k.startswith("liabilities"))
    return {
        "assets":      assets,
        "liabilities": liabilities,
        "net_worth":   assets + liabilities,
        "accounts":    accounts,
    }


def account_balance(journal: Path, account: str, as_of: str) -> float:
    out = _run(journal, "bal", account, "-e", as_of, "--no-total", "--flat")
    accounts = _parse_bal_output(out)
    return sum(accounts.values())


def income_expenses(journal: Path, month: str) -> dict:
    begin, end = _period(month)
    out = _run(journal, "bal", "income", "expenses",
               "-b", begin, "-e", end, "--no-total", "--flat")
    accounts = _parse_bal_output(out)
    income   = sum(v for k, v in accounts.items() if k.startswith("income"))
    expenses = sum(v for k, v in accounts.items() if k.startswith("expenses"))
    return {
        "income":   abs(income),
        "expenses": expenses,
        "net":      abs(income) - expenses,
    }


def expenses_by_account(journal: Path, month: str, depth: int = 4) -> dict:
    begin, end = _period(month)
    out = _run(journal, "bal", "expenses",
               "-b", begin, "-e", end,
               f"--depth={depth}", "--no-total", "--flat")
    return _parse_bal_output(out)


def mortgage_equity(journal: Path, month: str) -> dict:
    _, end = _period(month)
    mortgage = account_balance(journal, "liabilities:loans:mortgage", end)
    home     = account_balance(journal, "assets:property:home", end)
    return {
        "home_value":       home,
        "mortgage_balance": abs(mortgage),
        "equity":           home + mortgage,
    }


def monthly_comparison(journal: Path, month: str) -> dict:
    prev     = _prev_month(month)
    current  = income_expenses(journal, month)
    previous = income_expenses(journal, prev)
    return {
        "current":    current,
        "previous":   previous,
        "prev_month": prev,
    }


def large_transactions(journal: Path, month: str, threshold: float = 150.0) -> list:
    begin, end = _period(month)
    out = _run(journal, "print", "-b", begin, "-e", end, "-O", "csv")
    results = []
    lines = out.splitlines()
    if len(lines) < 2:
        return results
    for line in lines[1:]:
        parts = [p.strip().strip('"') for p in line.split(',')]
        if len(parts) < 9:
            continue
        try:
            amt = abs(float(parts[8]))
        except (ValueError, IndexError):
            continue
        if amt >= threshold:
            results.append({
                "date":    parts[1],
                "payee":   parts[5],
                "account": parts[7],
                "amount":  amt,
            })
    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: x["amount"], reverse=True):
        key = (r["date"], r["payee"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:10]
