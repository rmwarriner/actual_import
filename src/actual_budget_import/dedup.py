"""
dedup.py
--------
Scans existing hledger journal files for previously imported ab-id fingerprints.

The journal files themselves are the source of truth — no separate state file
is needed. The scan follows include directives recursively so that a multi-file
journal structure (e.g. main.journal including 2025/2025.journal and
2026/2026.journal) is fully covered from a single starting directory.
"""

import re
import sys
from pathlib import Path


_AB_ID_RE   = re.compile(r"\bab-id:([a-f0-9]{12})\b")
_INCLUDE_RE = re.compile(r"^\s*include\s+(.+)$", re.MULTILINE)


def collect_journal_files(start_dir: Path, visited: set | None = None) -> list[Path]:
    """
    Recursively collect all .journal files reachable from start_dir,
    following include directives to find files in other directories.

    visited prevents infinite loops from circular includes.
    """
    if visited is None:
        visited = set()

    files: list[Path] = []

    for path in sorted(start_dir.rglob("*.journal")):
        resolved = path.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        files.append(path)

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError):
            continue

        for match in _INCLUDE_RE.finditer(text):
            inc = (path.parent / match.group(1).strip()).resolve()
            if inc in visited:
                continue
            if inc.is_file() and inc.suffix == ".journal":
                visited.add(inc)
                files.append(inc)
            elif inc.is_dir():
                files.extend(collect_journal_files(inc, visited))

    return files


def load_seen_ids(journal_dir: Path) -> set[str]:
    """
    Scan all reachable .journal files under journal_dir and return
    the set of ab-id fingerprint values already present in the ledger.
    """
    seen: set[str] = set()

    for jf in collect_journal_files(journal_dir):
        try:
            text = jf.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError) as exc:
            print(f"WARNING: could not read {jf}: {exc}", file=sys.stderr)
            continue
        for m in _AB_ID_RE.finditer(text):
            seen.add(m.group(1))

    return seen
