#!/usr/bin/env python3
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "spec" / "00_CANONICAL.md"

PREFIXES = [
    "INTENT_",
    "PROD_",
    "URG_",
    "RISK_",
    "DOC_",
    "ENT_",
    "QUEUE_",
    "SLA_",
    "MOD_",
    "STAGE_",
    "SCHEMA_ID_",
    "PATH_",
    "CLI_",
    "EXIT_",
    "INGESTION_SOURCE_",
    "AV_STATUS_",
    "ACTOR_",
    "ID_ENTITY_",
    "ACTION_"
]

# Match markdown bullet definitions like:
# - INTENT_SAMPLE_LABEL — description
# - SCHEMA_ID_SAMPLE: "urn:ieim:schema:sample:1.0.0"
BULLET_RE = re.compile(r"^\s*-\s+([A-Z0-9_]+)")


def scan_markdown(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    in_fence = False
    violations = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = BULLET_RE.match(line)
        if not m:
            continue
        token = m.group(1)
        if any(token.startswith(p) for p in PREFIXES):
            violations.append((idx, token, line.strip()))
    return violations


def main() -> int:
    if not CANONICAL.exists():
        print("SINGLE_DEFINITION_RULE_FAILED: missing spec/00_CANONICAL.md")
        return 60

    violations_total = []
    for md in ROOT.rglob("*.md"):
        if md.resolve() == CANONICAL.resolve():
            continue
        rel = md.relative_to(ROOT)
        # do not scan LICENSE
        if rel.name.lower() == "license":
            continue
        v = scan_markdown(md)
        for (line_no, token, line) in v:
            violations_total.append((str(rel), line_no, token, line))

    if violations_total:
        print("SINGLE_DEFINITION_RULE_FAILED")
        for rel, line_no, token, line in violations_total:
            print(f"{rel}:{line_no}: {token}: {line}")
        return 60

    print("SINGLE_DEFINITION_RULE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
