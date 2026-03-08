"""
report.py
---------
Assembles financial data from hledger and Actual Budget,
calls the Claude API, and renders the monthly narrative report.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    raise ImportError("httpx is required. Run: pip install -r requirements.txt")


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"


# ── Data assembly ─────────────────────────────────────────────────────────────

def assemble_context(
    month: str,
    hledger_data: dict,
    budget_data: dict,
    config: dict,
) -> dict:
    """
    Merge hledger query results and Actual Budget data into a single
    context dict that will be serialised and sent to Claude.
    """
    targets = config.get("targets", {})

    # Flatten Actual Budget category spending for easy comparison
    ab_categories = {}
    for group in budget_data.get("groups", []):
        group_name = group.get("name", "")
        for cat in group.get("categories", []):
            key = f"{group_name} / {cat['name']}"
            ab_categories[key] = {
                "budgeted": cat.get("budgeted", 0.0),
                "spent":    abs(cat.get("spent", 0.0)),
                "balance":  cat.get("budgeted", 0.0) + cat.get("spent", 0.0),
            }

    nw       = hledger_data["net_worth"]
    nw_prev  = hledger_data["net_worth_prev"]
    ie       = hledger_data["income_expenses"]
    mortgage = hledger_data["mortgage"]
    expenses = hledger_data["expenses_by_account"]
    large    = hledger_data["large_transactions"]
    comp     = hledger_data["comparison"]

    # Savings rate: net / income (only meaningful if paychecks are in hledger)
    income   = ie.get("income", 0.0)
    net_flow = ie.get("net", 0.0)
    savings_rate = (net_flow / income * 100) if income > 0 else None

    return {
        "report_month":      month,
        "generated":         date.today().isoformat(),
        "household":         config.get("household", {}),
        "net_worth": {
            "current":        nw["net_worth"],
            "previous":       nw_prev["net_worth"],
            "change":         nw["net_worth"] - nw_prev["net_worth"],
            "total_assets":   nw["assets"],
            "total_liabilities": abs(nw["liabilities"]),
        },
        "income_expenses": {
            "income":         income,
            "expenses":       ie["expenses"],
            "net":            net_flow,
            "savings_rate":   savings_rate,
            "target_savings_rate": targets.get("savings_rate_pct"),
            "prev_month":     comp["prev_month"],
            "prev_income":    comp["previous"]["income"],
            "prev_expenses":  comp["previous"]["expenses"],
        },
        "mortgage": {
            "home_value":     mortgage["home_value"],
            "balance":        mortgage["mortgage_balance"],
            "equity":         mortgage["equity"],
        },
        "expenses_detail":   expenses,
        "budget_vs_actual":  ab_categories,
        "large_transactions": large,
        "targets":           targets,
    }


# ── Claude API call ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a sharp, practical household CFO writing a monthly
financial narrative report for Robert Warriner and his family in Beaumont, TX.
The household includes Robert (works for BNSF Railway), Katie, and Walter.

Your tone is direct and conversational -- like a trusted advisor, not a
corporate report. Use plain language. Be specific about dollar amounts.
Don't pad with generic financial advice unless it's directly relevant.

You will receive a JSON object with financial data for the month. Write a
markdown report with these sections:

## [Month Year] Financial Summary

### Net Worth
One paragraph. State the current net worth, the change from last month, and
what drove the change (market moves, debt paydown, savings). Call out home
equity specifically since it's the largest asset.

### Income & Cash Flow
One paragraph. Cover income received, total spending, and net cash flow.
If savings rate data is available, compare to the 10% target. If income
data is sparse (paychecks not yet in hledger), note this briefly and work
with what's available.

### Budget Performance
A tight summary of how each category performed against the Actual Budget
envelopes. Flag anything more than 15% over budget. Call out the grocery
($230/wk) and dining ($50/wk) targets specifically since these are tracked
closely. Keep this section scannable.

IMPORTANT for budget analysis: each category includes a `funded_from_prior`
flag and a `pre_spend_balance` field. If `funded_from_prior` is true, the
envelope carried funds from a prior month -- spending against it was planned,
not a surprise, even if `budgeted` shows $0 for the current month. Use
`pre_spend_balance` as the true available amount when assessing whether
spending was within plan. Only flag a category as an unplanned overspend if
`spent` exceeds `pre_spend_balance`.

### Mortgage & Debt
One paragraph. State current mortgage balance, equity, and principal paid
this month. Note remaining student loan balance if still active.

### Notable Transactions
Brief list of any large or unusual transactions worth reviewing.

### One Thing to Watch
One specific, actionable observation for the coming month. Not generic advice
-- something specific to this household's numbers.

Keep the whole report under 600 words. Be honest if data is incomplete."""


def call_claude(context: dict) -> str:
    """Send context to Claude API and return the narrative text."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "system":     SYSTEM_PROMPT,
        "messages": [
            {
                "role":    "user",
                "content": (
                    f"Here is the financial data for {context['report_month']}:\n\n"
                    f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
                    "Please write the monthly financial narrative report."
                ),
            }
        ],
    }

    resp = httpx.post(
        CLAUDE_API_URL,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json=payload,
        timeout=60,
    )
    if not resp.is_success:
        raise RuntimeError(
            f"Claude API error {resp.status_code}: {resp.text}"
        )
    data = resp.json()
    return data["content"][0]["text"]


# ── Report rendering ──────────────────────────────────────────────────────────

def render_report(narrative: str, context: dict, output_dir: Path) -> Path:
    """
    Write the final markdown report to output_dir/YYYY-MM.md.
    Returns the path of the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    month    = context["report_month"]
    out_path = output_dir / f"{month}.md"

    header = (
        f"---\n"
        f"month: {month}\n"
        f"generated: {context['generated']}\n"
        f"net_worth: {context['net_worth']['current']:.2f}\n"
        f"---\n\n"
    )

    out_path.write_text(header + narrative, encoding="utf-8")
    return out_path
