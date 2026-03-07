"""
__main__.py
-----------
CLI entry point for actual-budget-import.

Run as:
    python -m actual_budget_import  export.csv -o ledger/2026/2026.journal
    python -m actual_budget_import  export.csv --dry-run
"""

import argparse
import sys
from pathlib import Path

from . import config as cfg_mod
from . import dedup
from . import importer


def _build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(
        prog="actual-budget-import",
        description="Import an Actual Budget CSV export to an hledger journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # First import — creates the output file
  python -m actual_budget_import jan-2026.csv -o ledger/2026/2026.journal

  # Any subsequent import — duplicates suppressed automatically
  python -m actual_budget_import feb-2026.csv -o ledger/2026/2026.journal

  # Dry run — preview without writing
  python -m actual_budget_import export.csv --dry-run

  # Custom config location
  python -m actual_budget_import export.csv --config ~/ledger/actual-budget.yaml

  # Scan a multi-year ledger tree for existing fingerprints
  python -m actual_budget_import export.csv -o ledger/2026/2026.journal \\
      --journal-dir ledger/
        """,
    )

    parser.add_argument(
        "input",
        help="Path to Actual Budget CSV export file",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output .journal file (appends if exists; creates if not)",
    )
    parser.add_argument(
        "--config",
        default=str(script_dir.parent.parent / "config" / cfg_mod.DEFAULT_CONFIG_NAME),
        help=(
            f"YAML config file "
            f"(default: config/{cfg_mod.DEFAULT_CONFIG_NAME} in project root)"
        ),
    )
    parser.add_argument(
        "--journal-dir",
        help=(
            "Directory to scan for existing ab-id fingerprints "
            "(default: parent dir of --output, or cwd)"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print journal output to stdout; do not write any files",
    )
    parser.add_argument(
        "--no-splits", action="store_true",
        help="Import split transactions as individual simple transactions",
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Skip deduplication check (unsafe for repeated imports)",
    )
    parser.add_argument(
        "--warn-unmatched", action="store_true",
        help="Print stderr warnings for orphaned split parents",
    )
    parser.add_argument(
        "--currency",
        help="Override currency symbol (default: from config settings.currency)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = cfg_mod.load(Path(args.config))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.currency:
        config["settings"]["currency"] = args.currency

    # ── Build seen-id set for dedup ───────────────────────────────────────────
    if args.no_dedup:
        seen_ids    = set()
        journal_dir = None
    else:
        if args.journal_dir:
            journal_dir = Path(args.journal_dir)
        elif args.output:
            journal_dir = Path(args.output).parent
        else:
            journal_dir = Path.cwd()

        if journal_dir.exists():
            seen_ids = dedup.load_seen_ids(journal_dir)
            print(
                f"Dedup: {len(seen_ids)} existing fingerprints in {journal_dir}",
                file=sys.stderr,
            )
        else:
            seen_ids = set()
            print(
                f"Dedup: {journal_dir} does not exist yet — starting fresh.",
                file=sys.stderr,
            )

    # ── Run import ────────────────────────────────────────────────────────────
    try:
        result, stats = importer.run(
            args.input,
            config=config,
            no_splits=args.no_splits,
            warn_unmatched=args.warn_unmatched,
            seen_ids=seen_ids,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: input file not found — {exc}", file=sys.stderr)
        return 1

    print(
        f"Result: {stats['written']} written, {stats['skipped']} skipped, "
        f"{stats['dupes']} duplicates suppressed"
        + (f", {stats['transfers']} transfers" if stats.get("transfers") else "")
        + (f", {stats['orphans']} orphaned splits" if stats["orphans"] else ""),
        file=sys.stderr,
    )

    # ── Write output ──────────────────────────────────────────────────────────
    if args.dry_run or not args.output:
        print(result)
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if output_path.exists() else "w"
        with open(output_path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n")
            f.write(result)
        print(f"Written to {output_path} ({mode})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
