#!/usr/bin/env python3
"""Fail-closed scan for unfinished-work markers.

The pack must not contain common unfinished markers in any text file.
The scan is conservative and is intended to run in CI.

Exit code on failure: 60 (EXIT_PACK_VERIFICATION_FAILED)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".py", ".sh", ".txt", ".eml"}

# Exclude only the manifest (generated) to avoid confusing failures during local regeneration.
EXCLUDE_FILES = {"MANIFEST.sha256"}


def _tok(*parts: str) -> str:
    return "".join(parts)


def _compile_patterns() -> list[tuple[str, re.Pattern]]:
    """Return list of (label, compiled_pattern)."""

    # Build strings without embedding the disallowed sequences verbatim in this source file.
    w1 = _tok("TO", "DO")
    w2 = _tok("TB", "D")
    w3 = _tok("FI", "X", "ME")
    w4 = _tok("place", "holder")
    w5 = _tok("lo", "rem")
    w6 = _tok("fill", " later")

    patterns: list[tuple[str, re.Pattern]] = []

    # Word-boundary markers (avoid false matches inside filenames like check_placeholders.py).
    for w in [w1, w2, w3, w5]:
        patterns.append((w, re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)))

    # Reserved word marker (singular or plural).
    patterns.append((w4, re.compile(r"\b" + re.escape(w4) + r"s?\b", re.IGNORECASE)))

    # Two-word phrase marker.
    patterns.append((w6, re.compile(re.escape(w6), re.IGNORECASE)))

    # Three-dot ellipsis marker.
    dot3 = "." * 3
    patterns.append((dot3, re.compile((r"\." * 3))))

    return patterns


PATTERNS = _compile_patterns()


def is_text_file(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS


def main() -> int:
    violations: list[tuple[str, int, str]] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if not is_text_file(path):
            continue

        rel = path.relative_to(ROOT).as_posix()

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            violations.append((rel, 0, "UNREADABLE"))
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pat in PATTERNS:
                if pat.search(line):
                    violations.append((rel, line_no, label))

    if violations:
        print("PLACEHOLDER_SCAN_FAILED")
        for rel, line_no, label in violations[:400]:
            if line_no == 0:
                print(f"{rel}: unreadable")
            else:
                print(f"{rel}:{line_no}: {label}")
        return 60

    print("PLACEHOLDER_SCAN_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
