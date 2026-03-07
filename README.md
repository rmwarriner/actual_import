# hledger-import

Imports [Actual Budget](https://actualbudget.org/) CSV exports into
[hledger](https://hledger.org/) journal format.

## Features

- Full split transaction reconstruction across account boundaries
- Deduplication — safe to run at any cadence; re-importing overlapping exports never creates duplicates
- YAML-driven account mapping — no need to edit the script
- Per-account and all-accounts export support

## Project layout

```
hledger-import/
├── config/
│   └── actual-budget.yaml     # ← edit this to add accounts/categories
├── src/
│   └── actual_budget_import/
│       ├── __init__.py
│       ├── __main__.py        # CLI entry point
│       ├── config.py          # YAML loading and validation
│       ├── dedup.py           # journal scanning for seen fingerprints
│       ├── fingerprint.py     # stable transaction hashing
│       ├── formatter.py       # hledger journal entry rendering
│       ├── importer.py        # import pipeline orchestration
│       ├── mapping.py         # account name resolution
│       └── splitter.py        # two-pass global split grouping
├── tests/
│   ├── conftest.py
│   ├── test_dedup.py
│   ├── test_fingerprint.py
│   ├── test_formatter.py
│   ├── test_importer.py
│   ├── test_mapping.py
│   └── test_splitter.py
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## Setup

```bash
git clone <this-repo> hledger-import
cd hledger-import

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt    # runtime deps
pip install -r requirements-dev.txt  # adds pytest + coverage
```

## Configuration

All account mappings live in `config/actual-budget.yaml`. Edit that file to:

- Add a new credit card to `payment_accounts`
- Map a new Actual Budget category in `category_map`
- Add a restaurant or subscription to `payee_overrides`

The script itself should rarely need to change.

## Usage

```bash
# Standard import — appends new transactions, skips duplicates
python -m actual_budget_import export.csv -o ../hledger-ledger/2026/2026.journal

# Dry run — preview without writing
python -m actual_budget_import export.csv --dry-run

# Custom config location
python -m actual_budget_import export.csv --config /path/to/actual-budget.yaml

# Scan a multi-year ledger tree for dedup
python -m actual_budget_import export.csv \
    -o ../hledger-ledger/2026/2026.journal \
    --journal-dir ../hledger-ledger/

# Skip dedup check (not recommended for normal use)
python -m actual_budget_import export.csv --no-dedup
```

## Export source

Prefer the **per-account** export from Actual Budget over the all-accounts
screen. The all-accounts export can separate split parents from their children
across account sections. The importer handles this correctly via two-pass
global grouping, but per-account exports are simpler and faster.

## Running tests

```bash
pytest                        # run all tests
pytest -v                     # verbose output
pytest --cov --cov-report=term-missing   # with coverage
pytest tests/test_splitter.py # single module
```

## Monthly import workflow

1. Export from Actual Budget (per-account or all-accounts)
2. `cd hledger-import && source .venv/bin/activate`
3. `python -m actual_budget_import export.csv -o ../hledger-ledger/2026/2026.journal`
4. `cd ../hledger-ledger && git add -A && git commit -m "import: $(date +%Y-%m)"`
5. Query as needed: `hledger -f main.journal bal expenses -M`
