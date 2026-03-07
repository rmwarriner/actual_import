"""
config.py
---------
Loads and validates the actual-budget.yaml configuration file.
All account mappings, payee overrides, and skip lists live in that file.
This module is the only place that touches the config structure.
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required.\n"
        "  Activate your venv and run:  pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


DEFAULT_CONFIG_NAME = "actual-budget.yaml"

_FALLBACK: dict = {
    "payment_accounts":  {},
    "category_map":      {},
    "payee_overrides":   [],
    "skip_payees":       [],
    "clearing_accounts": [],
    "settings": {
        "currency":        "USD",
        "default_account": "expenses:discretionary:unclassified",
    },
}


def load(config_path: Path) -> dict:
    """
    Load actual-budget.yaml and return a validated config dict.

    Raises FileNotFoundError if the file does not exist (callers should handle
    this and decide whether to abort or fall back to defaults).
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Copy config/{DEFAULT_CONFIG_NAME} to that location and edit it."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = dict(_FALLBACK)
    config.update({k: v for k, v in raw.items() if v is not None})

    # Ensure settings sub-keys exist
    settings = dict(_FALLBACK["settings"])
    settings.update(config.get("settings") or {})
    config["settings"] = settings

    # Validate and compile payee_overrides
    validated = []
    for i, entry in enumerate(config.get("payee_overrides", [])):
        if not isinstance(entry, dict) or "pattern" not in entry or "account" not in entry:
            print(
                f"WARNING: payee_overrides[{i}] missing 'pattern' or 'account' — skipped.",
                file=sys.stderr,
            )
            continue
        try:
            re.compile(entry["pattern"], re.IGNORECASE)
        except re.error as exc:
            print(
                f"WARNING: payee_overrides[{i}] invalid regex "
                f"'{entry['pattern']}': {exc} — skipped.",
                file=sys.stderr,
            )
            continue
        validated.append(entry)
    config["payee_overrides"] = validated

    # Normalise list fields to plain Python lists
    for key in ("skip_payees", "clearing_accounts"):
        config[key] = list(config.get(key) or [])

    return config


def default_account(config: dict) -> str:
    return config["settings"].get("default_account", "expenses:discretionary:unclassified")


def currency(config: dict) -> str:
    return config["settings"].get("currency", "USD")
